"""Binary-safe framing for the private parent/child pipe.

A frame is a big-endian byte count followed by a length-prefixed binary encoding
of the request. The encoding is a small tagged codec rather than JSON because
provider requests legitimately carry raw bytes: a description request embeds the
whole image in ``image_bytes``, which no text serialiser can carry unchanged.

Only frames cross the private pipe; nothing here writes to argv, logs or files.
Frames are bounded so a misbehaving peer cannot force unbounded allocation.
"""

import struct

# Generous headroom for one image plus prompt/description; the parent already
# holds the whole request in memory before sending it.
MAX_FRAME_BYTES = 256 * 1024 * 1024
MAX_DEPTH = 32

_HEADER = struct.Struct(">I")
_NONE = b"n"
_TRUE = b"t"
_FALSE = b"f"
_INT = b"i"
_FLOAT = b"d"
_STR = b"s"
_BYTES = b"b"
_LIST = b"l"
_MAP = b"m"
_LEN = struct.Struct(">I")


class FrameError(Exception):
    """Malformed, oversized or truncated frame; always sanitized by callers."""


def _pack_length(count: int) -> bytes:
    if count > MAX_FRAME_BYTES:
        raise FrameError("oversized frame")
    return _LEN.pack(count)


def _pack(value, depth: int) -> bytes:
    if depth > MAX_DEPTH:
        raise FrameError("frame too deeply nested")
    if value is None:
        return _NONE
    if value is True:
        return _TRUE
    if value is False:
        return _FALSE
    if isinstance(value, int):
        return _INT + value.to_bytes(24, "big", signed=True)
    if isinstance(value, float):
        return _FLOAT + struct.pack(">d", value)
    if isinstance(value, str):
        data = value.encode("utf-8")
        return _STR + _pack_length(len(data)) + data
    if isinstance(value, (bytes, bytearray, memoryview)):
        data = bytes(value)
        return _BYTES + _pack_length(len(data)) + data
    if isinstance(value, (list, tuple)):
        items = b"".join(_pack(item, depth + 1) for item in value)
        return _LIST + _pack_length(len(value)) + items
    if isinstance(value, dict):
        parts = []
        for key, item in value.items():
            if not isinstance(key, str):
                raise FrameError("map keys must be strings")
            parts.append(_pack(key, depth + 1))
            parts.append(_pack(item, depth + 1))
        return _MAP + _pack_length(len(value)) + b"".join(parts)
    raise FrameError("unrepresentable value")


class _Reader:
    def __init__(self, data: bytes) -> None:
        self.data = data
        self.offset = 0

    def take(self, count: int) -> bytes:
        end = self.offset + count
        if end > len(self.data):
            raise FrameError("truncated frame")
        chunk = self.data[self.offset : end]
        self.offset = end
        return chunk

    def length(self) -> int:
        (count,) = _LEN.unpack(self.take(_LEN.size))
        if count > MAX_FRAME_BYTES:
            raise FrameError("oversized frame")
        return count

    def value(self, depth: int):
        if depth > MAX_DEPTH:
            raise FrameError("frame too deeply nested")
        tag = self.take(1)
        if tag == _NONE:
            return None
        if tag == _TRUE:
            return True
        if tag == _FALSE:
            return False
        if tag == _INT:
            return int.from_bytes(self.take(24), "big", signed=True)
        if tag == _FLOAT:
            return struct.unpack(">d", self.take(8))[0]
        if tag == _STR:
            raw = self.take(self.length())
            try:
                return raw.decode("utf-8")
            except UnicodeDecodeError as error:
                # Malformed text is a frame fault, not a caller error: callers
                # sanitize FrameError and nothing else from this module.
                raise FrameError("malformed string") from error
        if tag == _BYTES:
            return self.take(self.length())
        if tag == _LIST:
            return [self.value(depth + 1) for _ in range(self.length())]
        if tag == _MAP:
            result = {}
            for _ in range(self.length()):
                key = self.value(depth + 1)
                if not isinstance(key, str):
                    raise FrameError("map keys must be strings")
                result[key] = self.value(depth + 1)
            return result
        raise FrameError("malformed frame")


def encode_frame(body) -> bytes:
    payload = _pack(body, 0)
    if len(payload) > MAX_FRAME_BYTES:
        raise FrameError("oversized frame")
    return _HEADER.pack(len(payload)) + payload


def decode_frame(data: bytes):
    """Decode exactly one complete frame; trailing or missing bytes are errors."""
    if len(data) < _HEADER.size:
        raise FrameError("missing frame header")
    (size,) = _HEADER.unpack(data[: _HEADER.size])
    body = data[_HEADER.size :]
    if size != len(body):
        raise FrameError("truncated frame")
    reader = _Reader(body)
    value = reader.value(0)
    if reader.offset != len(body):
        raise FrameError("trailing frame data")
    return value
