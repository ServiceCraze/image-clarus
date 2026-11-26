"""Strict management selection and clear transaction tests."""

import sqlite3
from types import SimpleNamespace

import pytest

from image_clarus.state import management, storage
from image_clarus.state.storage import (
    SQLiteStorage,
    StateError,
    StateStopped,
    initialize,
)


def test_clear_preserves_unrelated_state(tmp_path):
    directory = tmp_path / ".image-clarus"
    initialize(directory)
    SQLiteStorage(directory).add_categories(["A/B", "C/D"])
    with sqlite3.connect(directory / storage.DATABASE_NAME) as conn:
        conn.execute("CREATE TABLE other (value TEXT)")
        conn.execute("INSERT INTO other VALUES ('retained')")
    target = management.select_target(None, tmp_path)
    assert management.clear_categories(target) == 2
    assert management.clear_categories(target) == 0
    with sqlite3.connect(target.path) as conn:
        assert conn.execute("SELECT * FROM other").fetchall() == [("retained",)]
        assert conn.execute("SELECT * FROM known_categories").fetchall() == []


def test_missing_and_explicit_invalid_never_select_alternate(tmp_path):
    with pytest.raises(StateError):
        management.select_target(None, tmp_path)
    initialize(tmp_path / ".image-clarus")
    with pytest.raises(StateError):
        management.select_target(tmp_path / "missing", tmp_path)


def test_clear_migration_and_delete_commit_together(tmp_path, monkeypatch):
    directory = tmp_path / "state"
    initialize(directory)
    SQLiteStorage(directory).add_categories(["A/B"])
    target = management.select_target(directory, tmp_path)
    monkeypatch.setattr(storage, "DOMAIN_VERSION", 2)

    def migrate(conn):
        conn.execute("UPDATE domain_versions SET version=2 WHERE domain='categories'")
        conn.execute("CREATE TABLE migrated (value TEXT)")

    assert management.clear_categories(target, migrations={(1, 1): migrate}) == 1
    with sqlite3.connect(target.path) as conn:
        assert conn.execute("SELECT version FROM domain_versions").fetchone() == (2,)
        assert conn.execute("SELECT count(*) FROM known_categories").fetchone() == (0,)
        assert conn.execute(
            "SELECT name FROM sqlite_master WHERE name='migrated'"
        ).fetchone()


def test_clear_migration_failure_rolls_back(tmp_path, monkeypatch):
    directory = tmp_path / "state"
    initialize(directory)
    SQLiteStorage(directory).add_categories(["A/B"])
    target = management.select_target(directory, tmp_path)
    monkeypatch.setattr(storage, "DOMAIN_VERSION", 2)

    def migrate(conn):
        conn.execute("UPDATE domain_versions SET version=2 WHERE domain='categories'")
        raise ValueError("synthetic private message")

    with pytest.raises(StateError):
        management.clear_categories(target, migrations={(1, 1): migrate})
    with sqlite3.connect(target.path) as conn:
        assert conn.execute("SELECT version FROM domain_versions").fetchone() == (1,)
        assert conn.execute("SELECT path FROM known_categories").fetchall() == [
            ("A/B",)
        ]


def test_clear_stop_before_commit_rolls_back(tmp_path, monkeypatch):
    directory = tmp_path / "state"
    initialize(directory)
    SQLiteStorage(directory).add_categories(["A/B"])
    target = management.select_target(directory, tmp_path)
    token = SimpleNamespace(signum=None)
    real_busy = storage._busy

    def stop_after_delete(conn, deadline):
        real_busy(conn, deadline)
        if conn.in_transaction:
            token.signum = 15

    monkeypatch.setattr(storage, "_busy", stop_after_delete)
    with pytest.raises(StateStopped):
        management.clear_categories(target, stop=token)
    assert SQLiteStorage(directory).snapshot_categories() == ["A/B"]


def test_clear_detects_target_replacement(tmp_path):
    directory = tmp_path / "state"
    initialize(directory)
    target = management.select_target(directory, tmp_path)
    replacement = tmp_path / "other"
    initialize(replacement)
    target.path.rename(tmp_path / "old.sqlite3")
    (replacement / storage.DATABASE_NAME).replace(target.path)
    if target.identity is None:
        pytest.skip("filesystem does not expose stable file identity")
    with pytest.raises(StateError):
        management.clear_categories(target)


@pytest.mark.parametrize("fault", ["begin", "delete", "commit"])
def test_clear_transaction_failures_do_not_report_success(tmp_path, monkeypatch, fault):
    directory = tmp_path / "state"
    initialize(directory)
    SQLiteStorage(directory).add_categories(["A/B"])
    target = management.select_target(directory, tmp_path)

    class FaultConnection(sqlite3.Connection):
        def execute(self, sql, parameters=()):
            if (fault == "begin" and sql == "BEGIN IMMEDIATE") or (
                fault == "delete" and sql == "DELETE FROM known_categories"
            ):
                raise sqlite3.OperationalError("synthetic fault")
            return super().execute(sql, parameters)

        def commit(self):
            if fault == "commit":
                raise sqlite3.OperationalError("synthetic fault")
            return super().commit()

    def connect(path, deadline):
        conn = sqlite3.connect(
            path.resolve().as_uri() + "?mode=rw",
            uri=True,
            isolation_level=None,
            factory=FaultConnection,
        )
        storage._busy(conn, deadline)
        return conn

    monkeypatch.setattr(storage, "_connect", connect)
    with pytest.raises(StateError) as error:
        management.clear_categories(target)
    assert "synthetic fault" not in str(error.value)
    if fault == "commit":
        assert "unknown" in str(error.value)
    with sqlite3.connect(target.path) as conn:
        assert conn.execute("SELECT path FROM known_categories").fetchall() == [
            ("A/B",)
        ]


def test_clear_without_optional_file_identity(tmp_path, monkeypatch):
    directory = tmp_path / "state"
    initialize(directory)
    SQLiteStorage(directory).add_categories(["A/B"])
    monkeypatch.setattr(management, "_identity", lambda _path: None)
    target = management.select_target(directory, tmp_path)
    assert target.identity is None
    assert management.clear_categories(target) == 1


def test_inaccessible_target_is_sanitized(tmp_path, monkeypatch):
    directory = tmp_path / "state"
    initialize(directory)

    def denied(_path):
        raise PermissionError("fictional private path")

    monkeypatch.setattr(management, "_identity", denied)
    with pytest.raises(StateError) as error:
        management.select_target(directory, tmp_path)
    assert str(error.value) == "repository unavailable"
