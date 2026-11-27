"""Metadata capabilities of the fixed stages.

These predicates predict work only; they do not validate or recover artifacts.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class StageDescriptor:
    name: str
    uses_llm: bool
    skip_if_valid_output_exists: bool
    predicted_output_exists: Callable[[Path], bool]
    # A stage may expose a resumable seam or only its existing synchronous run.
    # Resolve lazily so planning never imports execution or provider machinery.
    module: str | None = None
    run_name: str | None = None
    resumable: bool = False
    # False means definitely unavailable; True includes uncertain metadata.
    # Upstream names are selected stages preceding this descriptor in order.
    predicted_prerequisites: Callable[[Path, tuple[str, ...]], bool] | None = None

    @property
    def inspect(self) -> Callable | None:
        return (
            import_module(self.module).inspect
            if self.resumable and self.module
            else None
        )

    @property
    def start_or_resume(self) -> Callable | None:
        return (
            import_module(self.module).start_or_resume
            if self.resumable and self.module
            else None
        )

    @property
    def run(self) -> Callable | None:
        return (
            getattr(import_module(self.module), self.run_name)
            if self.module and self.run_name
            else None
        )


def _sidecar(suffix: str) -> Callable[[Path], bool]:
    return lambda image: Path(str(image) + suffix).exists()


def _never(_image: Path) -> bool:
    return False


def _structure_prerequisites(image: Path, upstream: tuple[str, ...]) -> bool:
    """Predict without validating, recovering, or reading sidecar content."""
    if "desc" in upstream:
        return True
    for suffix in (".desc.txt", ".desc.txt.bak"):
        try:
            Path(str(image) + suffix).lstat()
        except FileNotFoundError:
            continue
        except OSError:
            return True
        return True
    return False


STAGES = (
    StageDescriptor(
        "desc",
        True,
        True,
        _sidecar(".desc.txt"),
        "image_clarus.stages.description",
        "run_description",
        True,
    ),
    StageDescriptor(
        "json",
        True,
        True,
        _sidecar(".desc.json"),
        "image_clarus.stages.structure",
        "run_structure",
        True,
        _structure_prerequisites,
    ),
    StageDescriptor(
        "xmp",
        False,
        False,
        _never,
        "image_clarus.stages.xmp",
        "run_xmp",
        True,
    ),
)


def predicted_bypass(
    stage: StageDescriptor, image: Path, config: Mapping[str, Any]
) -> bool:
    return (
        stage.skip_if_valid_output_exists
        and not config["stages"][stage.name]["regenerate"]
        and stage.predicted_output_exists(image)
    )
