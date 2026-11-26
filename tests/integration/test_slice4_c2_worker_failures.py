"""Concurrent worker failure accounting with queued and active stage work.

Stage callbacks are synthetic; the planner, coordinator and event stream are real.
"""

import threading
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

from image_clarus.artifacts import ArtifactService
from image_clarus.batch_execution import run_concurrent
from image_clarus.batch_plan import PlanningInput, build_plan
from image_clarus.results import StageResult
from image_clarus.stage_protocol import Terminal


def _stage(name, callback):
    return SimpleNamespace(
        name=name,
        uses_llm=True,
        skip_if_valid_output_exists=False,
        predicted_output_exists=lambda _image: False,
        inspect=lambda image, *_args, **_kwargs: callback(image),
        start_or_resume=lambda *_args: None,
    )


def test_worker_failure_settles_queued_work_and_preserves_blocked_result(tmp_path):
    entered = threading.Event()
    release = threading.Event()
    aborted = threading.Event()
    events = []
    seen = []
    sentinel = "synthetic-private-worker-error"

    def desc(image):
        seen.append(("desc", Path(image).name))
        if Path(image).name == "second.jpg":
            assert entered.wait(5), "downstream stage did not start"
            raise RuntimeError(sentinel)
        return Terminal(StageResult("desc", "completed"))

    def json_stage(image):
        seen.append(("json", Path(image).name))
        entered.set()
        assert release.wait(10), "test did not release blocked stage"
        return Terminal(StageResult("json", "completed"))

    stages = (_stage("desc", desc), _stage("json", json_stage))
    config = {
        "state": {"directory": None, "accumulate_categories": False},
        "pipeline": {"missing_prerequisite": "fail", "on_stage_failure": "continue"},
        "stages": {"desc": {"regenerate": False}, "json": {"regenerate": False}},
    }
    images = [tmp_path / name for name in ("first.jpg", "second.jpg", "third.jpg")]
    for image in images:
        image.write_bytes(b"fictional image")
    plan = build_plan(
        [
            PlanningInput(str(p), (str(p), str(p.parent.resolve()), "file"))
            for p in images
        ],
        config,
        selected=("desc", "json"),
        stages=stages,
    )
    services = SimpleNamespace(
        artifacts=ArtifactService(), provider_factory=lambda *_: None
    )
    result = {}

    def on_event(event):
        events.append(event)
        if event.kind == "abort" and event.cause == "internal_error":
            aborted.set()

    def run():
        try:
            result["value"] = run_concurrent(
                plan, config, services, cwd=tmp_path, on_event=on_event
            )
        except BaseException as exc:  # noqa: BLE001 - propagate thread failures to test
            result["error"] = exc

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    try:
        assert aborted.wait(5), "worker failure did not abort while downstream held"
        assert not release.is_set()
        assert ("desc", "third.jpg") not in seen
    finally:
        release.set()
        thread.join(10)
    assert not thread.is_alive(), "coordinator stranded work after worker failure"
    assert "error" not in result, repr(result.get("error"))
    execution = result["value"]
    assert execution.exit_code == 1
    outcomes = {
        (i, stage.stage): stage
        for i, image in enumerate(execution.images)
        for stage in image.stages
    }
    assert len(outcomes) == 6
    assert outcomes[(0, "desc")].disposition == "completed"
    assert outcomes[(0, "json")].disposition == "completed"
    assert outcomes[(1, "desc")].disposition == "failed"
    assert outcomes[(1, "json")].reason_code == "stage_not_run_after_failure"
    for name in ("desc", "json"):
        assert outcomes[(2, name)].disposition == "not_attempted"
        assert outcomes[(2, name)].reason_code == "batch_aborted"
    terminals = [event for event in events if event.kind == "stage_terminal"]
    assert Counter((event.image_id, event.stage) for event in terminals) == Counter(
        outcomes.keys()
    )
    for event in terminals:
        outcome = outcomes[(event.image_id, event.stage)]
        assert event.disposition == outcome.disposition
        assert event.reason_code == outcome.reason_code
        assert event.error_category == (
            outcome.result.error_category if outcome.result is not None else None
        )
        assert event.generation == plan.rows[event.image_id][5]
        assert event.admission is plan.rows[event.image_id][4]
    assert sentinel not in repr(events)
    assert sentinel not in repr(execution)
    assert [p.read_bytes() for p in images] == [b"fictional image"] * 3
