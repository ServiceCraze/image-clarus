"""Strict, logically read-only category snapshots of an existing repository."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from image_clarus.state.storage import (
    DATABASE_NAME,
    DOMAIN_VERSION,
    FORMAT_VERSION,
    TIMEOUT,
    StateError,
    _validate,
)


def list_categories(directory: Path) -> list[str]:
    """List one consistent snapshot; never initialize, migrate, or fall back.

    The directory is the already-selected repository directory. SQLite's normal
    journal and shared-memory handling is permitted; application data and schema
    are not modified. Errors contain no path, database message, or category data.
    """
    conn = None
    try:
        path = (Path(directory) / DATABASE_NAME).resolve(strict=True)
        conn = sqlite3.connect(
            path.as_uri() + "?mode=ro", uri=True, timeout=TIMEOUT, isolation_level=None
        )
        conn.execute("BEGIN")
        # Force the snapshot before recognition, not merely at enumeration.
        conn.execute("SELECT count(*) FROM sqlite_master").fetchone()
        if _validate(conn) != (FORMAT_VERSION, DOMAIN_VERSION):
            raise StateError("repository migration required")
        values = [
            row[0]
            for row in conn.execute(
                "SELECT path FROM known_categories ORDER BY path COLLATE BINARY"
            )
        ]
        if any(not isinstance(value, str) for value in values):
            raise StateError("category read failed")
        conn.rollback()
        return values
    except StateError:
        raise
    except (OSError, ValueError, sqlite3.Error, UnicodeError):
        raise StateError("repository read failed") from None
    finally:
        if conn is not None:
            # Preserve an active failure if cleanup itself fails.
            import sys

            failed = sys.exc_info()[0] is not None
            try:
                conn.close()
            except sqlite3.Error:
                if not failed:
                    raise StateError("repository close failed") from None
