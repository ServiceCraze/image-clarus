"""Configuration discovery, layering, and selected-stage preflight."""

import json
import math
import os
import re
import sys
from copy import deepcopy
from pathlib import Path

import yaml
from jsonschema import (
    Draft3Validator,
    Draft4Validator,
    Draft6Validator,
    Draft7Validator,
    Draft201909Validator,
    Draft202012Validator,
)
from jsonschema.exceptions import SchemaError
from jsonschema.validators import validator_for
from referencing import Registry, Resource
from referencing.exceptions import Unresolvable
from referencing.jsonschema import (
    DRAFT3,
    DRAFT4,
    DRAFT6,
    DRAFT7,
    DRAFT201909,
    DRAFT202012,
    lookup_recursive_ref,
)

from image_clarus.endpoint import validate_base_url


class ConfigurationError(ValueError):
    """A sanitized preflight failure with a stable category."""

    def __init__(self, message, category="configuration"):
        if category == "configuration" and not message.startswith(
            ("Invalid configuration", "Cannot load configuration")
        ):
            message = f"Invalid configuration: {message}"
        super().__init__(message)
        self.category = category


class UniqueSafeLoader(yaml.SafeLoader):
    """Safe YAML loader rejecting duplicate mapping keys."""

    def construct_mapping(self, node, deep=False):
        self.flatten_mapping(node)
        keys = set()
        for key_node, _ in node.value:
            key = self.construct_object(key_node, deep=deep)
            try:
                if key in keys:
                    raise ConfigurationError(
                        f"configuration: duplicate YAML key at line {key_node.start_mark.line + 1}, column {key_node.start_mark.column + 1}; remove the duplicate key"
                    )
                keys.add(key)
            except TypeError:
                raise ConfigurationError(
                    f"configuration: invalid YAML mapping key at line {key_node.start_mark.line + 1}, column {key_node.start_mark.column + 1}; replace it with a scalar key"
                ) from None
        return super().construct_mapping(node, deep=deep)


EFFORTS = {
    "default",
    "off",
    "minimal",
    "low",
    "medium",
    "high",
    "extra_high",
    "max",
    "ultra",
}
ALIAS = re.compile(r"^[A-Za-z0-9_-]+$")
ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
DEFAULTS = {
    "providers": {},
    "models": {},
    "stages": {
        "desc": {
            "model": None,
            "prompt_file": None,
            "reasoning_effort": None,
            "regenerate": False,
        },
        "json": {
            "model": None,
            "prompt_file": None,
            "schema_file": None,
            "reasoning_effort": None,
            "regenerate": False,
            "validation_retries": 0,
        },
    },
    "pipeline": {
        "missing_prerequisite": "fail",
        "on_stage_failure": "stop",
        "backup_retention": "remove",
    },
    "logging": {"level": "WARNING"},
}
PROVIDER_FIELDS = {
    "base_url",
    "api_key",
    "api_key_env",
    "timeout_seconds",
    "reasoning_effort_mapping",
}
MODEL_FIELDS = {"provider", "model_id", "reasoning_effort", "reasoning_effort_mapping"}
PATH_FIELDS = {
    ("stages", "desc", "prompt_file"),
    ("stages", "json", "prompt_file"),
    ("stages", "json", "schema_file"),
}


def _valid_utf8_text(value):
    if not isinstance(value, str):
        return False
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True


def _valid_header_credential(value):
    if not isinstance(value, str):
        return False
    try:
        encoded = value.encode("latin-1")
    except UnicodeEncodeError:
        return False
    return all(byte >= 32 and byte != 127 for byte in encoded)


def discovery_locations(platform=None, environ=None, home=None):
    """Return OS-specific user and system config paths without touching them."""
    platform = sys.platform if platform is None else platform
    environ = os.environ if environ is None else environ
    home = Path.home() if home is None else Path(home)
    if platform == "darwin":
        return (
            home / "Library/Application Support/image-clarus/config.yaml",
            Path("/Library/Application Support/image-clarus/config.yaml"),
        )
    if platform == "win32":
        paths = []
        for name in ("APPDATA", "PROGRAMDATA"):
            if environ.get(name):
                paths.append(Path(environ[name]) / "image-clarus" / "config.yaml")
        return tuple(paths)
    return (
        home / ".config/image-clarus/config.yaml",
        Path("/etc/image-clarus/config.yaml"),
    )


def _fail():
    raise ConfigurationError("Invalid configuration")


def _override_path(parts):
    """Only disclose schema-owned segments; aliases and unknown input are private."""
    if not parts or parts[0] not in DEFAULTS:
        return "<unknown>"
    root = parts[0]
    safe = [root]
    rest = parts[1:]
    if root in {"providers", "models"} and rest:
        safe.append("<name>")
        rest = rest[1:]
        allowed = PROVIDER_FIELDS if root == "providers" else MODEL_FIELDS
    else:
        allowed = DEFAULTS[root]
    for part in rest:
        if part not in allowed:
            break
        safe.append(part)
        if root == "stages" and len(safe) == 2:
            allowed = DEFAULTS["stages"][part]
        elif part == "reasoning_effort_mapping":
            allowed = {"parameter", "values"}
        elif part == "values":
            allowed = EFFORTS - {"default"}
        else:
            allowed = {}
    return ".".join(safe)


def _with_relevant_overrides(error, override_paths):
    """Add only override paths overlapping the sanitized diagnostic field."""
    message = str(error)
    field = message.removeprefix("Invalid configuration: ").split(":", 1)[0]
    relevant = [
        path
        for path in dict.fromkeys(override_paths)
        if path == field or path.startswith(field + ".") or field.startswith(path + ".")
    ]
    if relevant:
        return ConfigurationError(
            f"{message}; override paths: {', '.join(relevant)}", error.category
        )
    return error


def _mapping(value, fields, path="configuration"):
    if not isinstance(value, dict):
        raise ConfigurationError(
            f"{path}: expected a mapping; replace it with a mapping"
        )
    if any(not isinstance(k, str) or k not in fields for k in value):
        raise ConfigurationError(f"{path}: unknown key; remove the unknown key")


def _merge(target, source):
    for key, value in source.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _merge(target[key], value)
        else:
            target[key] = deepcopy(value)


def _path(value, base):
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        _fail()
    try:
        return (base / Path(value).expanduser()).resolve()
    except (OSError, RuntimeError, ValueError):
        raise ConfigurationError("Invalid configuration path") from None


def _normalize_paths(data, base):
    for root, stage, field in PATH_FIELDS:
        stages = data.get(root, {})
        if not isinstance(stages, dict):
            continue
        entry = stages.get(stage, {})
        if not isinstance(entry, dict):
            continue
        if field in entry:
            try:
                entry[field] = _path(entry[field], base)
            except ConfigurationError:
                # A later layer may replace this path, or its stage may be unselected.
                pass


def _validate_keys(data):
    """Reject unknown keys in every layer without validating replaceable values."""
    _mapping(data, DEFAULTS)
    for group, fields in (("providers", PROVIDER_FIELDS), ("models", MODEL_FIELDS)):
        entries = data.get(group)
        if isinstance(entries, dict):
            for alias, entry in entries.items():
                if not isinstance(alias, str) or not ALIAS.fullmatch(alias):
                    raise ConfigurationError(
                        f"{group}.<name>: invalid alias; set an alias using letters, digits, underscores or hyphens"
                    )
                if isinstance(entry, dict):
                    _mapping(entry, fields, f"{group}.<name>")
                    mapping = entry.get("reasoning_effort_mapping")
                    if isinstance(mapping, dict):
                        _mapping(
                            mapping,
                            {"parameter", "values"},
                            f"{group}.<name>.reasoning_effort_mapping",
                        )
                        values = mapping.get("values")
                        if isinstance(values, dict):
                            _mapping(
                                values,
                                EFFORTS - {"default"},
                                f"{group}.<name>.reasoning_effort_mapping.values",
                            )
                            for value in values.values():
                                if isinstance(value, dict):
                                    _mapping(
                                        value,
                                        {"omit"},
                                        f"{group}.<name>.reasoning_effort_mapping.values",
                                    )
    stages = data.get("stages")
    if isinstance(stages, dict):
        _mapping(stages, DEFAULTS["stages"], "stages")
        for stage, values in stages.items():
            if isinstance(values, dict):
                _mapping(values, DEFAULTS["stages"][stage], f"stages.{stage}")
    for section in ("pipeline", "logging"):
        values = data.get(section)
        if isinstance(values, dict):
            _mapping(values, DEFAULTS[section], section)


def _validate_shape(data):
    _mapping(data, DEFAULTS)
    for group, fields in (("providers", PROVIDER_FIELDS), ("models", MODEL_FIELDS)):
        entries = data.get(group, {})
        if not isinstance(entries, dict):
            raise ConfigurationError(
                f"{group}: expected a mapping; replace it with a mapping"
            )
        for alias, entry in entries.items():
            if not isinstance(alias, str) or not ALIAS.fullmatch(alias):
                raise ConfigurationError(
                    f"{group}.<name>: invalid alias; set an alias using letters, digits, underscores or hyphens"
                )
            _mapping(entry, fields, f"{group}.<name>")
            for key, value in entry.items():
                if key == "reasoning_effort_mapping":
                    _mapping(
                        value,
                        {"parameter", "values"},
                        f"{group}.<name>.reasoning_effort_mapping",
                    )
                    if "parameter" in value and not isinstance(value["parameter"], str):
                        raise ConfigurationError(
                            f"{group}.<name>.reasoning_effort_mapping.parameter: expected a string; set a string"
                        )
                    if "values" in value:
                        if not isinstance(value["values"], dict):
                            raise ConfigurationError(
                                f"{group}.<name>.reasoning_effort_mapping.values: expected a mapping; replace it with a mapping"
                            )
                        for level, native in value["values"].items():
                            if not isinstance(level, str) or level not in EFFORTS - {
                                "default"
                            }:
                                raise ConfigurationError(
                                    f"{group}.<name>.reasoning_effort_mapping.values: unknown effort key; remove the unknown key"
                                )
                            if isinstance(native, dict):
                                if (
                                    level != "off"
                                    or native != {"omit": True}
                                    or type(native.get("omit")) is not bool
                                ):
                                    raise ConfigurationError(
                                        f"{group}.<name>.reasoning_effort_mapping.values: invalid omission; set a supported value"
                                    )
                            elif not isinstance(native, (str, int, float, bool)) or (
                                isinstance(native, float) and not math.isfinite(native)
                            ):
                                raise ConfigurationError(
                                    f"{group}.<name>.reasoning_effort_mapping.values: invalid mapped value; set a finite scalar"
                                )
                elif key == "timeout_seconds":
                    if isinstance(value, bool) or not isinstance(value, (int, float)):
                        raise ConfigurationError(
                            f"{group}.<name>.{key}: expected a number; set a numeric value"
                        )
                elif key == "reasoning_effort" and isinstance(value, bool):
                    raise ConfigurationError(
                        f"{group}.<name>.reasoning_effort: expected a string, not a boolean; "
                        "YAML treats unquoted off as a boolean. "
                        'To disable reasoning, use "off" (with quotes)'
                    )
                elif not isinstance(value, str):
                    raise ConfigurationError(
                        f"{group}.<name>.{key}: expected a string; set a string value"
                    )
    stage_data = data.get("stages", {})
    _mapping(stage_data, DEFAULTS["stages"], "stages")
    for stage, values in stage_data.items():
        _mapping(values, DEFAULTS["stages"][stage], f"stages.{stage}")
        for key, value in values.items():
            if key == "regenerate":
                if type(value) is not bool:
                    raise ConfigurationError(
                        f"stages.{stage}.{key}: expected a boolean; set true or false"
                    )
            elif key == "validation_retries":
                if type(value) is not int:
                    raise ConfigurationError(
                        f"stages.{stage}.{key}: expected an integer; set an integer"
                    )
            elif key == "reasoning_effort" and isinstance(value, bool):
                raise ConfigurationError(
                    f"stages.{stage}.reasoning_effort: expected a string, not a boolean; "
                    "YAML treats unquoted off as a boolean. "
                    'To disable reasoning, use "off" (with quotes)'
                )
            elif value is not None and not isinstance(value, (str, Path)):
                raise ConfigurationError(
                    f"stages.{stage}.{key}: expected a string; set a string"
                )
    for section in ("pipeline", "logging"):
        values = data.get(section, {})
        _mapping(values, DEFAULTS[section], section)
        for key, value in values.items():
            if not isinstance(value, str):
                raise ConfigurationError(
                    f"{section}.{key}: expected a string; set a string"
                )


def _check_mapping(mapping):
    if set(mapping) != {"parameter", "values"}:
        _fail()
    param, values = mapping["parameter"], mapping["values"]
    if (
        not param.strip()
        or param in {"model", "messages", "stream", "n", "response_format"}
        or not values
    ):
        _fail()
    for key, value in values.items():
        if not isinstance(key, str) or key not in EFFORTS - {"default"}:
            _fail()
        if isinstance(value, dict):
            if (
                key != "off"
                or value != {"omit": True}
                or type(value.get("omit")) is not bool
            ):
                _fail()
        elif not isinstance(value, (str, int, float, bool)) or (
            isinstance(value, float) and not math.isfinite(value)
        ):
            _fail()


def _strict_json(path):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError
            result[key] = value
        return result

    def invalid_constant(_):
        raise ValueError

    try:
        result = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=pairs,
            parse_constant=invalid_constant,
        )
        pending = [result]
        while pending:
            value = pending.pop()
            if isinstance(value, str):
                value.encode("utf-8")
            elif isinstance(value, float) and not math.isfinite(value):
                raise ValueError
            elif isinstance(value, dict):
                pending.extend(value.keys())
                pending.extend(value.values())
            elif isinstance(value, list):
                pending.extend(value)
        return result
    except (OSError, UnicodeError, ValueError, RecursionError):
        raise ConfigurationError("Invalid selected schema") from None


def _check_schema(path):
    schema = _strict_json(path)
    if (
        not isinstance(schema, dict)
        or schema.get("type") != "object"
        or schema.get("$schema", "https://json-schema.org/draft/2020-12/schema")
        != "https://json-schema.org/draft/2020-12/schema"
    ):
        _fail()

    # Descend uses the caller's specification for scope, then evolves the
    # validator using the child's $schema (including jsonschema's fallback).
    specs = {
        Draft3Validator: DRAFT3,
        Draft4Validator: DRAFT4,
        Draft6Validator: DRAFT6,
        Draft7Validator: DRAFT7,
        Draft201909Validator: DRAFT201909,
        Draft202012Validator: DRAFT202012,
    }

    def children(node, cls):
        maps = {"properties", "patternProperties", "definitions"}
        arrays = (
            {"allOf", "anyOf", "oneOf"} if cls is not Draft3Validator else {"extends"}
        )
        singles = {"additionalProperties", "additionalItems"}
        if cls is not Draft3Validator:
            singles.add("not")
        if cls in (
            Draft6Validator,
            Draft7Validator,
            Draft201909Validator,
            Draft202012Validator,
        ):
            singles.update({"contains", "propertyNames"})
        if cls in (Draft7Validator, Draft201909Validator, Draft202012Validator):
            singles.update({"if", "then", "else"})
        if cls in (Draft201909Validator, Draft202012Validator):
            maps.update({"$defs", "dependentSchemas"})
            singles.update(
                {"contentSchema", "unevaluatedItems", "unevaluatedProperties"}
            )
        if cls is Draft202012Validator:
            arrays.add("prefixItems")
            singles.discard("additionalItems")
        for key in maps:
            value = node.get(key)
            if isinstance(value, dict):
                yield from value.values()
        for key in arrays:
            value = node.get(key)
            if isinstance(value, list):
                yield from value
            elif key == "extends" and isinstance(value, (dict, bool)):
                yield value
        for key in singles | {"items"}:
            value = node.get(key)
            if isinstance(value, (dict, bool)):
                yield value
            elif (
                key == "items"
                and cls is not Draft202012Validator
                and isinstance(value, list)
            ):
                yield from value
        if cls is Draft3Validator:
            # Draft 3 permits schemas as alternatives to named types.
            for key in ("type", "disallow"):
                value = node.get(key)
                for option in value if isinstance(value, list) else (value,):
                    if isinstance(option, dict):
                        yield option
        if cls in (Draft3Validator, Draft4Validator, Draft6Validator, Draft7Validator):
            dependencies = node.get("dependencies")
            if isinstance(dependencies, dict):
                for value in dependencies.values():
                    if isinstance(value, (dict, bool)):
                        yield value

    try:
        Draft202012Validator.check_schema(schema)
        uri = schema.get("$id", "urn:image-clarus:selected-schema")
        registry = Registry().with_resource(
            uri, Resource.from_contents(schema, default_specification=DRAFT202012)
        )
        # A lookup supplies an already-entered resolver; ordinary descent does not.
        pending = [(schema, Draft202012Validator, registry.resolver(uri), True)]
        seen = []
        while pending:
            node, caller, resolver, entered = pending.pop()
            if not isinstance(node, (dict, bool)):
                _fail()
            if not entered:
                resolver = resolver.in_subresource(specs[caller].create_resource(node))
            cls = validator_for(node, default=caller)
            state = (id(node), cls, caller, resolver)
            if state in seen:
                continue
            seen.append(state)
            if isinstance(node, bool):
                continue
            if entered and node is not schema:
                cls.check_schema(node)
            if (node is not schema and "$id" in node) or "$dynamicRef" in node:
                _fail()
            if "$ref" in node:
                ref = node["$ref"]
                if not isinstance(ref, str) or not ref.startswith("#"):
                    _fail()
                resolved = resolver.lookup(ref)
                pending.append((resolved.contents, cls, resolved.resolver, True))
            if cls is Draft201909Validator and "$recursiveRef" in node:
                ref = node["$recursiveRef"]
                if not isinstance(ref, str) or not ref.startswith("#"):
                    _fail()
                # Enforce the same fragment/resolvability policy even though
                # referencing's recursive lookup follows its recursive anchor.
                resolver.lookup(ref)
                resolved = lookup_recursive_ref(resolver)
                pending.append((resolved.contents, cls, resolved.resolver, True))
            pending.extend(
                (child, cls, resolver, False) for child in children(node, cls)
            )
    except (SchemaError, Unresolvable, RecursionError, ValueError, TypeError, KeyError):
        raise ConfigurationError("Invalid selected schema") from None


def _selected(config, stage):
    if stage not in config["stages"]:
        _fail()
    settings = config["stages"][stage]
    alias = settings["model"]
    if not isinstance(alias, str) or alias not in config["models"]:
        raise ConfigurationError(
            f"stages.{stage}.model: model reference is missing or undefined; set it to a configured model"
        )
    model = config["models"][alias]
    provider_alias = model.get("provider")
    if provider_alias not in config["providers"]:
        raise ConfigurationError(
            "models.<name>.provider: provider reference is missing or undefined; set it to a configured provider"
        )
    if not model.get("model_id", "").strip():
        raise ConfigurationError(
            "models.<name>.model_id: model ID is missing; set a nonempty model ID"
        )
    if not _valid_utf8_text(model["model_id"]):
        raise ConfigurationError(
            "models.<name>.model_id: model ID must be valid UTF-8; set a valid text value"
        )
    provider = config["providers"][provider_alias]
    try:
        validate_base_url(provider.get("base_url", ""))
        valid_url = True
    except ValueError:
        valid_url = False
    if not valid_url:
        raise ConfigurationError(
            "providers.<name>.base_url: invalid URL; set a valid HTTP or HTTPS base URL"
        )
    timeout = provider["timeout_seconds"]
    try:
        valid_timeout = math.isfinite(timeout) and timeout > 0
    except OverflowError:
        valid_timeout = False
    if not valid_timeout:
        raise ConfigurationError(
            "providers.<name>.timeout_seconds: timeout must be finite and positive; set a positive number"
        )
    if "api_key" in provider and "api_key_env" in provider:
        raise ConfigurationError(
            "providers.<name>: conflicting credential settings; set only one credential source"
        )
    if "api_key" in provider and not provider["api_key"].strip():
        raise ConfigurationError(
            "providers.<name>.api_key: credential is empty; set a nonempty credential",
            "authentication",
        )
    if "api_key" in provider and not _valid_header_credential(provider["api_key"]):
        raise ConfigurationError(
            "providers.<name>.api_key: credential is not safe for an HTTP header; set a header-safe value"
        )
    if "api_key_env" in provider:
        name = provider["api_key_env"]
        if not ENV_NAME.fullmatch(name):
            raise ConfigurationError(
                "providers.<name>.api_key_env: invalid environment variable name; set a valid name"
            )
        if not os.environ.get(name, "").strip():
            raise ConfigurationError(
                "providers.<name>.api_key_env: credential unavailable; set the configured environment variable",
                "authentication",
            )
        if not _valid_header_credential(os.environ[name]):
            raise ConfigurationError(
                "providers.<name>.api_key_env: credential is not safe for an HTTP header; set a header-safe value"
            )
    effort = (
        settings["reasoning_effort"]
        if settings["reasoning_effort"] is not None
        else model["reasoning_effort"]
    )
    if model["reasoning_effort"] not in EFFORTS:
        raise ConfigurationError(
            "models.<name>.reasoning_effort: invalid effort; set a supported effort"
        )
    if effort not in EFFORTS:
        raise ConfigurationError(
            f"stages.{stage}.reasoning_effort: invalid effort; set a supported effort"
        )
    for group, obj in (("providers", provider), ("models", model)):
        if "reasoning_effort_mapping" in obj:
            parameter = obj["reasoning_effort_mapping"].get("parameter")
            if parameter in {"model", "messages", "stream", "n", "response_format"}:
                raise ConfigurationError(
                    f"{group}.<name>.reasoning_effort_mapping.parameter: reserved parameter; set a non-reserved parameter"
                )
            try:
                _check_mapping(obj["reasoning_effort_mapping"])
            except ConfigurationError:
                raise ConfigurationError(
                    f"{group}.<name>.reasoning_effort_mapping: invalid mapping; set a valid parameter and effort values"
                ) from None
    mapping = model.get(
        "reasoning_effort_mapping", provider.get("reasoning_effort_mapping")
    )
    if effort != "default" and mapping is not None and effort not in mapping["values"]:
        raise ConfigurationError(
            f"stages.{stage}.reasoning_effort: effort has no mapping; set a mapped effort or update the mapping"
        )
    if stage == "json" and settings["validation_retries"] not in (0, 1, 2):
        raise ConfigurationError(
            "stages.json.validation_retries: invalid retry count; set 0, 1, or 2"
        )
    for field in ("prompt_file", "schema_file"):
        path = settings.get(field)
        if path is not None:
            if not isinstance(path, Path):
                raise ConfigurationError(
                    f"stages.{stage}.{field}: invalid file path; set a readable file"
                )
            try:
                if not path.is_file():
                    raise ConfigurationError(
                        f"stages.{stage}.{field}: file unavailable; set a readable file"
                    )
                if field == "prompt_file":
                    path.read_text(encoding="utf-8")
                else:
                    from image_clarus import schema_worker

                    schema_text = path.read_text(encoding="utf-8")
                    result = schema_worker.preflight(
                        schema_text, timeout=schema_worker.SCHEMA_TIMEOUT_SECONDS
                    )
                    if result.get("status") != "ok":
                        raise ConfigurationError(
                            f"stages.{stage}.{field}: invalid schema; set a valid local JSON schema"
                        )
            except (OSError, UnicodeError):
                raise ConfigurationError(
                    f"stages.{stage}.{field}: file unavailable or unreadable; set a readable file"
                ) from None


def resolve_config(
    *,
    stages=(),
    discovery_paths=None,
    config_file=None,
    overrides=(),
    desc_prompt=None,
    json_prompt=None,
    json_schema=None,
    regenerate=False,
    missing_prerequisite=None,
):
    """Resolve the complete config; environment credentials are never copied into it."""
    config = deepcopy(DEFAULTS)
    paths = (
        (config_file,)
        if config_file is not None
        else (discovery_locations() if discovery_paths is None else discovery_paths)
    )
    for raw_path in paths:
        try:
            path = Path(raw_path).expanduser().resolve()
            if config_file is None and not path.exists():
                continue
            text = path.read_text(encoding="utf-8")
            try:
                data = yaml.load(text, Loader=UniqueSafeLoader)
            except ConfigurationError:
                raise
            except ValueError:
                raise ConfigurationError(
                    "Cannot load configuration: invalid YAML value; correct the YAML value"
                ) from None
        except ConfigurationError:
            raise
        except yaml.YAMLError as error:
            mark = getattr(error, "problem_mark", None)
            location = (
                f" at line {mark.line + 1}, column {mark.column + 1}" if mark else ""
            )
            raise ConfigurationError(
                f"Cannot load configuration: invalid YAML{location}; correct the YAML syntax"
            ) from None
        except (OSError, UnicodeError, ValueError, RuntimeError):
            raise ConfigurationError(
                "configuration: cannot load file; set a readable configuration file"
            ) from None
        _validate_keys(data)
        _normalize_paths(data, path.parent)
        _merge(config, data)
        break
    override_paths = []
    override_parts = []
    for override in overrides:
        name, separator, value = override.partition("=")
        parts = name.split(".")
        safe_path = _override_path(parts)
        override_paths.append(safe_path)
        override_parts.append(parts)
        if (
            not separator
            or not value
            or any(not part for part in parts)
            or (len(parts) >= 3 and parts[0] == "providers" and parts[2] == "api_key")
        ):
            raise ConfigurationError(
                f"Invalid override: {safe_path}: invalid syntax or forbidden credential; correct the override"
            )
        # Build an isolated overlay, then validate it against the same schema.
        overlay = {}
        node = overlay
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        try:
            node[parts[-1]] = yaml.load(value, Loader=UniqueSafeLoader)
        except ConfigurationError as error:
            raise ConfigurationError(
                f"Invalid override: {safe_path}: {error}"
            ) from None
        except (yaml.YAMLError, ValueError, RecursionError):
            raise ConfigurationError(
                f"Invalid override: {safe_path}: invalid YAML; correct the override syntax"
            ) from None
        try:
            _validate_keys(overlay)
        except ConfigurationError as error:
            raise ConfigurationError(
                f"Invalid override: {safe_path}: {error}", error.category
            ) from None
        providers = overlay.get("providers", {})
        if isinstance(providers, dict) and any(
            isinstance(provider, dict) and "api_key" in provider
            for provider in providers.values()
        ):
            raise ConfigurationError(
                f"Invalid override: {safe_path}: invalid syntax or forbidden credential; correct the override"
            )
        _normalize_paths(overlay, Path.cwd())
        target = config
        normalized = overlay
        for part in parts[:-1]:
            normalized = normalized[part]
            if part not in target or not isinstance(target[part], dict):
                target[part] = {}
            target = target[part]
        target[parts[-1]] = normalized[parts[-1]]
    complete = deepcopy(DEFAULTS)
    _merge(complete, config)
    config = complete
    for stage, field, value in (
        ("desc", "prompt_file", desc_prompt),
        ("json", "prompt_file", json_prompt),
        ("json", "schema_file", json_schema),
    ):
        if value is not None and stage in stages:
            if not isinstance(config["stages"], dict):
                config["stages"] = deepcopy(DEFAULTS["stages"])
            if not isinstance(config["stages"].get(stage), dict):
                config["stages"][stage] = deepcopy(DEFAULTS["stages"][stage])
            try:
                config["stages"][stage][field] = _path(str(value), Path.cwd())
            except ConfigurationError:
                raise ConfigurationError(
                    f"stages.{stage}.{field}: invalid file path; set a valid readable file path"
                ) from None
    if regenerate:
        for stage in stages:
            if not isinstance(config["stages"], dict):
                config["stages"] = deepcopy(DEFAULTS["stages"])
            if stage not in config["stages"]:
                _fail()
            if not isinstance(config["stages"][stage], dict):
                config["stages"][stage] = deepcopy(DEFAULTS["stages"][stage])
            config["stages"][stage]["regenerate"] = True
    if missing_prerequisite is not None:
        if not isinstance(config["pipeline"], dict):
            config["pipeline"] = deepcopy(DEFAULTS["pipeline"])
        config["pipeline"]["missing_prerequisite"] = missing_prerequisite
    try:
        _validate_shape(config)
    except ConfigurationError as error:
        raise _with_relevant_overrides(error, override_paths) from None
    for section, field, valid in (
        ("pipeline", "missing_prerequisite", {"fail", "skip"}),
        ("pipeline", "on_stage_failure", {"stop", "continue"}),
        ("pipeline", "backup_retention", {"remove", "retain"}),
        ("logging", "level", {"DEBUG", "INFO", "WARNING", "ERROR"}),
    ):
        if config[section][field] not in valid:
            path = f"{section}.{field}"
            raise ConfigurationError(f"{path}: invalid option; set a supported value")
    for provider in config["providers"].values():
        provider.setdefault("timeout_seconds", 60)
    for model in config["models"].values():
        model.setdefault("reasoning_effort", "default")
    for stage in stages:
        try:
            _selected(config, stage)
        except ConfigurationError as error:
            selected_model = config["stages"].get(stage, {}).get("model")
            selected_provider = config["models"].get(selected_model, {}).get("provider")
            relevant_paths = [
                safe
                for parts, safe in zip(override_parts, override_paths)
                if len(parts) < 2
                or parts[0] not in {"providers", "models"}
                or parts[1]
                == (selected_provider if parts[0] == "providers" else selected_model)
            ]
            raise _with_relevant_overrides(error, relevant_paths) from None
    return config
