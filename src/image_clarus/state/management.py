"""Strict category-management target and transactional clear operations."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable, Mapping
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


@dataclass(frozen=True)
class UnionResult:
    """Outcome of one contribution; inserted is confirmed only on commit."""

    status: str  # skipped, committed, failed, interrupted, unknown
    attempted: bool = False
    inserted: int = 0
    close_failed: bool = False
    diagnostic: str | None = None


def union_categories(
    target: Target,
    paths: Iterable[str],
    *,
    stop: Any = None,
    migrations: Mapping[tuple[int, int], storage.Migration] | None = None,
) -> UnionResult:
    """Atomically migrate and union one nonempty contribution on the target."""
    conn = None
    attempted = False
    committed = False
    commit_started = False
    inserted = 0
    result = None
    migrations = migrations or {}
    try:
        storage._check_stop(stop)
        values = list(dict.fromkeys(storage._category_values(paths)))
        storage._check_stop(stop)
        if not values:
            return UnionResult("skipped")
        deadline = storage._deadline()
        check_target(target)
        conn = storage._connect(target.path, deadline)
        check_target(target)
        storage._busy(conn, deadline)
        storage._check_stop(stop)
        conn.execute("BEGIN IMMEDIATE")
        attempted = True
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
        for value in values:
            inserted += conn.execute(
                "INSERT OR IGNORE INTO known_categories(path) VALUES (?)", (value,)
            ).rowcount
        storage._busy(conn, deadline)
        storage._check_stop(stop)
        check_target(target)
        storage._check_stop(stop)
        commit_started = True
        conn.commit()
        committed = True
        check_target(target)
        result = UnionResult("committed", attempted=True, inserted=inserted)
    except Exception as error:  # noqa: BLE001 - sanitized operation boundary
        rollback_failed = False
        if conn is not None and not committed:
            try:
                conn.rollback()
            except sqlite3.Error:
                rollback_failed = True
        if committed or commit_started or rollback_failed:
            result = UnionResult(
                "unknown",
                attempted=attempted,
                diagnostic="category union outcome unknown",
            )
        elif isinstance(error, StateStopped):
            result = UnionResult(
                "interrupted",
                attempted=attempted,
                diagnostic="state operation interrupted",
            )
        else:
            diagnostic = (
                str(error)
                if isinstance(error, StateError)
                else "category update failed"
            )
            result = UnionResult("failed", attempted=attempted, diagnostic=diagnostic)
    finally:
        if conn is not None:
            try:
                conn.close()
            except sqlite3.Error:
                if result is not None:
                    result = UnionResult(
                        result.status,
                        result.attempted,
                        result.inserted,
                        True,
                        result.diagnostic,
                    )
    assert result is not None
    return result


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
        if isinstance(error, StateError):
            raise
        if isinstance(error, (sqlite3.Error, OSError)):
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
