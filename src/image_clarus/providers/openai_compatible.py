"""Synchronous, stateless OpenAI-compatible Chat Completions boundary.

Inputs are content snapshots, not filesystem paths. ``effort`` is the selected
stage override, or None to inherit the selected model. ``history`` contains
only prior invalid assistant content and normalized validation feedback.
"""

import base64
import contextvars
import json
import logging
import math
import os

import httpx

from image_clarus.config import EFFORTS, ConfigurationError, _check_mapping
from image_clarus.endpoint import validate_base_url


class ProviderError(Exception):
    """A sanitized provider failure carrying an A2 category."""

    def __init__(self, category):
        self.category = category
        super().__init__(f"Provider request failed: {category}")


# HTTPX and httpcore log URL/host at INFO/DEBUG. Filter only requests made in
# this context, without muting unrelated concurrent clients or changing levels.
_in_request = contextvars.ContextVar("image_clarus_provider_request", default=False)


class _PrivateRequestFilter(logging.Filter):
    def filter(self, record):
        return not _in_request.get()


_filter = _PrivateRequestFilter()
for _name in (
    "httpx",
    "httpcore.connection",
    "httpcore.http11",
    "httpcore.http2",
    "httpcore.proxy",
    "httpcore.socks",
):
    logging.getLogger(_name).addFilter(_filter)


_MIMES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
}
_BUILTIN = {
    "parameter": "reasoning_effort",
    "values": {
        "off": "none",
        "minimal": "minimal",
        "low": "low",
        "medium": "medium",
        "high": "high",
        "extra_high": "xhigh",
        "max": "max",
        "ultra": "max",
    },
}


def _endpoint(raw):
    try:
        return validate_base_url(raw)
    except ValueError:
        pass
    raise ProviderError("configuration")


def _strict_json(content):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError
            result[key] = value
        return result

    def invalid(_):
        raise ValueError

    result = json.loads(content, object_pairs_hook=pairs, parse_constant=invalid)
    pending = [result]
    while pending:
        value = pending.pop()
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError
        if isinstance(value, str):
            value.encode("utf-8")
        if isinstance(value, dict):
            pending.extend(value.keys())
            pending.extend(value.values())
        elif isinstance(value, list):
            pending.extend(value)
    return result


def _category(response):
    status = response.status_code
    if status in (401, 403):
        return "authentication"
    if status == 408:
        return "network_timeout"
    if status == 413:
        return "unsupported_image"
    if status == 429 or status >= 500:
        return "provider_unavailable"
    if 300 <= status < 400:
        return "configuration"
    if 400 <= status < 500:
        try:
            error = _strict_json(response.content).get("error", {})
            if isinstance(error, dict):
                code, kind, param = (
                    error.get("code"),
                    error.get("type"),
                    error.get("param"),
                )
                if code == "model_not_found" or param == "model":
                    return "unknown_model"
                if code in ("invalid_image", "corrupt_image") or kind in (
                    "invalid_image",
                    "corrupt_image",
                ):
                    return "corrupt_image"
                if code in (
                    "unsupported_image",
                    "unsupported_image_format",
                    "unsupported_image_mime_type",
                ) or kind in (
                    "unsupported_image",
                    "unsupported_image_format",
                    "unsupported_image_mime_type",
                ):
                    return "unsupported_image"
        except (ValueError, TypeError, AttributeError, UnicodeError, RecursionError):
            pass
        return "configuration"
    return "provider_unavailable"


class OpenAICompatible:
    """Adapter for one resolved provider/model pair; never owns stage logic."""

    def __init__(self, provider, model, *, transport=None):
        self.provider = provider
        self.model = model
        self.transport = transport

    def image(self, *, prompt, image_bytes, suffix, effort=None):
        mime = _MIMES.get(suffix.lower())
        if mime is None:
            raise ProviderError("unsupported_image")
        data = base64.b64encode(image_bytes).decode("ascii")
        user = [
            {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{data}"}}
        ]
        return self._send(prompt, user, effort)

    def structured(self, *, prompt, description, schema, effort=None, history=()):
        user = [
            {"type": "text", "text": "Persisted description:\n" + description},
            {
                "type": "text",
                "text": "Selected JSON Schema:\n"
                + json.dumps(schema, ensure_ascii=False, allow_nan=False),
            },
        ]
        return self._send(prompt, user, effort, history=history, structured=True)

    def _send(self, prompt, user, effort, *, history=(), structured=False):
        endpoint = _endpoint(self.provider.get("base_url"))
        timeout = self.provider.get("timeout_seconds", 60)
        if (
            isinstance(timeout, bool)
            or not isinstance(timeout, (int, float))
            or not math.isfinite(timeout)
            or timeout <= 0
        ):
            raise ProviderError("configuration")
        if (
            not isinstance(self.model.get("model_id"), str)
            or not self.model["model_id"].strip()
        ):
            raise ProviderError("configuration")
        if "api_key" in self.provider and "api_key_env" in self.provider:
            raise ProviderError("configuration")
        key = self.provider.get("api_key")
        if "api_key_env" in self.provider:
            key = os.environ.get(self.provider["api_key_env"])
        if ("api_key" in self.provider or "api_key_env" in self.provider) and (
            not isinstance(key, str) or not key.strip()
        ):
            raise ProviderError("authentication")
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        if key is not None:
            headers["Authorization"] = "Bearer " + key
        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": user},
        ]
        for prior, feedback in history:
            messages.extend(
                [
                    {"role": "assistant", "content": prior},
                    {
                        "role": "user",
                        "content": json.dumps(
                            feedback, ensure_ascii=False, allow_nan=False
                        ),
                    },
                ]
            )
        body = {
            "model": self.model["model_id"],
            "messages": messages,
            "stream": False,
            "n": 1,
        }
        if structured:
            body["response_format"] = {"type": "json_object"}
        effort = (
            self.model.get("reasoning_effort", "default") if effort is None else effort
        )
        if effort not in EFFORTS:
            raise ProviderError("configuration")
        mapping = self.model.get(
            "reasoning_effort_mapping",
            self.provider.get("reasoning_effort_mapping", _BUILTIN),
        )
        try:
            _check_mapping(mapping)
            if effort != "default":
                native = mapping["values"][effort]
                if native != {"omit": True}:
                    body[mapping["parameter"]] = native
        except (ConfigurationError, KeyError, TypeError, AttributeError):
            mapping_invalid = True
        else:
            mapping_invalid = False
        if mapping_invalid:
            raise ProviderError("configuration")
        token = _in_request.set(True)
        failure = None
        try:
            with httpx.Client(
                transport=self.transport,
                timeout=timeout,
                follow_redirects=False,
                verify=True,
                trust_env=True,
            ) as client:
                response = client.post(endpoint, json=body, headers=headers)
        except httpx.TimeoutException:
            failure = "network_timeout"
        except (httpx.HTTPError, OSError, ValueError, UnicodeError):
            failure = "provider_unavailable"
        finally:
            _in_request.reset(token)
        if failure:
            raise ProviderError(failure)
        if not 200 <= response.status_code < 300:
            raise ProviderError(_category(response))
        media = (
            response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        )
        if media != "application/json" and not (
            media.startswith("application/") and media.endswith("+json")
        ):
            raise ProviderError("provider_unavailable")
        try:
            envelope = _strict_json(response.content)
            choices = envelope["choices"]
            if not isinstance(choices, list) or len(choices) != 1:
                raise ValueError
            choice = choices[0]
            message = choice["message"]
            if (
                type(choice["index"]) is not int
                or choice["index"] != 0
                or choice["finish_reason"] != "stop"
                or message["role"] != "assistant"
                or not isinstance(message["content"], str)
                or message.get("refusal") is not None
                or message.get("tool_calls")
                or message.get("function_call")
            ):
                raise ValueError
            return message["content"]
        except (
            ValueError,
            TypeError,
            KeyError,
            IndexError,
            UnicodeError,
            RecursionError,
        ):
            pass
        raise ProviderError("provider_unavailable")
