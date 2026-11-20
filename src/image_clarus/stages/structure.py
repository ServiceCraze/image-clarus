"""Generate structured metadata from the persisted description."""

import hashlib
import json
import math
from pathlib import Path
from urllib.parse import unquote

from jsonschema import Draft202012Validator

from image_clarus import resources, schema_worker
from image_clarus.artifacts import ArtifactError
from image_clarus.config import ConfigurationError, _strict_json, _valid_tag_path
from image_clarus.providers.openai_compatible import ProviderError
from image_clarus.results import StageResult


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


def _pointer(parts):
    return "".join("/" + str(x).replace("~", "~0").replace("/", "~1") for x in parts)


def _schema_nodes(root):
    """Index every subschema object of the document to its true pointer."""
    nodes = {}

    def walk(node, tokens):
        if isinstance(node, dict):
            nodes.setdefault(id(node), tokens)
            for key, value in node.items():
                walk(value, tokens + (key,))
        elif isinstance(node, list):
            for position, value in enumerate(node):
                walk(value, tokens + (position,))

    walk(root, ())
    return nodes


def _anchor_pointer(root, anchor):
    """Locate the subschema declaring an $anchor."""
    pending = [((), root)]
    while pending:
        tokens, node = pending.pop()
        if isinstance(node, dict):
            if node.get("$anchor") == anchor:
                return tokens
            pending.extend((tokens + (key,), value) for key, value in node.items())
        elif isinstance(node, list):
            pending.extend(
                (tokens + (position,), value) for position, value in enumerate(node)
            )
    return None


def _resolve_ref(root, ref):
    """Resolve a same-document reference to (pointer tokens, subschema)."""
    seen = set()
    while isinstance(ref, str) and ref not in seen:
        seen.add(ref)
        ref = unquote(ref)
        if ref == "#":
            tokens, node = (), root
        elif ref.startswith("#/"):
            tokens = tuple(
                token.replace("~1", "/").replace("~0", "~")
                for token in ref[2:].split("/")
            )
            node = root
            for token in tokens:
                if isinstance(node, dict) and token in node:
                    node = node[token]
                elif isinstance(node, list) and token.isdigit():
                    node = node[int(token)]
                else:
                    return None
        else:
            tokens = _anchor_pointer(root, ref[1:])
            if tokens is None:
                return None
            node = root
            for token in tokens:
                node = node[token]
        if isinstance(node, dict) and "$ref" in node:
            ref = node["$ref"]
            continue
        return tokens, node
    return None


def _schema_pointer(schema, nodes, error):
    """Actual RFC 6901 pointer to the subschema that reported the error.

    jsonschema's absolute_schema_path records the referring side of every
    $ref it crossed (the $ref keyword itself is never appended), so that
    path alone can name a location that does not exist in the document.
    The failing keyword always sits under error.schema, the real subschema
    object from the document, so anchor the reported keyword there.
    """
    if hasattr(error, "_actual_boolean_schema_path"):
        return _pointer(error._actual_boolean_schema_path)
    reported = tuple(error.absolute_schema_path)
    tokens = nodes.get(id(error.schema))
    if tokens is not None and reported:
        keyword = error.validator
        if isinstance(error.schema, dict) and keyword in error.schema:
            return _pointer(tokens + (keyword,))
        return _pointer(tokens + (reported[-1],))
    # Boolean subschemas have no addressable object identity: replay the
    # reported walk, following local references as jsonschema did.
    node, walked = schema, ()
    for token in reported:
        if isinstance(node, dict) and token in node:
            walked, node = walked + (token,), node[token]
        else:
            return _pointer(reported)
    if isinstance(node, dict) and "$ref" in node:
        resolved = _resolve_ref(schema, node["$ref"])
        if resolved is not None and resolved[1] is error.schema:
            return _pointer(resolved[0])
    return _pointer(reported)


def _feedback(schema, errors):
    nodes = _schema_nodes(schema)
    entries = sorted(
        {
            (
                _pointer(e.absolute_path),
                _schema_pointer(schema, nodes, e),
                str(e.validator),
            )
            for e in errors
        }
    )
    return {
        "kind": "schema_validation",
        "total_errors": len(entries),
        "truncated": len(entries) > 20,
        "errors": [
            {"instance_path": a, "schema_path": b, "keyword": c}
            for a, b, c in entries[:20]
        ],
    }


def _valid_description(data):
    try:
        return bool(data.decode("utf-8").strip())
    except UnicodeError:
        return False


def _valid_envelope(data):
    try:
        value = _strict_json(_Snapshot(data))
        return Draft202012Validator(_ENVELOPE).is_valid(value)
    except ConfigurationError:
        return False


def run_structure(image_path, config, services):
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
            return StageResult(
                "json", "failed", error_category=error.category, message=str(error)
            )
        exists = True
    if exists and not regenerate:
        return StageResult(
            "json", "skipped", output_path=output, reason_code="output_exists"
        )
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
    history = []
    metadata = None
    for attempt in range(retries + 1):
        try:
            content = services.provider_factory(
                config["providers"][provider_alias], model
            ).structured(
                prompt=prompt,
                description=description,
                schema=schema,
                effort=settings["reasoning_effort"],
                history=history,
                preferred_categories=preferred_categories,
            )
        except ProviderError as error:
            return StageResult("json", "failed", error_category=error.category)
        try:
            metadata = _parse(content)
        except _ParseError as error:
            feedback = {"kind": "json_parse", "code": str(error)}
        else:
            validation = schema_worker.validate(
                schema_text, metadata, timeout=schema_worker.SCHEMA_TIMEOUT_SECONDS
            )
            if validation.get("status") == "ok":
                break
            if validation.get("status") != "invalid_instance":
                return StageResult("json", "failed", error_category="configuration")
            feedback = validation["feedback"]
        if attempt == retries:
            return StageResult("json", "failed", error_category="schema_validation")
        history.append((content, feedback))
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
        return StageResult("json", "failed", error_category="configuration")
    data = (
        json.dumps(
            envelope, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False
        )
        + "\n"
    ).encode("utf-8")
    try:
        services.artifacts.write(
            output, data, _valid_envelope, validation_category="configuration"
        )
    except ArtifactError as error:
        return StageResult(
            "json", "failed", error_category=error.category, message=str(error)
        )
    return StageResult("json", "completed", output_path=output)
