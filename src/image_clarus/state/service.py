"""Invocation-local domain service with nonpersistent failure fallback."""

import sys
from pathlib import Path

from image_clarus.state.resolution import select_directory
from image_clarus.state.storage import (
    MemoryStorage,
    MemoryStoragePool,
    SQLiteStorage,
    StateError,
    StateStopped,
)


def diagnostic(operation, on_diagnostic=None):
    print(
        f"image-clarus: state error: {operation}; using temporary state",
        file=sys.stderr,
    )
    if on_diagnostic is not None:
        on_diagnostic(operation)


class StateService:
    def __init__(self, storage, *, stop=None, on_diagnostic=None):
        self.storage = storage
        self.stop = stop
        self.on_diagnostic = on_diagnostic

    @classmethod
    def select(
        cls,
        explicit: Path | None,
        cwd: Path,
        image: Path,
        *,
        stop=None,
        memory_pool: MemoryStoragePool | None = None,
        on_diagnostic=None,
    ):
        try:
            if stop is not None and stop.signum is not None:
                raise StateStopped("interrupted")
            directory = select_directory(explicit, cwd, image)
        except StateStopped:
            raise
        except StateError:
            diagnostic("repository unavailable", on_diagnostic)
            return cls(MemoryStorage(stop=stop), stop=stop, on_diagnostic=on_diagnostic)
        if directory is None:
            storage = (
                memory_pool.open(stop=stop)
                if memory_pool is not None
                else MemoryStorage(stop=stop)
            )
        else:
            try:
                storage = SQLiteStorage(directory, stop=stop)
            except StateStopped:
                raise
            except StateError:
                diagnostic("repository unavailable", on_diagnostic)
                storage = MemoryStorage(stop=stop)
        return cls(storage, stop=stop, on_diagnostic=on_diagnostic)

    def _fallback(self, operation):
        diagnostic(operation, self.on_diagnostic)
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
            diagnostic("repository close failed", self.on_diagnostic)
