"""Initial metadata-only admission and routing, independent of stage results."""

import sys
from collections import deque
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from image_clarus.discovery import Candidate
from image_clarus.stage_registry import STAGES, StageDescriptor, predicted_bypass


class Admission(Enum):
    ADMITTED = "ADMITTED"
    NO_LLM_WORK = "NO_LLM_WORK"
    KNOWN_EXCLUDED = "KNOWN_EXCLUDED"


@dataclass(frozen=True)
class PlanningInput:
    identity: str
    origin: tuple[str, str, str]

    @classmethod
    def from_candidate(cls, candidate: Candidate) -> "PlanningInput":
        """Preserve first-selection provenance from completed discovery."""
        if (
            candidate.kind not in {"file", "directory", "pattern"}
            or candidate.anchor is None
        ):
            raise ValueError("invalid candidate kind")
        return cls(
            candidate.identity, (candidate.selection, candidate.anchor, candidate.kind)
        )


# Row is deliberately the A4 six-tuple; route is derived, not stored.
Row = tuple[str, tuple[str, str, str], int, int, Admission, int]


@dataclass
class Plan:
    rows: list[Row]
    identities: set[str]
    origins: list[tuple[str, str, str]]
    stages: tuple[StageDescriptor, ...]
    queues: tuple[deque, ...]
    lifecycle: list
    tracking: tuple[list, ...]
    counts: dict[Admission, int]
    estimated_bytes: int


def route(row: Row, stages: tuple[StageDescriptor, ...]) -> tuple[int | None, int]:
    _, _, work, bypass, admission, _ = row
    for index, stage in enumerate(stages):
        bit = 1 << index
        if bypass & bit:
            continue
        if stage.uses_llm and admission is Admission.KNOWN_EXCLUDED and work & bit:
            continue
        return index, bypass & (bit - 1)
    # Even without predicted work, a selected image must reach an actor:
    # earlier predicted bypasses require confirmation and the last stage must
    # produce its own actual outcome (or budget exclusion).
    if stages:
        last = len(stages) - 1
        return last, bypass & ((1 << last) - 1)
    return None, 0


def _estimate(identities, origins, rows, queues, lifecycle, tracking):
    seen = {id(value) for value in identities}
    size = sys.getsizeof(identities) + sum(sys.getsizeof(value) for value in identities)
    size += sys.getsizeof(origins)
    for origin in origins:
        size += sys.getsizeof(origin)
        for value in origin:
            if id(value) not in seen:
                size += sys.getsizeof(value)
                seen.add(id(value))
    size += sys.getsizeof(rows) + sum(sys.getsizeof(row) for row in rows)
    size += sys.getsizeof(queues) + sum(sys.getsizeof(q) for q in queues)
    size += sum(sys.getsizeof(entry) for q in queues for entry in q)
    size += sys.getsizeof(lifecycle)
    if tracking is not queues:
        size += sys.getsizeof(tracking)
    size += sum(sys.getsizeof(t) for t in tracking)
    return size


def _description_may_exist(image: Path) -> bool:
    """Only classify the prerequisite as absent when both paths are absent.

    A backup, symlink, or metadata error is uncertain: execution owns recovery,
    validation, and diagnostics. No sidecar content is read during planning.
    """
    for suffix in (".desc.txt", ".desc.txt.bak"):
        try:
            Path(str(image) + suffix).lstat()
        except FileNotFoundError:
            continue
        except OSError:
            return True
        return True
    return False


def build_plan(
    inputs: Iterable[PlanningInput],
    config: Mapping[str, Any],
    *,
    selected: tuple[str, ...] | None = None,
    limit: int | None = None,
    stages: tuple[StageDescriptor, ...] = STAGES,
    stream: Callable[[Row, int | None, int], None] | None = None,
    aggregate_only: bool = False,
) -> Plan:
    """Classify all inputs; streamed rows are provisional until this returns.

    Aggregate mode retains no real rows or queue entries. Its calibration graph
    follows the same append sequence as the execution representation.
    """
    if limit is not None and (type(limit) is not int or limit < 0):
        raise ValueError("invalid admission limit")
    names = tuple(stage.name for stage in stages)
    if len(set(names)) != len(names):
        raise ValueError("duplicate stage")
    if selected is not None:
        if (
            not selected
            or len(set(selected)) != len(selected)
            or not set(selected) <= set(names)
        ):
            raise ValueError("invalid stage selection")
        stages = tuple(stage for stage in stages if stage.name in selected)
    identities: set[str] = set()
    strings: dict[str, str] = {}
    origin_lookup: dict[tuple[str, str, str], tuple[str, str, str]] = {}
    origins = []
    rows: list[Row] = []
    queues = tuple(deque() for _ in stages)
    lifecycle = []
    tracking = tuple([] for _ in stages)
    counts = {admission: 0 for admission in Admission}
    queue_counts = [0] * len(stages)
    total = 0
    admitted = 0
    for item in inputs:
        if item.identity in identities:
            continue
        path = strings.setdefault(item.identity, item.identity)
        identities.add(path)
        origin_values = tuple(strings.setdefault(value, value) for value in item.origin)
        if origin_values not in origin_lookup:
            origin_lookup[origin_values] = origin_values
            origins.append(origin_values)
        origin = origin_lookup[origin_values]
        bypass = 0
        work = 0
        llm_work = False
        for i, stage in enumerate(stages):
            if predicted_bypass(stage, Path(path), config):
                bypass |= 1 << i
            else:
                work |= 1 << i
                potentially_executable = (
                    stage.name != "json"
                    or "desc" in (selected or names)
                    or _description_may_exist(Path(path))
                )
                llm_work |= stage.uses_llm and potentially_executable
        if not llm_work:
            admission = Admission.NO_LLM_WORK
        elif limit is None or admitted < limit:
            admission = Admission.ADMITTED
            admitted += 1
        else:
            admission = Admission.KNOWN_EXCLUDED
        counts[admission] += 1
        row = (path, origin, work, bypass, admission, 0)
        target, confirmation = route(row, stages)
        if stream is not None:
            stream(row, target, confirmation)
        total += 1
        if target is not None:
            queue_counts[target] += 1
        if not aggregate_only:
            rows.append(row)
            lifecycle.append(None)
            for slots in tracking:
                slots.append(None)
            if target is not None:
                queues[target].append((row, confirmation))
    if aggregate_only:
        # Size only: references/rows are shared placeholders, not retained plan data.
        calibration_rows = []
        calibration_lifecycle = []
        calibration_tracking = tuple([] for _ in stages)
        placeholder_row = (None, None, 0, 0, 0, 0)
        for _ in range(total):
            calibration_rows.append(placeholder_row)
            calibration_lifecycle.append(None)
            for slots in calibration_tracking:
                slots.append(None)
        calibration_queues = tuple(deque() for _ in stages)
        for q, count in zip(calibration_queues, queue_counts, strict=True):
            for _ in range(count):
                q.append((None, 0))
        estimate = _estimate(
            identities,
            origins,
            calibration_rows,
            calibration_queues,
            calibration_lifecycle,
            calibration_tracking,
        )
    else:
        estimate = _estimate(identities, origins, rows, queues, lifecycle, tracking)
    return Plan(
        rows, identities, origins, stages, queues, lifecycle, tracking, counts, estimate
    )
