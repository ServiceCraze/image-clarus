import json
from pathlib import Path
from types import SimpleNamespace
from typing import Literal

import pytest

from image_clarus import batch_execution
from image_clarus.artifacts import ArtifactService
from image_clarus.batch_execution import run_sequential
from image_clarus.batch_plan import PlanningInput, build_plan
from image_clarus.results import StageResult
from image_clarus.stage_protocol import Terminal, WorkRequired
from image_clarus.stage_registry import STAGES
from image_clarus.state.storage import (
    DATABASE_NAME,
    MemoryStoragePool,
    SQLiteStorage,
    StateError,
    initialize,
)


def _config(*, state_directory=None, policy="continue", accumulate=True):
    return {
        "state": {
            "directory": state_directory,
            "accumulate_categories": accumulate,
        },
        "pipeline": {
            "missing_prerequisite": "fail",
            "on_stage_failure": policy,
        },
        "stages": {
            "desc": {"regenerate": False},
            "json": {"regenerate": False},
            "xmp": {"regenerate": False},
        },
    }


def _inputs(images):
    return [
        PlanningInput(str(image), (str(image), str(image.parent.resolve()), "file"))
        for image in images
    ]


def _plan(images, config, selected=("desc",), *, limit=None, stages=STAGES):
    return build_plan(
        _inputs(images),
        config,
        selected=selected,
        limit=limit,
        stages=stages,
    )


def _services(provider_factory=None):
    return SimpleNamespace(
        artifacts=ArtifactService(),
        provider_factory=provider_factory,
    )


@pytest.fixture(autouse=True)
def _working_directories(tmp_path):
    (tmp_path / "cwd").mkdir(exist_ok=True)
    (tmp_path / "no-store").mkdir(exist_ok=True)


def _test_stage(name, inspect):
    def advance(context, provider_result):
        raise AssertionError("the inspection should be terminal")

    return SimpleNamespace(
        name=name,
        uses_llm=False,
        skip_if_valid_output_exists=False,
        predicted_output_exists=lambda _image: False,
        inspect=inspect,
        start_or_resume=advance,
    )


def test_sequential_plan_is_complete_before_first_stage_and_not_mutated(tmp_path):
    images = [tmp_path / "first.jpg", tmp_path / "second.jpg"]
    for image in images:
        image.write_bytes(b"image")
    config = _config()
    observed = []
    stage = _test_stage(
        "desc",
        lambda image, *_args, **_kwargs: (
            observed.append(Path(image).name)
            or Terminal(StageResult("desc", "completed"))
        ),
    )
    plan = _plan(images, config, stages=(stage,))
    rows = list(plan.rows)
    queues = tuple(tuple(queue) for queue in plan.queues)
    events = []

    result = run_sequential(
        plan,
        config,
        _services(),
        cwd=tmp_path,
        on_event=events.append,
    )

    planned_ids = [event.image_id for event in events if event.kind == "planned"]
    first_stage_index = next(
        index for index, event in enumerate(events) if event.kind == "stage_evaluated"
    )
    assert planned_ids == [0, 1]
    assert events[first_stage_index].image_id == 0
    assert observed == ["first.jpg", "second.jpg"]
    assert [len(image.stages) for image in result.images] == [1, 1]
    assert plan.rows == rows
    assert tuple(tuple(queue) for queue in plan.queues) == queues


def test_known_exclusion_confirms_predicted_bypass_without_inference(tmp_path):
    image = tmp_path / "sample.jpg"
    image.write_bytes(b"image")
    image.with_name(image.name + ".desc.txt").write_text("Existing description")
    config = _config(policy="continue")
    plan = _plan([image], config, selected=("desc", "json"), limit=0)
    calls = []
    events = []

    def forbidden_provider(*_args, **_kwargs):
        calls.append(True)
        raise AssertionError("known-excluded inference must not start")

    result = run_sequential(
        plan,
        config,
        _services(forbidden_provider),
        cwd=tmp_path / "cwd",
        on_event=events.append,
    )

    outcomes = result.images[0].stages
    assert plan.rows[0][4].value == "KNOWN_EXCLUDED"
    assert [(item.stage, item.disposition, item.reason_code) for item in outcomes] == [
        ("desc", "skipped", "output_exists"),
        ("json", "skipped", "budget_excluded"),
    ]
    assert calls == []
    evaluated = [event.stage for event in events if event.kind == "stage_evaluated"]
    assert evaluated == ["desc"]
    assert [
        event.reason_code for event in events if event.kind == "stage_terminal"
    ] == [
        "output_exists",
        "budget_excluded",
    ]


def test_budget_excluded_json_created_after_planning_does_not_accumulate(tmp_path):
    image = tmp_path / "sample.jpg"
    image.write_bytes(b"image")
    state_dir = tmp_path / "state"
    initialize(state_dir)
    SQLiteStorage(state_dir).add_categories(["Existing/Keep"])
    config = _config(state_directory=state_dir)
    plan = _plan([image], config, selected=("json",), limit=0)
    assert plan.rows[0][4].value == "KNOWN_EXCLUDED"
    image.with_name(image.name + ".desc.json").write_text(
        json.dumps(_envelope({"caption": "example", "tag_candidates": [["New/Path"]]}))
    )
    provider_calls = []
    events = []

    def forbidden_provider(*_args, **_kwargs):
        provider_calls.append(True)
        raise AssertionError("a known-excluded image must not enter inference")

    result = run_sequential(
        plan,
        config,
        _services(forbidden_provider),
        cwd=tmp_path / "cwd",
        on_event=events.append,
    )

    assert result.images[0].stages[0].reason_code == "budget_excluded"
    assert not any(
        event.kind == "stage_evaluated" and event.stage == "json" for event in events
    )
    assert provider_calls == []
    assert SQLiteStorage(state_dir).snapshot_categories() == ["Existing/Keep"]


def test_invalid_predicted_description_fails_without_regeneration_or_replenishment(
    tmp_path,
):
    image = tmp_path / "sample.jpg"
    image.write_bytes(b"image")
    image.with_name(image.name + ".desc.txt").write_bytes(b"")
    config = _config(policy="continue")
    plan = _plan([image], config, selected=("desc", "json"), limit=0)
    provider_calls = []

    def forbidden_provider(*_args, **_kwargs):
        provider_calls.append(True)
        raise AssertionError("invalid primary must not trigger excluded inference")

    result = run_sequential(
        plan,
        config,
        _services(forbidden_provider),
        cwd=tmp_path / "cwd",
    )

    assert plan.rows[0][4].value == "KNOWN_EXCLUDED"
    assert [
        (
            item.stage,
            item.disposition,
            item.result.error_category if item.result else None,
        )
        for item in result.images[0].stages
    ] == [
        ("desc", "failed", "invalid_artifact"),
        ("json", "skipped", None),
    ]
    assert result.exit_code == 1
    assert provider_calls == []


def test_known_excluded_image_still_runs_selected_non_llm_stage(tmp_path):
    image = tmp_path / "sample.jpg"
    image.write_bytes(b"image")
    config = _config(policy="continue")
    config["pipeline"]["missing_prerequisite"] = "skip"
    plan = _plan([image], config, selected=("desc", "xmp"), limit=0)
    events = []
    provider_calls = []

    def forbidden_provider(*_args, **_kwargs):
        provider_calls.append(True)
        raise AssertionError("the selected stages require no provider request")

    result = run_sequential(
        plan,
        config,
        _services(forbidden_provider),
        cwd=tmp_path / "cwd",
        on_event=events.append,
    )

    assert plan.rows[0][4].value == "KNOWN_EXCLUDED"
    assert [
        (stage.stage, stage.disposition, stage.reason_code)
        for stage in result.images[0].stages
    ] == [
        ("desc", "skipped", "budget_excluded"),
        ("xmp", "skipped", "missing_prerequisite"),
    ]
    assert [event.stage for event in events if event.kind == "stage_evaluated"] == [
        "xmp"
    ]
    # The XMP stage is attempted but its prerequisite is missing, so nothing is
    # transformed; the event must not overstate work.
    assert [event.stage for event in events if event.kind == "transform_started"] == []
    assert provider_calls == []


def test_prediction_is_rechecked_and_valid_backup_is_recovered(tmp_path):
    image = tmp_path / "sample.jpg"
    image.write_bytes(b"image")
    output = image.with_name(image.name + ".desc.txt")
    output.write_bytes(b"planned description")
    config = _config()
    plan = _plan([image], config)
    backup = output.with_name(output.name + ".bak")
    output.unlink()
    backup.write_bytes(b"recovered description")
    provider_calls = []
    events = []

    def forbidden_provider(*_args, **_kwargs):
        provider_calls.append(True)
        raise AssertionError("valid recovered artifact should skip inference")

    result = run_sequential(
        plan,
        config,
        _services(forbidden_provider),
        cwd=tmp_path / "cwd",
        on_event=events.append,
    )

    assert result.images[0].stages[0].reason_code == "output_exists"
    assert output.read_bytes() == b"recovered description"
    assert not backup.exists()
    assert provider_calls == []
    assert [event.kind for event in events if event.kind == "stage_terminal"] == [
        "stage_terminal"
    ]


def test_output_appearing_before_continuation_recheck_does_not_start_transform(
    monkeypatch, tmp_path
):
    from image_clarus.stages import description

    image = tmp_path / "sample.jpg"
    image.write_bytes(b"image")
    output = image.with_name(image.name + ".desc.txt")
    config = _config()
    plan = _plan([image], config)
    original_inspect = description.inspect

    def inspect_then_create_output(*args, **kwargs):
        result = original_inspect(*args, **kwargs)
        if isinstance(result, WorkRequired):
            output.write_text("appeared after planning")
        return result

    monkeypatch.setattr(description, "inspect", inspect_then_create_output)
    events = []

    result = run_sequential(
        plan,
        config,
        _services(),
        cwd=tmp_path / "cwd",
        on_event=events.append,
    )

    assert result.images[0].stages[0].reason_code == "output_exists"
    assert output.read_text() == "appeared after planning"
    assert [event.kind for event in events if event.kind == "stage_evaluated"] == [
        "stage_evaluated"
    ]
    assert not any(event.kind == "transform_started" for event in events)


def test_initial_no_work_can_correct_missing_output_after_plan(tmp_path):
    image = tmp_path / "sample.jpg"
    image.write_bytes(b"image")
    output = image.with_name(image.name + ".desc.txt")
    output.write_text("stale planned output")
    prompt = tmp_path / "prompt.txt"
    prompt.write_text("Describe the example.")
    config = {
        **_config(),
        "providers": {"demo": {"base_url": "http://localhost/v1"}},
        "models": {"example": {"provider": "demo", "model_id": "example-model"}},
        "stages": {
            **_config()["stages"],
            "desc": {
                "model": "example",
                "prompt_file": prompt,
                "reasoning_effort": None,
                "regenerate": False,
            },
        },
    }
    plan = _plan([image], config, selected=("desc",), limit=0)
    output.unlink()
    calls = []

    class Provider:
        def image(self, **arguments):
            calls.append(arguments)
            return "repaired description"

    result = run_sequential(
        plan,
        config,
        _services(lambda _provider, _model: Provider()),
        cwd=tmp_path / "cwd",
    )

    assert plan.rows[0][4].value == "NO_LLM_WORK"
    assert result.images[0].stages[0].disposition == "completed"
    assert output.read_text() == "repaired description"
    assert len(calls) == 1
    assert result.exit_code == 0


def _envelope(metadata, *, model="example-model"):
    return {
        "format_version": 1,
        "schema_id": "urn:image-clarus:metadata-schema:2.0.0",
        "schema_version": "2.0.0",
        "metadata": metadata,
        "provenance": {
            "provider_alias": "demo",
            "model_alias": "example",
            "model_id": model,
            "prompt_id": "fixture",
            "description_sha256": "a" * 64,
        },
    }


@pytest.mark.parametrize(
    "accumulate,expected_first,expected_second",
    [
        (True, '["Nature/Birds"]', '["Nature/Birds","Nature/Flowers"]'),
        (False, "[]", "[]"),
    ],
)
def test_previous_valid_json_updates_shared_memory_before_next_prompt(
    tmp_path, accumulate, expected_first, expected_second
):
    first, second, third = (
        tmp_path / "first.jpg",
        tmp_path / "second.jpg",
        tmp_path / "third.jpg",
    )
    for image in (first, second, third):
        image.write_bytes(b"image")
    first_json = first.with_name(first.name + ".desc.json")
    first_json.write_text(
        json.dumps(
            _envelope({"caption": "first", "tag_candidates": [["Nature", "Birds"]]})
        )
    )
    second.with_name(second.name + ".desc.txt").write_text("A second image")
    third.with_name(third.name + ".desc.txt").write_text("A third image")
    description_prompt = tmp_path / "description-prompt.txt"
    description_prompt.write_text("Describe the example.")
    json_prompt = tmp_path / "json-prompt.txt"
    json_prompt.write_text("Known categories: {{state.categories.known}}")
    schema = tmp_path / "schema.json"
    schema.write_text(
        json.dumps(
            {
                "type": "object",
                "properties": {
                    "caption": {"type": "string"},
                    "tag_candidates": {
                        "type": "array",
                        "items": {"type": "array", "items": {"type": "string"}},
                    },
                },
                "required": ["caption", "tag_candidates"],
                "additionalProperties": False,
            }
        )
    )
    config = {
        **_config(policy="continue", accumulate=accumulate),
        "providers": {"demo": {"base_url": "http://localhost/v1"}},
        "models": {"example": {"provider": "demo", "model_id": "example-model"}},
        "prompt_expansion": {"macros": {}},
        "stages": {
            **_config()["stages"],
            "desc": {
                "model": "example",
                "prompt_file": description_prompt,
                "reasoning_effort": None,
                "regenerate": False,
            },
            "json": {
                "model": "example",
                "prompt_file": json_prompt,
                "schema_file": schema,
                "reasoning_effort": None,
                "regenerate": False,
                "validation_retries": 0,
                "preferred_categories": [],
                "include_prompt_sha256": False,
            },
        },
    }
    plan = _plan([first, second, third], config, selected=("desc", "json"), limit=3)
    events = []
    captured = {"images": 0, "prompts": []}

    class Provider:
        def image(self, **_arguments):
            captured["images"] += 1
            raise RuntimeError("provider failure detail must stay private")

        def structured(self, **arguments):
            captured["prompts"].append(arguments["prompt"])
            tag = "Flowers" if len(captured["prompts"]) == 1 else "Trees"
            return json.dumps(
                {"caption": "generated", "tag_candidates": [["Nature", tag]]}
            )

    result = run_sequential(
        plan,
        config,
        _services(lambda _provider, _model: Provider()),
        cwd=tmp_path / "no-store",
        on_event=events.append,
    )

    assert [(stage.stage, stage.disposition) for stage in result.images[0].stages] == [
        ("desc", "failed"),
        ("json", "skipped"),
    ]
    assert result.images[0].stages[1].reason_code == "output_exists"
    assert result.images[1].stages[0].reason_code == "output_exists"
    assert result.images[1].stages[1].disposition == "completed"
    assert result.images[2].stages[0].reason_code == "output_exists"
    assert result.images[2].stages[1].disposition == "completed"
    failed_description = result.images[0].stages[0].result
    assert failed_description is not None
    assert failed_description.error_category == "provider_unavailable"
    assert failed_description.message == "Description provider request failed"
    assert "provider failure detail must stay private" not in repr(events)
    assert [
        (event.image_id, event.stage)
        for event in events
        if event.kind == "transform_started"
    ] == [(0, "desc"), (1, "json"), (2, "json")]
    assert captured["images"] == 1
    assert len(captured["prompts"]) == 2
    assert expected_first in captured["prompts"][0]
    assert expected_second in captured["prompts"][1]
    provider_events = [
        event for event in events if event.kind.startswith("provider_request_")
    ]
    assert [
        (event.kind, event.image_id, event.disposition, event.error_category)
        for event in provider_events
    ] == [
        ("provider_request_started", 0, None, None),
        ("provider_request_result", 0, "failed", "provider_unavailable"),
        ("provider_request_started", 1, None, None),
        ("provider_request_result", 1, "completed", None),
        ("provider_request_started", 2, None, None),
        ("provider_request_result", 2, "completed", None),
    ]
    assert all(
        started.request_id == response.request_id
        for started, response in zip(provider_events[::2], provider_events[1::2])
    )
    assert result.exit_code == 1


def _observer_plan(
    images,
    config,
    observations,
    *,
    action=None,
    status: Literal["completed", "skipped", "failed"] = "completed",
):
    stage = _test_stage(
        "desc",
        lambda image, _config, services, **_kwargs: (
            observations.__setitem__(image, services.state.snapshot_categories())
            or (action(image, services.state) if action else None)
            or Terminal(StageResult("desc", status))
        ),
    )
    return _plan(images, config, stages=(stage,))


def test_invocation_memory_pool_closes_after_each_image_service(tmp_path, monkeypatch):
    pools = []

    class RecordingMemoryPool(MemoryStoragePool):
        def __init__(self, *, stop=None):
            super().__init__(stop=stop)
            pools.append(self)

    monkeypatch.setattr(batch_execution, "MemoryStoragePool", RecordingMemoryPool)
    images = [tmp_path / "first.jpg", tmp_path / "second.jpg"]
    for image in images:
        image.write_bytes(b"image")
    observations = {}
    config = _config()
    plan = _observer_plan(images, config, observations)

    result = run_sequential(plan, config, _services(), cwd=tmp_path / "cwd")

    assert result.exit_code == 0
    assert len(pools) == 1
    assert pools[0].active_views == 0
    with pytest.raises(StateError, match="memory storage pool closed"):
        pools[0].open()


def test_explicit_state_precedes_cwd_and_image_collections(tmp_path):
    cwd = tmp_path / "working"
    cwd.mkdir()
    roots = [tmp_path / "collection-one", tmp_path / "collection-two"]
    images = []
    for index, root in enumerate(roots, start=1):
        image_dir = root / "images"
        image_dir.mkdir(parents=True)
        image = image_dir / f"sample-{index}.jpg"
        image.write_bytes(b"image")
        images.append(image)
        initialize(root / ".image-clarus")
        SQLiteStorage(root / ".image-clarus").add_categories([f"Image/Root{index}"])
    cwd_store = cwd / ".image-clarus"
    initialize(cwd_store)
    SQLiteStorage(cwd_store).add_categories(["Cwd/Selected"])
    observations = {}
    plan = _observer_plan(images, _config(), observations)

    run_sequential(plan, _config(), _services(), cwd=cwd)
    assert list(observations.values()) == [["Cwd/Selected"], ["Cwd/Selected"]]

    explicit_store = tmp_path / "explicit-state"
    initialize(explicit_store)
    SQLiteStorage(explicit_store).add_categories(["Explicit/Selected"])
    explicit_config = _config(state_directory=explicit_store)
    observations.clear()
    plan = _observer_plan(images, explicit_config, observations)
    run_sequential(plan, explicit_config, _services(), cwd=cwd)
    assert list(observations.values()) == [
        ["Explicit/Selected"],
        ["Explicit/Selected"],
    ]


def test_invalid_explicit_state_does_not_fall_back_to_cwd_store(tmp_path, capsys):
    cwd = tmp_path / "working"
    cwd.mkdir()
    store = cwd / ".image-clarus"
    initialize(store)
    SQLiteStorage(store).add_categories(["Cwd/MustNotBeSelected"])
    images = [tmp_path / "images" / f"sample-{index}.jpg" for index in range(2)]
    images[0].parent.mkdir()
    for image in images:
        image.write_bytes(b"image")
    missing = tmp_path / "missing-explicit-state"
    config = _config(state_directory=missing)
    observations = {}

    def add_to_first_fallback(image, state):
        if image == images[0]:
            state.add_categories(["Memory/FirstOnly"])

    plan = _observer_plan(images, config, observations, action=add_to_first_fallback)
    events = []

    result = run_sequential(
        plan,
        config,
        _services(),
        cwd=cwd,
        on_event=events.append,
    )

    assert observations == {images[0]: [], images[1]: []}
    assert result.exit_code == 0
    assert [event.image_id for event in events if event.kind == "state_diagnostic"] == [
        0,
        1,
    ]
    stderr = capsys.readouterr().err
    assert "state error: repository unavailable" in stderr
    assert str(missing) not in stderr
    assert SQLiteStorage(store).snapshot_categories() == ["Cwd/MustNotBeSelected"]


@pytest.mark.parametrize("accumulate,expected", [(True, ["Nature/Birds"]), (False, [])])
def test_valid_skipped_json_finalizes_after_later_selected_failure(
    tmp_path, accumulate, expected
):
    image = tmp_path / "sample.jpg"
    image.write_bytes(b"image")
    artifact = image.with_name(image.name + ".desc.json")
    artifact.write_text(
        json.dumps(
            _envelope({"caption": "example", "tag_candidates": [["Nature", "Birds"]]})
        )
    )
    state_dir = tmp_path / "state"
    initialize(state_dir)
    config = _config(state_directory=state_dir, accumulate=accumulate)
    failing_xmp = _test_stage(
        "xmp",
        lambda *_args, **_kwargs: Terminal(
            StageResult("xmp", "failed", error_category="invalid_artifact")
        ),
    )
    plan = _plan(
        [image],
        config,
        selected=("json", "xmp"),
        stages=(STAGES[1], failing_xmp),
    )
    events = []

    result = run_sequential(
        plan,
        config,
        _services(),
        cwd=tmp_path / "cwd",
        on_event=events.append,
    )

    assert [
        (stage.stage, stage.disposition, stage.reason_code)
        for stage in result.images[0].stages
    ] == [
        ("json", "skipped", "output_exists"),
        ("xmp", "failed", None),
    ]
    assert result.exit_code == 1
    assert SQLiteStorage(state_dir).snapshot_categories() == expected
    assert [event.kind for event in events].count("image_finalized") == 1
    xmp_terminal = next(
        event
        for event in events
        if event.kind == "stage_terminal" and event.stage == "xmp"
    )
    finalized = next(event for event in events if event.kind == "image_finalized")
    assert xmp_terminal.sequence < finalized.sequence


def test_stop_after_json_terminal_skips_optional_accumulation(tmp_path):
    from image_clarus.stages.structure import _read_envelope

    image = tmp_path / "sample.jpg"
    image.write_bytes(b"image")
    artifact = image.with_name(image.name + ".desc.json")
    artifact.write_text(
        json.dumps(
            _envelope({"caption": "example", "tag_candidates": [["Nature", "Birds"]]})
        )
    )
    state_dir = tmp_path / "state"
    initialize(state_dir)
    SQLiteStorage(state_dir).add_categories(["Existing/Keep"])
    config = _config(state_directory=state_dir)
    plan = _plan([image], config, selected=("json",))
    stop = SimpleNamespace(signum=None)
    events = []
    envelope_reads = []

    def observe(event):
        events.append(event)
        if event.kind == "stage_terminal" and event.stage == "json":
            stop.signum = 2

    def read_envelope(data):
        envelope_reads.append(data)
        return _read_envelope(data)

    result = run_sequential(
        plan,
        config,
        _services(),
        cwd=tmp_path / "cwd",
        stop=stop,
        on_event=observe,
        read_envelope=read_envelope,
    )

    assert result.exit_code == 130
    assert result.interrupted_by == 2
    assert envelope_reads == []
    assert SQLiteStorage(state_dir).snapshot_categories() == ["Existing/Keep"]
    assert [event.kind for event in events].count("image_finalized") == 1


def test_each_image_selects_its_own_collection_state(tmp_path):
    cwd = tmp_path / "working"
    cwd.mkdir()
    images = []
    for label in ("One", "Two"):
        root = tmp_path / f"collection-{label.lower()}"
        image_dir = root / "images"
        image_dir.mkdir(parents=True)
        image = image_dir / f"sample-{label.lower()}.jpg"
        image.write_bytes(b"image")
        store = root / ".image-clarus"
        initialize(store)
        SQLiteStorage(store).add_categories([f"Collection/{label}"])
        images.append(image)
    observations = {}
    config = _config()
    plan = _observer_plan(images, config, observations)

    result = run_sequential(plan, config, _services(), cwd=cwd)

    assert observations[images[0]] == ["Collection/One"]
    assert observations[images[1]] == ["Collection/Two"]
    assert result.exit_code == 0


def test_corrupt_selected_state_is_visible_and_fallback_is_image_local(
    tmp_path, capsys
):
    cwd = tmp_path / "working"
    cwd.mkdir()
    bad_root = tmp_path / "collection-bad"
    good_root = tmp_path / "collection-good"
    bad_dir = bad_root / ".image-clarus"
    good_dir = good_root / ".image-clarus"
    bad_dir.mkdir(parents=True)
    corrupt = bad_dir / DATABASE_NAME
    corrupt.write_bytes(b"not a database")
    good_image_dir = good_root / "images"
    good_image_dir.mkdir(parents=True)
    bad_image_dir = bad_root / "images"
    bad_image_dir.mkdir(parents=True)
    bad_image = bad_image_dir / "bad.jpg"
    good_image = good_image_dir / "good.jpg"
    bad_image.write_bytes(b"image")
    good_image.write_bytes(b"image")
    initialize(good_dir)
    SQLiteStorage(good_dir).add_categories(["Persisted/Good"])
    observations = {}

    def add_local(image, state):
        state.add_categories(["Written/Bad" if image == bad_image else "Written/Good"])

    config = _config()
    plan = _observer_plan(
        [bad_image, good_image],
        config,
        observations,
        action=add_local,
        status="completed",
    )
    events = []

    result = run_sequential(
        plan,
        config,
        _services(),
        cwd=cwd,
        on_event=events.append,
    )

    assert observations[bad_image] == []
    assert observations[good_image] == ["Persisted/Good"]
    assert result.exit_code == 0
    assert [event.image_id for event in events if event.kind == "state_diagnostic"] == [
        0
    ]
    stderr = capsys.readouterr().err
    assert "state error: repository unavailable" in stderr
    assert str(bad_dir) not in stderr
    assert corrupt.read_bytes() == b"not a database"
    assert SQLiteStorage(good_dir).snapshot_categories() == [
        "Persisted/Good",
        "Written/Good",
    ]


def test_stop_before_execution_marks_all_selected_stages_not_attempted(tmp_path):
    image = tmp_path / "sample.jpg"
    image.write_bytes(b"image")
    config = _config()
    entered = []
    stage = _test_stage(
        "desc",
        lambda *_args, **_kwargs: (
            entered.append(True) or Terminal(StageResult("desc", "completed"))
        ),
    )
    plan = _plan([image], config, stages=(stage,))
    events = []

    result = run_sequential(
        plan,
        config,
        _services(),
        cwd=tmp_path / "cwd",
        stop=SimpleNamespace(signum=15),
        on_event=events.append,
    )

    assert result.exit_code == 143
    assert result.images[0].stages[0].disposition == "not_attempted"
    assert entered == []
    assert [event.kind for event in events].count("stop") == 1
    assert not any(event.kind == "state_diagnostic" for event in events)


@pytest.mark.parametrize(
    "policy,expected,aborted",
    [
        ("continue", ["failed", "completed"], False),
        ("stop", ["failed", "not_attempted"], False),
        ("abort", ["failed", "not_attempted"], True),
    ],
)
def test_failure_policy_controls_later_selected_stages(
    tmp_path, policy, expected, aborted
):
    image = tmp_path / f"{policy}.jpg"
    image.write_bytes(b"image")
    config = _config(policy=policy)
    second_called = []
    desc = _test_stage(
        "desc",
        lambda *_args, **_kwargs: Terminal(
            StageResult("desc", "failed", error_category="provider_unavailable")
        ),
    )
    json_stage = _test_stage(
        "json",
        lambda *_args, **_kwargs: (
            second_called.append(True) or Terminal(StageResult("json", "completed"))
        ),
    )
    plan = _plan([image], config, selected=("desc", "json"), stages=(desc, json_stage))

    result = run_sequential(plan, config, _services(), cwd=tmp_path / "cwd")

    assert [outcome.disposition for outcome in result.images[0].stages] == expected
    assert result.aborted is aborted
    assert bool(second_called) is (policy == "continue")
    assert result.exit_code == 1
