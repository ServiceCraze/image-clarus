import sqlite3
import traceback

import pytest

from image_clarus.state import storage


def test_nocase_primary_key_is_rejected(tmp_path):
    directory = tmp_path / "state"
    storage.initialize(directory)
    with sqlite3.connect(directory / storage.DATABASE_NAME) as conn:
        conn.execute("DROP TABLE known_categories")
        conn.execute(
            "CREATE TABLE known_categories (path TEXT COLLATE NOCASE PRIMARY KEY NOT NULL)"
        )
    with pytest.raises(storage.StateError):
        storage.SQLiteStorage(directory)


def test_silent_ignore_trigger_is_rejected(tmp_path):
    directory = tmp_path / "state"
    storage.initialize(directory)
    with sqlite3.connect(directory / storage.DATABASE_NAME) as conn:
        conn.execute(
            "CREATE TRIGGER discard BEFORE INSERT ON known_categories BEGIN SELECT RAISE(IGNORE); END"
        )
    with pytest.raises(storage.StateError):
        storage.SQLiteStorage(directory)


def test_blob_category_is_never_returned(tmp_path):
    directory = tmp_path / "state"
    storage.initialize(directory)
    store = storage.SQLiteStorage(directory)
    with sqlite3.connect(directory / storage.DATABASE_NAME) as conn:
        conn.execute("INSERT INTO known_categories VALUES (?)", (b"private-data",))
    with pytest.raises(storage.StateError) as error:
        store.snapshot_categories()
    assert "private-data" not in str(error.value)


def test_connect_setup_failure_closes_handle(tmp_path, monkeypatch):
    directory = tmp_path / "state"
    storage.initialize(directory)
    handles = []
    real_connect = sqlite3.connect

    class Connection(sqlite3.Connection):
        def close(self):
            handles.append("closed")
            super().close()

    def connect(*args, **kwargs):
        return real_connect(*args, **kwargs, factory=Connection)

    monkeypatch.setattr(storage.sqlite3, "connect", connect)
    monkeypatch.setattr(
        storage,
        "_busy",
        lambda *_: (_ for _ in ()).throw(sqlite3.OperationalError("private")),
    )
    with pytest.raises(storage.StateError):
        storage.SQLiteStorage(directory)
    assert handles == ["closed"]


def test_cleanup_failures_do_not_mask_primary_state_error(tmp_path, monkeypatch):
    directory = tmp_path / "state"
    storage.initialize(directory)
    store = storage.SQLiteStorage(directory)
    real_connect = sqlite3.connect
    calls = []

    class Connection(sqlite3.Connection):
        def executemany(self, *args):
            raise sqlite3.OperationalError("private primary")

        def rollback(self):
            calls.append("rollback")
            raise sqlite3.OperationalError("private rollback")

        def close(self):
            calls.append("close")
            super().close()
            raise sqlite3.OperationalError("private close")

    def connect(path, deadline):
        return real_connect(path, isolation_level=None, factory=Connection)

    monkeypatch.setattr(storage, "_connect", connect)
    with pytest.raises(storage.StateError, match="category update failed") as error:
        store.add_categories(["test"])
    assert "private" not in "".join(traceback.format_exception(error.value))
    assert calls == ["rollback", "close"]


def test_close_failure_after_commit_is_typed_failure(tmp_path, monkeypatch):
    directory = tmp_path / "state"
    storage.initialize(directory)
    store = storage.SQLiteStorage(directory)
    real_connect = sqlite3.connect

    class Connection(sqlite3.Connection):
        def close(self):
            super().close()
            raise sqlite3.OperationalError("private close")

    monkeypatch.setattr(
        storage,
        "_connect",
        lambda path, deadline: real_connect(
            path, isolation_level=None, factory=Connection
        ),
    )
    with pytest.raises(storage.StateError) as error:
        store.add_categories(["test"])
    assert "private" not in "".join(traceback.format_exception(error.value))


def test_migration_callback_exception_is_sanitized(tmp_path, monkeypatch):
    directory = tmp_path / "state"
    storage.initialize(directory)
    monkeypatch.setattr(storage, "DOMAIN_VERSION", 2)

    def migrate(conn):
        raise ValueError("private callback")

    with pytest.raises(storage.StateError) as error:
        storage.SQLiteStorage(directory, migrations={(1, 1): migrate})
    assert "private" not in "".join(traceback.format_exception(error.value))


def test_migration_cycle_is_rejected(tmp_path, monkeypatch):
    directory = tmp_path / "state"
    storage.initialize(directory)
    monkeypatch.setattr(storage, "DOMAIN_VERSION", 3)
    calls = []

    def one(conn):
        calls.append(1)
        if len(calls) > 3:
            raise RuntimeError("cycle was not detected")
        conn.execute("UPDATE domain_versions SET version=2")

    def two(conn):
        conn.execute("UPDATE domain_versions SET version=1")

    with pytest.raises(storage.StateError, match="invalid repository migration"):
        storage.SQLiteStorage(directory, migrations={(1, 1): one, (1, 2): two})
    assert calls == [1]


def test_other_domain_and_its_trigger_are_allowed(tmp_path):
    directory = tmp_path / "state"
    storage.initialize(directory)
    with sqlite3.connect(directory / storage.DATABASE_NAME) as conn:
        conn.execute("INSERT INTO domain_versions VALUES ('future', 1)")
        conn.execute("CREATE TABLE future (value TEXT)")
        conn.execute(
            "CREATE TRIGGER future_trigger AFTER INSERT ON future BEGIN SELECT 1; END"
        )
    store = storage.SQLiteStorage(directory)
    store.add_categories(["A", "a"])
    assert store.snapshot_categories() == ["A", "a"]


def test_additional_unique_constraint_cannot_silently_drop_union(tmp_path):
    directory = tmp_path / "state"
    storage.initialize(directory)
    with sqlite3.connect(directory / storage.DATABASE_NAME) as conn:
        conn.execute(
            "CREATE UNIQUE INDEX folded ON known_categories(path COLLATE NOCASE)"
        )
    store = storage.SQLiteStorage(directory)
    with pytest.raises(storage.StateError):
        store.add_categories(["A", "a"])
    assert store.snapshot_categories() == []


@pytest.mark.parametrize("operation", ["open", "initialize", "migration"])
def test_cleanup_sqlite_errors_during_setup_are_sanitized(
    tmp_path, monkeypatch, operation
):
    directory = tmp_path / "state"
    if operation != "initialize":
        storage.initialize(directory)
    if operation == "migration":
        monkeypatch.setattr(storage, "DOMAIN_VERSION", 2)
    real_connect = sqlite3.connect
    closed = []
    rollbacks = []

    class Connection(sqlite3.Connection):
        def rollback(self):
            rollbacks.append(True)
            if operation != "migration" or len(rollbacks) > 1:
                raise sqlite3.OperationalError("private rollback")
            return super().rollback()

        def close(self):
            closed.append(True)
            super().close()
            raise sqlite3.OperationalError("private close")

    monkeypatch.setattr(
        storage,
        "_connect",
        lambda path, deadline: real_connect(
            path, isolation_level=None, factory=Connection
        ),
    )
    with pytest.raises(storage.StateError) as error:
        if operation == "initialize":
            storage.initialize(directory)
        elif operation == "migration":
            storage.SQLiteStorage(
                directory,
                migrations={
                    (1, 1): lambda conn: (_ for _ in ()).throw(
                        ValueError("private migration")
                    )
                },
            )
        else:
            storage.SQLiteStorage(directory)
    assert "private" not in "".join(traceback.format_exception(error.value))
    assert closed == [True]


@pytest.mark.parametrize("when", ["open", "write"])
def test_case_insensitive_trigger_table_is_rejected_without_data_loss(tmp_path, when):
    directory = tmp_path / "state"
    storage.initialize(directory)
    store = storage.SQLiteStorage(directory)
    store.add_categories(["old"])
    with sqlite3.connect(directory / storage.DATABASE_NAME) as conn:
        conn.execute(
            "CREATE TRIGGER destructive AFTER INSERT ON KNOWN_CATEGORIES "
            "BEGIN DELETE FROM known_categories WHERE path = 'old'; END"
        )
    with pytest.raises(storage.StateError):
        if when == "open":
            storage.SQLiteStorage(directory)
        else:
            store.add_categories(["new"])
    with sqlite3.connect(directory / storage.DATABASE_NAME) as conn:
        assert conn.execute("SELECT path FROM known_categories").fetchall() == [
            ("old",)
        ]


@pytest.mark.parametrize("backend", ["memory", "sqlite"])
@pytest.mark.parametrize("kind", ["iterator", "nonstring", "surrogate"])
def test_invalid_write_is_atomic_typed_and_sanitized(tmp_path, backend, kind):
    if backend == "sqlite":
        directory = tmp_path / "state"
        storage.initialize(directory)
        store = storage.SQLiteStorage(directory)
    else:
        store = storage.MemoryStorage()
    store.add_categories(["old"])
    sentinel = "fictional-sensitive-marker"

    def broken():
        yield "new"
        raise ValueError(sentinel)

    values = {
        "iterator": broken(),
        "nonstring": ["new", 123],
        "surrogate": ["new", sentinel + "\ud800"],
    }[kind]
    with pytest.raises(storage.StateError) as error:
        store.add_categories(values)
    assert sentinel not in "".join(traceback.format_exception(error.value))
    assert store.snapshot_categories() == ["old"]


@pytest.mark.parametrize("backend", ["memory", "sqlite"])
def test_valid_unicode_full_paths_are_preserved(tmp_path, backend):
    if backend == "sqlite":
        directory = tmp_path / "state"
        storage.initialize(directory)
        store = storage.SQLiteStorage(directory)
    else:
        store = storage.MemoryStorage()
    paths = ["/根/🐈", "a|b/ c ", "a\x00b", "", "é/🖼"]
    store.add_categories(paths)
    assert store.snapshot_categories() == sorted(paths)


@pytest.mark.parametrize("backend", ["memory", "sqlite"])
@pytest.mark.parametrize("value", ["food/desserts/cookies", ""])
def test_scalar_string_is_rejected_without_mutation(tmp_path, backend, value):
    if backend == "sqlite":
        directory = tmp_path / "state"
        storage.initialize(directory)
        store = storage.SQLiteStorage(directory)
    else:
        store = storage.MemoryStorage()
    store.add_categories(["existing/path"])
    with pytest.raises(storage.StateError, match="category update failed") as error:
        store.add_categories(value)
    assert str(error.value) == "category update failed"
    assert store.snapshot_categories() == ["existing/path"]
    store.add_categories(["food/desserts/cookies"])
    assert store.snapshot_categories() == ["existing/path", "food/desserts/cookies"]
