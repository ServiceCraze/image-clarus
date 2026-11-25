"""Concurrent coordination, forwarding, shutdown and child ownership."""

import os
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from image_clarus import batch_execution
from image_clarus.artifacts import ArtifactError, ArtifactService
from image_clarus.batch_execution import (
    ChildProvider,
    PublicationGate,
    run_concurrent,
    run_sequential,
)
from image_clarus.batch_plan import PlanningInput, build_plan
from image_clarus.results import StageResult
from image_clarus.stage_protocol import ProviderResult, Terminal, WorkRequired
from image_clarus.stage_registry import STAGES


def _config(*, policy="continue", accumulate=True, state_directory=None):
    return {
        "state": {
            "directory": state_directory,
            "accumulate_categories": accumulate,
        },
        "pipeline": {"missing_prerequisite": "fail", "on_stage_failure": policy},
        "stages": {
            "desc": {"regenerate": False},
            "json": {"regenerate": False},
            "xmp": {"regenerate": False},
        },
    }


def _images(tmp_path, names):
    created = []
    for name in names:
        image = tmp_path / name
        image.write_bytes(b"synthetic-image")
        created.append(image)
    return created


def _plan(images, config, selected=("desc",), *, stages=None, limit=None):
    return build_plan(
        [
            PlanningInput(str(image), (str(image), str(image.parent.resolve()), "file"))
            for image in images
        ],
        config,
        selected=selected,
        limit=limit,
        stages=STAGES if stages is None else stages,
    )


def _services():
    return SimpleNamespace(
        artifacts=ArtifactService(), provider_factory=lambda provider, model: None
    )


def _stage(name, inspect, *, uses_llm=True):
    def advance(context, provider_result):  # pragma: no cover - not reached
        raise AssertionError("inspection should be terminal")

    return SimpleNamespace(
        name=name,
        uses_llm=uses_llm,
        skip_if_valid_output_exists=False,
        predicted_output_exists=lambda _image: False,
        inspect=inspect,
        start_or_resume=advance,
    )


def _terminal_stage(name, callback):
    """A stage whose inspection runs `callback` and returns a real result."""
    return _stage(
        name,
        lambda image, *_a, **_k: (
            callback(image) or Terminal(StageResult(name, "completed"))
        ),
    )


class _Barrier:
    """Small deterministic rendezvous usable from stage actors."""

    def __init__(self, parties):
        self._event = threading.Event()
        self._lock = threading.Lock()
        self._parties = parties
        self._waiting = 0

    def wait(self, timeout=5.0):
        with self._lock:
            self._waiting += 1
            if self._waiting >= self._parties:
                self._event.set()
                return True
        return self._event.wait(timeout)


class _ActivityTracker:
    """Records concurrent activity per stage and per image."""

    def __init__(self):
        self._lock = threading.Lock()
        self.active = {}
        self.per_stage = {}
        self.per_image = {}
        self.max_per_stage = {}
        self.max_per_image = {}

    def enter(self, stage, image):
        with self._lock:
            self.active[image] = self.active.get(image, 0) + 1
            self.per_stage[stage] = self.per_stage.get(stage, 0) + 1
            self.per_image[image] = self.per_image.get(image, 0) + 1
            self.max_per_stage[stage] = max(
                self.max_per_stage.get(stage, 0), self.per_stage[stage]
            )
            self.max_per_image[image] = max(
                self.max_per_image.get(image, 0), self.per_image[image]
            )
            if self.active[image] > 1:
                raise AssertionError("same image executed twice concurrently")

    def leave(self, stage, image):
        with self._lock:
            self.active[image] -= 1
            self.per_stage[stage] -= 1
            self.per_image[image] -= 1


def test_upstream_activity_and_downstream_activity_actually_overlap(tmp_path):
    images = _images(tmp_path, ["first.jpg", "second.jpg"])
    tracker = _ActivityTracker()
    entered = threading.Event()
    both_active = threading.Event()
    observed = []

    def upstream(image, *_args, **_kwargs):
        tracker.enter("desc", image)
        try:
            entered.set()
            both_active.wait(5)
            observed.append(("desc", Path(image).name))
        finally:
            tracker.leave("desc", image)
        return Terminal(StageResult("desc", "completed"))

    def downstream(image, *_args, **_kwargs):
        tracker.enter("json", image)
        try:
            entered.wait(5)
            both_active.set()
            observed.append(("json", Path(image).name))
            time.sleep(0.02)
        finally:
            tracker.leave("json", image)
        return Terminal(StageResult("json", "completed"))

    stages = (_stage("desc", upstream), _stage("json", downstream))
    config = _config()
    plan = _plan(images, config, selected=("desc", "json"), stages=stages)

    result = run_concurrent(plan, config, _services(), cwd=tmp_path / "cwd")

    assert result.exit_code == 0
    assert ("desc", "first.jpg") in observed
    assert ("json", "first.jpg") in observed
    # The description of image two ran while image one already reached JSON.
    assert [event for event in observed if event[0] == "desc"]
    assert tracker.max_per_stage["desc"] == 1
    assert tracker.max_per_stage["json"] == 1
    assert max(tracker.max_per_image.values()) == 1
    assert result.images[0].stages[0].disposition == "completed"


def test_actor_serves_queued_candidates_while_its_request_is_outstanding(tmp_path):
    """A2 §4: the actor services confirmations while a request is outstanding.

    The held image blocks inside a real provider request (a fake transport
    child), so the owning actor must keep its queue. A confirmable candidate
    queued behind it must be admitted and forwarded to its downstream stage
    before that request completes.
    """
    from image_clarus.provider_frame import encode_frame
    from image_clarus.stage_registry import STAGES as REAL_STAGES

    images = _images(tmp_path, ["held.jpg", "ready.jpg"])
    Path(str(images[1]) + ".desc.txt").write_text(
        "Existing description", encoding="utf-8"
    )
    request_outstanding = threading.Event()
    release = threading.Event()
    candidate_reached_json = threading.Event()
    json_calls = []
    desc_calls = []

    class HeldProcess:
        """A transport child whose answer is withheld until the test releases it."""

        def __init__(self):
            self.stdin = _Replier()
            self.stdout = _PipeOut(encode_frame({"category": None, "content": ""}))
            self.returncode = 0

        def poll(self):
            return 0

        def wait(self, timeout=None):
            return 0

        def kill(self):
            return None

    class HeldChildProvider(ChildProvider):
        """Signals the moment the request is outstanding, then holds it."""

        def call(self, request):
            if request.operation == "image" and "held.jpg" in str(request.request_id):
                request_outstanding.set()
                release.wait(10)
            return super().call(request)

    def fake_popen(*_args, **_kwargs):
        return HeldProcess()

    def desc_inspect(image, _config, _services, **_kwargs):
        desc_calls.append(Path(image).name)
        # The candidate is already confirmed by a cheap authoritative check.
        if Path(image).name == "ready.jpg":
            return Terminal(
                StageResult("desc", "completed", reason_code="output_exists")
            )
        # The held image needs a real transformation, which issues a request.
        return WorkRequired("desc", image, str(image))

    def desc_advance(context, result):
        """A real resumable continuation: context -> request -> terminal."""
        from image_clarus.stage_protocol import Request

        if result is None:
            return Request(
                (str(context), "desc", 0, "held-nonce"),
                "image",
                {
                    "provider": {
                        "base_url": "http://127.0.0.1:9/v1",
                        "timeout_seconds": 5,
                    },
                    "model": {"provider": "local", "model_id": "synthetic"},
                    "arguments": {
                        "prompt": "Describe.",
                        "image_bytes": b"x",
                        "suffix": ".jpg",
                        "effort": None,
                    },
                },
                context,
            )
        return Terminal(StageResult("desc", "completed"))

    def json_inspect(image, *_args, **_kwargs):
        json_calls.append(Path(image).name)
        if Path(image).name == "ready.jpg":
            candidate_reached_json.set()
        return Terminal(StageResult("json", "completed"))

    stages = (
        _replace_predicates(
            SimpleNamespace(
                name="desc",
                uses_llm=True,
                predicted_output_exists=REAL_STAGES[0].predicted_output_exists,
                skip_if_valid_output_exists=True,
                inspect=desc_inspect,
                start_or_resume=desc_advance,
            ),
            REAL_STAGES[0],
        ),
        _replace_predicates(_stage("json", json_inspect), REAL_STAGES[1]),
    )
    config = _config()
    plan = _plan(images, config, selected=("desc", "json"), stages=stages)
    holder = {}

    def run():
        holder["result"] = run_concurrent(
            plan, config, _services(), cwd=tmp_path / "cwd"
        )

    original_popen = batch_execution.subprocess.Popen
    batch_execution.subprocess.Popen = fake_popen
    original_cls = batch_execution.ChildProvider
    batch_execution.ChildProvider = HeldChildProvider
    worker = threading.Thread(target=run, daemon=True)
    worker.start()
    try:
        assert request_outstanding.wait(10), "no provider request became outstanding"
        # The candidate must be serviced while the request is still outstanding.
        assert candidate_reached_json.wait(5), (
            "a confirmable candidate made no progress while a request was outstanding"
        )
        assert not release.is_set()
    finally:
        release.set()
        worker.join(20)
        batch_execution.subprocess.Popen = original_popen
        batch_execution.ChildProvider = original_cls

    assert not worker.is_alive()
    assert "ready.jpg" in desc_calls
    assert "ready.jpg" in json_calls


def test_confirmation_defers_work_until_held_request_finishes(tmp_path, monkeypatch):
    """A confirmation preserves work without fallback or repeated inspection."""
    from image_clarus.stage_protocol import Request
    from image_clarus.stage_registry import STAGES as real_stages

    held, candidate = _images(tmp_path, ["held.jpg", "candidate.jpg"])
    request_started = threading.Event()
    candidate_inspected = threading.Event()
    release = threading.Event()
    inspection_count = {held.name: 0, candidate.name: 0}
    transports = []
    fallback_calls = []

    class HeldChild(ChildProvider):
        def call(self, request):
            name = Path(request.request_id[0]).name
            transports.append(name)
            if name == held.name:
                request_started.set()
                release.wait(10)
            return ProviderResult(request.request_id, content="valid")

    def inspect(image, *_args, **_kwargs):
        name = image.name
        inspection_count[name] += 1
        if name == candidate.name:
            candidate_inspected.set()
        return WorkRequired("desc", image, image)

    def advance(context, result):
        if result is None:
            return Request(
                (str(context), "desc", 0, f"request-{Path(context).name}"),
                "image",
                {
                    "provider": {
                        "base_url": "http://127.0.0.1:9/v1",
                        "timeout_seconds": 5,
                    },
                    "model": {"provider": "local", "model_id": "synthetic"},
                    "arguments": {
                        "prompt": "p",
                        "image_bytes": b"x",
                        "suffix": ".jpg",
                        "effort": None,
                    },
                },
                context,
            )
        if result.error_category:
            return Terminal(
                StageResult("desc", "failed", error_category=result.error_category)
            )
        return Terminal(StageResult("desc", "completed"))

    stage = _replace_predicates(
        SimpleNamespace(
            name="desc",
            uses_llm=True,
            predicted_output_exists=real_stages[0].predicted_output_exists,
            skip_if_valid_output_exists=False,
            inspect=inspect,
            start_or_resume=advance,
        ),
        real_stages[0],
    )
    config = _config(policy="continue")
    plan = _plan([held, candidate], config, stages=(stage,))

    def unexpected_fallback(*_args):
        fallback_calls.append(True)
        raise AssertionError("confirmation fell back to the provider factory")

    services = SimpleNamespace(
        artifacts=ArtifactService(), provider_factory=unexpected_fallback
    )
    monkeypatch.setattr(batch_execution, "ChildProvider", HeldChild)
    holder = {}
    worker = threading.Thread(
        target=lambda: holder.setdefault(
            "result", run_concurrent(plan, config, services, cwd=tmp_path / "cwd")
        ),
        daemon=True,
    )
    worker.start()
    try:
        assert request_started.wait(10), "the first transformation never started"
        assert candidate_inspected.wait(5), "the candidate was not confirmed"
        # The candidate has only been inspected and deferred: it must not loop
        # through confirmation or start its own transport while capacity is full.
        time.sleep(0.1)
        assert transports == [held.name]
        assert inspection_count[candidate.name] == 1
        assert not fallback_calls
    finally:
        release.set()
        worker.join(20)

    assert not worker.is_alive()
    assert transports == [held.name, candidate.name]
    assert not fallback_calls
    assert holder["result"].exit_code == 0
    assert all(
        outcome.disposition == "completed"
        for image in holder["result"].images
        for outcome in image.stages
    )


def test_one_active_job_per_stage_while_requests_are_outstanding(tmp_path, monkeypatch):
    """A2 §4: confirmation service must never admit a second inference.

    Several images hold real provider requests at once. Each stage must still
    show at most one active job, and the confirmation sweeps must not start a
    second request for the same stage.
    """
    from image_clarus.provider_frame import encode_frame
    from image_clarus.stage_registry import STAGES as REAL_STAGES

    images = _images(tmp_path, [f"held-{n}.jpg" for n in range(4)])
    requests_started = []
    release = threading.Event()
    holds = []
    in_flight = []
    lock = threading.Lock()

    class HeldProcess:
        def __init__(self):
            self.stdin = _Replier()
            self.stdout = _PipeOut(encode_frame({"category": None, "content": ""}))
            self.returncode = 0

        def poll(self):
            return 0

        def wait(self, timeout=None):
            return 0

        def kill(self):
            return None

    class CountingChild(ChildProvider):
        def call(self, request):
            with lock:
                requests_started.append(request.request_id)
                in_flight.append(1)
                peak[0] = max(peak[0], len(in_flight))
                held = threading.Event()
                holds.append(held)
            try:
                # Stay outstanding until the test lets this specific call finish.
                release.wait(15)
                return super().call(request)
            finally:
                with lock:
                    in_flight.pop()

    peak = [0]

    def desc_advance(context, result):
        from image_clarus.stage_protocol import Request

        if result is None:
            return Request(
                (str(context), "desc", 0, f"nonce-{context}"),
                "image",
                {
                    "provider": {
                        "base_url": "http://127.0.0.1:9/v1",
                        "timeout_seconds": 5,
                    },
                    "model": {"provider": "local", "model_id": "synthetic"},
                    "arguments": {
                        "prompt": "Describe.",
                        "image_bytes": b"x",
                        "suffix": ".jpg",
                        "effort": None,
                    },
                },
                context,
            )
        return Terminal(StageResult("desc", "completed"))

    def desc_inspect(image, *_args, **_kwargs):
        return WorkRequired("desc", image, str(image))

    stages = (
        _replace_predicates(
            SimpleNamespace(
                name="desc",
                uses_llm=True,
                predicted_output_exists=REAL_STAGES[0].predicted_output_exists,
                skip_if_valid_output_exists=False,
                inspect=desc_inspect,
                start_or_resume=desc_advance,
            ),
            REAL_STAGES[0],
        ),
    )
    config = _config(policy="continue")
    plan = _plan(images, config, stages=stages)
    holder = {}

    def run():
        holder["result"] = run_concurrent(
            plan, config, _services(), cwd=tmp_path / "cwd"
        )

    monkeypatch.setattr(
        batch_execution.subprocess, "Popen", lambda *a, **k: HeldProcess()
    )
    monkeypatch.setattr(batch_execution, "ChildProvider", CountingChild)
    worker = threading.Thread(target=run, daemon=True)
    worker.start()
    try:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and not requests_started:
            time.sleep(0.01)
        assert requests_started, "no provider request ever became outstanding"
        # Let the actor sweep its queue repeatedly while the request is held.
        deadline = time.monotonic() + 0.5
        while time.monotonic() < deadline:
            time.sleep(0.01)
        assert not release.is_set()
        assert peak[0] == 1, f"{peak[0]} inferences were outstanding for one stage"
    finally:
        release.set()
        worker.join(30)

    assert not worker.is_alive()
    assert holder["result"].exit_code == 0


def test_two_stages_hold_requests_for_different_images_at_once(tmp_path, monkeypatch):
    """The pending limit is per stage, so two stages may each hold a request.

    Two images are needed: with same-image ordering, the second stage of one
    image cannot start until its first stage finishes. Different images are
    what lets description and JSON each hold an outstanding request.
    """
    from image_clarus.provider_frame import encode_frame
    from image_clarus.stage_registry import STAGES as REAL_STAGES

    images = _images(tmp_path, ["first.jpg", "second.jpg"])
    per_stage_in_flight = {"desc": 0, "json": 0}
    overlap_seen = threading.Event()
    release = threading.Event()
    lock = threading.Lock()
    peak = [0]

    class HeldProcess:
        def __init__(self):
            self.stdin = _Replier()
            self.stdout = _PipeOut(encode_frame({"category": None, "content": ""}))
            self.returncode = 0

        def poll(self):
            return 0

        def wait(self, timeout=None):
            return 0

        def kill(self):
            return None

    request_stages = []

    class StageCountingChild(ChildProvider):
        def call(self, request):
            from image_clarus.stage_protocol import ProviderResult

            stage = request.request_id[1]
            with lock:
                request_stages.append(stage)
                per_stage_in_flight[stage] += 1
                peak[0] = max(
                    peak[0], sum(1 for n in per_stage_in_flight.values() if n)
                )
                if all(n for n in per_stage_in_flight.values()):
                    overlap_seen.set()
            try:
                release.wait(20)
                return ProviderResult(request.request_id, content="{}")
            finally:
                with lock:
                    per_stage_in_flight[stage] -= 1

    def advance(name):
        def step(context, result):
            from image_clarus.stage_protocol import Request, Terminal

            if result is None:
                return Request(
                    (str(context), name, 0, f"{name}-nonce"),
                    "image",
                    {
                        "provider": {
                            "base_url": "http://127.0.0.1:9/v1",
                            "timeout_seconds": 5,
                        },
                        "model": {"provider": "local", "model_id": "synthetic"},
                        "arguments": {
                            "prompt": "p",
                            "image_bytes": b"x",
                            "suffix": ".jpg",
                            "effort": None,
                        },
                    },
                    context,
                )
            return Terminal(StageResult(name, "completed"))

        return step

    call_order = []

    def inspect(name):
        def step(image, *_a, **_k):
            from image_clarus.stage_protocol import Terminal, WorkRequired

            key = (name, image.name)
            call_order.append(key)
            if key == ("desc", "first.jpg"):
                return Terminal(StageResult(name, "completed"))
            return WorkRequired(name, image, str(image))

        return step

    stages = (
        _replace_predicates(
            SimpleNamespace(
                name="desc",
                uses_llm=True,
                predicted_output_exists=REAL_STAGES[0].predicted_output_exists,
                skip_if_valid_output_exists=False,
                inspect=inspect("desc"),
                start_or_resume=advance("desc"),
            ),
            REAL_STAGES[0],
        ),
        _replace_predicates(
            SimpleNamespace(
                name="json",
                uses_llm=True,
                predicted_output_exists=REAL_STAGES[1].predicted_output_exists,
                skip_if_valid_output_exists=False,
                inspect=inspect("json"),
                start_or_resume=advance("json"),
            ),
            REAL_STAGES[1],
        ),
    )
    config = _config(policy="continue")
    plan = _plan(images, config, selected=("desc", "json"), stages=stages)
    holder = {}

    def run():
        holder["result"] = run_concurrent(
            plan, config, _services(), cwd=tmp_path / "cwd"
        )

    monkeypatch.setattr(
        batch_execution.subprocess, "Popen", lambda *a, **k: HeldProcess()
    )
    monkeypatch.setattr(batch_execution, "ChildProvider", StageCountingChild)
    worker = threading.Thread(target=run, daemon=True)
    worker.start()
    try:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and not overlap_seen.is_set():
            time.sleep(0.01)
        overlapped = overlap_seen.is_set()
        observed_peak = peak[0]
        release.set()
        assert overlapped and observed_peak >= 2, (
            f"two stages never held requests at once (peak {observed_peak})"
        )
    finally:
        release.set()
        worker.join(30)

    assert not worker.is_alive()
    assert holder["result"].exit_code == 0
    assert sorted(request_stages) == ["desc", "json", "json"]
    assert all(
        outcome.disposition == "completed"
        for image in holder["result"].images
        for outcome in image.stages
    )


def test_unpollable_pipe_path_never_blocks_the_actor(tmp_path, monkeypatch):
    """Where pipes cannot be polled, neither write nor read may block the actor.

    The non-POSIX branch runs the whole exchange on a helper thread. A child
    that never answers must still end the call at its deadline, and the actor
    must never touch the pipe itself.
    """
    import image_clarus.batch_execution as batch

    stop_reader = threading.Event()

    class SilentStdout:
        """A reader that blocks until the test releases it, like a silent pipe.

        Closing it must not be required for boundedness: a real buffered stream
        cannot be closed while another thread is blocked inside it.
        """

        closed = False

        def read(self, size=-1):
            stop_reader.wait(30)
            return b""

        def fileno(self):
            return -1

        def close(self):
            return None

    class UnpollableProcess:
        def __init__(self):
            self.stdin = _Replier()
            self.stdout = SilentStdout()
            self.returncode = None
            self.killed = False
            self.reaped = False

        def poll(self):
            return None

        def wait(self, timeout=None):
            self.reaped = True
            return -9

        def kill(self):
            self.killed = True

    holder = {}

    def fake_popen(*_a, **_k):
        holder["process"] = UnpollableProcess()
        return holder["process"]

    monkeypatch.setattr(batch.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(ChildProvider, "_portable_io", lambda self: False)
    # The actor must not read the pipe directly on this path.
    monkeypatch.setattr(
        ChildProvider,
        "_read_exact",
        lambda self, stream, count: (_ for _ in ()).throw(
            AssertionError("the actor must not read the pipe directly here")
        ),
    )

    child = ChildProvider(None)
    elapsed = {}

    def run_call():
        started = time.monotonic()
        child.call(_child_request(tmp_path, timeout_seconds=0.05))
        elapsed["v"] = time.monotonic() - started

    # The request deadline includes the startup allowance; shorten it so the
    # test does not have to wait out the production value.
    allowance = 0.2
    child._startup_allowance = allowance
    caller = threading.Thread(target=run_call, daemon=True)
    caller.start()
    caller.join(allowance + 10)
    try:
        assert not caller.is_alive(), (
            "the actor thread was still inside the exchange after its deadline"
        )
        # Bounded by the deadline, not by the read ever returning.
        assert elapsed["v"] < allowance + 5.0
        assert holder["process"].killed is True
        assert holder["process"].reaped is True
    finally:
        stop_reader.set()


def test_disabled_concurrency_runs_image_first(tmp_path):
    images = _images(tmp_path, ["first.jpg", "second.jpg"])
    order = []

    def desc(image, *_args, **_kwargs):
        order.append(("desc", Path(image).name))
        return Terminal(StageResult("desc", "completed"))

    def json_stage(image, *_args, **_kwargs):
        order.append(("json", Path(image).name))
        return Terminal(StageResult("json", "completed"))

    stages = (_stage("desc", desc), _stage("json", json_stage))
    config = _config()
    plan = _plan(images, config, selected=("desc", "json"), stages=stages)

    result = run_sequential(plan, config, _services(), cwd=tmp_path / "cwd")

    assert result.exit_code == 0
    assert order == [
        ("desc", "first.jpg"),
        ("json", "first.jpg"),
        ("desc", "second.jpg"),
        ("json", "second.jpg"),
    ]


def test_sequential_accumulation_visible_to_next_image(tmp_path):
    images = _images(tmp_path, ["first.jpg", "second.jpg"])
    observations = []

    def desc(image, _config, services, **_kwargs):
        observations.append(
            (Path(image).name, dict(services.state.snapshot_categories()))
        )
        return Terminal(StageResult("desc", "completed"))

    stages = (_stage("desc", desc),)
    config = _config(state_directory=tmp_path / "collection")
    (tmp_path / "collection").mkdir()
    plan = _plan(images, config, stages=stages)

    run_sequential(plan, config, _services(), cwd=tmp_path / "collection")

    assert [name for name, _ in observations] == ["first.jpg", "second.jpg"]


@pytest.mark.parametrize(
    "policy,expect_second_stage,expect_exit",
    [("continue", True, 1), ("stop", False, 1), ("abort", False, 1)],
)
def test_failure_policy_while_another_stage_is_active(
    tmp_path, policy, expect_second_stage, expect_exit
):
    images = _images(tmp_path, ["failing.jpg", "other.jpg"])
    other_started = threading.Event()

    def desc(image, *_args, **_kwargs):
        if Path(image).name == "failing.jpg":
            other_started.wait(5)
            return Terminal(
                StageResult("desc", "failed", error_category="invalid_artifact")
            )
        other_started.set()
        time.sleep(0.02)
        return Terminal(StageResult("desc", "completed"))

    def json_stage(image, *_args, **_kwargs):
        return Terminal(StageResult("json", "completed"))

    stages = (_stage("desc", desc), _stage("json", json_stage))
    config = _config(policy=policy)
    plan = _plan(images, config, selected=("desc", "json"), stages=stages)

    result = run_concurrent(plan, config, _services(), cwd=tmp_path / "cwd")

    failing = result.images[0]
    assert failing.stages[0].disposition == "failed"
    assert (failing.stages[1].disposition == "completed") is expect_second_stage
    assert result.exit_code == expect_exit


def test_unselected_stages_are_never_invoked(tmp_path):
    images = _images(tmp_path, ["only.jpg"])
    invoked = []

    def desc(image, *_args, **_kwargs):
        invoked.append("desc")
        return Terminal(StageResult("desc", "completed"))

    stages = (_stage("desc", desc),)
    config = _config()
    plan = _plan(images, config, selected=("desc",), stages=stages)

    result = run_concurrent(plan, config, _services(), cwd=tmp_path / "cwd")

    assert result.exit_code == 0
    assert invoked == ["desc"]
    assert [outcome.stage for outcome in result.images[0].stages] == ["desc"]


def test_stop_closes_dispatch_and_reports_not_attempted(tmp_path):
    images = _images(tmp_path, ["first.jpg", "second.jpg"])
    stop = SimpleNamespace(signum=None, request=lambda signum: None)
    entered = threading.Event()

    def desc(image, *_args, **_kwargs):
        entered.set()
        stop.signum = 15
        return Terminal(StageResult("desc", "completed"))

    stages = (_stage("desc", desc),)
    config = _config()
    plan = _plan(images, config, stages=stages)
    events = []

    result = run_concurrent(
        plan,
        config,
        _services(),
        cwd=tmp_path / "cwd",
        stop=stop,
        on_event=events.append,
    )

    assert entered.is_set()
    assert result.interrupted_by == 15
    assert result.exit_code == 128 + 15
    dispositions = [
        outcome.disposition for image in result.images for outcome in image.stages
    ]
    assert "completed" not in [d for d in dispositions if d == "failed"]


def test_stop_before_execution_marks_selected_stages_not_attempted(tmp_path):
    images = _images(tmp_path, ["only.jpg"])
    stop = SimpleNamespace(signum=None, request=lambda signum: None)
    stop.signum = 2
    called = []
    stages = (_stage("desc", lambda image, *_a, **_k: called.append(image)),)
    config = _config()
    plan = _plan(images, config, stages=stages)

    result = run_concurrent(plan, config, _services(), cwd=tmp_path / "cwd", stop=stop)

    assert called == []
    # Stop was already in force when the batch began: no stage was attempted and
    # the image is reported interrupted by the signal, never completed.
    assert [o.disposition for o in result.images[0].stages] == ["interrupted"]
    assert result.images[0].stages[0].reason_code == "interrupted"
    assert result.exit_code == 128 + 2


def test_dispatch_closing_between_dequeue_and_execution_stays_locked(
    tmp_path, monkeypatch
):
    """Closing dispatch in that window must not touch the condition unlocked.

    If dispatch closes after an actor dequeues but before it runs the stage, the
    settlement path notifies on the coordinator condition. A stage actor runs
    outside that lock, so this raises `RuntimeError: cannot notify on
    un-acquired lock` and escapes as an internal batch failure.
    """
    images = _images(tmp_path, ["only.jpg"])

    def desc(_image, *_a, **_k):
        return Terminal(StageResult("desc", "completed"))

    stages = (_stage("desc", desc),)
    config = _config()
    plan = _plan(images, config, stages=stages)
    errors = []
    holder = {}

    class ProbeQueue:
        """A deque stand-in that closes dispatch immediately after a dequeue."""

        def __init__(self):
            self._items = []

        def __bool__(self):
            return bool(self._items)

        def __len__(self):
            return len(self._items)

        def append(self, item):
            self._items.append(item)

        def popleft(self):
            item = self._items.pop(0)
            coordinator = holder.get("coordinator")
            if coordinator is not None and not coordinator._closed:
                # Inside the actor's locked region: dispatch closes here.
                holder["during_dequeue"] = True
                coordinator._close_dispatch("stage_failure")
            return item

    class ClosingCoordinator(batch_execution._ConcurrentCoordinator):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            holder["coordinator"] = self
            # Replace only the stage queues; `_offer` stays the real one.
            self._queues = {name: ProbeQueue() for name in self.stage_names}

    # The actor is entered directly so this exercises exactly the dequeue
    # window rather than a race the scheduler usually hides.
    def run():
        coordinator = ClosingCoordinator(
            plan=plan,
            emitter=batch_execution._Emitter(None),
            stop=None,
            config=config,
            cwd=tmp_path / "cwd",
            memory_pool=batch_execution.MemoryStoragePool(),
            policy=config["pipeline"]["on_stage_failure"],
            gate=batch_execution.PublicationGate(),
            base_services=_services(),
            read_envelope=batch_execution._read_envelope,
            override=None,
        )
        coordinator.seed()
        try:
            # Dequeue happens here; dispatch is closed from inside it.
            coordinator._run_thread(0)
        except BaseException as error:  # noqa: BLE001 - escapes are the failure
            errors.append(error)

    worker = threading.Thread(target=run, daemon=True)
    worker.start()
    worker.join(30)

    assert not worker.is_alive()
    assert holder.get("during_dequeue"), "dispatch never closed mid-dequeue"
    assert not errors, f"an exception escaped the stage actor: {errors!r}"


def test_dequeued_later_stage_is_settled_after_prior_stage_completed(tmp_path):
    """A prior completed outcome does not erase later-actor ownership."""
    image = _images(tmp_path, ["only.jpg"])[0]
    stages = (
        _stage(
            "desc", lambda *_args, **_kwargs: Terminal(StageResult("desc", "completed"))
        ),
        _stage(
            "json", lambda *_args, **_kwargs: Terminal(StageResult("json", "completed"))
        ),
    )
    config = _config(policy="abort")
    plan = _plan([image], config, selected=("desc", "json"), stages=stages)
    coordinator = batch_execution._ConcurrentCoordinator(
        plan=plan,
        emitter=batch_execution._Emitter(None),
        stop=None,
        config=config,
        cwd=tmp_path / "cwd",
        memory_pool=batch_execution.MemoryStoragePool(),
        policy="abort",
        gate=batch_execution.PublicationGate(),
        base_services=_services(),
        read_envelope=batch_execution._read_envelope,
        override=None,
    )
    coordinator.seed()
    job = coordinator._jobs[0]
    with coordinator._condition:
        assert coordinator._queues["desc"].popleft() == job.image_id
        coordinator._queued.discard(job.image_id)
        coordinator._active.add(job.image_id)
    coordinator._process(job, 0)
    assert [outcome.stage for outcome in job.outcomes] == ["desc"]

    with coordinator._condition:
        assert coordinator._queues["json"].popleft() == job.image_id
        coordinator._queued.discard(job.image_id)
        coordinator._active.add(job.image_id)
        coordinator._close_dispatch("stage_failure")

    # The previous desc actor runs its finally block after JSON has dequeued the
    # image. It must not settle JSON's active ownership.
    coordinator._finish_if_interrupted(job, 0)
    assert job.image_id not in coordinator._finalized

    coordinator._finish_if_interrupted(job, 1)

    finalized = coordinator._finalized[job.image_id]
    assert [outcome.disposition for outcome in finalized.stages] == [
        "completed",
        "not_attempted",
    ]
    assert finalized.stages[1].reason_code == "batch_aborted"


def test_completed_transport_releases_stage_slot_before_waking_retry(monkeypatch):
    """A completed response may immediately submit its validation retry."""
    entered_set = threading.Event()
    allow_set_return = threading.Event()

    class GateEvent:
        def set(self):
            entered_set.set()
            allow_set_return.wait(10)

        def wait(self, _timeout=None):
            return entered_set.is_set()

    class ControlledPending:
        def __init__(self, image_id, request):
            self.image_id = image_id
            self.request = request
            self.result = None
            self.done = GateEvent()

    class ImmediateTransport:
        def call(self, request):
            return ProviderResult(request.request_id, content="valid")

    coordinator = object.__new__(batch_execution._ConcurrentCoordinator)
    coordinator._condition = threading.Condition()
    coordinator._stage_requests = {}
    coordinator._pending = {}
    coordinator._transport_threads = set()
    coordinator.stage_names = ("desc",)
    monkeypatch.setattr(batch_execution, "_PendingRequest", ControlledPending)
    job = SimpleNamespace(image_id=0)
    first_request = SimpleNamespace(request_id=("image", "desc", 0, "first"))
    retry_request = SimpleNamespace(request_id=("image", "desc", 1, "retry"))

    coordinator._submit(job, 0, ImmediateTransport(), first_request)
    try:
        assert entered_set.wait(5), "the first transport did not complete"
        # `done.set()` is deliberately held. The new request must still be
        # admitted because the completed request released the stage slot first.
        coordinator._submit(job, 0, ImmediateTransport(), retry_request)
    finally:
        allow_set_return.set()


def test_worker_exception_aborts_without_hiding_outcomes(tmp_path):
    images = _images(tmp_path, ["boom.jpg", "later.jpg"])

    def desc(image, *_args, **_kwargs):
        raise RuntimeError("synthetic failure")

    stages = (_stage("desc", desc),)
    config = _config(policy="continue")
    plan = _plan(images, config, stages=stages)
    events = []

    result = run_concurrent(
        plan, config, _services(), cwd=tmp_path / "cwd", on_event=events.append
    )

    assert result.exit_code == 1
    assert any(
        event.kind == "abort" and event.cause == "internal_error" for event in events
    )
    seen = {outcome.disposition for image in result.images for outcome in image.stages}
    # Nothing may be reported as successful, and the batch must say why it
    # stopped, but queued work may be honestly interrupted rather than "failed".
    assert "completed" not in seen
    assert {"failed", "not_attempted"} & seen


def test_empty_plan_terminates_without_stranding_actors(tmp_path):
    config = _config()
    plan = _plan([], config)

    result = run_concurrent(plan, config, _services(), cwd=tmp_path / "cwd")

    assert result.images == ()
    assert result.exit_code == 0


def test_blocked_publication_drains_before_stop_reports(tmp_path):
    """Shutdown waits for an already-admitted write, then admits no more."""
    image = _images(tmp_path, ["only.jpg"])[0]
    stop = SimpleNamespace(signum=None, request=lambda signum: None)
    entered = threading.Event()
    release = threading.Event()
    finished = threading.Event()
    observed = {}
    later = {}

    class BlockingArtifacts(ArtifactService):
        """The real artifact service, stalled inside one publication."""

        def write(self, *args, **kwargs):
            if not entered.is_set():
                entered.set()
                release.wait(10)
            # Sampled from inside the admitted write: this is the observation
            # that proves shutdown is waiting on a live publication.
            observed["protected_during_write"] = self._gate.protected
            return super().write(*args, **kwargs)

    def publish(image_path, _config, services, **_kwargs):
        # The coordinator wraps the service it hands to stages; that wrapper's
        # gate is the very gate the coordinator drains on shutdown.
        holder["gate"] = services.artifacts.gate
        holder["artifacts"]._gate = holder["gate"]
        # A genuine publication through the coordinator's own gate.
        services.artifacts.write(
            Path(str(image_path) + ".desc.txt"), b"description", lambda data: True
        )
        gate = services.artifacts.gate
        finished.set()
        # Stop is now in force: a later write must be refused, not published.
        later["admitted"] = gate.begin()
        later["sidecar"] = Path(str(image_path) + ".later.txt")
        if later["admitted"]:
            gate.end()
        return Terminal(StageResult("desc", "completed"))

    stages = (_stage("desc", publish),)
    config = _config()
    plan = _plan([image], config, stages=stages)
    artifacts = BlockingArtifacts()
    services = SimpleNamespace(
        artifacts=artifacts,
        provider_factory=lambda provider, model: None,
    )
    holder = {"artifacts": artifacts}

    def run():
        holder["result"] = run_concurrent(
            plan, config, services, cwd=tmp_path / "cwd", stop=stop, drain_timeout=10
        )

    worker = threading.Thread(target=run, daemon=True)
    worker.start()
    # The write is admitted and genuinely stalled inside publication.
    assert entered.wait(10), "publication never started"
    # Drive the real stop transition while it is in flight.
    stop.signum = 15
    holder["gate"].stop()
    release.set()
    worker.join(20)

    assert not worker.is_alive(), "shutdown did not complete"
    assert finished.is_set(), "the admitted write was abandoned by shutdown"
    # It was still protected while running, and drained before the batch ended.
    assert observed["protected_during_write"] == 1
    assert holder["gate"].protected == 0
    # The protected write really landed on disk.
    assert Path(str(image) + ".desc.txt").read_bytes() == b"description"
    # Subsequent writes were refused once stop held.
    assert later["admitted"] is False
    # The run reports interruption rather than a clean completion.
    assert holder["result"].exit_code == 128 + 15


def test_abort_refuses_publication_after_another_stage_inference(tmp_path, monkeypatch):
    """A batch abort closes publication admission before a held peer resumes."""
    from image_clarus.stage_protocol import Publish, Request
    from image_clarus.stage_registry import STAGES as real_stages

    held, failing = _images(tmp_path, ["held.jpg", "failing.jpg"])
    Path(str(failing) + ".desc.txt").write_text("existing", encoding="utf-8")
    request_started = threading.Event()
    release_request = threading.Event()
    json_failed = threading.Event()
    gate_holder = {}
    write_calls = []

    class RecordingArtifacts(ArtifactService):
        def write(self, *args, **kwargs):
            write_calls.append(args[0])
            return super().write(*args, **kwargs)

    class HeldChild(ChildProvider):
        def call(self, request):
            if held.name in request.request_id[0]:
                request_started.set()
                release_request.wait(10)
            return ProviderResult(request.request_id, content="valid")

    def desc_inspect(image, _config, services, **_kwargs):
        if image.name == failing.name:
            return Terminal(StageResult("desc", "completed"))
        gate_holder["gate"] = services.artifacts.gate
        context = SimpleNamespace(
            image=image,
            output=Path(str(image) + ".desc.txt"),
            validation_category="invalid_artifact",
        )
        return WorkRequired("desc", image, context)

    def desc_advance(context, result):
        if result is None:
            return Request(
                (str(context.image), "desc", 0, "held-request"),
                "image",
                {
                    "provider": {
                        "base_url": "http://127.0.0.1:9/v1",
                        "timeout_seconds": 5,
                    },
                    "model": {"provider": "local", "model_id": "synthetic"},
                    "arguments": {
                        "prompt": "p",
                        "image_bytes": b"x",
                        "suffix": ".jpg",
                        "effort": None,
                    },
                },
                context,
            )
        if isinstance(result, ProviderResult):
            return Publish(
                "held-publication", b"must-not-write", lambda data: True, context
            )
        return Terminal(StageResult("desc", "completed"))

    def json_inspect(image, *_args, **_kwargs):
        if image.name == failing.name:
            json_failed.set()
            return Terminal(
                StageResult("json", "failed", error_category="invalid_artifact")
            )
        return Terminal(StageResult("json", "completed"))

    stages = (
        _replace_predicates(
            SimpleNamespace(
                name="desc",
                uses_llm=True,
                predicted_output_exists=real_stages[0].predicted_output_exists,
                skip_if_valid_output_exists=True,
                inspect=desc_inspect,
                start_or_resume=desc_advance,
            ),
            real_stages[0],
        ),
        _replace_predicates(_stage("json", json_inspect), real_stages[1]),
    )
    config = _config(policy="abort")
    plan = _plan([held, failing], config, selected=("desc", "json"), stages=stages)
    services = SimpleNamespace(
        artifacts=RecordingArtifacts(), provider_factory=lambda *_args: None
    )
    monkeypatch.setattr(batch_execution, "ChildProvider", HeldChild)
    holder = {}
    worker = threading.Thread(
        target=lambda: holder.setdefault(
            "result", run_concurrent(plan, config, services, cwd=tmp_path / "cwd")
        ),
        daemon=True,
    )
    worker.start()
    try:
        assert request_started.wait(10), "the held inference did not start"
        assert json_failed.wait(10), "the peer stage did not fail"
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and not gate_holder["gate"].refusing:
            time.sleep(0.01)
        assert gate_holder["gate"].refusing, "abort left publication admission open"
        # The stage may abandon the request promptly, but the coordinator still
        # owns its transport thread and cannot return before that thread exits.
        time.sleep(0.15)
        assert worker.is_alive(), "batch returned while its provider transport was live"
        release_request.set()
        worker.join(20)
    finally:
        release_request.set()
        worker.join(20)

    assert not worker.is_alive()
    assert write_calls == []
    assert not Path(str(held) + ".desc.txt").exists()
    assert holder["result"].exit_code == 1


def test_admitted_publication_is_not_abandoned_by_shutdown(tmp_path):
    """Shutdown waits for a write that passed admission before stop.

    Separate from the drain assertion above: this checks *outcome* — the
    admitted write finishes and lands — rather than the gate's counter.
    """
    image = _images(tmp_path, ["only.jpg"])[0]
    stop = SimpleNamespace(signum=None, request=lambda signum: None)
    entered = threading.Event()
    release = threading.Event()

    class SlowArtifacts(ArtifactService):
        def write(self, *args, **kwargs):
            if not entered.is_set():
                entered.set()
                release.wait(10)
            return super().write(*args, **kwargs)

    def publish(image_path, _config, services, **_kwargs):
        services.artifacts.write(
            Path(str(image_path) + ".desc.txt"), b"admitted", lambda data: True
        )
        return Terminal(StageResult("desc", "completed"))

    stages = (_stage("desc", publish),)
    config = _config()
    plan = _plan([image], config, stages=stages)
    services = SimpleNamespace(
        artifacts=SlowArtifacts(), provider_factory=lambda provider, model: None
    )
    holder = {}

    def run():
        holder["result"] = run_concurrent(
            plan, config, services, cwd=tmp_path / "cwd", stop=stop, drain_timeout=10
        )

    worker = threading.Thread(target=run, daemon=True)
    worker.start()
    assert entered.wait(10)
    stop.signum = 15
    release.set()
    worker.join(20)

    assert not worker.is_alive()
    # The admitted write completed and its bytes are on disk.
    assert Path(str(image) + ".desc.txt").read_bytes() == b"admitted"
    assert holder["result"].exit_code == 128 + 15


def test_timed_out_publication_is_reported_but_drained_before_return(tmp_path):
    """A shutdown timeout is reported, but cannot abandon an admitted write."""
    image = _images(tmp_path, ["only.jpg"])[0]
    stop = SimpleNamespace(signum=None, request=lambda signum: None)
    entered = threading.Event()
    # Created unset: the write is still stalled when the drain deadline expires.
    stall = threading.Event()
    finished = threading.Event()

    class StalledArtifacts(ArtifactService):
        def write(self, *args, **kwargs):
            entered.set()
            # Stalled well past the drain deadline, so it cannot be drained.
            stall.wait(30)
            result = super().write(*args, **kwargs)
            finished.set()
            return result

    gate_holder = {}

    def publish(image_path, _config, services, **_kwargs):
        gate_holder["gate"] = services.artifacts.gate
        services.artifacts.write(
            Path(str(image_path) + ".desc.txt"), b"x", lambda data: True
        )
        return Terminal(StageResult("desc", "completed"))

    stages = (_stage("desc", publish),)
    config = _config()
    plan = _plan([image], config, stages=stages)
    services = SimpleNamespace(
        artifacts=StalledArtifacts(), provider_factory=lambda provider, model: None
    )
    holder = {}

    def run():
        holder["result"] = run_concurrent(
            plan,
            config,
            services,
            cwd=tmp_path / "cwd",
            stop=stop,
            drain_timeout=0.05,
        )

    worker = threading.Thread(target=run, daemon=True)
    worker.start()
    try:
        assert entered.wait(10), "the publication never started"
        # Close admission while the protected write remains stalled beyond the
        # responsiveness deadline. The run may record that timeout, but cannot
        # return ownership of the shared services until the write drains.
        gate_holder["gate"].stop()
        time.sleep(0.15)
        assert worker.is_alive(), "shutdown returned before its admitted write drained"
        assert not finished.is_set(), "the publication finished before release"
        stall.set()
        worker.join(30)
        assert not worker.is_alive(), "shutdown did not finish after drain"
        result = holder["result"]
        assert finished.is_set(), "the admitted publication was not cleaned up"
        assert Path(str(image) + ".desc.txt").read_bytes() == b"x"
        # A timed-out drain is still an unsuccessful batch, even after cleanup.
        assert result.exit_code != 0
        assert result.aborted is True
    finally:
        stall.set()
        worker.join(10)
        finished.wait(10)


def test_publication_refused_after_stop_is_not_completed(tmp_path):
    image = _images(tmp_path, ["only.jpg"])[0]
    stop = SimpleNamespace(signum=None, request=lambda signum: None)

    def stop_then_publish(image_path, _config, services, **_kwargs):
        stop.signum = 15
        services.artifacts.gate.stop()
        services.artifacts.write(
            Path(str(image_path) + ".desc.txt"), b"description", lambda data: True
        )
        return Terminal(StageResult("desc", "completed"))

    stages = (_stage("desc", stop_then_publish),)
    config = _config()
    plan = _plan([image], config, stages=stages)

    result = run_concurrent(plan, config, _services(), cwd=tmp_path / "cwd", stop=stop)

    assert result.exit_code == 128 + 15
    # The stage reached publication but was refused admission; it is interrupted,
    # never reported as completed, and the sidecar is untouched.
    assert [o.disposition for o in result.images[0].stages] == ["interrupted"]
    assert not Path(str(image) + ".desc.txt").exists()


def test_gated_recovery_failure_is_visible():
    gate = PublicationGate()
    artifacts = batch_execution.GatedArtifacts(
        SimpleNamespace(
            recover=lambda *a, **k: (_ for _ in ()).throw(ArtifactError("file_io")),
            write=lambda *a, **k: None,
        ),
        gate,
    )
    with pytest.raises(ArtifactError):
        artifacts.recover(Path("sidecar.json"), lambda data: True)
    gate.stop()
    with pytest.raises(batch_execution.PublicationRefused):
        artifacts.recover(Path("sidecar.json"), lambda data: True)


# -- provider child ------------------------------------------------------


def _child_request(tmp_path, **provider):
    provider.update({"base_url": "http://127.0.0.1:9/v1"})
    payload = {
        "provider": provider,
        "model": {"provider": "local", "model_id": "synthetic-model"},
        "operation": "structured",
        "arguments": {
            "prompt": "Summarize.",
            "description": "A synthetic scene.",
            "schema": {"type": "object"},
            "effort": None,
            "history": [],
        },
    }
    from image_clarus.stage_protocol import Request

    return Request(("image", "json", 0, "nonce"), "structured", payload, None)


@pytest.mark.parametrize(
    "provider,factory,expected",
    [
        ({"timeout_seconds": 5}, None, "provider_unavailable"),
        ({"timeout_seconds": -1}, None, "configuration"),
    ],
)
def test_child_reports_sanitized_categories(tmp_path, provider, factory, expected):
    stopper = SimpleNamespace(signum=None, request=lambda signum: None)
    child = ChildProvider(stopper)
    request = _child_request(tmp_path, **provider)
    try:
        result = child.call(request)
    finally:
        child.terminate()
    assert isinstance(result, ProviderResult)
    assert result.request_id == request.request_id
    assert result.error_category == expected
    assert result.content is None


def test_child_start_failure_is_sanitized(tmp_path, monkeypatch):
    def refuse(*_args, **_kwargs):
        raise OSError("synthetic spawn failure")

    monkeypatch.setattr(batch_execution.subprocess, "Popen", refuse)
    child = ChildProvider(None)
    result = child.call(_child_request(tmp_path, timeout_seconds=1))
    assert result.error_category == "provider_unavailable"


def test_child_malformed_frame_is_sanitized(tmp_path, monkeypatch):
    class FakeStream:
        """A pipe whose only content is one unreadable byte."""

        def __init__(self, reply=b"\x00"):
            self._fd = os.open(os.devnull, os.O_RDONLY)
            self.reply = reply
            self.closed = False

        def write(self, _data):
            return len(_data)

        def flush(self):
            return None

        def read(self, size=-1):
            return self.reply

        def fileno(self):
            return self._fd

        def close(self):
            if not self.closed:
                self.closed = True
                os.close(self._fd)

    class FakeProcess:
        def __init__(self):
            self.stdin = FakeStream()
            self.stdout = FakeStream()
            self.returncode = 0

        def poll(self):
            return 0

        def wait(self, timeout=None):
            return 0

        def kill(self):
            return None

    monkeypatch.setattr(
        batch_execution.subprocess, "Popen", lambda *a, **k: FakeProcess()
    )
    child = ChildProvider(None)
    result = child.call(_child_request(tmp_path, timeout_seconds=1))
    assert result.error_category == "provider_unavailable"


def test_child_credentials_never_appear_in_argv(tmp_path, monkeypatch):
    captured = {}

    class FakeStream:
        """Records whatever the parent writes; reads return end-of-file."""

        def __init__(self):
            self.payload = bytearray()
            self._fd = os.open(os.devnull, os.O_RDONLY)
            self.closed = False

        def write(self, data):
            self.payload.extend(data)

        def flush(self):
            return None

        def read(self, size=-1):
            return b""

        def fileno(self):
            return self._fd

        def close(self):
            if not self.closed:
                self.closed = True
                os.close(self._fd)

    class FakeProcess:
        def __init__(self, *args, **kwargs):
            captured["argv"] = kwargs.get("argv") or args
            self.stdin = FakeStream()
            self.stdout = FakeStream()
            self.returncode = 1

        def poll(self):
            return 1

        def wait(self, timeout=None):
            return 1

        def kill(self):
            return None

    monkeypatch.setattr(
        batch_execution.subprocess,
        "Popen",
        lambda argv, **kwargs: FakeProcess(argv, **kwargs),
    )
    secret = "private-synthetic-credential"
    child = ChildProvider(None)
    result = child.call(_child_request(tmp_path, timeout_seconds=1, api_key=secret))
    assert result.error_category == "provider_unavailable"
    flattened = " ".join(str(part) for part in captured["argv"])
    assert secret not in flattened


class FakeStream:
    """Minimal framed stream: writes are discarded, reads return the reply."""

    def __init__(self, reply=b""):
        self.reply = reply
        self.closed = False
        self._fd = os.open(os.devnull, os.O_RDONLY)

    def write(self, data):
        return len(data)

    def flush(self):
        return None

    def read(self, size=-1):
        payload, self.reply = self.reply, b""
        return payload

    def fileno(self):
        return self._fd

    def close(self):
        if not self.closed:
            self.closed = True
            os.close(self._fd)


def test_child_rechecks_stop_after_registration(tmp_path, monkeypatch):
    spawned = []

    class FakeProcess:
        def __init__(self):
            self.stdin = FakeStream()
            self.stdout = FakeStream()
            self.returncode = -15

        def poll(self):
            return None

        def wait(self, timeout=None):
            return -15

        def kill(self):
            spawned.append("killed")

    class Stopper:
        signum = None

        def request(self, signum):
            self.signum = signum

    stopper = Stopper()

    def launch(*_args, **_kwargs):
        stopper.signum = 15
        return FakeProcess()

    monkeypatch.setattr(batch_execution.subprocess, "Popen", launch)
    child = ChildProvider(stopper)
    result = child.call(_child_request(tmp_path, timeout_seconds=1))
    assert result.error_category == "interrupted"
    assert spawned == ["killed"]


def test_child_reaps_late_spawn_after_batch_cancellation(tmp_path, monkeypatch):
    """Cancellation during Popen still owns and reaps the late child."""
    spawn_started = threading.Event()
    allow_spawn = threading.Event()
    cancelled = threading.Event()
    killed = []
    reaped = []

    class LateProcess:
        def __init__(self):
            self.stdin = FakeStream()
            self.stdout = FakeStream()
            self.returncode = None

        def poll(self):
            return None

        def kill(self):
            killed.append(True)

        def wait(self, timeout=None):
            reaped.append(True)
            return -9

    process = LateProcess()

    def launch(*_args, **_kwargs):
        spawn_started.set()
        allow_spawn.wait(10)
        return process

    monkeypatch.setattr(batch_execution.subprocess, "Popen", launch)
    child = ChildProvider(None, cancelled=cancelled.is_set)
    holder = {}
    worker = threading.Thread(
        target=lambda: holder.setdefault(
            "result", child.call(_child_request(tmp_path, timeout_seconds=1))
        ),
        daemon=True,
    )
    worker.start()
    try:
        assert spawn_started.wait(5), "the transport did not enter child creation"
        cancelled.set()
        # This mirrors coordinator abort before the child is registered.
        child.terminate()
        allow_spawn.set()
        worker.join(10)
    finally:
        allow_spawn.set()
        worker.join(10)

    assert not worker.is_alive()
    assert holder["result"].error_category == "interrupted"
    assert killed == [True]
    assert reaped == [True]


def test_sequential_and_concurrent_agree_on_terminal_dispositions(tmp_path):
    images = _images(tmp_path, ["one.jpg", "two.jpg"])

    def make_order():
        return []

    def build(order):
        def desc(image, *_args, **_kwargs):
            order.append((Path(image).name, "desc"))
            return Terminal(StageResult("desc", "completed"))

        def json_stage(image, *_args, **_kwargs):
            order.append((Path(image).name, "json"))
            return Terminal(StageResult("json", "completed"))

        return (_stage("desc", desc), _stage("json", json_stage))

    config = _config()
    sequential_order = make_order()
    sequential = run_sequential(
        _plan(
            images, config, selected=("desc", "json"), stages=build(sequential_order)
        ),
        config,
        _services(),
        cwd=tmp_path / "cwd",
    )
    concurrent_order = make_order()
    concurrent = run_concurrent(
        _plan(
            images, config, selected=("desc", "json"), stages=build(concurrent_order)
        ),
        config,
        _services(),
        cwd=tmp_path / "cwd",
    )

    def dispositions(result):
        return [
            (
                Path(image.image_path).name,
                [(o.stage, o.disposition) for o in image.stages],
            )
            for image in result.images
        ]

    assert dispositions(sequential) == dispositions(concurrent)
    assert sequential.exit_code == concurrent.exit_code == 0
    assert set(sequential_order) == set(concurrent_order)


# -- corrected and additional B5 evidence --------------------------------


def test_stage_actors_own_their_stages_and_overlap_in_activity(tmp_path):
    """Two different stages are simultaneously active, each on its own actor."""
    images = _images(tmp_path, ["first.jpg", "second.jpg"])
    observed_stages = SimpleNamespace(desc=set(), json=set())
    active = {}
    lock = threading.Lock()
    simultaneous = threading.Event()
    names = {}
    order = []

    def make(stage):
        def run(image, *_args, **_kwargs):
            key = Path(image).name
            # A stage actor may only ever run its own stage.
            getattr(observed_stages, stage).add(stage)
            with lock:
                active[stage] = active.get(stage, 0) + 1
                names.setdefault(stage, set()).add(threading.current_thread().name)
                order.append((stage, key))
                others = [
                    other
                    for other, count in active.items()
                    if other != stage and count > 0
                ]
                if others:
                    simultaneous.set()
            try:
                # Hold briefly so the other stage can enter, but never depend on
                # it: a sequential executor must still finish.
                deadline = time.monotonic() + 2.0
                while not simultaneous.is_set() and time.monotonic() < deadline:
                    time.sleep(0.005)
            finally:
                with lock:
                    active[stage] -= 1
            return Terminal(StageResult(stage, "completed"))

        return run

    stages = (
        _stage("desc", make("desc")),
        _stage("json", make("json")),
    )
    config = _config()
    plan = _plan(images, config, selected=("desc", "json"), stages=stages)

    result = run_concurrent(plan, config, _services(), cwd=tmp_path / "cwd")

    assert result.exit_code == 0, result.images
    # Real simultaneity: a description and a JSON operation were in flight at
    # the same instant, which a sequential executor can never produce.
    assert simultaneous.is_set()
    # And each stage's work happened only on that stage's own actor thread:
    # no actor ever executes another stage's decision.
    assert names["desc"] == {"image-clarus-stage-desc"}
    assert names["json"] == {"image-clarus-stage-json"}
    assert observed_stages.desc == {"desc"}
    assert observed_stages.json == {"json"}
    assert ("desc", "second.jpg") in order or ("desc", "first.jpg") in order


def _replace_predicates(stage, real):
    stage.predicted_output_exists = real.predicted_output_exists
    stage.skip_if_valid_output_exists = real.skip_if_valid_output_exists
    return stage


class _RecordedInspect:
    """Records every inspection per image and stage, in order."""

    def __init__(self, results):
        self.calls = []
        self._results = results
        self._lock = threading.Lock()

    def __call__(self, image, _config, _services, **_kwargs):
        key = Path(image).name
        with self._lock:
            self.calls.append(key)
        return Terminal(StageResult(self._results, "completed"))


def test_bypassed_stage_is_still_confirmed_authoritatively(tmp_path):
    """A predicted bypass is confirmed by its own stage, never merely assumed."""
    image = _images(tmp_path, ["only.jpg"])[0]
    (tmp_path / "only.jpg.desc.txt").write_text("existing", encoding="utf-8")
    desc_calls = _RecordedInspect("desc")
    json_calls = _RecordedInspect("json")
    # Real descriptors: their metadata predicate sees the existing sidecar, so
    # planning records a predicted bypass for description.
    stages = (
        _stage("desc", desc_calls),
        _stage("json", json_calls),
    )
    stages = (
        _replace_predicates(stages[0], STAGES[0]),
        _replace_predicates(stages[1], STAGES[1]),
    )
    config = _config()
    plan = _plan([image], config, selected=("desc", "json"), stages=stages)
    assert plan.rows[0][3] & 1, "test premise: description is predicted bypassed"

    result = run_concurrent(plan, config, _services(), cwd=tmp_path / "cwd")

    # The description was predicted present but only the stage itself can say
    # so; exactly one authoritative confirmation ran.
    assert desc_calls.calls == ["only.jpg"]
    assert json_calls.calls == ["only.jpg"]
    assert [o.stage for o in result.images[0].stages] == ["desc", "json"]
    assert all(o.disposition == "completed" for o in result.images[0].stages)


def test_bypass_confirmation_failure_is_not_skipped_over(tmp_path):
    """An existing sidecar is confirmed by description's own inspection."""
    image = _images(tmp_path, ["only.jpg"])[0]
    (tmp_path / "only.jpg.desc.txt").write_bytes(b"   \n")
    desc_calls = _RecordedInspect("desc")
    json_calls = _RecordedInspect("json")
    stages = (
        _replace_predicates(_stage("desc", desc_calls), STAGES[0]),
        _stage("json", json_calls),
    )
    config = _config(policy="stop")
    plan = _plan([image], config, selected=("desc", "json"), stages=stages)
    assert plan.rows[0][3] & 1, "test premise: description is predicted bypassed"

    result = run_concurrent(plan, config, _services(), cwd=tmp_path / "cwd")

    # The authoritative check ran on the owning actor rather than being assumed
    # from metadata, and its outcome is what the image reports.
    assert desc_calls.calls == ["only.jpg"]
    assert [o.stage for o in result.images[0].stages] == ["desc", "json"]
    assert result.images[0].stages[0].disposition == "completed"


def test_unconfirmed_prerequisite_is_authoritatively_checked_before_downstream(
    tmp_path,
):
    """A blank sidecar must not let JSON run before description confirms it.

    The description stage is routed *directly* to JSON by planning, and its own
    inspection then rejects the existing sidecar under `on_stage_failure=stop`.
    JSON must never execute, and the description's failure is what is reported.
    """
    image = _images(tmp_path, ["only.jpg"])[0]
    (tmp_path / "only.jpg.desc.txt").write_text("   \n", encoding="utf-8")
    order = []
    lock = threading.Lock()

    def desc_inspect(thumb, _config, _services, **_kwargs):
        with lock:
            order.append("desc")
        # The real description stage inspects the sidecar and rejects it.
        return Terminal(
            StageResult("desc", "failed", error_category="invalid_artifact")
        )

    def json_inspect(thumb, _config, _services, **_kwargs):
        with lock:
            order.append("json")
        return Terminal(StageResult("json", "completed"))

    stages = (
        _replace_predicates(_stage("desc", desc_inspect), STAGES[0]),
        _replace_predicates(_stage("json", json_inspect), STAGES[1]),
    )
    config = _config(policy="stop")
    plan = _plan([image], config, selected=("desc", "json"), stages=stages)
    assert plan.rows[0][3] & 1, "test premise: description is predicted bypassed"
    assert plan.rows[0][3] & 2 == 0, "test premise: JSON is the predicted target"

    result = run_concurrent(plan, config, _services(), cwd=tmp_path / "cwd")

    assert order == ["desc"], "JSON executed before description confirmed"
    assert result.images[0].stages[0].disposition == "failed"
    assert result.images[0].stages[1].disposition == "not_attempted"
    assert result.exit_code == 1


class _Replier:
    """A pipe stand-in: writes are swallowed, reads are a one-shot FIFO."""

    def __init__(self, buffer=b""):
        self.closed = False
        self._buffer = buffer
        # Its own descriptor: closing the child's stdin must not disturb stdout.
        self._fd = os.open(os.devnull, os.O_RDONLY)

    def write(self, data):
        return len(data)

    def flush(self):
        return None

    def read(self, size=-1):
        if size is None or size < 0:
            size = len(self._buffer)
        chunk, self._buffer = self._buffer[:size], self._buffer[size:]
        return chunk

    def fileno(self):
        return self._fd

    def close(self):
        if not self.closed:
            self.closed = True
            os.close(self._fd)


class _PipeOut:
    """A real anonymous pipe pre-loaded with one encoded reply."""

    def __init__(self, payload: bytes):
        read_fd, write_fd = os.pipe()
        os.write(write_fd, payload)
        os.close(write_fd)
        self._fd = read_fd
        self.closed = False

    def write(self, data):
        return len(data)

    def flush(self):
        return None

    def read(self, size=-1):
        return b""

    def fileno(self):
        return self._fd

    def close(self):
        if not self.closed:
            self.closed = True
            os.close(self._fd)


def test_vision_request_crosses_the_child_boundary(tmp_path, monkeypatch):
    """A description request carries real image bytes through the wire codec."""
    from image_clarus.provider_frame import decode_frame, encode_frame
    from image_clarus.stage_protocol import Request

    frames = {}
    argv_seen = []

    class Stdin:
        """A real pipe the parent writes into; the test reads the far end."""

        def __init__(self):
            self._fd, write_fd = os.pipe()
            self._write_fd = write_fd
            self._closed = False
            self._reader = threading.Thread(target=self._drain, daemon=True)
            self._reader.start()

        def _drain(self):
            buffer = b""
            while True:
                chunk = os.read(self._fd, 65536)
                if not chunk:
                    break
                buffer += chunk
            frames["data"] = buffer
            if len(buffer) >= 4:
                size = int.from_bytes(buffer[:4], "big")
                if len(buffer) - 4 == size:
                    frames["decoded"] = decode_frame(buffer)

        def write(self, data):
            return os.write(self._write_fd, data)

        def flush(self):
            return None

        def fileno(self):
            # The parent writes through this descriptor; the drain thread reads
            # the other end.
            return self._write_fd

        @property
        def closed(self):
            return self._closed

        def close(self):
            if not self._closed:
                self._closed = True
                os.close(self._write_fd)

    class Process:
        def __init__(self):
            self.stdin = Stdin()
            frames["stdin"] = self.stdin
            self.stdout = _PipeOut(
                encode_frame({"category": None, "content": "synthetic description"})
            )
            self.returncode = 0

        def poll(self):
            return 0

        def wait(self, timeout=None):
            return 0

        def kill(self):
            return None

    def fake_popen(argv, **kwargs):
        argv_seen.extend(argv)
        return Process()

    monkeypatch.setattr(batch_execution.subprocess, "Popen", fake_popen)
    image_bytes = b"\x89PNG\r\n\x1a\n\x00\xff\xfe binary"
    payload = {
        "provider": {"base_url": "http://127.0.0.1:9/v1", "timeout_seconds": 5},
        "model": {"provider": "local", "model_id": "synthetic-vision"},
        "operation": "image",
        "arguments": {
            "prompt": "Describe.",
            "image_bytes": image_bytes,
            "suffix": ".png",
            "effort": None,
        },
    }
    request = Request(("image", "desc", 0, "nonce"), "image", payload, None)

    result = ChildProvider(None).call(request)
    process_stdin = frames.get("stdin")
    if process_stdin is not None:
        process_stdin._reader.join(5)

    # Binary image bytes crossed the wire unchanged; JSON could not carry them.
    sent = frames["decoded"]["payload"]
    assert sent["operation"] == "image"
    assert sent["arguments"]["image_bytes"] == image_bytes
    assert result.content == "synthetic description"
    assert result.error_category is None
    assert "provider_worker" in " ".join(argv_seen)


REAL_SELECT = batch_execution.select.select


def test_held_child_is_timed_out_and_reaped(tmp_path, monkeypatch):
    """A child that never answers is terminated at the deadline, classified once."""
    reaped = []
    killed = []

    class HungProcess:
        def __init__(self):
            self.stdin = _Replier()
            self.stdout = _Replier()
            self.returncode = None

        def poll(self):
            return None

        def wait(self, timeout=None):
            reaped.append(True)
            return -9

        def kill(self):
            killed.append(True)

    monkeypatch.setattr(
        batch_execution.subprocess, "Popen", lambda *a, **k: HungProcess()
    )
    # The child accepted the request and never answers: the pipe stays open and
    # empty, so the reader must stop at its deadline rather than block forever.
    monkeypatch.setattr(
        batch_execution.select, "select", lambda r, w, x, timeout: ([], [], [])
    )
    child = ChildProvider(None)
    started = time.monotonic()
    result = child.call(_child_request(tmp_path, timeout_seconds=0.05))
    elapsed = time.monotonic() - started

    assert result.error_category == "network_timeout"
    # Reaped, not orphaned: a stalled child is always terminated.
    assert killed == [True]
    assert reaped == [True]
    # Bounded by the request deadline (plus the fixed startup allowance), not a
    # fixed long default and not an unbounded wait.
    assert elapsed < 60.0

    # A child that dies without answering is a provider failure, not a timeout.
    # The real selector is restored so end-of-file is observed, not a fake stall.
    monkeypatch.setattr(batch_execution.select, "select", REAL_SELECT)
    monkeypatch.setattr(
        batch_execution.subprocess,
        "Popen",
        lambda *a, **k: DeadProcess([]),
    )
    child = ChildProvider(None)
    dead = child.call(_child_request(tmp_path, timeout_seconds=5))
    assert dead.error_category == "provider_unavailable"


class DeadProcess:
    """A child whose reply pipe is already at end-of-file."""

    def __init__(self, reaped):
        self.stdin = _Replier()
        read_fd, write_fd = os.pipe()
        os.close(write_fd)  # nothing will ever be written
        self.stdout = _Replier()
        self.stdout._fd = read_fd
        self.returncode = 1
        self._reaped = reaped

    def poll(self):
        return 1

    def wait(self, timeout=None):
        self._reaped.append(True)
        return 1

    def kill(self):
        return None


def test_child_that_never_reads_its_request_is_a_timeout(tmp_path, monkeypatch):
    """Writing must be deadline-bounded too, not just reading the reply."""

    class StuckStdin:
        """A pipe whose reader never drains it and never closes."""

        def __init__(self):
            self._fd = os.open(os.devnull, os.O_WRONLY)
            self.closed = False

        def write(self, data):
            raise AssertionError("the blocking stream write must not be used")

        def flush(self):
            return None

        def fileno(self):
            return self._fd

        def close(self):
            if not self.closed:
                self.closed = True
                os.close(self._fd)

    killed = []
    reaped = []

    class StuckProcess:
        def __init__(self):
            self.stdin = StuckStdin()
            self.stdout = _Replier()
            self.returncode = None

        def poll(self):
            return None

        def wait(self, timeout=None):
            reaped.append(True)
            return -9

        def kill(self):
            killed.append(True)

    monkeypatch.setattr(
        batch_execution.subprocess, "Popen", lambda *a, **k: StuckProcess()
    )
    # The write side is never ready: the child stopped consuming its input.
    monkeypatch.setattr(
        batch_execution.select, "select", lambda r, w, x, timeout: ([], [], [])
    )
    child = ChildProvider(None)
    started = time.monotonic()
    result = child.call(_child_request(tmp_path, timeout_seconds=0.05))
    elapsed = time.monotonic() - started

    assert result.error_category == "network_timeout"
    assert killed == [True]
    assert reaped == [True]
    assert elapsed < 60.0


def test_write_all_makes_a_partially_writable_pipe_nonblocking(tmp_path, monkeypatch):
    """Partial readiness cannot turn a frame write into a blocking syscall."""
    read_fd, write_fd = os.pipe()
    os.set_blocking(write_fd, False)
    try:
        while True:
            os.write(write_fd, b"x" * 4096)
    except BlockingIOError:
        pass
    # Make the write end ready while keeping it blocking: the old implementation
    # could enter a blocking large os.write at precisely this point.
    os.read(read_fd, 4096)
    os.set_blocking(write_fd, True)

    class PartlyWritablePipe:
        def fileno(self):
            return write_fd

    observed = []

    def writable(_read, _write, _error, _timeout):
        return [], [PartlyWritablePipe()], []

    def assert_nonblocking(fd, data):
        observed.append(os.get_blocking(fd))
        raise BlockingIOError

    monkeypatch.setattr(batch_execution.select, "select", writable)
    monkeypatch.setattr(batch_execution.os, "write", assert_nonblocking)
    child = ChildProvider(None)
    child._deadline = time.monotonic() + 0.05
    try:
        assert child._write_all(PartlyWritablePipe(), b"y" * (8 * 1024 * 1024)) is False
    finally:
        os.close(write_fd)
        os.close(read_fd)

    assert observed
    assert observed == [False] * len(observed)


def test_real_full_pipe_bounds_a_large_request(tmp_path):
    """A real, undrained pipe cannot hold a large request past its deadline.

    No selector is mocked. The pipe is a genuine OS pipe filled to capacity and
    never read, so the write cannot complete and only the deadline can end it.
    """
    read_fd, write_fd = os.pipe()
    os.set_blocking(write_fd, False)
    try:
        while True:
            os.write(write_fd, b"x" * 4096)
    except BlockingIOError:
        pass
    os.set_blocking(write_fd, True)

    class FullPipe:
        closed = False

        def fileno(self):
            return write_fd

    child = ChildProvider(None)
    child._deadline = time.monotonic() + 0.2
    try:
        started = time.monotonic()
        # Far larger than the pipe can absorb.
        written = child._write_all(FullPipe(), b"y" * (8 * 1024 * 1024))
        elapsed = time.monotonic() - started
    finally:
        os.close(write_fd)
        os.close(read_fd)

    assert written is False
    assert child._exhausted is True
    # Bounded by the deadline, not by the pipe ever draining.
    assert elapsed < 5.0


def test_malformed_child_reply_is_sanitized_not_fatal(tmp_path, monkeypatch):
    """Undecodable text and junk frames become provider_unavailable.

    Decoding happens inside `ChildProvider.call`, so any codec fault must be a
    sanitized category: an escaping UnicodeDecodeError would reach the stage
    actor and be reported as an internal batch failure instead.
    """
    from image_clarus.provider_frame import _LEN, _STR, FrameError, decode_frame

    class Process:
        def __init__(self, payload):
            self.stdin = _Replier()
            self.stdout = _PipeOut(payload)
            self.returncode = 0

        def poll(self):
            return 0

        def wait(self, timeout=None):
            return 0

        def kill(self):
            return None

    def body_frame(*parts):
        body = b"".join(parts)
        return len(body).to_bytes(4, "big") + body

    bad_utf8 = body_frame(_STR + _LEN.pack(4), b"\xff\xfe\xfd\xfc")
    bad_key = body_frame(
        b"m",
        _LEN.pack(1),
        _STR + _LEN.pack(3),
        b"\xff\xfe\xfd",
        _STR + _LEN.pack(1),
        b"v",
    )
    cases = [
        ("undecodable content", bad_utf8),
        ("undecodable map key", bad_key),
        ("junk tag", body_frame(b"junk")),
        ("non-map body", b"\x00\x00\x00\x04junk"),
        ("truncated header", b"\x00\x00"),
    ]
    for _label, payload in cases:
        # The codec must reject these as frame faults, never as codec errors.
        with pytest.raises(FrameError):
            decode_frame(payload)

    for label, payload in cases:
        monkeypatch.setattr(
            batch_execution.subprocess,
            "Popen",
            lambda *a, _p=payload, **k: Process(_p),
        )
        result = ChildProvider(None).call(_child_request(tmp_path, timeout_seconds=5))
        assert result.error_category == "provider_unavailable", label
        assert result.content is None, label


def test_unadmitted_publication_never_cleans_up_the_original(tmp_path):
    """A refused write is a no-op on disk, even with backups retained.

    Admission is refused before any recovery or cleanup, so stop must never
    leave the destination's backup consumed without a replacement in place.
    """
    from image_clarus.artifacts import ArtifactService as RealArtifacts

    image = _images(tmp_path, ["only.jpg"])[0]
    sidecar = Path(str(image) + ".desc.txt")
    sidecar.write_bytes(b"original-bytes")
    stop = SimpleNamespace(signum=None, request=lambda signum: None)
    gate = PublicationGate(stop)
    real = RealArtifacts(retention="retain")
    gated = batch_execution.GatedArtifacts(real, gate)

    # Admitted normally: the write lands and the original is backed up.
    gated.write(sidecar, b"replacement", lambda data: True)
    assert sidecar.read_bytes() == b"replacement"

    # Now stop holds: admission is refused and nothing on disk changes.
    gate.stop()
    with pytest.raises(batch_execution.PublicationRefused):
        gated.write(sidecar, b"must-not-land", lambda data: True)
    assert sidecar.read_bytes() == b"replacement"
    # The retained backup still exists and still holds the original bytes.
    backups = sorted(sidecar.parent.iterdir())
    originals = [p for p in backups if p.read_bytes() == b"original-bytes"]
    assert originals, f"no retained original among {[p.name for p in backups]}"
    assert not any(b"must-not-land" in p.read_bytes() for p in backups if p.is_file())


def test_worker_reports_no_debug_output(monkeypatch):
    """The child stays silent on stderr even when the request is unreadable."""
    from image_clarus import provider_worker

    class Broken:
        def read(self, size=-1):
            raise ValueError("synthetic")

    class Out:
        def write(self, data):
            raise AssertionError("nothing should be written")

        def flush(self):
            return None

    captured = []

    class Stderr:
        def write(self, text):
            captured.append(text)

        def flush(self):
            return None

    monkeypatch.setattr(provider_worker.sys, "stderr", Stderr())
    assert provider_worker.main(Broken(), Out()) == 1
    assert captured == []


def test_aborted_queued_work_is_not_attempted_not_interrupted(tmp_path):
    """An abort is not a signal: untouched work is not_attempted/batch_aborted.

    Several images are queued on one stage actor; the first to run fails and
    aborts the batch, so the rest are dropped without ever starting.
    """
    images = _images(tmp_path, ["boom.jpg", "queued-a.jpg", "queued-b.jpg"])
    started = []
    stop = SimpleNamespace(signum=None, request=lambda signum: None)

    def desc(image, *_args, **_kwargs):
        started.append(Path(image).name)
        if Path(image).name == "boom.jpg":
            return Terminal(
                StageResult("desc", "failed", error_category="invalid_artifact")
            )
        return Terminal(StageResult("desc", "completed"))

    stages = (_stage("desc", desc),)
    # Abort by stage failure; independently, an unrelated image is also queued.
    config = _config(policy="abort")
    plan = _plan(images, config, stages=stages)

    result = run_concurrent(plan, config, _services(), cwd=tmp_path / "cwd", stop=stop)

    reasons = {
        (Path(image.image_path).name, o.disposition, o.reason_code)
        for image in result.images
        for o in image.stages
    }
    assert reasons == {
        ("boom.jpg", "failed", None),
        ("queued-a.jpg", "not_attempted", "batch_aborted"),
        ("queued-b.jpg", "not_attempted", "batch_aborted"),
    }, reasons
    assert result.exit_code == 1


def test_events_are_unique_and_ordered_under_concurrency(tmp_path):
    """Sequence numbers and observer calls stay serialized across actors."""
    images = _images(tmp_path, [f"{index}.jpg" for index in range(6)])
    stages = (
        _stage(
            "desc", lambda image, *_a, **_k: Terminal(StageResult("desc", "completed"))
        ),
        _stage(
            "json", lambda image, *_a, **_k: Terminal(StageResult("json", "completed"))
        ),
    )
    config = _config()
    plan = _plan(images, config, selected=("desc", "json"), stages=stages)
    events = []

    result = run_concurrent(
        plan, config, _services(), cwd=tmp_path / "cwd", on_event=events.append
    )

    assert result.exit_code == 0
    sequences = [event.sequence for event in events]
    assert sequences == list(range(len(events)))
    assert len({event.invocation_id for event in events}) == 1
    # Every stage terminal is present exactly once per image and stage.
    terminals = [
        (event.image_id, event.stage)
        for event in events
        if event.kind == "stage_terminal"
    ]
    assert len(terminals) == len(set(terminals))
    assert len(terminals) == 12

    # Directly hammered from many threads, the channel still yields each
    # sequence number once and never calls the observer concurrently.
    emitter_events = []
    in_sink = []
    overlapping = []

    def sink(event):
        in_sink.append(1)
        if len(in_sink) > 1:
            overlapping.append(event.sequence)
        time.sleep(0)
        in_sink.pop()
        emitter_events.append(event)

    emitter = batch_execution._Emitter(sink)

    def hammer():
        for _ in range(200):
            emitter.emit("probe")

    threads = [threading.Thread(target=hammer) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert emitter_events, "no events recorded"
    assert not overlapping, "observer entered concurrently"
    assert sorted(e.sequence for e in emitter_events) == list(
        range(len(emitter_events))
    )


def test_publication_refusal_does_not_wait_on_the_gate(tmp_path):
    """The gate is held only for admission: stop linearizes while a write runs."""
    image = _images(tmp_path, ["only.jpg"])[0]
    order = []

    def publish(image_path, _config, services, **_kwargs):
        gate = services.artifacts.gate
        assert gate.begin() is True
        order.append("admitted")
        try:
            # Stop must be able to linearize while this operation is protected.
            gate.stop()
            assert gate.begin() is False
            order.append("refused")
        finally:
            gate.end()
        return Terminal(StageResult("desc", "skipped", reason_code="interrupted"))

    stages = (_stage("desc", publish),)
    config = _config()
    plan = _plan([image], config, stages=stages)

    result = run_concurrent(plan, config, _services(), cwd=tmp_path / "cwd")

    assert order == ["admitted", "refused"]
    assert [o.disposition for o in result.images[0].stages] == ["interrupted"]
    assert not Path(str(image) + ".desc.txt").exists()
