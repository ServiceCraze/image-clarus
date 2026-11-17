"""Validate OpenAI-compatible base URLs without resolving hosts."""

import posixpath
import re
from urllib.parse import urlsplit

import httpx

_AUTHORITY_CHARS = frozenset("-._~!$&'()*+,;=:%[]")
_PATH_CHARS = frozenset("-._~!$&'()*+,;=:@/%")
_UNRESERVED = frozenset(
    b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~"
)


def _valid_component(value, allowed):
    return all(ord(char) >= 128 or char.isalnum() or char in allowed for char in value)


def _decode_unreserved(path):
    def replace(match):
        value = int(match.group(1), 16)
        return bytes((value,)) if value in _UNRESERVED else match.group(0)

    return re.sub(rb"%([0-9A-Fa-f]{2})", replace, path)


def validate_base_url(raw):
    """Return the chat-completions URL, or raise a sanitized ValueError."""
    try:
        if not isinstance(raw, str):
            raise TypeError
        u = urlsplit(raw)
        if (
            "?" in raw
            or "#" in raw
            or any(c.isspace() or ord(c) < 32 for c in raw)
            or re.search(r"%(?![0-9A-Fa-f]{2})", raw)
            or u.scheme not in {"http", "https"}
            or not u.hostname
            or not _valid_component(u.netloc, _AUTHORITY_CHARS)
            or not _valid_component(u.path, _PATH_CHARS)
            or "\\" in u.netloc
            or u.username is not None
            or u.password is not None
        ):
            raise ValueError
        _ = u.port
        normalized = httpx.URL(raw)
        normalized_path = posixpath.normpath(_decode_unreserved(normalized.raw_path))
        if normalized_path.rstrip(b"/").endswith(b"/chat/completions"):
            raise ValueError
        return raw.rstrip("/") + "/chat/completions"
    except (ValueError, TypeError, httpx.InvalidURL, UnicodeError):
        pass
    raise ValueError("Invalid provider base URL")
