"""Fixed stage ordering and single-image coordination.

Stage implementations are supplied by the caller.
"""

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from image_clarus.results import PipelineResult, StageResult

STAGE_REGISTRY = ("desc", "json", "xmp")
Stage = Callable[[Path, Mapping[str, Any], Any], StageResult]


class StopToken:
    """Cooperative signal state shared with the caller and stage services."""

    def __init__(self) -> None:
        self.signum: int | None = None

    def request(self, signum: int) -> None:
        if signum not in (2, 15):
            raise ValueError("unsupported stop signal")
        if self.signum is None:
            self.signum = signum


def run_pipeline(
    image_path: Path,
    config: Mapping[str, Any],
    services: Any,
    stages: Mapping[str, Stage],
    *,
    selected: tuple[str, ...] | None = None,
    stop: StopToken | None = None,
) -> PipelineResult:
    if selected is not None:
        if (
            not selected
            or len(set(selected)) != len(selected)
            or not set(selected) <= set(STAGE_REGISTRY)
        ):
            raise ValueError("invalid stage selection")
        names = tuple(name for name in STAGE_REGISTRY if name in selected)
    else:
        names = STAGE_REGISTRY
    if any(name not in stages or not callable(stages[name]) for name in names):
        raise ValueError("selected stage implementation is unavailable")
    results = []
    stopped = False
    policy = config.get("pipeline", {}).get("on_stage_failure", "stop")
    for name in names:
        if stop is not None and stop.signum is not None:
            result = StageResult(name, "skipped", reason_code="interrupted")
        elif stopped:
            result = StageResult(
                name, "skipped", reason_code="stage_not_run_after_failure"
            )
        else:
            result = stages[name](image_path, config, services)
            stopped = result.status == "failed" and policy == "stop"
        results.append(result)
    return PipelineResult(image_path, tuple(results), stop.signum if stop else None)
