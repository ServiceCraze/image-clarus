"""Disposable transport child for one provider request.

The parent sends one framed request on a private pipe and receives one framed
sanitized response. Credentials never cross the argument vector: the provider
mapping, including any resolved key, travels only inside the private request
payload. Child exceptions are reduced to an A2 category, so tracebacks and
payloads cannot reach stderr, logs or persistent files.

Only transport happens here; stage decisions and publication stay in the
parent. This is a local termination boundary, not a memory or network sandbox.
"""

import sys

from image_clarus.provider_frame import FrameError, decode_frame, encode_frame

_READ_CHUNK = 1 << 20


def _read_exact(stream, count):
    chunks = []
    remaining = count
    while remaining:
        chunk = stream.read(min(remaining, _READ_CHUNK))
        if not chunk:
            return None
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def read_request(stream):
    """Read one length-prefixed frame; None means the parent went away."""
    header = _read_exact(stream, 4)
    if header is None:
        return None
    size = int.from_bytes(header, "big")
    body = _read_exact(stream, size) if size else b""
    if body is None:
        return None
    return decode_frame(header + body)


def _transport(request):
    """Resolve the adapter and invoke exactly one operation."""
    from image_clarus.providers.openai_compatible import OpenAICompatible, ProviderError

    if not isinstance(request, dict):
        return {"category": "configuration"}
    payload = request.get("payload")
    if not isinstance(payload, dict):
        return {"category": "configuration"}
    operation = payload.get("operation")
    if operation not in {"image", "structured"}:
        return {"category": "configuration"}
    try:
        client = OpenAICompatible(payload.get("provider"), payload.get("model"))
        content = getattr(client, operation)(**(payload.get("arguments") or {}))
    except ProviderError as error:
        return {"category": error.category}
    except Exception:  # noqa: BLE001 - never disclose child exceptions
        return {"category": "provider_unavailable"}
    return {"category": None, "content": content}


def main(stdin, stdout):
    try:
        request = read_request(stdin)
        if request is None:
            return 1
        stdout.write(encode_frame(_transport(request)))
        stdout.flush()
    except (FrameError, OSError, ValueError, UnicodeError):
        # Silent by design: a category already travelled to the parent as a
        # response, and anything else must not leak into stderr or files.
        return 1
    except Exception:  # noqa: BLE001 - never disclose child exceptions
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.stdin.buffer, sys.stdout.buffer))
