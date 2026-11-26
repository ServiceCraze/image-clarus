"""Sequential execution of complete plans with per-image finalization."""

import math
import os
import select
import subprocess
import sys
import threading
import time
from collections import deque
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from time import monotonic, monotonic_ns
from types import SimpleNamespace
from typing import Any, Literal
from uuid import uuid4

from image_clarus.batch_plan import Admission, Plan, Row, route
from image_clarus.provider_frame import (
    FrameError,
    decode_frame,
    encode_frame,
    validate_frame_size,
)
from image_clarus.results import PipelineResult, StageResult
from image_clarus.stage_protocol import (
    ProviderResult,
    Request,
    Terminal,
    WorkRequired,
    drive,
)
from image_clarus.state.accumulation import accumulate_categories
from image_clarus.state.service import StateService
from image_clarus.state.storage import MemoryStoragePool, StateStopped

# A provider call is bounded by the configured request timeout plus child
# startup and teardown; the stage actor owns the child for its one request.
CHILD_STARTUP_ALLOWANCE_SECONDS = 30.0
# A2 §4: at most this many confirmations before returning to queued work.
CONFIRMATION_RUN_LIMIT = 8
# Bounded reap: a child whose pipe is held by a helper thread may not be
# reapable at once, and the actor must never block on it.
CHILD_REAP_ALLOWANCE_SECONDS = 5.0

# One pipe read at a time; large image frames stream in bounded chunks.
CHILD_READ_CHUNK = 1 << 20

StageDisposition = Literal[
    "completed", "skipped", "failed", "interrupted", "not_attempted"
]


@dataclass(frozen=True, slots=True)
class ExecutionEvent:
    """Sanitized coordinator fact; paths and provider payloads are excluded."""

    sequence: int
    monotonic_ns: int
    invocation_id: str
    kind: str
    image_id: int | None = None
    origin_id: int | None = None
    stage: str | None = None
    generation: int | None = None
    admission: Admission | None = None
    stage_predictions: tuple[tuple[str, str], ...] = ()
    route: str | None = None
    admission_ordinal: int | None = None
    request_id: str | None = None
    attempt_number: int | None = None
    is_validation_retry: bool | None = None
    disposition: str | None = None
    reason_code: str | None = None
    publication_confirmed: bool | None = None
    error_category: str | None = None
    state_outcome: str | None = None
    signal: int | None = None
    cause: str | None = None


@dataclass(frozen=True, slots=True)
class StageOutcome:
    stage: str
    disposition: StageDisposition
    result: StageResult | None
    reason_code: str | None = None


@dataclass(frozen=True, slots=True)
class ImageExecutionResult:
    image_path: Path
    admission: Admission
    stages: tuple[StageOutcome, ...]
    pipeline: PipelineResult
    state_outcome: str
    state_diagnostics: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class BatchExecutionResult:
    images: tuple[ImageExecutionResult, ...]
    aborted: bool = False
    interrupted_by: int | None = None

    @property
    def exit_code(self) -> int:
        if self.interrupted_by is not None:
            return 128 + self.interrupted_by
        if self.aborted or any(
            outcome.disposition in {"failed", "interrupted"}
            for image in self.images
            for outcome in image.stages
        ):
            return 1
        return 0


class _Emitter:
    """Ordered event channel shared by coordinator and stage actors.

    Sequence assignment, event construction and the observer callback happen
    under one lock, so identifiers are unique and monotonic and a reporting
    consumer never sees overlapping calls.
    """

    def __init__(
        self,
        sink: Callable[[ExecutionEvent], None] | None,
        invocation_id: str | None = None,
    ) -> None:
        self.sink = sink
        self.invocation_id = invocation_id or uuid4().hex
        self.sequence = 0
        self._lock = threading.Lock()

    def emit(self, kind: str, **values: Any) -> None:
        with self._lock:
            event = ExecutionEvent(
                sequence=self.sequence,
                monotonic_ns=monotonic_ns(),
                invocation_id=self.invocation_id,
                kind=kind,
                **values,
            )
            self.sequence += 1
            if self.sink is not None:
                self.sink(event)


def _read_envelope(data: bytes) -> Any:
    from image_clarus.stages.structure import _read_envelope as read

    return read(data)


def _stage_functions(plan: Plan) -> tuple[tuple[Any, Callable, Callable], ...]:
    resolved = []
    try:
        for stage in plan.stages:
            inspect_stage = stage.inspect
            execute_stage = stage.start_or_resume
            if not callable(inspect_stage) or not callable(execute_stage):
                raise TypeError
            resolved.append((stage, inspect_stage, execute_stage))
    except Exception:  # noqa: BLE001 - no image may start with partial wiring
        raise ValueError("selected stage implementation is unavailable") from None
    return tuple(resolved)


def _stage_predictions(
    row: Row, stages: tuple[Any, ...]
) -> tuple[tuple[str, str], ...]:
    _, _, work, bypass, admission, _ = row
    predictions = []
    for index, stage in enumerate(stages):
        bit = 1 << index
        if bypass & bit:
            prediction = "existing_output"
        elif work & bit and stage.uses_llm and admission is Admission.KNOWN_EXCLUDED:
            prediction = "budget_excluded"
        elif work & bit:
            prediction = "predicted_work"
        else:
            prediction = "not_required"
        predictions.append((stage.name, prediction))
    return tuple(predictions)


def _emit_plan(plan: Plan, emitter: _Emitter) -> None:
    origin_ids = {origin: index for index, origin in enumerate(plan.origins)}
    admission_ordinal = 0
    for image_id, row in enumerate(plan.rows):
        _, origin, _, _, admission, generation = row
        if origin not in origin_ids:
            raise ValueError("invalid batch plan")
        emitter.emit("discovered", image_id=image_id, origin_id=origin_ids[origin])
        ordinal = None
        if admission is Admission.ADMITTED:
            admission_ordinal += 1
            ordinal = admission_ordinal
        target, _ = route(row, plan.stages)
        route_name = plan.stages[target].name if target is not None else None
        emitter.emit(
            "planned",
            image_id=image_id,
            generation=generation,
            admission=admission,
            stage_predictions=_stage_predictions(row, plan.stages),
            route=route_name,
            admission_ordinal=ordinal,
        )


def _disposition(result: StageResult) -> StageDisposition:
    if result.status == "skipped" and result.reason_code == "interrupted":
        return "interrupted"
    return result.status


class PublicationGate:
    """Serialize stop with admission of protected publication and recovery.

    The lock guards only the atomic check-and-increment (or refusal), then is
    released before any filesystem or subprocess work, so an admitted
    publication never blocks the coordinator's stop transition from linearizing.
    """

    def __init__(self, stop: Any = None) -> None:
        self._lock = threading.Lock()
        self._stop = stop
        self._stopping = False
        self._protected = 0

    @property
    def protected(self) -> int:
        """Admitted protected operations not yet finished."""
        with self._lock:
            return self._protected

    @property
    def refusing(self) -> bool:
        """True once stop has linearly preceded all further admission."""
        with self._lock:
            return self._stopping or (
                self._stop is not None and self._stop.signum is not None
            )

    def begin(self) -> bool:
        with self._lock:
            if self._stopping or (
                self._stop is not None and self._stop.signum is not None
            ):
                return False
            self._protected += 1
            return True

    def end(self) -> None:
        with self._lock:
            self._protected -= 1

    def stop(self) -> None:
        with self._lock:
            self._stopping = True

    def drain(self, timeout: float | None = None) -> bool:
        """Wait for admitted protected operations; False if some are still active."""
        deadline = None if timeout is None else monotonic() + timeout
        while True:
            with self._lock:
                if self._protected == 0:
                    return True
            if deadline is not None and monotonic() >= deadline:
                return False
            time.sleep(0.001)


class PublicationRefused(Exception):
    """Stop linearized before an operation could be admitted."""


class GatedArtifacts:
    """Present the artifact boundary while gating every mutating call.

    `write` and `recover` can both replace files inside the destination
    directory, so both are admitted against the publication gate. Admission is
    checked immediately before the call, never held across it.
    """

    def __init__(self, inner: Any, gate: PublicationGate) -> None:
        self._inner = inner
        self.gate = gate
        self._lock = threading.Lock()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    def write(self, *args: Any, **kwargs: Any) -> Any:
        if not self.gate.begin():
            raise PublicationRefused
        try:
            # Stages share one artifact service; keep mutations serialized.
            with self._lock:
                return self._inner.write(*args, **kwargs)
        finally:
            self.gate.end()

    def recover(self, *args: Any, **kwargs: Any) -> Any:
        if not self.gate.begin():
            raise PublicationRefused
        try:
            with self._lock:
                return self._inner.recover(*args, **kwargs)
        finally:
            self.gate.end()


def _not_attempted(
    image_id: int,
    image_path: Path,
    admission: Admission,
    stage_names: tuple[str, ...],
    generation: int,
    reason: str,
    emitter: _Emitter,
    *,
    interrupted_by: int | None = None,
) -> ImageExecutionResult:
    outcomes = []
    for name in stage_names:
        outcomes.append(StageOutcome(name, "not_attempted", None, reason))
        emitter.emit(
            "stage_terminal",
            image_id=image_id,
            stage=name,
            generation=generation,
            admission=admission,
            disposition="not_attempted",
            reason_code=reason,
            publication_confirmed=False,
        )
    pipeline = PipelineResult(image_path, (), interrupted_by)
    emitter.emit(
        "image_finalized",
        image_id=image_id,
        state_outcome="not_attempted",
    )
    return ImageExecutionResult(
        image_path,
        admission,
        tuple(outcomes),
        pipeline,
        "not_attempted",
    )


def _request_metadata(request: Request) -> tuple[str, int]:
    request_id = request.request_id
    if (
        not isinstance(request_id, tuple)
        or len(request_id) < 4
        or type(request_id[2]) is not int
        or request_id[2] < 0
        or not isinstance(request_id[-1], str)
    ):
        raise ValueError("invalid provider request identity")
    # The opaque nonce plus the separate attempt number is enough for event
    # correlation; the stage's private ID also contains the image path.
    return request_id[-1], request_id[2]


def _run_stage(
    *,
    image_id: int,
    row: Row,
    stage_index: int,
    stage: Any,
    inspect_stage: Callable,
    execute_stage: Callable,
    services: Any,
    config: Mapping[str, Any],
    emitter: _Emitter,
    stop: Any,
    call_provider: Callable[[Request], ProviderResult] | None = None,
    submit_provider: Callable[[Request], Any] | None = None,
    await_provider: Callable[[Any], ProviderResult] | None = None,
    defer_transformation: bool = False,
    resume: Any = None,
) -> tuple[StageResult, bool] | WorkRequired:
    image_path = Path(row[0])
    generation = row[5]
    admission = row[4]
    bit = 1 << stage_index
    known_excluded_llm = stage.uses_llm and admission is Admission.KNOWN_EXCLUDED
    if known_excluded_llm and row[2] & bit:
        return StageResult(stage.name, "skipped", reason_code="budget_excluded"), False
    inference_allowed = not known_excluded_llm

    emitter.emit(
        "stage_evaluated",
        image_id=image_id,
        stage=stage.name,
        generation=generation,
        admission=admission,
    )
    previous_transform_callback = getattr(services, "on_transform_started", None)
    transform_started = False

    def mark_transform() -> None:
        nonlocal transform_started
        if transform_started:
            return
        transform_started = True
        emitter.emit(
            "transform_started",
            image_id=image_id,
            stage=stage.name,
            generation=generation,
            admission=admission,
        )

    services.on_transform_started = mark_transform
    try:
        # A preserved continuation is driven from where it stopped; only a
        # fresh stage runs its own authoritative inspection.
        step = (
            resume
            if resume is not None
            else inspect_stage(
                image_path, config, services, inference_allowed=inference_allowed
            )
        )
        if isinstance(step, Terminal):
            result = step.result
        elif isinstance(step, WorkRequired):
            if step.stage != stage.name:
                raise ValueError("stage continuation identity mismatch")
            if defer_transformation:
                # Deferring inspection is finished: the continuation is returned
                # untouched, before `start_or_resume` can turn it into a request.
                # The caller keeps it and runs it once this stage has capacity.
                return step
            if stop is not None and stop.signum is not None:
                return StageResult(
                    stage.name, "skipped", reason_code="interrupted"
                ), False

            def request_started(request: Request) -> None:
                request_nonce, attempt = _request_metadata(request)
                emitter.emit(
                    "provider_request_started",
                    image_id=image_id,
                    stage=stage.name,
                    generation=generation,
                    admission=admission,
                    request_id=request_nonce,
                    attempt_number=attempt,
                    is_validation_retry=attempt > 0,
                )

            def request_result(request: Request, response: ProviderResult) -> None:
                request_nonce, attempt = _request_metadata(request)
                emitter.emit(
                    "provider_request_result",
                    image_id=image_id,
                    stage=stage.name,
                    generation=generation,
                    admission=admission,
                    request_id=request_nonce,
                    attempt_number=attempt,
                    is_validation_retry=attempt > 0,
                    disposition="failed" if response.error_category else "completed",
                    error_category=response.error_category,
                )

            result = drive(
                stage,
                step,
                services,
                start_or_resume=execute_stage,
                call_provider=call_provider,
                on_provider_request=request_started,
                on_provider_result=request_result,
                submit_provider=submit_provider,
                await_provider=await_provider,
                defer_transformation=defer_transformation,
            )
        else:
            raise TypeError("invalid stage inspection result")
        if not isinstance(result, StageResult) or result.stage != stage.name:
            raise TypeError("invalid stage terminal result")
        return result, False
    except PublicationRefused:
        # No file was replaced: the stage is interrupted, not failed.
        return StageResult(stage.name, "skipped", reason_code="interrupted"), False
    except StateStopped:
        if stop is not None and stop.signum is not None:
            return StageResult(stage.name, "skipped", reason_code="interrupted"), False
        return (
            StageResult(
                stage.name,
                "failed",
                error_category="internal",
                message="Stage execution failed",
            ),
            True,
        )
    except Exception:  # noqa: BLE001 - unexpected stage faults abort the coordinator
        return (
            StageResult(
                stage.name,
                "failed",
                error_category="internal",
                message="Stage execution failed",
            ),
            True,
        )
    finally:
        services.on_transform_started = previous_transform_callback


def _execute_image(
    *,
    image_id: int,
    row: Row,
    resolved_stages: tuple[tuple[Any, Callable, Callable], ...],
    config: Mapping[str, Any],
    base_services: Any,
    memory_pool: MemoryStoragePool,
    cwd: Path,
    stop: Any,
    observe_stop: Callable[[], None],
    emitter: _Emitter,
    policy: str,
    read_envelope: Callable[[bytes], Any],
) -> tuple[ImageExecutionResult, str | None]:
    image_path = Path(row[0])
    admission = row[4]
    generation = row[5]
    stage_names = tuple(stage.name for stage, _, _ in resolved_stages)
    needs_state = any(name in {"desc", "json"} for name in stage_names)
    diagnostics: list[str] = []
    state = None

    def state_diagnostic(operation: str) -> None:
        diagnostics.append(operation)
        emitter.emit(
            "state_diagnostic",
            image_id=image_id,
            error_category=operation,
            reason_code=operation,
        )

    if needs_state:
        try:
            state = StateService.select(
                config.get("state", {}).get("directory"),
                cwd,
                image_path,
                stop=stop,
                memory_pool=memory_pool,
                on_diagnostic=state_diagnostic,
            )
        except StateStopped:
            if stop is not None and stop.signum is not None:
                observe_stop()
                return (
                    _not_attempted(
                        image_id,
                        image_path,
                        admission,
                        stage_names,
                        generation,
                        "interrupted",
                        emitter,
                        interrupted_by=stop.signum,
                    ),
                    None,
                )
            raise

    stage_services = SimpleNamespace(
        artifacts=getattr(base_services, "artifacts", None),
        provider_factory=getattr(base_services, "provider_factory", None),
        state=state,
        stop=stop,
    )
    actual_results: list[StageResult] = []
    outcomes: list[StageOutcome] = []
    abort_cause = None
    remaining_reason = None

    try:
        for stage_index, (stage, inspect_stage, execute_stage) in enumerate(
            resolved_stages
        ):
            if stop is not None and stop.signum is not None:
                observe_stop()
                remaining_reason = "interrupted"
                break
            if remaining_reason is not None:
                break
            result, fatal = _run_stage(
                image_id=image_id,
                row=row,
                stage_index=stage_index,
                stage=stage,
                inspect_stage=inspect_stage,
                execute_stage=execute_stage,
                services=stage_services,
                config=config,
                emitter=emitter,
                stop=stop,
            )
            # Sequential execution never defers, so a WorkRequired cannot occur.
            assert not isinstance(result, WorkRequired)
            actual_results.append(result)
            disposition = _disposition(result)
            outcome = StageOutcome(stage.name, disposition, result, result.reason_code)
            outcomes.append(outcome)
            emitter.emit(
                "stage_terminal",
                image_id=image_id,
                stage=stage.name,
                generation=generation,
                admission=admission,
                disposition=disposition,
                reason_code=result.reason_code,
                publication_confirmed=result.status == "completed",
                error_category=result.error_category,
            )

            if stop is not None and stop.signum is not None:
                observe_stop()
                remaining_reason = "interrupted"
                break
            if fatal:
                abort_cause = "internal_error"
                remaining_reason = "batch_aborted"
                emitter.emit("abort", cause=abort_cause)
                break
            if result.status == "failed":
                if policy == "stop":
                    remaining_reason = "stage_not_run_after_failure"
                    break
                if policy == "abort":
                    abort_cause = "stage_failure"
                    remaining_reason = "stage_not_run_after_failure"
                    emitter.emit("abort", cause=abort_cause)
                    break

        if remaining_reason is not None:
            next_index = len(outcomes)
            for stage, _, _ in resolved_stages[next_index:]:
                outcomes.append(
                    StageOutcome(stage.name, "not_attempted", None, remaining_reason)
                )
                emitter.emit(
                    "stage_terminal",
                    image_id=image_id,
                    stage=stage.name,
                    generation=generation,
                    admission=admission,
                    disposition="not_attempted",
                    reason_code=remaining_reason,
                    publication_confirmed=False,
                )

        pipeline = PipelineResult(
            image_path,
            tuple(actual_results),
            stop.signum if stop is not None else None,
        )
        if state is not None:
            accumulate_categories(
                pipeline,
                state,
                enabled=config.get("state", {}).get("accumulate_categories", True),
                read_envelope=read_envelope,
                stop=stop,
                on_diagnostic=state_diagnostic,
            )
    finally:
        if state is not None:
            state.close()

    state_outcome = "diagnostic" if diagnostics else "closed"
    emitter.emit(
        "image_finalized",
        image_id=image_id,
        state_outcome=state_outcome if needs_state else "not_required",
    )
    return (
        ImageExecutionResult(
            image_path,
            admission,
            tuple(outcomes),
            pipeline,
            state_outcome if needs_state else "not_required",
            tuple(diagnostics),
        ),
        abort_cause,
    )


class ChildProvider:
    """Own exactly one disposable transport child per admitted request.

    Credentials travel only in the private framed payload on stdin; never in
    argv, logs or files. The child runs in its own session so terminal-generated
    group signals cannot reach it, and the actor terminates and reaps it on
    stop, deadline expiry, or a malformed result. Every pipe operation is bounded
    by the request deadline, so a stalled child cannot block the actor forever.
    """

    def __init__(
        self, stop: Any = None, *, cancelled: Callable[[], bool] | None = None
    ) -> None:
        self.stop = stop
        self._cancelled = cancelled
        self._lock = threading.Lock()
        self._process: subprocess.Popen | None = None
        self._deadline: float | None = None
        self._exhausted = False
        self._unreaped = False
        self._helper_threads: set[threading.Thread] = set()
        self._startup_allowance = CHILD_STARTUP_ALLOWANCE_SECONDS

    def _is_cancelled(self) -> bool:
        return (self.stop is not None and self.stop.signum is not None) or (
            self._cancelled is not None and self._cancelled()
        )

    def _timed_out(self) -> bool:
        return self._deadline is not None and monotonic() >= self._deadline

    def _portable_io(self) -> bool:
        """Whether this platform can do readiness-checked, bounded pipe I/O."""
        return os.name != "nt"

    def _wait(self, stream: Any, writing: bool) -> bool:
        """Wait until `stream` is ready for `writing`, bounded by the deadline.

        The deadline is re-read every pass so `terminate()` cannot strand this
        wait. Readiness alone is never trusted: callers still retry on
        `BlockingIOError`, so a race between "ready" and "would block" cannot
        turn into an unbounded wait.
        """
        while True:
            deadline = self._deadline
            if deadline is None:
                return True
            remaining = deadline - monotonic()
            if remaining <= 0:
                self._exhausted = True
                return False
            try:
                if writing:
                    _, ready, _ = select.select([], [stream], [], remaining)
                else:
                    ready, _, _ = select.select([stream], [], [], remaining)
            except (OSError, ValueError):
                return False
            if ready:
                return True

    def _write_all(self, stream: Any, data: bytes) -> bool:
        """Write one whole frame, bounded by the deadline in both directions.

        Each chunk is at most `CHILD_READ_CHUNK` and is retried when the pipe
        reports it would block, so a writable-but-full pipe cannot stall the
        actor past its deadline.
        """
        view = memoryview(data)
        try:
            fd = stream.fileno()
            # Readiness only says that *some* bytes fit. A blocking write of a
            # larger chunk can still wait for the rest, so put this disposable
            # child pipe in non-blocking mode before every os.write.
            os.set_blocking(fd, False)
        except (AttributeError, OSError, ValueError):
            return False
        while view:
            if not self._wait(stream, writing=True):
                return False
            try:
                written = os.write(fd, view[:CHILD_READ_CHUNK])
            except (BlockingIOError, InterruptedError):
                continue
            except (OSError, ValueError):
                return False
            if written <= 0:
                return False
            view = view[written:]
        return True

    def _read_exact(self, stream: Any, count: int) -> bytes | None:
        """Read exactly `count` bytes or give up at the deadline.

        Readiness is bounded per chunk, so a child that never writes (or writes
        a short frame) is classified as a timeout instead of hanging the actor.
        End-of-file is reported as short input, which the caller classifies
        using the deadline rather than as a timeout by itself.
        """
        chunks = []
        remaining = count
        while remaining:
            if not self._wait(stream, writing=False):
                return None
            try:
                chunk = os.read(stream.fileno(), min(remaining, CHILD_READ_CHUNK))
            except (BlockingIOError, InterruptedError):
                continue
            except (OSError, ValueError):
                return None
            if not chunk:
                return None
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)

    def _exchange(self, frame: bytes) -> bytes | None:
        process = self._process
        if process is None or process.stdin is None or process.stdout is None:
            return None
        if not self._portable_io():
            # Windows pipes are not selectable in any direction, so the whole
            # exchange runs on a helper thread bounded by the deadline.
            return self._exchange_threaded(process, frame)
        # Deadline-bounded in both directions on POSIX pipes.
        try:
            if not self._write_all(process.stdin, frame):
                return None
            process.stdin.flush()
            process.stdin.close()
        except (OSError, ValueError):
            return None
        header = self._read_exact(process.stdout, 4)
        if header is None:
            return None
        try:
            size = validate_frame_size(int.from_bytes(header, "big"))
        except FrameError:
            return None
        body = self._read_exact(process.stdout, size) if size else b""
        if body is None:
            return None
        return header + body

    def _exchange_threaded(self, process: Any, frame: bytes) -> bytes | None:
        """Run the whole exchange on a helper thread; give up at the deadline.

        Used where a pipe cannot be polled. Neither the write nor the read may
        run on the stage actor there, so both happen on this thread. The thread
        may outlive the call: `terminate()` kills the child, which unblocks it.
        """
        outcome: dict[str, bytes | None] = {}
        finished = threading.Event()

        def exchange() -> None:
            try:
                process.stdin.write(frame)
                process.stdin.flush()
                process.stdin.close()
                header = process.stdout.read(4)
                if not header or len(header) != 4:
                    return
                try:
                    size = validate_frame_size(int.from_bytes(header, "big"))
                except FrameError:
                    return
                body = process.stdout.read(size) if size else b""
                if body is None or len(body) != size:
                    return
                outcome["frame"] = header + body
            except (OSError, ValueError):
                return
            finally:
                finished.set()
                with self._lock:
                    self._helper_threads.discard(threading.current_thread())

        worker = threading.Thread(
            target=exchange, name="image-clarus-pipe-exchange", daemon=True
        )
        # Register and start while holding the same lock `terminate()` uses for
        # its helper snapshot. A shutdown cannot join a thread in the interval
        # after registration but before `start()` makes it joinable.
        with self._lock:
            self._helper_threads.add(worker)
            worker.start()
        while True:
            if finished.wait(0.01):
                return outcome.get("frame")
            deadline = self._deadline
            if deadline is not None and monotonic() >= deadline:
                self._exhausted = True
                return None

    def call(self, request: Request) -> ProviderResult:
        payload = request.private_payload
        provider = payload.get("provider") or {}
        timeout = (
            provider.get("timeout_seconds", 60) if isinstance(provider, dict) else 60
        )
        if (
            isinstance(timeout, bool)
            or not isinstance(timeout, (int, float))
            or not math.isfinite(timeout)
            or timeout <= 0
        ):
            return ProviderResult(request.request_id, error_category="configuration")
        if self._is_cancelled():
            return ProviderResult(request.request_id, error_category="interrupted")
        self._exhausted = False
        self._unreaped = False
        try:
            frame = encode_frame(
                {
                    "payload": {
                        "provider": payload.get("provider"),
                        "model": payload.get("model"),
                        "operation": request.operation,
                        "arguments": payload.get("arguments"),
                    }
                }
            )
        except FrameError:
            return ProviderResult(request.request_id, error_category="configuration")
        try:
            process = subprocess.Popen(
                [sys.executable, "-m", "image_clarus.provider_worker"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                shell=False,
                start_new_session=True,
            )
        except (OSError, ValueError):
            return ProviderResult(
                request.request_id, error_category="provider_unavailable"
            )
        with self._lock:
            self._process = process
            self._deadline = monotonic() + float(timeout) + self._startup_allowance
        # Register-then-recheck: cancellation that won the spawn race reaps this child.
        if self._is_cancelled():
            self.terminate()
            category = "provider_unavailable" if self._unreaped else "interrupted"
            return ProviderResult(request.request_id, error_category=category)
        cleanup_failed = False
        try:
            raw = self._exchange(frame)
            timed_out = raw is None and (self._timed_out() or self._exhausted)
            stopped = self._is_cancelled()
        finally:
            self.terminate()
            cleanup_failed = self._unreaped
            with self._lock:
                self._deadline = None
        if cleanup_failed:
            return ProviderResult(
                request.request_id, error_category="provider_unavailable"
            )
        if raw is None:
            if stopped:
                return ProviderResult(request.request_id, error_category="interrupted")
            category = "network_timeout" if timed_out else "provider_unavailable"
            return ProviderResult(request.request_id, error_category=category)
        try:
            result = decode_frame(raw)
        except FrameError:
            return ProviderResult(
                request.request_id, error_category="provider_unavailable"
            )
        if not isinstance(result, dict):
            return ProviderResult(
                request.request_id, error_category="provider_unavailable"
            )
        category = result.get("category")
        content = result.get("content")
        if category is not None:
            if not isinstance(category, str):
                return ProviderResult(
                    request.request_id, error_category="provider_unavailable"
                )
            return ProviderResult(request.request_id, error_category=category)
        if not isinstance(content, str):
            return ProviderResult(
                request.request_id, error_category="provider_unavailable"
            )
        return ProviderResult(request.request_id, content=content)

    def terminate(self) -> None:
        """Kill and reap the registered child; never leave it unowned.

        The reap is bounded: a child whose pipe is still held by a helper thread
        may not become reapable immediately, and the actor must never wait on it
        longer than the reap allowance.
        """
        with self._lock:
            process, self._process = self._process, None
        if process is None:
            return
        try:
            if process.poll() is None:
                process.kill()
        except OSError:
            pass
        # Reap before closing: a stream another thread is blocked in cannot be
        # closed without waiting for that thread, which would undo the bound.
        try:
            process.wait(timeout=CHILD_REAP_ALLOWANCE_SECONDS)
        except subprocess.TimeoutExpired:
            self._unreaped = True
        except OSError:
            self._unreaped = True
        for stream in (process.stdin, process.stdout):
            try:
                if stream is not None and not stream.closed:
                    stream.close()
            except (OSError, ValueError):
                pass
        # Windows exchange helpers are child-owned I/O too. Once the child is
        # terminated and its streams are closed they must finish before the
        # transport result is accepted; a bounded failure is surfaced above.
        with self._lock:
            helpers = tuple(self._helper_threads)
        for helper in helpers:
            helper.join(timeout=CHILD_REAP_ALLOWANCE_SECONDS)
            if helper.is_alive():
                self._unreaped = True


class _PendingRequest:
    """One admitted provider request that is outstanding for its stage.

    The request runs on its own transport thread while the owning actor keeps
    servicing confirmations. The actor alone decides what the result means, so
    this object carries no stage decision, only the transport result and the
    completion signal.
    """

    __slots__ = ("done", "image_id", "request", "result")

    def __init__(self, image_id: int, request: Any) -> None:
        self.image_id = image_id
        self.request = request
        self.done = threading.Event()
        self.result: ProviderResult | None = None


class _ImageJob:
    """Per-image job state shared by the actor that owns it and the coordinator."""

    __slots__ = (
        "aborted",
        "confirmations",
        "finished",
        "image_id",
        "image_path",
        "outcomes",
    )

    def __init__(self, image_id: int, image_path: str, confirmations: int = 0) -> None:
        self.image_id = image_id
        self.image_path = image_path
        # Predicted earlier-stage bypasses still requiring authoritative
        # confirmation. These are never terminal outcomes.
        self.confirmations = confirmations
        self.outcomes: list[StageOutcome] = []
        self.finished = False
        self.aborted = False


class _ConcurrentCoordinator:
    """A2 concurrent coordination: one long-lived actor per selected stage.

    Each actor owns its queue and runs its stage's inspection, transformation
    coordination and publication serially; at most one job per stage is active
    because there is exactly one actor. An image moves between queues only when
    its owning actor forwards it, so same-image work is strictly ordered while
    unrelated images overlap across stages.
    """

    def __init__(
        self,
        *,
        plan: Plan,
        emitter: _Emitter,
        stop: Any,
        config: Mapping[str, Any],
        cwd: Path,
        memory_pool: MemoryStoragePool,
        policy: str,
        gate: PublicationGate,
        base_services: Any,
        read_envelope: Callable[[bytes], Any],
        override: tuple[Callable, Callable] | None,
    ) -> None:
        self.plan = plan
        self.emitter = emitter
        self.stop = stop
        self.config = config
        self.cwd = cwd
        self.memory_pool = memory_pool
        self.policy = policy
        self.gate = gate
        self.base_services = base_services
        self.read_envelope = read_envelope
        self.stages = plan.stages
        self.stage_names = tuple(stage.name for stage in plan.stages)
        self._override = override
        self._condition = threading.Condition()
        self._queues: dict[str, deque[int]] = {
            name: deque() for name in self.stage_names
        }
        self._queued: set[int] = set()
        self._active: set[int] = set()
        self._owners: dict[int, int] = {}
        self._finalized: dict[int, ImageExecutionResult] = {}
        self._jobs: dict[int, _ImageJob] = {}
        self._children: dict[int, ChildProvider] = {}
        self._stage_requests: dict[int, _PendingRequest] = {}
        self._deferred: dict[int, Any] = {}
        self._pending: dict[int, _PendingRequest] = {}
        self._services: dict[int, Any] = {}
        self._abort_cause: str | None = None
        self._stopping_cause: str | None = None
        self._stop_emitted = False
        self._closed = False
        self._actor_error = False
        self._drain_timeout: float | None = None
        self._threads: list[threading.Thread] = []
        self._transport_threads: set[threading.Thread] = set()
        for index in range(len(self.stage_names)):
            self._threads.append(
                threading.Thread(
                    target=self._run_thread,
                    args=(index,),
                    name=f"image-clarus-stage-{self.stage_names[index]}",
                    daemon=True,
                )
            )

    # -- shared coordinator state ----------------------------------------

    def _observe_stop(self) -> None:
        if self.stop is None or self.stop.signum is None:
            return
        with self._condition:
            if not self._stop_emitted:
                self._stop_emitted = True
                self.emitter.emit("stop", signal=self.stop.signum)

    def _close_dispatch(self, cause: str) -> None:
        """Close dispatch and settle queued work; never active work.

        A queued image cannot be picked up once an actor stops draining, so it
        can be settled here exactly once. Active work is deliberately left
        alone: its actor is still inside a provider request or an admitted
        publication, and only its own real result may become terminal. The
        actor that observes the closed dispatch marks its own operation.
        """
        with self._condition:
            # Linearize publication admission with dispatch closure. Work that
            # already passed `begin()` remains protected and drains normally;
            # no inference completing after this point can start a new write.
            self.gate.stop()
            self._closed = True
            if cause in {"signal", "interrupted"} and self._abort_cause is None:
                self._stopping_cause = "interrupted"
            elif cause == "publication_refused":
                if self._abort_cause is None:
                    self._abort_cause = "publication_refused"
            elif cause == "stage_failure" and self._abort_cause is None:
                self._abort_cause = "stage_failure"
            elif cause == "internal_error":
                self._abort_cause = "internal_error"
                self.emitter.emit("abort", cause="internal_error")
            self._settle_queued_locked()
            self._condition.notify_all()

    def _settle_queued_locked(self) -> None:
        """Caller holds the condition: not-attempted facts for queued work."""
        for name in self.stage_names:
            while self._queues[name]:
                queued = self._queues[name].popleft()
                self._queued.discard(queued)
                job = self._jobs.get(queued)
                if job is None or queued in self._finalized:
                    continue
                self._stop_unstarted_locked(job, reason=self._settle_reason())

    def _settle_reason(self) -> str:
        """The interruption cause that applies to work which never started."""
        if self._abort_cause is not None:
            return "batch_aborted"
        return "interrupted"

    def _dispatch_closed(self) -> bool:
        with self._condition:
            return self._closed

    def _interrupting(self) -> bool:
        """Caller may hold the condition: no new work may start."""
        return self._closed or self._abort_cause is not None or self._stopping()

    def _stopping(self) -> bool:
        """Interruption by signal, independent of publication admission."""
        return self._stopping_cause is not None or (
            self.stop is not None and self.stop.signum is not None
        )

    def _enqueue(self, stage_index: int, image_id: int) -> bool:
        with self._condition:
            return self._offer(stage_index, image_id)

    def _offer(self, stage_index: int, image_id: int) -> bool:
        """Caller holds the condition; atomically hand ownership to a queue."""
        if self._closed:
            return False
        if image_id in self._queued or image_id in self._finalized:
            return False
        # Transfer, never duplicate: an image is either queued or active.
        self._active.discard(image_id)
        self._owners[image_id] = stage_index
        self._queued.add(image_id)
        self._queues[self.stage_names[stage_index]].append(image_id)
        self._condition.notify_all()
        return True

    def _finish(self, image_id: int, result: ImageExecutionResult) -> None:
        with self._condition:
            self._finish_locked(image_id, result)

    def _finish_locked(self, image_id: int, result: ImageExecutionResult) -> None:
        if image_id in self._finalized:
            return
        self._finalized[image_id] = result
        self._owners.pop(image_id, None)
        self._active.discard(image_id)
        self._queued.discard(image_id)
        self._condition.notify_all()

    # -- seeding ----------------------------------------------------------

    def seed(self) -> None:
        """Seed predicted routes only after planning is complete."""
        with self._condition:
            self._seed_all()

    def _seed_all(self) -> None:
        for image_id, row in enumerate(self.plan.rows):
            target, confirmation = route(row, self.stages)
            if target is None:
                image_path = Path(row[0])
                self.emitter.emit(
                    "image_finalized", image_id=image_id, state_outcome="not_required"
                )
                self._finish_locked(
                    image_id,
                    ImageExecutionResult(
                        image_path,
                        row[4],
                        (),
                        PipelineResult(image_path, (), None),
                        "not_required",
                    ),
                )
                continue
            self._jobs[image_id] = _ImageJob(image_id, row[0], confirmation)
            # A predicted bypass is an unproven prerequisite, so the image starts
            # at the earliest stage that still owes an authoritative check: a
            # downstream stage must never run ahead of its unconfirmed upstream.
            origin = target
            for index in range(target):
                if confirmation & (1 << index):
                    origin = index
                    break
            self.emitter.emit(
                "routed", image_id=image_id, stage=self.stage_names[origin]
            )
            self._offer(origin, image_id)

    # -- actors -----------------------------------------------------------

    def _run_thread(self, stage_index: int) -> None:
        name = self.stage_names[stage_index]
        try:
            while True:
                with self._condition:
                    while not self._queues[name] and not self._closed:
                        self._condition.wait()
                    if not self._queues[name]:
                        return
                    image_id = self._queues[name].popleft()
                    self._queued.discard(image_id)
                    # A stopped or aborted actor services only the image it is
                    # already running: nothing new starts here, and queued work
                    # is settled as not attempted by the coordinator.
                    if self._closed or self._interrupting():
                        # This image was dequeued but never started, so it is no
                        # longer visible to the coordinator's queued settlement.
                        self._condition.notify_all()
                        self._finish_if_interrupted(self._jobs[image_id], stage_index)
                        return
                    if image_id in self._finalized:
                        continue
                    job = self._jobs[image_id]
                    self._active.add(image_id)
                try:
                    self._process(job, stage_index)
                except Exception:
                    with self._condition:
                        self._actor_error = True
                    self._close_dispatch("internal_error")
                    raise
                finally:
                    # An interrupted actor abandons the image it was running;
                    # nothing else will ever mark it, so mark it here.
                    self._finish_if_interrupted(job, stage_index)
        except BaseException:  # noqa: BLE001 - a dead actor is fatal infrastructure
            with self._condition:
                self._actor_error = True
            self._close_dispatch("internal_error")

    def _finish_if_interrupted(self, job: _ImageJob, stage_index: int) -> None:
        """Settle an image this actor took but could not keep running.

        Called when an actor gives up on an image it had already dequeued. The
        coordinator settles queued work, so a dequeued image is invisible to it
        and would otherwise hold a token forever.
        """
        with self._condition:
            if job.image_id in self._finalized:
                return
            if not self._interrupting():
                return
            # Queue state alone cannot identify ownership: the next actor may
            # already have dequeued the job. Only the currently assigned stage
            # may settle its in-flight work.
            if self._owners.get(job.image_id) != stage_index:
                return
            self._stop_unstarted_locked(job, reason=self._settle_reason())

    def _process(
        self, job: _ImageJob, stage_index: int, *, confirmation: bool = False
    ) -> None:
        name = self.stage_names[stage_index]
        try:
            self._observe_stop()
            # Nothing new starts once interruption has begun; the coordinator
            # settles queued work. An image that is already running keeps its
            # token and reports its own real result.
            with self._condition:
                if self._closed or self._interrupting():
                    return
            result = self._run_stage(job, stage_index, confirmation=confirmation)
            if result is None:
                return
            if self._abort_resolved(job):
                return
            self.forward(job)
        except PublicationRefused:
            # Admission was refused, so this stage published nothing.
            self._not_attempted_image(job, "interrupted")
        except StateStopped:
            if self.stop is not None and self.stop.signum is not None:
                self._observe_stop()
                self._not_attempted_image(job, "interrupted")
            else:
                self._internal_error(job, name)
        except Exception:  # noqa: BLE001 - unexpected stage faults abort the batch
            self._internal_error(job, name)

    def _run_stage(
        self, job: _ImageJob, stage_index: int, *, confirmation: bool = False
    ) -> StageResult | WorkRequired | None:
        """Run one stage on its own actor and publish the terminal fact.

        A confirmation is inspection (and, if the stage decides it must do real
        work, forwarding) only: it must never start a live request for a stage
        that already has one outstanding.
        """
        name = self.stage_names[stage_index]
        resolved = self._resolved()
        services = self._services.get(job.image_id)
        if services is None:
            services = self._open_services(job)
            if services is None:
                return None
        deferred = None if confirmation else self._deferred.pop(job.image_id, None)
        step = self._run(
            job,
            resolved[stage_index],
            stage_index,
            services,
            confirmation=confirmation,
            resume=deferred,
        )
        if isinstance(step, WorkRequired):
            # Deferred transformation: the image keeps its continuation and goes
            # back to this stage's queue for when inference capacity is free.
            with self._condition:
                self._deferred[job.image_id] = step
            return None
        if step is None:
            return None
        result, fatal = step
        disposition = _disposition(result)
        job.outcomes.append(StageOutcome(name, disposition, result, result.reason_code))
        self._emit_stage_terminal(
            job.image_id,
            name,
            self.plan.rows[job.image_id][5],
            self.plan.rows[job.image_id][4],
            disposition,
            reason=result.reason_code,
            error_category=result.error_category,
        )
        if fatal:
            # The stage seam already reduced an unexpected fault; an actor
            # exception or internal failure stops new dispatch batch-wide.
            self._failed(job, result, cause="internal_error")
            return None
        if result.status == "failed":
            self._failed(job, result)
            return None
        return result

    def _abort_resolved(self, job: _ImageJob) -> bool:
        """Did this stage's own outcome already finalize the image?"""
        return self._finalized.get(job.image_id) is not None

    def _resolved(self) -> tuple[tuple[Any, Callable, Callable], ...]:
        if self._override is not None:
            inspect_stage, execute_stage = self._override
            return tuple((stage, inspect_stage, execute_stage) for stage in self.stages)
        return _stage_functions(self.plan)

    def _run(
        self,
        job: _ImageJob,
        resolved: tuple[Any, Callable, Callable],
        stage_index: int,
        services: Any,
        *,
        confirmation: bool = False,
        resume: Any = None,
    ) -> tuple[StageResult, bool] | WorkRequired | None:
        stage, inspect_stage, execute_stage = resolved
        transport = ChildProvider(self.stop, cancelled=self._dispatch_closed)
        with self._condition:
            self._children[job.image_id] = transport
        try:
            step = _run_stage(
                image_id=job.image_id,
                row=self.plan.rows[job.image_id],
                stage_index=stage_index,
                stage=stage,
                inspect_stage=inspect_stage,
                execute_stage=execute_stage,
                services=services,
                config=self.config,
                emitter=self.emitter,
                stop=self.stop,
                # A confirmation has no transport at all: it cannot issue live
                # work even by falling back, so it can only inspect or defer.
                call_provider=None if confirmation else transport.call,
                submit_provider=None
                if confirmation
                else (lambda step: self._submit(job, stage_index, transport, step)),
                await_provider=None
                if confirmation
                else (lambda pending: self._await(job, stage_index, pending)),
                defer_transformation=confirmation,
                resume=resume,
            )
            if isinstance(step, WorkRequired):
                # A stage that re-inspects mid-flight can decide again that real
                # work is required. Either way the continuation is kept and run
                # by a later turn, never silently dropped.
                return step
            result, fatal = step
        finally:
            transport.terminate()
            with self._condition:
                self._children.pop(job.image_id, None)
                self._pending.pop(job.image_id, None)
        return result, fatal

    # -- outstanding provider request (A2 §4) ------------------------------

    def _submit(
        self,
        job: _ImageJob,
        stage_index: int,
        transport: ChildProvider,
        request: Any,
    ) -> _PendingRequest:
        """Admit one request and hand it to a transport thread.

        The actor keeps its queue: it does not wait here, so confirmations for
        other images continue to be serviced while this request is outstanding.
        """
        pending = _PendingRequest(job.image_id, request)
        with self._condition:
            # One outstanding inference *per stage*, not one per batch: a second
            # stage may hold its own request at the same time.
            assert stage_index not in self._stage_requests, (
                "a second inference was admitted for this stage"
            )
            self._stage_requests[stage_index] = pending
            self._pending[job.image_id] = pending

        def run_transport() -> None:
            try:
                pending.result = transport.call(request)
            except Exception:  # noqa: BLE001 - transport never escapes to the actor
                pending.result = ProviderResult(
                    request.request_id, error_category="provider_unavailable"
                )
            finally:
                # The actor may immediately issue a validation retry once the
                # result is visible, so release this stage's slot before waking
                # its waiter.
                with self._condition:
                    if self._stage_requests.get(stage_index) is pending:
                        del self._stage_requests[stage_index]
                    self._condition.notify_all()
                pending.done.set()
                with self._condition:
                    self._transport_threads.discard(threading.current_thread())
                    self._condition.notify_all()

        transport_thread = threading.Thread(
            target=run_transport,
            name=f"image-clarus-provider-{self.stage_names[stage_index]}",
            daemon=True,
        )
        with self._condition:
            self._transport_threads.add(transport_thread)
        transport_thread.start()
        return pending

    def _await(
        self, job: _ImageJob, stage_index: int, pending: _PendingRequest
    ) -> ProviderResult:
        """Wait for an outstanding request, servicing confirmations meanwhile.

        While this image's request is outstanding the actor admits only
        lightweight confirmations for other images: no second inference, no
        second transformation or publication, and stop is checked before each
        one. An interruption ends the wait so the caller can abandon the image.

        A confirmation is inspection only. If the confirmed image's stage turns
        out to need real work, it is returned to the queue and picked up when
        this request has finished, so this stage never has two live requests.
        """
        confirmations = 0
        while not pending.done.wait(0.01):
            with self._condition:
                if self._closed or self._interrupting():
                    break
                other = self._dequeue_confirmation_locked(stage_index)
            if other is None:
                continue
            confirmations += 1
            try:
                self._confirm(other, stage_index)
            except Exception:
                with self._condition:
                    self._actor_error = True
                self._close_dispatch("internal_error")
                raise
            finally:
                self._finish_if_interrupted(other, stage_index)
            if confirmations >= CONFIRMATION_RUN_LIMIT:
                # Bounded arbitration: the run ends, the request does not. This
                # is a yield to ready work, never a reason to abandon inference.
                confirmations = 0
                pending.done.wait(0.01)
        if pending.result is None:
            # Either interrupted or abandoned; report it as interruption so the
            # stage seam records one truthful outcome instead of a false result.
            return ProviderResult(
                pending.request.request_id, error_category="interrupted"
            )
        return pending.result

    def _dequeue_confirmation_locked(self, stage_index: int) -> _ImageJob | None:
        """Return one confirmation-ready job without consuming deferred work.

        A confirmed ``WorkRequired`` job remains on its actor's ordinary queue
        with its saved continuation. It is transformation work, not another
        confirmation candidate, until the outstanding request completes.
        """
        name = self.stage_names[stage_index]
        queued_count = len(self._queues[name])
        for _ in range(queued_count):
            image_id = self._queues[name].popleft()
            if image_id in self._deferred:
                # Keep this job in FIFO rotation for the normal actor turn that
                # resumes its saved continuation after capacity is available.
                self._queues[name].append(image_id)
                continue
            self._queued.discard(image_id)
            other = self._jobs.get(image_id)
            if other is None or image_id in self._finalized:
                continue
            self._active.add(image_id)
            return other
        return None

    def _confirm(self, job: _ImageJob, stage_index: int) -> None:
        """Service one confirmation: inspection only, never a live request.

        `Terminal` records the real stage outcome through the normal path.
        `WorkRequired` is deferred: the image keeps its continuation and returns
        to this stage's queue, so it is transformed once capacity is free.
        """
        self._process(job, stage_index, confirmation=True)
        with self._condition:
            if job.image_id in self._deferred and job.image_id not in self._finalized:
                self._queued.add(job.image_id)
                self._queues[self.stage_names[stage_index]].append(job.image_id)
                self._condition.notify_all()

    def _open_services(self, job: _ImageJob) -> Any:
        row = self.plan.rows[job.image_id]
        image_path = Path(row[0])
        needs_state = any(name in {"desc", "json"} for name in self.stage_names)
        diagnostics: list[str] = []

        def state_diagnostic(operation: str) -> None:
            diagnostics.append(operation)
            self.emitter.emit(
                "state_diagnostic",
                image_id=job.image_id,
                error_category=operation,
                reason_code=operation,
            )

        state = None
        if needs_state:
            try:
                state = StateService.select(
                    self.config.get("state", {}).get("directory"),
                    self.cwd,
                    image_path,
                    stop=self.stop,
                    memory_pool=self.memory_pool,
                    on_diagnostic=state_diagnostic,
                )
            except StateStopped:
                if self.stop is not None and self.stop.signum is not None:
                    self._observe_stop()
                    self._not_attempted_image(job, "interrupted")
                else:
                    self._internal_error(job, self.stage_names[0])
                return None
        artifacts = getattr(self.base_services, "artifacts", None)
        services = SimpleNamespace(
            artifacts=GatedArtifacts(artifacts, self.gate)
            if artifacts is not None
            else None,
            provider_factory=getattr(self.base_services, "provider_factory", None),
            state=state,
            stop=self.stop,
        )
        services.diagnostics = diagnostics
        self._services[job.image_id] = services
        return services

    # -- forwarding, failures and finalization ----------------------------

    def forward(self, job: _ImageJob) -> None:
        """Hand the image to the next selected stage's own actor."""
        with self._condition:
            self._forward_locked(job)

    def _forward_locked(self, job: _ImageJob) -> None:
        image_id = job.image_id
        _, _, work, _, admission, generation = self.plan.rows[image_id]
        done = {outcome.stage for outcome in job.outcomes}
        # A predicted bypass is an obligation of its own stage actor until that
        # actor records the authoritative result; it is not a finished stage.
        pending = {
            index
            for index in range(len(self.stage_names))
            if job.confirmations & (1 << index) and self.stage_names[index] not in done
        }
        for index, name in enumerate(self.stage_names):
            if name in done:
                continue
            # Unconfirmed bypasses are dispatched to their owning actors first,
            # in registry order, exactly once each.
            if index in pending:
                if self._offer(index, image_id):
                    return
                self._stop_unstarted_locked(job)
                return
            stage = self.stages[index]
            if (
                stage.uses_llm
                and admission is Admission.KNOWN_EXCLUDED
                and work & (1 << index)
            ):
                job.outcomes.append(
                    StageOutcome(name, "skipped", None, "budget_excluded")
                )
                self._emit_stage_terminal(
                    image_id,
                    name,
                    generation,
                    admission,
                    "skipped",
                    reason="budget_excluded",
                )
                continue
            if self._offer(index, image_id):
                return
            self._stop_unstarted_locked(job)
            return
        self._finalize_locked(job)

    def _stop_unstarted_locked(
        self, job: _ImageJob, *, reason: str | None = None
    ) -> None:
        """Caller holds the condition: terminal facts for stages that never ran."""
        if reason is None:
            reason = self._settle_reason()
            disposition: StageDisposition = (
                "not_attempted" if reason == "batch_aborted" else "interrupted"
            )
        else:
            disposition = "interrupted" if reason == "interrupted" else "not_attempted"
        done = {outcome.stage for outcome in job.outcomes}
        _, _, _, _, admission, generation = self.plan.rows[job.image_id]
        for name in self.stage_names:
            if name in done:
                continue
            job.outcomes.append(StageOutcome(name, disposition, None, reason))
            self._emit_stage_terminal(
                job.image_id,
                name,
                generation,
                admission,
                disposition,
                reason=reason,
            )
        self._finalize_locked(job)

    def _emit_stage_terminal(
        self,
        image_id: int,
        name: str,
        generation: int,
        admission: Admission,
        disposition: str,
        *,
        reason: str | None = None,
        error_category: str | None = None,
    ) -> None:
        self.emitter.emit(
            "stage_terminal",
            image_id=image_id,
            stage=name,
            generation=generation,
            admission=admission,
            disposition=disposition,
            reason_code=reason,
            error_category=error_category,
            publication_confirmed=disposition == "completed",
        )

    def _failed(
        self, job: _ImageJob, result: StageResult, *, cause: str | None = None
    ) -> None:
        if cause is None and self.policy == "continue":
            self.forward(job)
            return
        with self._condition:
            self._failed_locked(job, result, cause)

    def _failed_locked(
        self, job: _ImageJob, result: StageResult, cause: str | None
    ) -> None:
        name = result.stage
        index = self.stage_names.index(name)
        for later in self.stage_names[index + 1 :]:
            job.outcomes.append(
                StageOutcome(
                    later, "not_attempted", None, "stage_not_run_after_failure"
                )
            )
            self.emitter.emit(
                "stage_terminal",
                image_id=job.image_id,
                stage=later,
                generation=self.plan.rows[job.image_id][5],
                admission=self.plan.rows[job.image_id][4],
                disposition="not_attempted",
                reason_code="stage_not_run_after_failure",
                publication_confirmed=False,
            )
        if cause is not None:
            job.aborted = True
            # Record why before closing, so unstarted work is reported as aborted.
            with self._condition:
                self._abort_cause = cause
            self._close_dispatch(cause)
        elif self.policy == "abort":
            job.aborted = True
            with self._condition:
                self._abort_cause = "stage_failure"
            self._close_dispatch("stage_failure")
        self._finalize_locked(job)

    def _internal_error(self, job: _ImageJob, name: str) -> None:
        result = StageResult(
            name,
            "failed",
            error_category="internal",
            message="Stage execution failed",
        )
        job.outcomes.append(StageOutcome(name, "failed", result, None))
        self.emitter.emit(
            "stage_terminal",
            image_id=job.image_id,
            stage=name,
            generation=self.plan.rows[job.image_id][5],
            admission=self.plan.rows[job.image_id][4],
            disposition="failed",
            error_category="internal",
            publication_confirmed=False,
        )
        for later in self.stage_names[self.stage_names.index(name) + 1 :]:
            job.outcomes.append(
                StageOutcome(later, "not_attempted", None, "batch_aborted")
            )
            self.emitter.emit(
                "stage_terminal",
                image_id=job.image_id,
                stage=later,
                generation=self.plan.rows[job.image_id][5],
                admission=self.plan.rows[job.image_id][4],
                disposition="not_attempted",
                reason_code="batch_aborted",
                publication_confirmed=False,
            )
        self._close_dispatch("internal_error")
        self._finalize(job)

    def _not_attempted_image(self, job: _ImageJob, reason: str) -> None:
        """Caller holds the condition or is the sole owner of the job."""
        with self._condition:
            self._stop_unstarted_locked(job, reason=reason)

    def _finalize(self, job: _ImageJob) -> None:
        with self._condition:
            self._finalize_locked(job)

    def _finalize_locked(self, job: _ImageJob) -> None:
        if self._finalized.get(job.image_id) is not None:
            return
        row = self.plan.rows[job.image_id]
        image_path = row[0]
        order = {name: index for index, name in enumerate(self.stage_names)}
        seen: dict[str, StageOutcome] = {}
        for outcome in job.outcomes:
            current = seen.get(outcome.stage)
            if current is None or current.disposition == "not_attempted":
                seen[outcome.stage] = outcome
        outcomes = tuple(
            seen[name] for name in sorted(seen, key=lambda name: order[name])
        )
        results = tuple(
            outcome.result
            for outcome in outcomes
            if outcome.result is not None and outcome.disposition != "not_attempted"
        )
        services = self._services.pop(job.image_id, None)
        diagnostics: tuple[str, ...] = ()
        state_outcome = "not_required"
        stop_signum = self.stop.signum if self.stop is not None else None
        try:
            if services is not None:
                accumulate_categories(
                    PipelineResult(image_path, results, stop_signum),
                    services.state,
                    enabled=self.config.get("state", {}).get(
                        "accumulate_categories", True
                    ),
                    read_envelope=self.read_envelope,
                    stop=self.stop,
                    on_diagnostic=lambda operation: self.emitter.emit(
                        "state_diagnostic",
                        image_id=job.image_id,
                        error_category=operation,
                        reason_code=operation,
                    ),
                )
                diagnostics = tuple(services.diagnostics)
                state_outcome = "diagnostic" if diagnostics else "closed"
        finally:
            if services is not None and getattr(services, "state", None) is not None:
                services.state.close()
        self.emitter.emit(
            "image_finalized", image_id=job.image_id, state_outcome=state_outcome
        )
        self._finalized[job.image_id] = ImageExecutionResult(
            image_path,
            row[4],
            outcomes,
            PipelineResult(image_path, results, stop_signum),
            state_outcome,
            diagnostics,
        )
        self._owners.pop(job.image_id, None)
        self._active.discard(job.image_id)
        self._queued.discard(job.image_id)
        self._condition.notify_all()

    # -- run and shutdown --------------------------------------------------

    def _drain_deadline(self) -> float | None:
        """When shutdown stops waiting for protected publications.

        Fixed when the run starts so the wait is a real bound rather than one
        that restarts on every poll.
        """
        return (
            None if self._drain_timeout is None else monotonic() + self._drain_timeout
        )

    def run(self, *, drain_timeout: float | None) -> BatchExecutionResult:
        self._drain_timeout = drain_timeout
        for thread in self._threads:
            thread.start()
        self.seed()
        # Drain in parallel with the finalization loop: a stalled protected
        # publication must be reported at its deadline instead of making
        # shutdown wait on an image that operation holds.
        drain_deadline = self._drain_deadline()
        drained = False
        with self._condition:
            while len(self._finalized) < len(self.plan.rows):
                if self._stopping():
                    # Signal first: it is the cause reported for every image
                    # whose work this interruption owns, queued or active.
                    self._close_dispatch("signal")
                elif self._abort_cause is None and self.gate.refusing:
                    # Admission was refused although no signal has arrived. This
                    # is a shutdown of dispatch, recorded so it is never
                    # reported as a clean run.
                    self._close_dispatch("publication_refused")
                if self._closed:
                    # Cancel owned inference and settle queued, unstarted work
                    # so the batch can finish instead of running to completion.
                    children = tuple(self._children.values())
                    for child in children:
                        child.terminate()
                    self._settle_queued_locked()
                if (
                    self._closed
                    and drain_deadline is not None
                    and monotonic() >= drain_deadline
                ):
                    break
                self._condition.wait(timeout=0.05)
            self._closed = True
            self._condition.notify_all()
        if self._stopping() or self._abort_cause is not None:
            self.gate.stop()
            with self._condition:
                children = tuple(self._children.values())
            for child in children:
                child.terminate()
        # A deadline is a responsiveness/reporting bound, not permission to
        # abandon a write that already crossed publication admission. Record the
        # timeout, then retain ownership until each admitted operation exits.
        drained = self.gate.drain(timeout=drain_timeout)
        if not drained:
            self._actor_error = True
        self.gate.drain()
        # Once admitted publication has drained, every actor must settle its own
        # active work before results or shared services can be released.
        for thread in self._threads:
            thread.join()
        # An actor may abandon a request while its child is still crossing the
        # spawn/registration boundary. Retain and join the transport threads so
        # their cancellation path has registered, terminated, and reaped any
        # late child before this coordinator relinquishes ownership.
        while True:
            with self._condition:
                transport_threads = tuple(self._transport_threads)
            if not transport_threads:
                break
            for thread in transport_threads:
                thread.join()
        with self._condition:
            # Only now may anything still unfinished be settled: actors have
            # returned, so nothing active remains that could still report.
            self._settle_queued_locked()
        results = []
        for image_id in range(len(self.plan.rows)):
            result = self._finalized.get(image_id)
            if result is None:
                result = _not_attempted(
                    image_id,
                    Path(self.plan.rows[image_id][0]),
                    self.plan.rows[image_id][4],
                    self.stage_names,
                    self.plan.rows[image_id][5],
                    "interrupted" if self._abort_cause is None else "batch_aborted",
                    self.emitter,
                )
            results.append(result)
        aborted = (
            self._abort_cause is not None
            or not drained
            or self._actor_error
            or any(job.aborted for job in self._jobs.values())
            or any(
                outcome.reason_code == "batch_aborted"
                for result in results
                for outcome in result.stages
            )
        )
        return BatchExecutionResult(
            tuple(results), aborted, self.stop.signum if self.stop is not None else None
        )


def run_concurrent(
    plan: Plan,
    config: Mapping[str, Any],
    services: Any,
    *,
    cwd: Path | None = None,
    stop: Any = None,
    on_event: Callable[[ExecutionEvent], None] | None = None,
    read_envelope: Callable[[bytes], Any] | None = None,
    inspect_stage: Callable | None = None,
    execute_stage: Callable | None = None,
    drain_timeout: float | None = 30.0,
) -> BatchExecutionResult:
    """Run the plan with one long-lived actor per selected stage."""
    if plan.identities and not plan.rows:
        raise ValueError("aggregate-only plan cannot be executed")
    if len(plan.rows) != len(plan.identities):
        raise ValueError("invalid batch plan")
    policy = config.get("pipeline", {}).get("on_stage_failure", "stop")
    if policy not in {"continue", "stop", "abort"}:
        raise ValueError("invalid stage failure policy")
    _stage_functions(plan) if inspect_stage is None else _check_override(
        inspect_stage, execute_stage
    )
    if plan.stages and not hasattr(services, "artifacts"):
        raise ValueError("artifact service is unavailable")
    if stop is None:
        stop = getattr(services, "stop", None)
    cwd = Path.cwd() if cwd is None else Path(cwd)
    emitter = _Emitter(on_event)
    _emit_plan(plan, emitter)
    read_envelope = read_envelope or _read_envelope
    gate = PublicationGate(stop)
    override = None if inspect_stage is None else (inspect_stage, execute_stage)
    coordinator = _ConcurrentCoordinator(
        plan=plan,
        emitter=emitter,
        stop=stop,
        config=config,
        cwd=cwd,
        memory_pool=MemoryStoragePool(stop=stop),
        policy=policy,
        gate=gate,
        base_services=services,
        read_envelope=read_envelope,
        override=override,
    )
    try:
        return coordinator.run(drain_timeout=drain_timeout)
    finally:
        coordinator.memory_pool.close()


def _check_override(inspect_stage: Any, execute_stage: Any) -> None:
    if not callable(inspect_stage) or not callable(execute_stage):
        raise TypeError("selected stage implementation is unavailable")


def run_sequential(
    plan: Plan,
    config: Mapping[str, Any],
    services: Any,
    *,
    cwd: Path | None = None,
    stop: Any = None,
    on_event: Callable[[ExecutionEvent], None] | None = None,
    read_envelope: Callable[[bytes], Any] | None = None,
) -> BatchExecutionResult:
    """Execute one full image lifecycle at a time without changing plan facts."""
    if plan.identities and not plan.rows:
        raise ValueError("aggregate-only plan cannot be executed")
    if len(plan.rows) != len(plan.identities):
        raise ValueError("invalid batch plan")
    policy = config.get("pipeline", {}).get("on_stage_failure", "stop")
    if policy not in {"continue", "stop", "abort"}:
        raise ValueError("invalid stage failure policy")
    resolved_stages = _stage_functions(plan)
    if plan.stages and not hasattr(services, "artifacts"):
        raise ValueError("artifact service is unavailable")
    if stop is None:
        stop = getattr(services, "stop", None)
    cwd = Path.cwd() if cwd is None else Path(cwd)
    emitter = _Emitter(on_event)
    _emit_plan(plan, emitter)
    read_envelope = read_envelope or _read_envelope
    stage_names = tuple(stage.name for stage in plan.stages)
    memory_pool = MemoryStoragePool(stop=stop)
    results = []
    aborted = False
    stop_emitted = False

    def observe_stop() -> None:
        nonlocal stop_emitted
        if stop is not None and stop.signum is not None and not stop_emitted:
            emitter.emit("stop", signal=stop.signum)
            stop_emitted = True

    try:
        for image_id, row in enumerate(plan.rows):
            image_path = Path(row[0])
            admission = row[4]
            generation = row[5]
            if stop is not None and stop.signum is not None:
                observe_stop()
                results.append(
                    _not_attempted(
                        image_id,
                        image_path,
                        admission,
                        stage_names,
                        generation,
                        "interrupted",
                        emitter,
                        interrupted_by=stop.signum,
                    )
                )
                continue
            if aborted:
                results.append(
                    _not_attempted(
                        image_id,
                        image_path,
                        admission,
                        stage_names,
                        generation,
                        "batch_aborted",
                        emitter,
                    )
                )
                continue
            image_result, abort_cause = _execute_image(
                image_id=image_id,
                row=row,
                resolved_stages=resolved_stages,
                config=config,
                base_services=services,
                memory_pool=memory_pool,
                cwd=cwd,
                stop=stop,
                observe_stop=observe_stop,
                emitter=emitter,
                policy=policy,
                read_envelope=read_envelope,
            )
            results.append(image_result)
            if abort_cause is not None:
                aborted = True
            observe_stop()
    finally:
        memory_pool.close()

    return BatchExecutionResult(
        tuple(results), aborted, stop.signum if stop is not None else None
    )
