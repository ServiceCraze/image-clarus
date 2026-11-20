"""Category domain, independent of repository selection and metadata extraction."""

from collections.abc import Iterable
from typing import Protocol


class CategoryStorage(Protocol):
    def snapshot_categories(self) -> list[str]: ...
    def add_categories(self, paths: Iterable[str]) -> None: ...
    def close(self) -> None: ...


class CategoryState:
    def __init__(self, storage: CategoryStorage) -> None:
        self.storage = storage

    def snapshot_categories(self) -> list[str]:
        return self.storage.snapshot_categories()

    def add_categories(self, paths: Iterable[str]) -> None:
        self.storage.add_categories(paths)

    def close(self) -> None:
        self.storage.close()
