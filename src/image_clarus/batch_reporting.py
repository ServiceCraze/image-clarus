"""Human-readable reporting for Slice 4 batch planning and execution."""

from __future__ import annotations

import json
import time
from collections import Counter, defaultdict
from collections.abc import Callable

from image_clarus.batch_execution import (
    BatchExecutionResult,
    ExecutionEvent,
    StageOutcome,
)
from image_clarus.batch_plan import Admission, Plan, Row, route

# Categories are internal codes, not provider messages. Unknown values must not
# be echoed: worker responses can cross a process boundary.
_FAILURE_CATEGORIES = frozenset(
    {
        "authentication",
        "configuration",
        "corrupt_image",
        "file_io",
        "internal",
        "interrupted",
        "invalid_artifact",
        "missing_prerequisite",
        "network_timeout",
        "provider_unavailable",
        "schema_validation",
        "unknown_model",
        "unsupported_image",
    }
)


class BatchReporter:
    """Reduce coordinator facts into bounded, deterministic terminal output."""

    def __init__(
        self,
        plan: Plan,
        *,
        emit: Callable[[str], None] = print,
        emit_error: Callable[[str], None] | None = None,
        redact: Callable[[str], str] | None = None,
        verbose: bool = False,
    ) -> None:
        self.plan = plan
        self.emit = emit
        self.emit_error = emit_error
        self.redact = redact or (lambda value: value)
        self.verbose = verbose
        self.started = time.monotonic()
        self.paths = {index: row[0] for index, row in enumerate(plan.rows)}
        self.evaluated: Counter[str] = Counter()
        self.transformed: Counter[str] = Counter()
        self.outcomes: dict[str, Counter[str]] = defaultdict(Counter)
        self.skip_reasons: dict[str, Counter[str]] = defaultdict(Counter)
        self.requests = 0
        self.retries = 0
        self.llm_images: set[int] = set()
        self.corrective_images: set[int] = set()
        self._request_starts: dict[str, ExecutionEvent] = {}
        self._request_results: dict[str, ExecutionEvent] = {}
        self._evaluated_pairs: set[tuple[int, str, int]] = set()
        self._transformed_pairs: set[tuple[int, str, int]] = set()
        self._terminal_events: dict[tuple[int, str], ExecutionEvent] = {}
        self._accounting_error = False

    def render_dry_run_row(
        self, row: Row, _target: int | None, _confirmation: int
    ) -> None:
        path, _origin, work, bypass, admission, _generation = row
        predictions = []
        for index, stage in enumerate(self.plan.stages):
            bit = 1 << index
            if bypass & bit:
                value = "existing_output"
            elif (
                work & bit and stage.uses_llm and admission is Admission.KNOWN_EXCLUDED
            ):
                value = "budget_excluded"
            elif work & bit:
                value = "work"
            else:
                value = "not_required"
            predictions.append(f"{stage.name}={value}")
        target, _ = route(row, self.plan.stages)
        route_name = self.plan.stages[target].name if target is not None else "none"
        ordinal = sum(
            1
            for candidate in self.plan.rows
            if candidate is row and candidate[4] is Admission.ADMITTED
        )
        # Aggregate dry-run intentionally has no retained rows, so calculate the
        # admission position from the streamed immutable classifications instead.
        if admission is Admission.ADMITTED:
            ordinal = getattr(self, "_admitted_seen", 0) + 1
            self._admitted_seen = ordinal
        limit = getattr(self, "_limit", None)
        if limit is None:
            budget = "unlimited"
        elif admission is Admission.ADMITTED and ordinal == limit:
            budget = "reached"
        else:
            budget = "not_reached"
        admission_field = "-" if admission is not Admission.ADMITTED else str(ordinal)
        self.emit(
            f"plan provisional image={self._quote(path)} class={admission.value} "
            f"{' '.join(predictions)} route={route_name} admission={admission_field} "
            f"budget={budget}"
        )

    def set_budget_limit(self, limit: int | None) -> None:
        self._limit = limit

    def render_complete_plan(self) -> None:
        counts = self.plan.counts
        self.emit(
            "plan complete "
            f"images={sum(counts.values())} admitted={counts[Admission.ADMITTED]} "
            f"no_work={counts[Admission.NO_LLM_WORK]} "
            f"excluded={counts[Admission.KNOWN_EXCLUDED]} "
            "runtime_dependencies=not_checked"
        )
        self.emit(
            "estimated initial plan/queue memory: "
            f"{self.plan.estimated_bytes} bytes (estimate, not peak or bound)"
        )

    def consume(self, event: ExecutionEvent) -> None:
        if event.kind == "state_diagnostic":
            return
        if event.image_id is None or event.stage is None or event.generation is None:
            return
        key = (event.image_id, event.stage, event.generation)
        if event.kind == "stage_evaluated" and key not in self._evaluated_pairs:
            self._evaluated_pairs.add(key)
            self.evaluated[event.stage] += 1
        elif event.kind == "transform_started" and key not in self._transformed_pairs:
            self._transformed_pairs.add(key)
            self.transformed[event.stage] += 1
        elif event.kind == "provider_request_started":
            if not self._record_request(self._request_starts, event):
                return
            self.requests += 1
            self.retries += bool(event.is_validation_retry)
            self.llm_images.add(event.image_id)
            if self.plan.rows[event.image_id][4] is Admission.NO_LLM_WORK:
                self.corrective_images.add(event.image_id)
        elif event.kind == "provider_request_result":
            self._record_request(self._request_results, event)
        elif event.kind == "stage_terminal":
            terminal_key = (event.image_id, event.stage)
            if terminal_key in self._terminal_events:
                self._accounting_error = True
                return
            self._terminal_events[terminal_key] = event
            self.outcomes[event.stage][event.disposition] += 1
            if event.disposition == "skipped" and event.reason_code:
                self.skip_reasons[event.stage][event.reason_code] += 1
        if self.verbose and event.kind in {"stage_evaluated", "stage_terminal"}:
            path = self.paths.get(event.image_id, "")
            stage = event.stage or ""
            elapsed = time.monotonic() - self.started
            if event.kind == "stage_evaluated":
                self.emit(
                    f"stage start image={self._quote(path)} stage={stage} elapsed={elapsed:.3f}s"
                )
            else:
                accounted = sum(
                    sum(values.values()) for values in self.outcomes.values()
                )
                total = len(self.plan.rows) * len(self.plan.stages)
                progress = "0/0 (no work)" if total == 0 else f"{accounted}/{total}"
                reason = event.reason_code or "-"
                if event.disposition == "failed":
                    reason = (
                        event.error_category
                        if event.error_category in _FAILURE_CATEGORIES
                        else "unknown"
                    )
                    reason = self.redact(reason)
                self.emit(
                    f"stage end image={self._quote(path)} stage={stage} "
                    f"status={event.disposition} reason={reason} "
                    f"progress={progress} accounted elapsed={elapsed:.3f}s"
                )

    def render_summary(self, result: BatchExecutionResult) -> bool:
        counts = self.plan.counts
        self.emit(
            "summary "
            f"images={len(self.plan.rows)} admitted={counts[Admission.ADMITTED]} "
            f"no_work={counts[Admission.NO_LLM_WORK]} excluded={counts[Admission.KNOWN_EXCLUDED]}"
        )
        for index, stage in enumerate(self.plan.stages):
            predicted = Counter()
            bit = 1 << index
            for row in self.plan.rows:
                if row[3] & bit:
                    predicted["existing_output"] += 1
                elif (
                    row[2] & bit
                    and stage.uses_llm
                    and row[4] is Admission.KNOWN_EXCLUDED
                ):
                    predicted["budget_excluded"] += 1
            actual = self.outcomes[stage.name]
            self.emit(
                f"planned stage={stage.name} existing_output={predicted['existing_output']} "
                f"budget_excluded={predicted['budget_excluded']}"
            )
            self.emit(
                f"actual stage={stage.name} evaluated={self.evaluated[stage.name]} "
                f"transformed={self.transformed[stage.name]} completed={actual['completed']} "
                f"skipped={actual['skipped']} failed={actual['failed']} "
                f"interrupted={actual['interrupted']} not_attempted={actual['not_attempted']}"
            )
            for reason, count in sorted(self.skip_reasons[stage.name].items()):
                self.emit(f"skip stage={stage.name} reason={reason} count={count}")
        self.emit(
            f"work llm_images={len(self.llm_images)} corrective_images={len(self.corrective_images)} "
            f"requests={self.requests} first_requests={self.requests - self.retries} retries={self.retries}"
        )
        if any(stage.name == "xmp" for stage in self.plan.stages):
            xmp = self.outcomes["xmp"]
            self.emit(
                f"xmp evaluated={self.evaluated['xmp']} writes={xmp['completed']} "
                f"no_change={self.skip_reasons['xmp']['no_change']}"
            )
        accounted = sum(sum(values.values()) for values in self.outcomes.values())
        total = len(self.plan.rows) * len(self.plan.stages)
        progress = "0/0 (no work)" if total == 0 else f"{accounted}/{total}"
        self.emit(
            f"progress accounted={progress} elapsed_seconds={time.monotonic() - self.started:.3f}"
        )
        reconciled = self.reconcile(result, accounted)
        if not reconciled:
            self._error("image-clarus: internal accounting error; summary incomplete")
        return reconciled

    def reconcile(
        self, result: BatchExecutionResult, accounted: int | None = None
    ) -> bool:
        """Check final executor outcomes without changing compatibility output."""
        expected_pairs = {
            (image_id, stage.name)
            for image_id in range(len(self.plan.rows))
            for stage in self.plan.stages
        }
        result_pairs = {
            (image_id, outcome.stage): outcome
            for image_id, image in enumerate(result.images)
            for outcome in image.stages
        }
        result_matches_events = all(
            self._terminal_matches_outcome(pair, outcome)
            for pair, outcome in result_pairs.items()
        )
        return (
            len(result.images) == len(self.plan.rows)
            and set(result_pairs) == expected_pairs
            and set(self._terminal_events) == expected_pairs
            and (accounted if accounted is not None else len(self._terminal_events))
            == len(expected_pairs)
            and self._request_identities_match()
            and result_matches_events
            and not self._accounting_error
        )

    def _quote(self, value: str) -> str:
        """Keep each redacted path on one UTF-8 terminal line."""
        return json.dumps(self.redact(value), ensure_ascii=True)

    def _error(self, value: str) -> None:
        if self.emit_error is not None:
            self.emit_error(value)

    def _record_request(
        self, collection: dict[str, ExecutionEvent], event: ExecutionEvent
    ) -> bool:
        if event.request_id is None or event.request_id in collection:
            self._accounting_error = True
            return False
        collection[event.request_id] = event
        return True

    def _request_identities_match(self) -> bool:
        return self._request_starts.keys() == self._request_results.keys() and all(
            self._request_identity(self._request_starts[request_id])
            == self._request_identity(self._request_results[request_id])
            for request_id in self._request_starts
        )

    def _terminal_matches_outcome(
        self, pair: tuple[int, str], outcome: StageOutcome
    ) -> bool:
        image_id, _stage = pair
        if image_id >= len(self.plan.rows):
            return False
        terminal = self._terminal_events.get(pair)
        if terminal is None:
            return False
        row = self.plan.rows[image_id]
        result = outcome.result
        return (
            terminal.generation == row[5]
            and terminal.admission is row[4]
            and terminal.disposition == outcome.disposition
            and terminal.reason_code == outcome.reason_code
            and terminal.error_category
            == (result.error_category if result is not None else None)
        )

    @staticmethod
    def _request_identity(
        event: ExecutionEvent,
    ) -> tuple[int | None, str | None, int | None, int | None, bool | None]:
        return (
            event.image_id,
            event.stage,
            event.generation,
            event.attempt_number,
            event.is_validation_retry,
        )
