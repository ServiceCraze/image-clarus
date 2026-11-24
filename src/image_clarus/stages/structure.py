"""Generate structured metadata from the persisted description."""

import hashlib
import json
import math
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from uuid import uuid4

from jsonschema import Draft202012Validator

from image_clarus import resources, schema_worker
from image_clarus.artifacts import ArtifactError
from image_clarus.config import ConfigurationError, _strict_json, _valid_tag_path
from image_clarus.results import StageResult
from image_clarus.schema_feedback import (
    _anchor_pointer as _anchor_pointer,  # noqa: PLC0414
)
from image_clarus.schema_feedback import (
    _feedback as _feedback,  # noqa: PLC0414
)
from image_clarus.schema_feedback import (
    _pointer as _pointer,  # noqa: PLC0414
)
from image_clarus.schema_feedback import (
    _resolve_ref as _resolve_ref,  # noqa: PLC0414
)
from image_clarus.schema_feedback import (
    _schema_nodes as _schema_nodes,  # noqa: PLC0414
)
from image_clarus.schema_feedback import (
    _schema_pointer as _schema_pointer,  # noqa: PLC0414
)
from image_clarus.stage_protocol import (
    ProviderResult,
    PublicationResult,
    Publish,
    Request,
    Terminal,
    WorkRequired,
    drive,
)


class _Snapshot:
    def __init__(self, data):
        self.data = data

    def read_text(self, encoding):
        return self.data.decode(encoding)


def _hash(data):
    return hashlib.sha256(data).hexdigest()


_PROVENANCE = (
    "provider_alias",
    "model_alias",
    "model_id",
    "prompt_id",
    "prompt_sha256",
    "description_sha256",
)
_ENVELOPE = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "format_version",
        "schema_id",
        "schema_version",
        "provenance",
        "metadata",
    ],
    "properties": {
        "format_version": {"type": "integer", "const": 1},
        "schema_id": {"type": "string", "minLength": 1},
        "schema_version": {"type": "string", "minLength": 1},
        "metadata": {"type": "object"},
        "provenance": {
            "type": "object",
            "additionalProperties": False,
            "required": [key for key in _PROVENANCE if key != "prompt_sha256"],
            "properties": {
                key: (
                    {
                        "type": "string",
                        "pattern": "^[0-9a-f]{64}$",
                        **(
                            {"minLength": 64, "maxLength": 64}
                            if key == "prompt_sha256"
                            else {}
                        ),
                    }
                    if key.endswith("_sha256")
                    else {"type": "string", "minLength": 1}
                )
                for key in _PROVENANCE
            },
        },
    },
}


class _ParseError(ValueError):
    pass


def _parse(content):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise _ParseError("duplicate_key")
            result[key] = value
        return result

    def constant(_):
        raise _ParseError("non_finite_number")

    try:
        value = json.loads(content, object_pairs_hook=pairs, parse_constant=constant)
        pending = [value]
        while pending:
            item = pending.pop()
            if isinstance(item, str):
                item.encode("utf-8")
            elif isinstance(item, float) and not math.isfinite(item):
                raise _ParseError("non_finite_number")
            elif isinstance(item, dict):
                pending.extend(item.keys())
                pending.extend(item.values())
            elif isinstance(item, list):
                pending.extend(item)
        return value
    except UnicodeError:
        raise _ParseError("invalid_unicode") from None
    except (json.JSONDecodeError, RecursionError):
        raise _ParseError("invalid_json") from None
    except ValueError as error:
        # Python 3.11+ int(max_str_digits) limit
        if isinstance(error, _ParseError):
            raise
        raise _ParseError("invalid_json") from None


def _valid_description(data):
    try:
        return bool(data.decode("utf-8").strip())
    except UnicodeError:
        return False


def _read_envelope(data):
    data.decode("utf-8")
    value = _strict_json(_Snapshot(data))
    if not Draft202012Validator(_ENVELOPE).is_valid(value):
        raise ValueError
    return value


def _valid_envelope(data):
    try:
        _read_envelope(data)
        return True
    except (ConfigurationError, UnicodeError, ValueError):
        return False


@dataclass
class _Context:
    image: Path
    config: dict
    services: object
    output: Path
    phase: str = "start"
    request_id: tuple | None = None
    publication_id: str | None = None
    validation_category: str = "configuration"
    history: list = field(default_factory=list)
    attempt: int = 0
    snapshot: dict = field(default_factory=dict)


def inspect(image_path, config, services, *, inference_allowed=True):
    image = Path(image_path)
    output = Path(str(image) + ".desc.json")
    settings = config["stages"]["json"]
    regenerate = settings["regenerate"]
    try:
        exists = services.artifacts.recover(
            output, _valid_envelope, retain_backup=regenerate
        )
    except ArtifactError as error:
        if not (regenerate and error.category == "invalid_artifact"):
            return Terminal(
                StageResult(
                    "json", "failed", error_category=error.category, message=str(error)
                )
            )
        exists = True
    if exists and not regenerate:
        return Terminal(
            StageResult(
                "json", "skipped", output_path=output, reason_code="output_exists"
            )
        )
    if not inference_allowed:
        return Terminal(StageResult("json", "skipped", reason_code="budget_excluded"))
    return WorkRequired(
        "json", image, _Context(image, deepcopy(config), services, output)
    )


def _prepare(context):
    image, config, services = context.image, context.config, context.services
    settings = config["stages"]["json"]
    description_path = Path(str(image) + ".desc.txt")
    try:
        if not description_path.exists():
            services.artifacts.recover(description_path, _valid_description)
        description_bytes = description_path.read_bytes()
        if not _valid_description(description_bytes):
            return StageResult("json", "failed", error_category="invalid_artifact")
        description = description_bytes.decode("utf-8")
    except ArtifactError as error:
        return StageResult(
            "json", "failed", error_category=error.category, message=str(error)
        )
    except FileNotFoundError:
        if config["pipeline"]["missing_prerequisite"] == "skip":
            return StageResult("json", "skipped", reason_code="missing_prerequisite")
        return StageResult("json", "failed", error_category="missing_prerequisite")
    except OSError:
        return StageResult("json", "failed", error_category="file_io")
    try:
        prompt_bytes = (
            settings["prompt_file"] or resources.structure_prompt()
        ).read_bytes()
        prompt = prompt_bytes.decode("utf-8")
        schema_bytes = (
            settings["schema_file"] or resources.structure_schema()
        ).read_bytes()
        snapshot = _Snapshot(schema_bytes)
        schema_text = schema_bytes.decode("utf-8")
        checked = schema_worker.preflight(
            schema_text, timeout=schema_worker.SCHEMA_TIMEOUT_SECONDS
        )
        if checked.get("status") != "ok":
            return StageResult("json", "failed", error_category="configuration")
        schema = _strict_json(snapshot)
    except (OSError, UnicodeError, ConfigurationError):
        return StageResult("json", "failed", error_category="configuration")
    model_alias = settings["model"]
    model = config["models"][model_alias]
    provider_alias = model["provider"]
    retries = settings["validation_retries"]
    if type(retries) is not int or retries not in (0, 1, 2):
        return StageResult("json", "failed", error_category="configuration")
    preferred_categories = settings.get("preferred_categories", [])
    if not isinstance(preferred_categories, list):
        return StageResult("json", "failed", error_category="configuration")
    preferred_categories = preferred_categories.copy()
    if not all(_valid_tag_path(item) for item in preferred_categories) or len(
        preferred_categories
    ) != len(set(preferred_categories)):
        return StageResult("json", "failed", error_category="configuration")
    try:
        # Deferred: XMP and schema-worker imports must not initialize expansion.
        from image_clarus.prompt_expansion import expand_prompt, safe_config_snapshot

        prompt = expand_prompt(
            prompt,
            safe_config_snapshot(config),
            getattr(services, "state", None),
            config.get("prompt_expansion", {}).get("macros", {}),
        )
    except ConfigurationError:
        return StageResult("json", "failed", error_category="configuration")
    context.snapshot = {
        "prompt": prompt,
        "prompt_bytes": prompt_bytes,
        "description": description,
        "description_bytes": description_bytes,
        "schema": schema,
        "schema_text": schema_text,
        "schema_bytes": schema_bytes,
        "model_alias": model_alias,
        "provider_alias": provider_alias,
        "model": model,
        "provider": config["providers"][provider_alias],
        "retries": retries,
        "settings": settings,
    }
    return None


def _request(context):
    snap = context.snapshot
    context.request_id = (str(context.image), "json", context.attempt, uuid4().hex)
    context.phase = "request"
    return Request(
        context.request_id,
        "structured",
        {
            "provider": deepcopy(snap["provider"]),
            "model": deepcopy(snap["model"]),
            "arguments": {
                "prompt": snap["prompt"],
                "description": snap["description"],
                "schema": deepcopy(snap["schema"]),
                "effort": snap["settings"]["reasoning_effort"],
                "history": deepcopy(context.history),
            },
        },
        context,
    )


def start_or_resume(context, provider_result):
    if context.phase == "start":
        if provider_result is not None:
            raise ValueError("unexpected stage result")
        checked = inspect(context.image, context.config, context.services)
        if isinstance(checked, Terminal):
            context.phase = "done"
            return checked
        result = _prepare(context)
        if result is not None:
            context.phase = "done"
            return Terminal(result)
        return _request(context)
    if context.phase == "publish":
        if (
            not isinstance(provider_result, PublicationResult)
            or provider_result.publication_id != context.publication_id
        ):
            raise ValueError("stale or invalid publication result")
        context.phase = "done"
        if provider_result.error:
            error = provider_result.error
            if error.category == "interrupted":
                return Terminal(
                    StageResult("json", "skipped", reason_code="interrupted")
                )
            return Terminal(
                StageResult(
                    "json", "failed", error_category=error.category, message=str(error)
                )
            )
        return Terminal(StageResult("json", "completed", output_path=context.output))
    if context.phase != "request":
        raise ValueError("continuation already consumed")
    if (
        not isinstance(provider_result, ProviderResult)
        or provider_result.request_id != context.request_id
    ):
        raise ValueError("stale or invalid provider result")
    if provider_result.error_category:
        context.phase = "done"
        if provider_result.error_category == "interrupted":
            return Terminal(StageResult("json", "skipped", reason_code="interrupted"))
        return Terminal(
            StageResult("json", "failed", error_category=provider_result.error_category)
        )
    content = provider_result.content
    try:
        metadata = _parse(content)
    except (TypeError, _ParseError) as error:
        feedback = {
            "kind": "json_parse",
            "code": str(error) if isinstance(error, _ParseError) else "invalid_json",
        }
    else:
        validation = schema_worker.validate(
            context.snapshot["schema_text"],
            metadata,
            timeout=schema_worker.SCHEMA_TIMEOUT_SECONDS,
        )
        if validation.get("status") == "ok":
            return _publish(context, metadata)
        if validation.get("status") != "invalid_instance":
            context.phase = "done"
            return Terminal(
                StageResult("json", "failed", error_category="configuration")
            )
        feedback = validation["feedback"]
    if context.attempt == context.snapshot["retries"]:
        context.phase = "done"
        return Terminal(
            StageResult("json", "failed", error_category="schema_validation")
        )
    context.history.append((content, feedback))
    context.attempt += 1
    return _request(context)


def _publish(context, metadata):
    snap = context.snapshot
    settings, model = snap["settings"], snap["model"]
    provider_alias, model_alias = snap["provider_alias"], snap["model_alias"]
    schema_bytes, description_bytes, prompt_bytes = (
        snap["schema_bytes"],
        snap["description_bytes"],
        snap["prompt_bytes"],
    )
    envelope = {
        "format_version": 1,
        "schema_id": "urn:image-clarus:custom-metadata-schema"
        if settings["schema_file"]
        else "urn:image-clarus:metadata-schema:2.0.0",
        "schema_version": "custom-sha256:" + _hash(schema_bytes)
        if settings["schema_file"]
        else "2.0.0",
        "metadata": metadata,
        "provenance": {
            "provider_alias": provider_alias,
            "model_alias": model_alias,
            "model_id": model["model_id"],
            "prompt_id": "custom"
            if settings["prompt_file"]
            else "builtin:image-structure",
            "description_sha256": _hash(description_bytes),
        },
    }
    if settings.get("include_prompt_sha256", False):
        envelope["provenance"]["prompt_sha256"] = _hash(prompt_bytes)
    if not Draft202012Validator(_ENVELOPE).is_valid(envelope):
        context.phase = "done"
        return Terminal(StageResult("json", "failed", error_category="configuration"))
    data = (
        json.dumps(
            envelope, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False
        )
        + "\n"
    ).encode("utf-8")
    context.publication_id = uuid4().hex
    context.phase = "publish"
    return Publish(context.publication_id, data, _valid_envelope, context)


def run_structure(image_path, config, services):
    import sys

    step = inspect(image_path, config, services)
    return (
        step.result
        if isinstance(step, Terminal)
        else drive(sys.modules[__name__], step, services)
    )
