"""Sequential execution of complete plans with per-image finalization."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from time import monotonic_ns
from types import SimpleNamespace
from typing import Any, Literal
from uuid import uuid4

from image_clarus.batch_plan import Admission, Plan, Row, route
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
    def __init__(
        self,
        sink: Callable[[ExecutionEvent], None] | None,
        invocation_id: str | None = None,
    ) -> None:
        self.sink = sink
        self.invocation_id = invocation_id or uuid4().hex
        self.sequence = 0

    def emit(self, kind: str, **values: Any) -> None:
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
) -> tuple[StageResult, bool]:
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
        step = inspect_stage(
            image_path, config, services, inference_allowed=inference_allowed
        )
        if isinstance(step, Terminal):
            result = step.result
        elif isinstance(step, WorkRequired):
            if step.stage != stage.name:
                raise ValueError("stage continuation identity mismatch")
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
                on_provider_request=request_started,
                on_provider_result=request_result,
            )
        else:
            raise TypeError("invalid stage inspection result")
        if not isinstance(result, StageResult) or result.stage != stage.name:
            raise TypeError("invalid stage terminal result")
        return result, False
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
