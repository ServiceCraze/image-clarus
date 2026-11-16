"""Configuration discovery, layering, and selected-stage preflight."""

import ipaddress
import json
import math
import os
import re
import sys
from copy import deepcopy
from pathlib import Path
from urllib.parse import urlsplit

import yaml
from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError
from referencing import Registry, Resource
from referencing.exceptions import Unresolvable
from referencing.jsonschema import DRAFT202012


class ConfigurationError(ValueError):
    """A sanitized preflight failure with a stable category."""

    def __init__(self, message, category="configuration"):
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
                    raise ConfigurationError("Duplicate YAML key")
                keys.add(key)
            except TypeError:
                raise ConfigurationError("Invalid YAML mapping key") from None
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


def _mapping(value, fields):
    if not isinstance(value, dict) or any(
        not isinstance(k, str) or k not in fields for k in value
    ):
        _fail()


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
                    _fail()
                if isinstance(entry, dict):
                    _mapping(entry, fields)
                    mapping = entry.get("reasoning_effort_mapping")
                    if isinstance(mapping, dict):
                        _mapping(mapping, {"parameter", "values"})
                        values = mapping.get("values")
                        if isinstance(values, dict):
                            _mapping(values, EFFORTS - {"default"})
                            for value in values.values():
                                if isinstance(value, dict):
                                    _mapping(value, {"omit"})
    stages = data.get("stages")
    if isinstance(stages, dict):
        _mapping(stages, DEFAULTS["stages"])
        for stage, values in stages.items():
            if isinstance(values, dict):
                _mapping(values, DEFAULTS["stages"][stage])
    for section in ("pipeline", "logging"):
        values = data.get(section)
        if isinstance(values, dict):
            _mapping(values, DEFAULTS[section])


def _validate_shape(data):
    _mapping(data, DEFAULTS)
    for group, fields in (("providers", PROVIDER_FIELDS), ("models", MODEL_FIELDS)):
        entries = data.get(group, {})
        if not isinstance(entries, dict):
            _fail()
        for alias, entry in entries.items():
            if not isinstance(alias, str) or not ALIAS.fullmatch(alias):
                _fail()
            _mapping(entry, fields)
            for key, value in entry.items():
                if key == "reasoning_effort_mapping":
                    _mapping(value, {"parameter", "values"})
                    if "parameter" in value and not isinstance(value["parameter"], str):
                        _fail()
                    if "values" in value:
                        if not isinstance(value["values"], dict):
                            _fail()
                        for level, native in value["values"].items():
                            if not isinstance(level, str) or level not in EFFORTS - {
                                "default"
                            }:
                                _fail()
                            if isinstance(native, dict):
                                if (
                                    level != "off"
                                    or native != {"omit": True}
                                    or type(native.get("omit")) is not bool
                                ):
                                    _fail()
                            elif not isinstance(native, (str, int, float, bool)) or (
                                isinstance(native, float) and not math.isfinite(native)
                            ):
                                _fail()
                elif key == "timeout_seconds":
                    if isinstance(value, bool) or not isinstance(value, (int, float)):
                        _fail()
                elif not isinstance(value, str):
                    _fail()
    stage_data = data.get("stages", {})
    _mapping(stage_data, DEFAULTS["stages"])
    for stage, values in stage_data.items():
        _mapping(values, DEFAULTS["stages"][stage])
        for key, value in values.items():
            if key == "regenerate":
                if type(value) is not bool:
                    _fail()
            elif key == "validation_retries":
                if type(value) is not int:
                    _fail()
            elif value is not None and not isinstance(value, (str, Path)):
                _fail()
    for section in ("pipeline", "logging"):
        values = data.get(section, {})
        _mapping(values, DEFAULTS[section])
        if any(not isinstance(value, str) for value in values.values()):
            _fail()


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
        return json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=pairs,
            parse_constant=invalid_constant,
        )
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

    references = []

    def scan(value, root=False):
        if not isinstance(value, dict):
            return
        if (
            (not root and "$id" in value)
            or "$dynamicRef" in value
            or (
                "$ref" in value
                and (
                    not isinstance(value["$ref"], str)
                    or not value["$ref"].startswith("#")
                )
            )
        ):
            _fail()
        if "$ref" in value:
            references.append(value["$ref"])
        for key in ("$defs", "properties", "patternProperties", "dependentSchemas"):
            children = value.get(key, {})
            if isinstance(children, dict):
                for child in children.values():
                    scan(child)
        for key in ("allOf", "anyOf", "oneOf", "prefixItems"):
            children = value.get(key, [])
            if isinstance(children, list):
                for child in children:
                    scan(child)
        for key in (
            "items",
            "contains",
            "additionalProperties",
            "propertyNames",
            "unevaluatedItems",
            "unevaluatedProperties",
            "not",
            "if",
            "then",
            "else",
            "contentSchema",
        ):
            scan(value.get(key))

    try:
        scan(schema, root=True)
        Draft202012Validator.check_schema(schema)
        uri = schema.get("$id", "urn:image-clarus:selected-schema")
        registry = Registry().with_resource(
            uri, Resource.from_contents(schema, default_specification=DRAFT202012)
        )
        resolver = registry.resolver(uri)
        seen = set()
        while references:
            reference = references.pop()
            if reference in seen:
                continue
            seen.add(reference)
            target = resolver.lookup(reference).contents
            if not isinstance(target, (dict, bool)):
                _fail()
            scan(target, root=target is schema)
    except (SchemaError, Unresolvable, RecursionError, ValueError):
        raise ConfigurationError("Invalid selected schema") from None


def _selected(config, stage):
    if stage not in config["stages"]:
        _fail()
    settings = config["stages"][stage]
    alias = settings["model"]
    if not isinstance(alias, str) or alias not in config["models"]:
        _fail()
    model = config["models"][alias]
    provider_alias = model.get("provider")
    if (
        provider_alias not in config["providers"]
        or not model.get("model_id", "").strip()
    ):
        _fail()
    provider = config["providers"][provider_alias]
    try:
        raw_url = provider.get("base_url", "")
        url = urlsplit(raw_url)
        if (
            "?" in raw_url
            or "#" in raw_url
            or any(char.isspace() or ord(char) < 32 for char in raw_url)
            or url.scheme not in {"http", "https"}
            or not url.hostname
            or url.username is not None
            or url.password is not None
            or url.query
            or url.fragment
            or url.path.rstrip("/").endswith("/chat/completions")
        ):
            _fail()
        _ = url.port
        if url.scheme == "http" and url.hostname != "localhost":
            try:
                address = ipaddress.ip_address(url.hostname)
            except ValueError:
                raise ConfigurationError("Invalid configuration") from None
            private_networks = (
                ipaddress.ip_network("10.0.0.0/8"),
                ipaddress.ip_network("172.16.0.0/12"),
                ipaddress.ip_network("192.168.0.0/16"),
                ipaddress.ip_network("fc00::/7"),
            )
            if not address.is_loopback and not any(
                address in network for network in private_networks
            ):
                _fail()
    except ValueError:
        _fail()
    timeout = provider["timeout_seconds"]
    try:
        if not math.isfinite(timeout) or timeout <= 0:
            _fail()
    except OverflowError:
        _fail()
    if "api_key" in provider and "api_key_env" in provider:
        _fail()
    if "api_key" in provider and not provider["api_key"].strip():
        raise ConfigurationError("Invalid provider credential", "authentication")
    if "api_key_env" in provider:
        name = provider["api_key_env"]
        if not ENV_NAME.fullmatch(name):
            _fail()
        if not os.environ.get(name):
            raise ConfigurationError(
                "Provider credential unavailable", "authentication"
            )
    effort = (
        settings["reasoning_effort"]
        if settings["reasoning_effort"] is not None
        else model["reasoning_effort"]
    )
    if effort not in EFFORTS or model["reasoning_effort"] not in EFFORTS:
        _fail()
    for obj in (provider, model):
        if "reasoning_effort_mapping" in obj:
            _check_mapping(obj["reasoning_effort_mapping"])
    mapping = model.get(
        "reasoning_effort_mapping", provider.get("reasoning_effort_mapping")
    )
    if effort != "default" and mapping is not None and effort not in mapping["values"]:
        _fail()
    if stage == "json" and settings["validation_retries"] not in (0, 1, 2):
        _fail()
    for field in ("prompt_file", "schema_file"):
        path = settings.get(field)
        if path is not None:
            if not isinstance(path, Path):
                _fail()
            try:
                if not path.is_file():
                    _fail()
                if field == "prompt_file":
                    path.read_text(encoding="utf-8")
                else:
                    _check_schema(path)
            except (OSError, UnicodeError):
                raise ConfigurationError("Invalid selected stage file") from None


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
            data = yaml.load(path.read_text(encoding="utf-8"), Loader=UniqueSafeLoader)
        except (yaml.YAMLError, OSError, UnicodeError, ValueError, RuntimeError):
            raise ConfigurationError("Cannot load configuration") from None
        _validate_keys(data)
        _normalize_paths(data, path.parent)
        _merge(config, data)
        break
    override_paths = []
    for override in overrides:
        name, separator, value = override.partition("=")
        parts = name.split(".")
        safe_path = _override_path(parts)
        override_paths.append(safe_path)
        if (
            not separator
            or not value
            or any(not part for part in parts)
            or (len(parts) >= 3 and parts[0] == "providers" and parts[2] == "api_key")
        ):
            raise ConfigurationError(f"Invalid override: {safe_path}")
        # Build an isolated overlay, then validate it against the same schema.
        overlay = {}
        node = overlay
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        try:
            node[parts[-1]] = yaml.load(value, Loader=UniqueSafeLoader)
        except (yaml.YAMLError, ValueError, RecursionError):
            raise ConfigurationError(f"Invalid override: {safe_path}") from None
        try:
            _validate_keys(overlay)
        except ConfigurationError:
            raise ConfigurationError(f"Invalid override: {safe_path}") from None
        providers = overlay.get("providers", {})
        if isinstance(providers, dict) and any(
            isinstance(provider, dict) and "api_key" in provider
            for provider in providers.values()
        ):
            raise ConfigurationError(f"Invalid override: {safe_path}")
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
            config["stages"][stage][field] = _path(str(value), Path.cwd())
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
    except ConfigurationError:
        if override_paths:
            paths = ", ".join(dict.fromkeys(override_paths))
            raise ConfigurationError(
                f"Invalid configuration; override paths: {paths}"
            ) from None
        raise
    for section, field, valid in (
        ("pipeline", "missing_prerequisite", {"fail", "skip"}),
        ("pipeline", "on_stage_failure", {"stop", "continue"}),
        ("pipeline", "backup_retention", {"remove", "retain"}),
        ("logging", "level", {"DEBUG", "INFO", "WARNING", "ERROR"}),
    ):
        if config[section][field] not in valid:
            path = f"{section}.{field}"
            if path in override_paths:
                raise ConfigurationError(f"Invalid override: {path}")
            _fail()
    for provider in config["providers"].values():
        provider.setdefault("timeout_seconds", 60)
    for model in config["models"].values():
        model.setdefault("reasoning_effort", "default")
    for stage in stages:
        try:
            _selected(config, stage)
        except ConfigurationError as error:
            if override_paths:
                paths = ", ".join(dict.fromkeys(override_paths))
                raise ConfigurationError(
                    f"{error}; override paths: {paths}", error.category
                ) from None
            raise
    return config
