"""Deterministic XMP planning and recoverable sidecar publication."""

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

from jsonschema import Draft202012Validator

from image_clarus import resources
from image_clarus.artifacts import ArtifactError
from image_clarus.config import ConfigurationError, _strict_json, _valid_tag_segment
from image_clarus.results import StageResult
from image_clarus.stages.structure import _ENVELOPE, _Snapshot, _valid_envelope
from image_clarus.xmp_backend import FIELDS, ExifToolBackend, XmpBackendError

_CUSTOM_ID = "urn:image-clarus:custom-metadata-schema"
_BUILTIN_ID = "urn:image-clarus:metadata-schema:"


@dataclass(frozen=True)
class XmpPlan:
    updates: dict
    effective_tag_policy: str
    status: str = "ready"
    reason_code: str | None = None
    error_category: str | None = None


def _publication_fields(json_bytes, settings):
    """Validate the fixed envelope and derive only explicitly supported fields."""
    if not isinstance(json_bytes, bytes):
        raise TypeError
    # Decode explicitly: json.loads(bytes) also accepts UTF-16/32, contrary to A4.
    json_bytes.decode("utf-8")
    envelope = _strict_json(_Snapshot(json_bytes))
    if not Draft202012Validator(_ENVELOPE).is_valid(envelope):
        raise ValueError
    identity = (envelope["schema_id"], envelope["schema_version"])
    metadata = envelope["metadata"]
    if identity in {(_BUILTIN_ID + "1.0.0", "1.0.0"), (_BUILTIN_ID + "2.0.0", "2.0.0")}:
        path = (
            resources.structure_schema_v1()
            if identity[1] == "1.0.0"
            else resources.structure_schema()
        )
        schema = json.loads(path.read_text(encoding="utf-8"))
        if not Draft202012Validator(schema).is_valid(metadata):
            raise ValueError
        if identity[1] == "1.0.0":
            return None, None, []
        title, caption, paths = (
            metadata["title"],
            metadata["caption"],
            metadata["tag_candidates"],
        )
    elif identity[0] == _CUSTOM_ID and re.fullmatch(
        r"custom-sha256:[0-9a-f]{64}", identity[1]
    ):

        def mapped(role):
            name = settings["custom_" + role + "_property"]
            return metadata[name] if name is not None and name in metadata else _MISSING

        title, caption, paths = mapped("title"), mapped("caption"), mapped("tags")
        for text in (title, caption):
            if text is not _MISSING:
                if not isinstance(text, str) or "\x00" in text:
                    raise ValueError
                os.fsencode(text)
        if paths is _MISSING:
            paths = []
        elif not isinstance(paths, list):
            raise ValueError
    else:
        raise ValueError
    unique = []
    seen = set()
    for path in paths:
        if (
            not isinstance(path, list)
            or not path
            or not all(_valid_tag_segment(part) for part in path)
        ):
            raise ValueError
        key = tuple(path)
        if key not in seen:
            seen.add(key)
            unique.append(key)
    return title, caption, unique


_MISSING = object()


def prepare_updates(
    json_bytes, snapshot, settings, directory, *, missing_prerequisite="fail"
):
    """Compute updates from persisted bytes, without invoking a model or writing files.

    ``None`` JSON means an absent prerequisite. The calling stage owns file
    discovery, recovery, publication, and conversion to a stage result.
    Settings are the already-resolved, validated XMP configuration.
    """
    root = settings["tag_root"]
    effective = settings["tag_policy"]
    if root == "" and effective != "disabled":
        effective = "add"
    if json_bytes is None:
        if missing_prerequisite == "skip":
            return XmpPlan({}, effective, "skipped", reason_code="missing_prerequisite")
        return XmpPlan({}, effective, "failed", error_category="missing_prerequisite")
    try:
        title, caption, paths = _publication_fields(json_bytes, settings)
        before = ExifToolBackend(directory).read(snapshot)
        selected = [
            "/".join((root, *path) if root else path)
            for path in paths[: settings["tag_limit"]]
        ]
        existing = before["tags"]
        updates = {}
        if selected and effective != "disabled":
            belongs = lambda tag: tag == root or tag.startswith(root + "/")
            # Do not remove malformed owned assignments by interpreting them
            # as valid hierarchy paths.
            if (
                root
                and effective in {"new", "overwrite"}
                and any(
                    belongs(tag)
                    and not all(_valid_tag_segment(part) for part in tag.split("/"))
                    for tag in existing
                )
            ):
                raise ValueError
            if effective == "new" and any(belongs(tag) for tag in existing):
                selected = []
            retained = [
                tag
                for tag in existing
                if not (effective == "overwrite" and belongs(tag))
            ]
            merged = retained + [tag for tag in selected if tag not in retained]
            if selected and merged != existing:
                updates["tags"] = merged
        for field, value, policy_key in (
            ("title", title, "title_policy"),
            ("caption", caption, "caption_policy"),
            ("author", settings["caption_author"], "caption_author_policy"),
        ):
            mode = settings[policy_key]
            if value is _MISSING or value is None or value == "" or mode == "disabled":
                continue
            if not isinstance(value, str):
                raise TypeError
            prop = before["properties"].get(FIELDS[field][0])
            occupied = prop is not None and any(text != "" for _, text in prop[1])
            if mode == "new" and occupied:
                continue
            if before[field] != value:
                # ExifTool receives argv, not JSON: reject NUL/unencodable values.
                if "\x00" in value:
                    raise ValueError
                os.fsencode(value)
                updates[field] = value
        if not updates:
            return XmpPlan({}, effective, "skipped", reason_code="no_change")
        return XmpPlan(updates, effective)
    except (ConfigurationError, UnicodeError, TypeError, ValueError, XmpBackendError):
        return XmpPlan({}, effective, "failed", error_category="invalid_artifact")
    except OSError:
        return XmpPlan({}, effective, "failed", error_category="file_io")


def _guard_aliases(paths):
    """Reject existing hard links and resolved (including dangling) symlink aliases."""
    resolved = [path.resolve() for path in paths]
    if len(set(resolved)) != len(resolved):
        raise ValueError("unsafe artifact alias")
    identities = set()
    for path in paths:
        try:
            info = path.stat()
        except FileNotFoundError:
            continue
        identity = (info.st_dev, info.st_ino)
        if identity in identities:
            raise ValueError("unsafe artifact alias")
        identities.add(identity)


def _interrupted(services):
    stop = getattr(services, "stop", None)
    return stop is not None and stop.signum is not None


def run_xmp(image_path, config, services):
    """Read persisted JSON, recover XMP, plan and safely publish a sidecar."""
    image = Path(image_path)
    source = Path(str(image) + ".desc.json")
    output = Path(str(image) + ".xmp")
    paths = (
        image,
        source,
        Path(str(source) + ".bak"),
        output,
        Path(str(output) + ".bak"),
    )
    backend = ExifToolBackend(output.parent)
    policy = config["pipeline"]["missing_prerequisite"]
    try:
        if _interrupted(services):
            return StageResult("xmp", "skipped", reason_code="interrupted")
        _guard_aliases(paths)
        exists = services.artifacts.recover(source, _valid_envelope)
        if _interrupted(services):
            return StageResult("xmp", "skipped", reason_code="interrupted")
        if not exists:
            if policy == "skip":
                return StageResult("xmp", "skipped", reason_code="missing_prerequisite")
            return StageResult("xmp", "failed", error_category="missing_prerequisite")
        json_bytes = source.read_bytes()
        if _interrupted(services):
            return StageResult("xmp", "skipped", reason_code="interrupted")
        _guard_aliases(paths)
        exists = services.artifacts.recover(output, backend.validate)
        snapshot = output.read_bytes() if exists else None
        plan = prepare_updates(
            json_bytes, snapshot, config["stages"]["xmp"], output.parent
        )
        if _interrupted(services):
            return StageResult("xmp", "skipped", reason_code="interrupted")
        if plan.status != "ready":
            return StageResult(
                "xmp",
                plan.status,
                output_path=output
                if plan.reason_code == "no_change" and exists
                else None,
                reason_code=plan.reason_code,
                error_category=plan.error_category,
                message=(
                    "Invalid or incompatible JSON or XMP artifact"
                    if plan.error_category == "invalid_artifact"
                    else "XMP artifact read failed"
                    if plan.error_category == "file_io"
                    else "Effective tag policy: " + plan.effective_tag_policy
                ),
            )
        candidate = backend.transform(snapshot, plan.updates)
        if _interrupted(services):
            return StageResult("xmp", "skipped", reason_code="interrupted")
        _guard_aliases(paths)
        services.artifacts.write(output, candidate, backend.validate)
        return StageResult(
            "xmp",
            "completed",
            output_path=output,
            message="Effective tag policy: " + plan.effective_tag_policy,
        )
    except ArtifactError as error:
        if error.category == "interrupted" or _interrupted(services):
            return StageResult("xmp", "skipped", reason_code="interrupted")
        return StageResult(
            "xmp",
            "failed",
            error_category=error.category,
            message="XMP artifact operation failed",
        )
    except XmpBackendError as error:
        if _interrupted(services):
            return StageResult("xmp", "skipped", reason_code="interrupted")
        category = (
            "file_io"
            if str(error) in {"ExifTool timeout", "XMP working file failure"}
            else "invalid_artifact"
        )
        return StageResult(
            "xmp",
            "failed",
            error_category=category,
            message="ExifTool timeout"
            if str(error) == "ExifTool timeout"
            else "XMP transformation failed",
        )
    except (OSError, ValueError, RuntimeError):
        if _interrupted(services):
            return StageResult("xmp", "skipped", reason_code="interrupted")
        return StageResult(
            "xmp",
            "failed",
            error_category="file_io",
            message="XMP artifact path or file operation failed",
        )
