import multiprocessing
import signal
import sqlite3
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from image_clarus.state import storage
from image_clarus.state.storage import (
    DATABASE_NAME,
    SQLiteStorage,
    StateError,
    StateStopped,
    initialize,
)


def _writer(directory, barrier, queue, path):
    try:
        store = SQLiteStorage(Path(directory))
        barrier.wait(timeout=5)
        store.add_categories([path])
        queue.put((None, store.snapshot_categories()))
    except (StateError, RuntimeError, OSError) as exc:
        queue.put(repr(exc))


def test_special_uri_and_missing_open_is_non_destructive(tmp_path):
    directory = tmp_path / "space ? # café"
    with pytest.raises(StateError):
        SQLiteStorage(directory)
    assert not directory.exists()
    initialize(directory)
    store = SQLiteStorage(directory)
    store.add_categories(["Things/Éclair", "things/éclair"])
    assert SQLiteStorage(directory).snapshot_categories() == [
        "Things/Éclair",
        "things/éclair",
    ]
    (directory / DATABASE_NAME).unlink()
    with pytest.raises(StateError):
        store.add_categories(["lost"])
    assert not (directory / DATABASE_NAME).exists()


def test_independent_processes_concurrent_union(tmp_path):
    directory = tmp_path / "state"
    initialize(directory)
    ctx = multiprocessing.get_context("spawn")
    barrier, queue = ctx.Barrier(2), ctx.Queue()
    processes = [
        ctx.Process(target=_writer, args=(str(directory), barrier, queue, p))
        for p in ("A/B/C", "A/B/D")
    ]
    try:
        for process in processes:
            process.start()
        for process in processes:
            process.join(10)
            assert process.exitcode == 0
        reports = [queue.get(timeout=2) for _ in processes]
        assert all(
            isinstance(report, tuple) and report[0] is None for report in reports
        )
        assert ["A/B/C", "A/B/D"] in [report[1] for report in reports]
        assert SQLiteStorage(directory).snapshot_categories() == ["A/B/C", "A/B/D"]
    finally:
        for process in processes:
            if process.is_alive():
                process.terminate()
            if process.pid is not None:
                process.join(5)
        queue.close()


def test_existing_directory_and_corrupt_database_are_preserved(tmp_path):
    directory = tmp_path / "existing"
    directory.mkdir()
    marker = directory / "notes"
    marker.write_bytes(b"untouched")
    with pytest.raises(StateError):
        initialize(directory)
    assert marker.read_bytes() == b"untouched"
    db = directory / DATABASE_NAME
    db.write_bytes(b"not a database")
    with pytest.raises(StateError):
        initialize(directory)
    with pytest.raises(StateError):
        SQLiteStorage(directory)
    assert db.read_bytes() == b"not a database"


def test_rejects_counterfeit_schema_without_primary_keys(tmp_path):
    directory = tmp_path / "state"
    directory.mkdir()
    with sqlite3.connect(directory / DATABASE_NAME) as conn:
        conn.execute(f"PRAGMA application_id={storage.APPLICATION_ID}")
        conn.execute("PRAGMA user_version=1")
        conn.execute("CREATE TABLE domain_versions (domain TEXT, version INTEGER)")
        conn.execute("CREATE TABLE known_categories (path TEXT)")
        conn.execute("INSERT INTO domain_versions VALUES ('categories', 1)")
    with pytest.raises(StateError):
        SQLiteStorage(directory)


def test_version_rejection_preserves_data(tmp_path):
    directory = tmp_path / "state"
    initialize(directory)
    SQLiteStorage(directory).add_categories(["A/B"])
    with sqlite3.connect(directory / DATABASE_NAME) as conn:
        conn.execute("PRAGMA user_version=99")
    with pytest.raises(StateError):
        SQLiteStorage(directory)
    with sqlite3.connect(directory / DATABASE_NAME) as conn:
        assert conn.execute("SELECT path FROM known_categories").fetchall() == [
            ("A/B",)
        ]
        assert conn.execute("PRAGMA user_version").fetchone() == (99,)


def test_migration_rolls_back_ddl_and_versions_on_fault(tmp_path, monkeypatch):
    directory = tmp_path / "state"
    initialize(directory)
    SQLiteStorage(directory).add_categories(["A/B"])
    monkeypatch.setattr(storage, "DOMAIN_VERSION", 2)

    def migration(conn):
        conn.execute("CREATE TABLE fixture_data (value TEXT)")
        conn.execute("UPDATE domain_versions SET version=2 WHERE domain='categories'")
        raise sqlite3.OperationalError("private fixture error")

    with pytest.raises(StateError, match="repository unavailable"):
        SQLiteStorage(directory, migrations={(1, 1): migration})
    with sqlite3.connect(directory / DATABASE_NAME) as conn:
        assert conn.execute("SELECT path FROM known_categories").fetchall() == [
            ("A/B",)
        ]
        assert conn.execute("SELECT version FROM domain_versions").fetchone() == (1,)
        assert (
            conn.execute(
                "SELECT name FROM sqlite_master WHERE name='fixture_data'"
            ).fetchall()
            == []
        )

    def successful(conn):
        conn.execute("CREATE TABLE fixture_data (value TEXT)")
        conn.execute("UPDATE domain_versions SET version=2 WHERE domain='categories'")

    assert SQLiteStorage(
        directory, migrations={(1, 1): successful}
    ).snapshot_categories() == ["A/B"]
    assert SQLiteStorage(directory).snapshot_categories() == ["A/B"]


def test_idempotent_init_and_invalid_identity_preserve_state(tmp_path):
    directory = tmp_path / "state"
    initialize(directory)
    SQLiteStorage(directory).add_categories(["A/B/C"])
    initialize(directory)
    assert SQLiteStorage(directory).snapshot_categories() == ["A/B/C"]
    with sqlite3.connect(directory / DATABASE_NAME) as conn:
        conn.execute("PRAGMA application_id=123")
    with pytest.raises(StateError):
        SQLiteStorage(directory)
    with sqlite3.connect(directory / DATABASE_NAME) as conn:
        assert conn.execute("SELECT path FROM known_categories").fetchall() == [
            ("A/B/C",)
        ]


def test_locked_reader_is_bounded(tmp_path):
    directory = tmp_path / "state"
    initialize(directory)
    store = SQLiteStorage(directory)
    conn = sqlite3.connect(directory / DATABASE_NAME, isolation_level=None)
    try:
        conn.execute("BEGIN EXCLUSIVE")
        start = time.monotonic()
        with pytest.raises(StateError, match="category read failed"):
            store.snapshot_categories()
        assert 0.15 <= time.monotonic() - start < 1.5
    finally:
        conn.rollback()
        conn.close()


def test_locked_writer_is_bounded_and_preserves_data(tmp_path):
    directory = tmp_path / "state"
    initialize(directory)
    store = SQLiteStorage(directory)
    store.add_categories(["A/B"])
    conn = sqlite3.connect(directory / DATABASE_NAME, isolation_level=None)
    try:
        conn.execute("BEGIN IMMEDIATE")
        start = time.monotonic()
        with pytest.raises(StateError, match="category update failed"):
            store.add_categories(["C/D"])
        elapsed = time.monotonic() - start
        assert 0.15 <= elapsed < 1.5
    finally:
        conn.rollback()
        conn.close()
    assert store.snapshot_categories() == ["A/B"]


def test_stop_before_begin_and_before_commit_rolls_back(tmp_path):
    directory = tmp_path / "state"
    initialize(directory)
    token = SimpleNamespace(signum=2)
    store = SQLiteStorage(directory)
    store.stop = token
    with pytest.raises(StateStopped):
        store.add_categories(["A/B"])
    token.signum = None

    def paths():
        yield "A/B"
        token.signum = 15

    with pytest.raises(StateStopped):
        store.add_categories(paths())
    token.signum = None
    assert store.snapshot_categories() == []


@pytest.mark.parametrize("signum", [signal.SIGINT, signal.SIGTERM])
@pytest.mark.parametrize("operation", ["initialize", "migration", "write"])
def test_stop_during_final_busy_rolls_back_before_commit(
    tmp_path, monkeypatch, operation, signum
):
    directory = tmp_path / "state"
    token = SimpleNamespace(signum=None)
    if operation != "initialize":
        initialize(directory)
        SQLiteStorage(directory).add_categories(["existing"])
    if operation == "migration":
        monkeypatch.setattr(storage, "DOMAIN_VERSION", 2)

    real_busy = storage._busy
    injected = []

    def stop_during_busy(conn, deadline):
        real_busy(conn, deadline)
        if conn.in_transaction:
            token.signum = signum
            injected.append(signum)

    monkeypatch.setattr(storage, "_busy", stop_during_busy)

    def migrate(conn):
        conn.execute("UPDATE domain_versions SET version=2 WHERE domain='categories'")
        conn.execute("INSERT INTO known_categories VALUES ('migrated')")

    with pytest.raises(StateStopped):
        if operation == "initialize":
            initialize(directory, stop=token)
        elif operation == "migration":
            SQLiteStorage(directory, stop=token, migrations={(1, 1): migrate})
        else:
            SQLiteStorage(directory, stop=token).add_categories(["new"])
    assert injected == [signum]
    with sqlite3.connect(directory / DATABASE_NAME) as conn:
        if operation == "initialize":
            assert (
                conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
                == []
            )
            assert conn.execute("PRAGMA application_id").fetchone() == (0,)
            assert conn.execute("PRAGMA user_version").fetchone() == (0,)
        else:
            assert conn.execute("SELECT path FROM known_categories").fetchall() == [
                ("existing",)
            ]
            assert conn.execute("SELECT version FROM domain_versions").fetchone() == (
                1,
            )


@pytest.mark.parametrize("fault_at", [1, 2, 3, 4, 5, 6])
def test_initialization_faults_rollback_each_schema_step(
    tmp_path, monkeypatch, fault_at
):
    directory = tmp_path / "state"
    real_connect = storage._connect

    class FaultConnection(sqlite3.Connection):
        count = 0

        def execute(self, sql, parameters=()):
            result = super().execute(sql, parameters)
            if sql.startswith(
                (
                    "CREATE TABLE",
                    "INSERT INTO",
                    "PRAGMA application_id =",
                    "PRAGMA user_version =",
                )
            ):
                self.count += 1
                if self.count == fault_at:
                    raise sqlite3.OperationalError("fictional fault")
            return result

        def commit(self):
            if fault_at == 6:
                raise sqlite3.OperationalError("fictional commit fault")
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
    with pytest.raises(StateError):
        initialize(directory)
    monkeypatch.setattr(storage, "_connect", real_connect)
    with sqlite3.connect(directory / DATABASE_NAME) as conn:
        assert (
            conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            == []
        )
        assert conn.execute("PRAGMA application_id").fetchone() == (0,)
        assert conn.execute("PRAGMA user_version").fetchone() == (0,)
    with pytest.raises(StateError):
        initialize(directory)


def test_failed_commit_rolls_back_union(tmp_path, monkeypatch):
    directory = tmp_path / "state"
    initialize(directory)
    store = SQLiteStorage(directory)
    store.add_categories(["A/B"])

    class FaultConnection(sqlite3.Connection):
        def commit(self):
            raise sqlite3.OperationalError("fictional commit error")

    def connect(path, deadline):
        conn = sqlite3.connect(
            path.resolve().as_uri() + "?mode=rw",
            uri=True,
            isolation_level=None,
            factory=FaultConnection,
        )
        storage._busy(conn, deadline)
        return conn

    with monkeypatch.context() as patch:
        patch.setattr(storage, "_connect", connect)
        with pytest.raises(StateError, match="category update failed"):
            store.add_categories(["C/D"])
    assert store.snapshot_categories() == ["A/B"]
