"""Best-effort category accumulation from an eligible persisted JSON snapshot."""

import re
import sys
from pathlib import Path

from image_clarus.config import _valid_tag_segment
from image_clarus.state.storage import StateStopped

_BUILTIN = "urn:image-clarus:metadata-schema:"
_CUSTOM = "urn:image-clarus:custom-metadata-schema"


def _extract(data, read_envelope):
    envelope = read_envelope(data)
    identity = (envelope["schema_id"], envelope["schema_version"])
    if identity == (_BUILTIN + "1.0.0", "1.0.0"):
        return []
    if identity != (_BUILTIN + "2.0.0", "2.0.0") and not (
        identity[0] == _CUSTOM
        and re.fullmatch(r"custom-sha256:[0-9a-f]{64}", identity[1])
    ):
        raise ValueError
    candidates = envelope["metadata"].get("tag_candidates", [])
    if not isinstance(candidates, list):
        raise TypeError
    paths = set()
    for candidate in candidates:
        if (
            not isinstance(candidate, list)
            or not candidate
            or not all(_valid_tag_segment(part) for part in candidate)
        ):
            raise ValueError
        paths.add("/".join(candidate))
    return sorted(paths)


def _diagnostic(operation, on_diagnostic=None):
    print(f"image-clarus: state error: {operation}", file=sys.stderr)
    if on_diagnostic is not None:
        on_diagnostic(operation)


def accumulate_categories(
    result, service, *, enabled, read_envelope, stop=None, on_diagnostic=None
):
    """Perform optional work without changing the primary pipeline result."""
    if not enabled or (stop is not None and stop.signum is not None):
        return
    if not any(
        stage.stage == "json"
        and (
            stage.status == "completed"
            or (stage.status == "skipped" and stage.reason_code == "output_exists")
        )
        for stage in result.stages
    ):
        return
    try:
        data = Path(str(result.image_path) + ".desc.json").read_bytes()
        paths = _extract(data, read_envelope)
        if paths and (stop is None or stop.signum is None):
            service.add_categories(paths)
    except StateStopped:
        if stop is None or stop.signum is None:
            _diagnostic("category update failed", on_diagnostic)
    except Exception:  # noqa: BLE001 - optional work must not affect primary results
        _diagnostic("category accumulation failed", on_diagnostic)
