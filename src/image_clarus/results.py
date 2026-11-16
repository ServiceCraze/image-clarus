"""Structured outcomes for a single-image pipeline run."""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal


@dataclass(frozen=True)
class StageResult:
    stage: str
    status: Literal["completed", "skipped", "failed"]
    output_path: Path | None = None
    reason_code: str | None = None
    error_category: str | None = None
    message: str = ""


@dataclass(frozen=True)
class PipelineResult:
    image_path: Path
    stages: tuple[StageResult, ...]
    interrupted_by: int | None = None

    @property
    def exit_code(self) -> int:
        if self.interrupted_by is not None:
            return 128 + self.interrupted_by
        return 1 if any(stage.status == "failed" for stage in self.stages) else 0
