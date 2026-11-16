"""Validate OpenAI-compatible base URLs without resolving hosts."""

from urllib.parse import urlsplit

import httpx


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
            or u.scheme not in {"http", "https"}
            or not u.hostname
            or "\\" in u.netloc
            or u.username is not None
            or u.password is not None
            or u.path.rstrip("/").endswith("/chat/completions")
        ):
            raise ValueError
        _ = u.port
        normalized = httpx.URL(raw)
        if normalized.raw_path.rstrip(b"/").endswith(b"/chat/completions"):
            raise ValueError
        return raw.rstrip("/") + "/chat/completions"
    except (ValueError, TypeError, httpx.InvalidURL, UnicodeError):
        pass
    raise ValueError("Invalid provider base URL")
