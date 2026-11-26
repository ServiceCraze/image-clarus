"""Strict category-management target and transactional clear operations."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from image_clarus.state import storage
from image_clarus.state.resolution import select_directory
from image_clarus.state.storage import StateError, StateStopped


@dataclass(frozen=True)
class Target:
    directory: Path
    origin: str
    identity: tuple[int, int] | None

    @property
    def path(self) -> Path:
        return self.directory / storage.DATABASE_NAME


def _identity(path: Path) -> tuple[int, int] | None:
    stat = path.stat()
    if not stat.st_dev or not stat.st_ino:
        return None
    return stat.st_dev, stat.st_ino


def select_target(explicit: Path | None, cwd: Path) -> Target:
    """Choose one existing persistent repository; never fall back to memory."""
    try:
        directory = select_directory(explicit, cwd, Path(cwd) / "placeholder")
        if directory is None:
            raise StateError("repository unavailable")
        path = directory / storage.DATABASE_NAME
        if not path.is_file():
            raise StateError("repository unavailable")
        return Target(
            directory, "configured" if explicit is not None else "cwd", _identity(path)
        )
    except (OSError, RuntimeError, ValueError):
        raise StateError("repository unavailable") from None


def check_target(target: Target) -> None:
    try:
        current = _identity(target.path)
        if target.identity is not None and current != target.identity:
            raise StateError("repository target changed")
    except (OSError, RuntimeError, ValueError):
        raise StateError("repository unavailable") from None


def clear_categories(target: Target, *, stop: Any = None, migrations=None) -> int:
    """Migrate and delete in one transaction; never count an uncertain commit."""
    deadline = storage._deadline()
    migrations = migrations or {}
    conn = None
    committed = False
    commit_started = False
    try:
        storage._check_stop(stop)
        check_target(target)
        conn = storage._connect(target.path, deadline)
        check_target(target)
        storage._busy(conn, deadline)
        storage._check_stop(stop)
        conn.execute("BEGIN IMMEDIATE")
        version = storage._validate(conn)
        seen = set()
        while version != (storage.FORMAT_VERSION, storage.DOMAIN_VERSION):
            if version in seen or version not in migrations:
                raise StateError("repository migration required")
            seen.add(version)
            try:
                migrations[version](conn)
            except StateStopped:
                raise
            except Exception:  # noqa: BLE001 - migration callback boundary
                raise StateError("repository migration failed") from None
            next_version = storage._validate(conn)
            if next_version == version:
                raise StateError("repository migration failed")
            version = next_version
        count = conn.execute("DELETE FROM known_categories").rowcount
        storage._busy(conn, deadline)
        storage._check_stop(stop)
        check_target(target)
        commit_started = True
        conn.commit()
        committed = True
        check_target(target)
        return count
    except BaseException as error:
        if conn is not None and not committed:
            try:
                conn.rollback()
            except sqlite3.Error:
                raise StateError("clear outcome unknown") from None
        if committed or commit_started:
            raise StateError("clear outcome unknown") from None
        if isinstance(error, StateStopped):
            raise
        if isinstance(error, (StateError, sqlite3.Error, OSError)):
            raise StateError("category clear failed") from None
        raise
    finally:
        if conn is not None:
            try:
                conn.close()
            except sqlite3.Error:
                if committed:
                    raise StateError(
                        "clear committed; repository close failed"
                    ) from None
                raise StateError("repository close failed") from None
