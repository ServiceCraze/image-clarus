"""Exercise registered fixture migrations, not a production schema upgrade."""

import multiprocessing
import sqlite3
from pathlib import Path

import pytest

from image_clarus.state import storage

PATHS = ["Animals/Birds", "Places/Éire"]
STEPS = (
    "CREATE TABLE migration_fixture (value TEXT NOT NULL)",
    "INSERT INTO migration_fixture VALUES ('preserved fixture')",
    f"PRAGMA application_id = {storage.APPLICATION_ID}",
    "PRAGMA user_version = 2",
    "UPDATE domain_versions SET version = 2 WHERE domain = 'categories'",
)


def _old_repository(directory):
    storage.initialize(directory)
    storage.SQLiteStorage(directory).add_categories(PATHS)


def _migration(fail_after=None):
    def migrate(conn):
        for index, sql in enumerate(STEPS, 1):
            conn.execute(sql)
            if index == fail_after:
                raise sqlite3.OperationalError("synthetic migration failure")

    return migrate


def _disk_state(directory):
    # Open a fresh, independent connection, not the migration handle.
    with sqlite3.connect(directory / storage.DATABASE_NAME) as conn:
        return (
            conn.execute("PRAGMA application_id").fetchone()[0],
            conn.execute("PRAGMA user_version").fetchone()[0],
            conn.execute("SELECT * FROM domain_versions ORDER BY domain").fetchall(),
            conn.execute("SELECT path FROM known_categories ORDER BY path").fetchall(),
            conn.execute(
                "SELECT name, sql FROM sqlite_master WHERE type = 'table' ORDER BY name"
            ).fetchall(),
        )


@pytest.fixture
def older_repository(tmp_path, monkeypatch):
    directory = tmp_path / "state"
    _old_repository(directory)
    before = _disk_state(directory)
    # Treat the real v1 layout as older only in this test; no production migration.
    monkeypatch.setattr(storage, "FORMAT_VERSION", 2)
    monkeypatch.setattr(storage, "DOMAIN_VERSION", 2)
    return directory, before


def test_registered_migration_commits_and_preserves_existing_data(older_repository):
    directory, before = older_repository
    store = storage.SQLiteStorage(directory, migrations={(1, 1): _migration()})
    assert store.snapshot_categories() == PATHS
    app, version, domains, paths, tables = _disk_state(directory)
    assert app == before[0]
    assert version == 2
    assert domains == [("categories", 2)]
    assert paths == before[3]
    assert {name for name, _ in tables} == {
        "domain_versions",
        "known_categories",
        "migration_fixture",
    }
    with sqlite3.connect(directory / storage.DATABASE_NAME) as conn:
        assert conn.execute("SELECT * FROM migration_fixture").fetchall() == [
            ("preserved fixture",)
        ]
    assert storage.SQLiteStorage(directory).snapshot_categories() == PATHS


@pytest.mark.parametrize("checkpoint", range(1, len(STEPS) + 1))
def test_migration_failure_rolls_back_every_checkpoint(older_repository, checkpoint):
    directory, before = older_repository
    with pytest.raises(storage.StateError, match="repository unavailable"):
        storage.SQLiteStorage(directory, migrations={(1, 1): _migration(checkpoint)})
    assert _disk_state(directory) == before
    # The rolled-back database can still be migrated successfully.
    assert (
        storage.SQLiteStorage(
            directory, migrations={(1, 1): _migration()}
        ).snapshot_categories()
        == PATHS
    )


def test_migration_commit_failure_rolls_back(older_repository, monkeypatch):
    directory, before = older_repository
    calls = []

    class CommitFailure(sqlite3.Connection):
        def commit(self):
            calls.append("commit")
            raise sqlite3.OperationalError("synthetic commit failure")

    def connect(path, deadline):
        conn = sqlite3.connect(
            path.resolve().as_uri() + "?mode=rw",
            uri=True,
            isolation_level=None,
            factory=CommitFailure,
        )
        storage._busy(conn, deadline)
        return conn

    with monkeypatch.context() as patch:
        patch.setattr(storage, "_connect", connect)
        with pytest.raises(storage.StateError, match="repository unavailable"):
            storage.SQLiteStorage(directory, migrations={(1, 1): _migration()})
    assert calls == ["commit"]
    assert _disk_state(directory) == before
    assert (
        storage.SQLiteStorage(
            directory, migrations={(1, 1): _migration()}
        ).snapshot_categories()
        == PATHS
    )


def _racing_opener(directory, barrier, reports):
    storage.FORMAT_VERSION = 2
    storage.DOMAIN_VERSION = 2
    original = storage._validate_or_migrate

    def synchronized(conn, deadline, stop, migrations):
        barrier.wait(timeout=5)  # Both processes recognized the older version.
        return original(conn, deadline, stop, migrations)

    def migrate(conn):
        reports.put("migration invoked")
        _migration()(conn)

    storage._validate_or_migrate = synchronized
    try:
        store = storage.SQLiteStorage(Path(directory), migrations={(1, 1): migrate})
        reports.put(("opened", store.snapshot_categories()))
    except (storage.StateError, sqlite3.Error, OSError, RuntimeError) as exc:
        reports.put(("error", type(exc).__name__, str(exc)))


def test_separate_processes_recheck_version_after_migration_lock(tmp_path):
    directory = tmp_path / "state"
    _old_repository(directory)
    ctx = multiprocessing.get_context("spawn")
    barrier, reports = ctx.Barrier(2), ctx.Queue()
    children = [
        ctx.Process(target=_racing_opener, args=(str(directory), barrier, reports))
        for _ in range(2)
    ]
    try:
        for child in children:
            child.start()
        for child in children:
            child.join(10)
            assert child.exitcode == 0
        messages = [reports.get(timeout=2) for _ in range(3)]
        assert messages.count("migration invoked") == 1
        assert messages.count(("opened", PATHS)) == 2
        with sqlite3.connect(directory / storage.DATABASE_NAME) as conn:
            assert conn.execute("PRAGMA user_version").fetchone() == (2,)
            assert conn.execute("SELECT version FROM domain_versions").fetchone() == (
                2,
            )
            assert conn.execute("SELECT * FROM migration_fixture").fetchall() == [
                ("preserved fixture",)
            ]
    finally:
        for child in children:
            if child.is_alive():
                child.terminate()
            if child.pid is not None:
                child.join(5)
        reports.close()
        reports.join_thread()
