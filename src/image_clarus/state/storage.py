"""Short-lived SQLite transactions and an invocation-local memory backend.

Repository selection and diagnostics belong to the caller. Errors never include
filesystem paths, SQLite messages, or category data.
"""

from __future__ import annotations

import os
import sqlite3
import sys
import time
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path
from typing import Any

APPLICATION_ID = 0x49434C52
FORMAT_VERSION = 1
DOMAIN_VERSION = 1
DATABASE_NAME = "state.sqlite3"
TIMEOUT = 0.250


class StateError(Exception):
    """A sanitized state operation failure."""


class StateStopped(StateError):
    """Optional state work was stopped before its commit."""


def _check_stop(stop: Any) -> None:
    if stop is not None and stop.signum is not None:
        raise StateStopped("state operation interrupted")


def _category_values(paths: Iterable[str]) -> list[str]:
    """Materialize and validate the common storage domain before mutation."""
    try:
        if isinstance(paths, str):
            raise TypeError
        values = []
        for path in paths:
            if not isinstance(path, str):
                raise TypeError
            path = str.__str__(path)
            path.encode("utf-8")
            values.append(path)
        return values
    except Exception:  # noqa: BLE001 - caller-provided iterable boundary
        raise StateError("category update failed") from None


def _deadline() -> float:
    return time.monotonic() + TIMEOUT


def _busy(connection: sqlite3.Connection, deadline: float) -> None:
    remaining = max(0, int((deadline - time.monotonic()) * 1000))
    connection.execute(f"PRAGMA busy_timeout = {remaining}")


def _rollback(conn: sqlite3.Connection) -> None:
    primary = sys.exc_info()[0] is not None
    try:
        conn.rollback()
    except sqlite3.Error:
        if not primary:
            raise


def _close(conn: sqlite3.Connection) -> None:
    primary = sys.exc_info()[0] is not None
    try:
        conn.close()
    except sqlite3.Error:
        if not primary:
            raise StateError("repository close failed") from None


def _connect(path: Path, deadline: float) -> sqlite3.Connection:
    # as_uri encodes URI delimiters as well as Unicode; mode=rw never creates.
    if not path.is_file():
        raise StateError("repository unavailable")
    conn = sqlite3.connect(
        path.resolve().as_uri() + "?mode=rw", uri=True, timeout=0, isolation_level=None
    )
    try:
        _busy(conn, deadline)
    except BaseException:
        _close(conn)
        raise
    return conn


def _validate(conn: sqlite3.Connection) -> tuple[int, int]:
    app = conn.execute("PRAGMA application_id").fetchone()[0]
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    if app != APPLICATION_ID or version <= 0 or version > FORMAT_VERSION:
        raise StateError("unsupported repository format")
    columns = {
        name: [
            (row[1], row[2].upper(), row[3], row[5])
            for row in conn.execute(f"PRAGMA table_info({name})")
        ]
        for name in ("domain_versions", "known_categories")
    }
    if columns != {
        "domain_versions": [("domain", "TEXT", 1, 1), ("version", "INTEGER", 1, 0)],
        "known_categories": [("path", "TEXT", 1, 1)],
    }:
        raise StateError("invalid repository schema")
    for table, column in (("domain_versions", "domain"), ("known_categories", "path")):
        indexes = list(conn.execute(f"PRAGMA index_list({table})"))
        primary = [row[1] for row in indexes if row[3] == "pk"]
        if len(primary) != 1:
            raise StateError("invalid repository schema")
        keys = [
            row
            for row in conn.execute(
                "SELECT * FROM pragma_index_xinfo(?)", (primary[0],)
            )
            if row[5]
        ]
        if len(keys) != 1 or keys[0][2] != column or keys[0][4].upper() != "BINARY":
            raise StateError("invalid repository schema")
    if conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='trigger' AND tbl_name COLLATE NOCASE IN ('domain_versions', 'known_categories') LIMIT 1"
    ).fetchone():
        raise StateError("invalid repository schema")
    row = conn.execute(
        "SELECT version FROM domain_versions WHERE domain = 'categories'"
    ).fetchone()
    if (
        row is None
        or not isinstance(row[0], int)
        or row[0] <= 0
        or row[0] > DOMAIN_VERSION
    ):
        raise StateError("unsupported category version")
    return version, row[0]


# Migration callbacks are deliberately supplied by the caller for test fixtures;
# there is no speculative production migration. Keys are (format, domain).
Migration = Callable[[sqlite3.Connection], None]


def _validate_or_migrate(
    conn: sqlite3.Connection,
    deadline: float,
    stop: Any,
    migrations: Mapping[tuple[int, int], Migration],
) -> None:
    _check_stop(stop)
    _busy(conn, deadline)
    conn.execute("BEGIN IMMEDIATE")
    try:
        version = _validate(conn)
        seen = set()
        while version != (FORMAT_VERSION, DOMAIN_VERSION):
            if version in seen:
                raise StateError("invalid repository migration")
            seen.add(version)
            migrate = migrations.get(version)
            if migrate is None:
                raise StateError("unsupported repository version")
            try:
                migrate(conn)
            except StateStopped:
                raise StateStopped("state operation interrupted") from None
            except Exception:  # noqa: BLE001 - untrusted migration callback boundary
                raise StateError("repository unavailable") from None
            next_version = _validate(conn)
            if next_version == version:
                raise StateError("invalid repository migration")
            version = next_version
        _check_stop(stop)
        _busy(conn, deadline)
        conn.commit()
    except BaseException:
        _rollback(conn)
        raise


def initialize(directory: Path, *, stop: Any = None) -> None:
    """Initialize a newly created directory, or recognize an existing store.

    Existing incomplete paths are never repaired or deleted. Concurrent callers
    only observe an in-progress initializer, for at most one contention budget.
    """
    directory = Path(directory)
    deadline = _deadline()
    _check_stop(stop)
    try:
        try:
            directory.mkdir()
        except FileExistsError:
            while True:
                _check_stop(stop)
                try:
                    conn = _connect(directory / DATABASE_NAME, deadline)
                    try:
                        _busy(conn, deadline)
                        conn.execute("BEGIN")
                        try:
                            if _validate(conn) != (FORMAT_VERSION, DOMAIN_VERSION):
                                raise StateError("unsupported repository version")
                        finally:
                            _rollback(conn)
                    finally:
                        _close(conn)
                    return
                except (StateError, sqlite3.Error, OSError):
                    if time.monotonic() >= deadline:
                        raise StateError(
                            "repository incomplete or unavailable"
                        ) from None
                    time.sleep(min(0.01, max(0, deadline - time.monotonic())))
        fd = os.open(
            directory / DATABASE_NAME, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600
        )
        os.close(fd)
        conn = _connect(directory / DATABASE_NAME, deadline)
        try:
            _check_stop(stop)
            _busy(conn, deadline)
            conn.execute("BEGIN IMMEDIATE")
            try:
                conn.execute(
                    "CREATE TABLE domain_versions (domain TEXT PRIMARY KEY NOT NULL, version INTEGER NOT NULL CHECK (version > 0))"
                )
                conn.execute(
                    "CREATE TABLE known_categories (path TEXT PRIMARY KEY NOT NULL)"
                )
                conn.execute(
                    "INSERT INTO domain_versions(domain, version) VALUES ('categories', 1)"
                )
                conn.execute(f"PRAGMA application_id = {APPLICATION_ID}")
                conn.execute(f"PRAGMA user_version = {FORMAT_VERSION}")
                _check_stop(stop)
                _busy(conn, deadline)
                conn.commit()
            except BaseException:
                _rollback(conn)
                raise
        finally:
            _close(conn)
    except StateError:
        raise
    except (OSError, sqlite3.Error):
        raise StateError("repository initialization failed") from None


class SQLiteStorage:
    def __init__(
        self,
        directory: Path,
        *,
        stop: Any = None,
        migrations: Mapping[tuple[int, int], Migration] | None = None,
    ) -> None:
        self.path = Path(directory) / DATABASE_NAME
        self.stop = stop
        self.closed = False
        deadline = _deadline()
        _check_stop(stop)
        conn = None
        try:
            conn = _connect(self.path, deadline)
            # Read-only recognition avoids acquiring a write lock on current stores.
            _busy(conn, deadline)
            conn.execute("BEGIN")
            try:
                version = _validate(conn)
            finally:
                _rollback(conn)
            if version != (FORMAT_VERSION, DOMAIN_VERSION):
                _validate_or_migrate(conn, deadline, stop, migrations or {})
        except StateError:
            raise
        except (OSError, sqlite3.Error):
            raise StateError("repository unavailable") from None
        finally:
            if conn is not None:
                _close(conn)

    def _transaction(self, write: bool, paths: Iterable[str] = ()) -> list[str]:
        if self.closed:
            raise StateError("repository closed")
        _check_stop(self.stop)
        deadline = _deadline()
        conn = None
        try:
            conn = _connect(self.path, deadline)
            _check_stop(self.stop)
            _busy(conn, deadline)
            conn.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            if _validate(conn) != (FORMAT_VERSION, DOMAIN_VERSION):
                raise StateError("unsupported repository version")
            if write:
                paths = _category_values(paths)
                conn.executemany(
                    "INSERT OR IGNORE INTO known_categories(path) VALUES (?)",
                    ((p,) for p in paths),
                )
                for path in paths:
                    if (
                        not isinstance(path, str)
                        or conn.execute(
                            "SELECT 1 FROM known_categories WHERE path = ? COLLATE BINARY AND typeof(path) = 'text'",
                            (path,),
                        ).fetchone()
                        is None
                    ):
                        raise StateError("category update failed")
                result = []
            else:
                result = [
                    row[0]
                    for row in conn.execute(
                        "SELECT path FROM known_categories ORDER BY path COLLATE BINARY"
                    )
                ]
                if any(not isinstance(path, str) for path in result):
                    raise StateError("category read failed")
            _check_stop(self.stop)
            _busy(conn, deadline)
            conn.commit()
            return result
        except StateError:
            if conn is not None:
                _rollback(conn)
            raise
        except (OSError, sqlite3.Error):
            if conn is not None:
                _rollback(conn)
            raise StateError(
                "category update failed" if write else "category read failed"
            ) from None
        finally:
            if conn is not None:
                _close(conn)

    def snapshot_categories(self) -> list[str]:
        return self._transaction(False)

    def add_categories(self, paths: Iterable[str]) -> None:
        self._transaction(True, paths)

    def close(self) -> None:
        self.closed = True


class MemoryStorage:
    def __init__(self, *, stop: Any = None) -> None:
        self.paths: set[str] = set()
        self.stop = stop
        self.closed = False

    def snapshot_categories(self) -> list[str]:
        if self.closed:
            raise StateError("repository closed")
        _check_stop(self.stop)
        return sorted(self.paths)

    def add_categories(self, paths: Iterable[str]) -> None:
        if self.closed:
            raise StateError("repository closed")
        _check_stop(self.stop)
        values = _category_values(paths)
        _check_stop(self.stop)
        self.paths.update(values)

    def close(self) -> None:
        self.closed = True
