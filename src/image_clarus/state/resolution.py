"""Select state without ever creating a repository."""

import stat
from pathlib import Path

from image_clarus.state.storage import DATABASE_NAME, StateError


def select_directory(explicit: Path | None, cwd: Path, image: Path) -> Path | None:
    try:
        if explicit is not None:
            path = Path(explicit).expanduser()
            return (path if path.is_absolute() else Path(cwd) / path).resolve(
                strict=True
            )
        seen = set()
        for start in (Path(cwd), Path(image).parent):
            root = start.resolve(strict=True)
            for parent in (root, *root.parents):
                if parent in seen:
                    continue
                seen.add(parent)
                candidate = parent / ".image-clarus"
                try:
                    candidate.lstat()
                except FileNotFoundError:
                    continue
                resolved = candidate.resolve(strict=True)
                if not stat.S_ISDIR(resolved.stat().st_mode):
                    raise StateError("repository unavailable")
                try:
                    (resolved / DATABASE_NAME).lstat()
                except FileNotFoundError:
                    continue
                return resolved
        return None
    except (OSError, RuntimeError, ValueError):
        raise StateError("repository unavailable") from None
