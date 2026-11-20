"""Invocation-local domain service with nonpersistent failure fallback."""

import sys
from pathlib import Path

from image_clarus.state.resolution import select_directory
from image_clarus.state.storage import (
    MemoryStorage,
    SQLiteStorage,
    StateError,
    StateStopped,
)


def diagnostic(operation):
    print(
        f"image-clarus: state error: {operation}; using temporary state",
        file=sys.stderr,
    )


class StateService:
    def __init__(self, storage, *, stop=None):
        self.storage = storage
        self.stop = stop

    @classmethod
    def select(cls, explicit: Path | None, cwd: Path, image: Path, *, stop=None):
        try:
            if stop is not None and stop.signum is not None:
                raise StateStopped("interrupted")
            directory = select_directory(explicit, cwd, image)
            storage = (
                SQLiteStorage(directory, stop=stop)
                if directory is not None
                else MemoryStorage(stop=stop)
            )
        except StateStopped:
            raise
        except StateError:
            diagnostic("repository unavailable")
            storage = MemoryStorage(stop=stop)
        return cls(storage, stop=stop)

    def _fallback(self, operation):
        diagnostic(operation)
        try:
            self.storage.close()
        except StateError:
            pass
        finally:
            self.storage = MemoryStorage(stop=self.stop)

    def snapshot_categories(self):
        try:
            return list(self.storage.snapshot_categories())
        except StateStopped:
            raise
        except StateError:
            self._fallback("category read failed")
            return []

    def add_categories(self, paths):
        try:
            self.storage.add_categories(paths)
        except StateStopped:
            raise
        except StateError:
            self._fallback("category update failed")

    def close(self):
        try:
            self.storage.close()
        except StateError:
            diagnostic("repository close failed")
