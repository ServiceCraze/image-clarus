"""Safe, single-pass expansion of explicitly namespaced prompt values."""

import json
import os
import re
from pathlib import Path

from image_clarus.config import ConfigurationError
from image_clarus.state.storage import StateStopped

_NAME = re.compile(r"(?:config|state)(?:\.[A-Za-z_][A-Za-z0-9_-]*)+")
_OMIT = object()
_SECRET_FIELDS = frozenset({"api_key", "api_key_env"})


def _error():
    return ConfigurationError(
        "prompt expansion: invalid or unavailable macro; correct the prompt or macro options"
    )


def safe_config_snapshot(config, environ=None):
    """Copy a resolved configuration while excluding credential-bearing data."""
    try:
        return _build_safe_snapshot(config, environ)
    except StateStopped:
        raise
    except Exception:  # noqa: BLE001 - boundary must not expose unexpected exceptions
        raise _error() from None


def _build_safe_snapshot(config, environ):
    environ = os.environ if environ is None else environ
    secrets = set()
    providers = config.get("providers", {})
    if isinstance(providers, dict):
        for provider in providers.values():
            if not isinstance(provider, dict):
                continue
            direct = provider.get("api_key")
            env_name = provider.get("api_key_env")
            if isinstance(direct, str) and direct:
                secrets.add(direct)
            if isinstance(env_name, str):
                value = environ.get(env_name)
                if isinstance(value, str) and value:
                    secrets.add(value)

    def clean(value):
        if isinstance(value, Path):
            value = str(value)
        if isinstance(value, str):
            return _OMIT if any(secret in value for secret in secrets) else value
        if isinstance(value, dict):
            result = {}
            for key, item in value.items():
                if not isinstance(key, str) or key in _SECRET_FIELDS:
                    continue
                if any(secret in key for secret in secrets):
                    continue
                filtered = clean(item)
                if filtered is not _OMIT:
                    result[key] = filtered
            return result
        if isinstance(value, (list, tuple)):
            return [
                filtered for item in value if (filtered := clean(item)) is not _OMIT
            ]
        if value is None or type(value) in (bool, int, float):
            return value
        raise _error()

    return clean(config)


def expand_prompt(source_text, safe_config, state_view, macro_options):
    """Expand a source once, reading categories through the invocation service."""
    state_snapshot = None

    def lookup(name):
        nonlocal state_snapshot
        parts = name.split(".")
        if parts[0] == "config":
            value = safe_config
        else:
            if name not in {"state.categories", "state.categories.known"}:
                raise _error()
            if state_snapshot is None:
                state_snapshot = {
                    "categories": {"known": list(state_view.snapshot_categories())}
                }
            value = state_snapshot
        for part in parts[1:]:
            if not isinstance(value, dict) or part not in value:
                raise _error()
            value = value[part]
        options = macro_options.get(name)
        if options is not None:
            if not isinstance(options, dict) or set(options) - {
                "delimiter",
                "max_depth",
            }:
                raise _error()
            delimiter = options.get("delimiter", "/")
            depth = options.get("max_depth")
            if (
                not isinstance(delimiter, str)
                or not delimiter
                or (depth is not None and (type(depth) is not int or depth < 0))
            ):
                raise _error()
            if not isinstance(value, list) or not all(
                isinstance(item, str) for item in value
            ):
                raise _error()
            if depth == 0:
                value = []
            elif depth is not None:
                value = list(
                    dict.fromkeys(
                        delimiter.join(item.split(delimiter)[:depth]) for item in value
                    )
                )
        if isinstance(value, str):
            value.encode("utf-8")
            return value
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )

    try:
        result = []
        cursor = 0
        while cursor < len(source_text):
            if source_text.startswith("\\{{", cursor):
                result.append("{{")
                cursor += 3
            elif source_text.startswith("{{", cursor):
                end = source_text.find("}}", cursor + 2)
                if end < 0:
                    raise _error()
                name = source_text[cursor + 2 : end]
                if not _NAME.fullmatch(name):
                    raise _error()
                result.append(lookup(name))
                cursor = end + 2
            else:
                result.append(source_text[cursor])
                cursor += 1
        text = "".join(result)
        text.encode("utf-8")
        return text
    except StateStopped:
        raise
    except Exception:  # noqa: BLE001 - boundary must not expose unexpected exceptions
        raise _error() from None
