"""Resolve the canonical built-in description prompt."""

from importlib.resources import files
from pathlib import Path


def description_prompt():
    packaged = files("image_clarus").joinpath(
        "resources", "prompts", "image-description.txt"
    )
    if packaged.is_file():
        return packaged
    source = Path(__file__).resolve().parents[2] / "prompts" / "image-description.txt"
    if source.is_file():
        return source
    raise FileNotFoundError("Built-in image description prompt is unavailable")
