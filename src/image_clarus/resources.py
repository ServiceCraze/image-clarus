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


def structure_prompt():
    packaged = files("image_clarus").joinpath(
        "resources", "prompts", "image-structure.txt"
    )
    if packaged.is_file():
        return packaged
    source = Path(__file__).resolve().parents[2] / "prompts" / "image-structure.txt"
    if source.is_file():
        return source
    raise FileNotFoundError("Built-in image structure prompt is unavailable")


def structure_schema():
    packaged = files("image_clarus").joinpath(
        "resources", "schemas", "image-structure.schema.json"
    )
    if packaged.is_file():
        return packaged
    source = (
        Path(__file__).resolve().parents[2] / "schemas" / "image-structure.schema.json"
    )
    if source.is_file():
        return source
    raise FileNotFoundError("Built-in image structure schema is unavailable")


def structure_schema_v1():
    """Return the historical 1.0.0 built-in schema resource."""
    packaged = files("image_clarus").joinpath(
        "resources", "schemas", "image-structure-v1.schema.json"
    )
    if packaged.is_file():
        return packaged
    source = (
        Path(__file__).resolve().parents[2]
        / "schemas"
        / "image-structure-v1.schema.json"
    )
    if source.is_file():
        return source
    raise FileNotFoundError("Built-in image structure schema v1 is unavailable")
