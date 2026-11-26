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


def test_union_counts_and_migration_are_atomic(tmp_path, monkeypatch):
    directory = tmp_path / "state"
    initialize(directory)
    SQLiteStorage(directory).add_categories(["existing"])
    target = management.select_target(directory, tmp_path)
    monkeypatch.setattr(storage, "DOMAIN_VERSION", 2)

    def migrate(conn):
        conn.execute("CREATE TABLE migrated (value TEXT)")
        conn.execute("UPDATE domain_versions SET version=2 WHERE domain='categories'")

    migrations = {(1, 1): migrate}
    assert (
        management.union_categories(target, [], migrations=migrations).status
        == "skipped"
    )
    with sqlite3.connect(target.path) as conn:
        assert conn.execute("SELECT version FROM domain_versions").fetchone() == (1,)
    result = management.union_categories(
        target, ["existing", "new", "new", "second"], migrations=migrations
    )
    assert result == management.UnionResult("committed", True, 2)
    assert management.union_categories(target, ["new"]).inserted == 0
    with sqlite3.connect(target.path) as conn:
        assert conn.execute("SELECT version FROM domain_versions").fetchone() == (2,)
        assert conn.execute(
            "SELECT path FROM known_categories ORDER BY path"
        ).fetchall() == [("existing",), ("new",), ("second",)]
        assert conn.execute(
            "SELECT name FROM sqlite_master WHERE name='migrated'"
        ).fetchone()


@pytest.mark.parametrize("failure", ["migration", "insert", "stop", "replacement"])
def test_union_rolls_back_migration_and_insert(tmp_path, monkeypatch, failure):
    directory = tmp_path / "state"
    initialize(directory)
    target = management.select_target(directory, tmp_path)
    monkeypatch.setattr(storage, "DOMAIN_VERSION", 2)
    token = SimpleNamespace(signum=None)

    def migrate(conn):
        conn.execute("CREATE TABLE migrated (value TEXT)")
        conn.execute("UPDATE domain_versions SET version=2 WHERE domain='categories'")
        if failure == "migration":
            raise ValueError("fictional private detail")
        if failure == "insert":
            conn.execute("DROP TABLE known_categories")

    original_busy = storage._busy

    def busy(conn, deadline):
        original_busy(conn, deadline)
        if failure == "stop" and conn.in_transaction:
            token.signum = 15

    monkeypatch.setattr(storage, "_busy", busy)
    original_check = management.check_target
    checks = 0

    def check(value):
        nonlocal checks
        checks += 1
        if failure == "replacement" and checks == 3:
            raise StateError("repository target changed")
        original_check(value)

    monkeypatch.setattr(management, "check_target", check)
    result = management.union_categories(
        target, ["new"], stop=token, migrations={(1, 1): migrate}
    )
    assert result.status == ("interrupted" if failure == "stop" else "failed")
    assert result.attempted
    assert result.inserted == 0
    assert "fictional" not in (result.diagnostic or "")
    with sqlite3.connect(target.path) as conn:
        assert conn.execute("SELECT version FROM domain_versions").fetchone() == (1,)
        assert conn.execute("SELECT * FROM known_categories").fetchall() == []
        assert not conn.execute(
            "SELECT name FROM sqlite_master WHERE name='migrated'"
        ).fetchone()


@pytest.mark.parametrize("fault", ["begin", "commit", "commit_after", "close"])
def test_union_failure_outcomes(tmp_path, monkeypatch, fault):
    directory = tmp_path / "state"
    initialize(directory)
    target = management.select_target(directory, tmp_path)

    class FaultConnection(sqlite3.Connection):
        def execute(self, sql, parameters=()):
            if fault == "begin" and sql == "BEGIN IMMEDIATE":
                raise sqlite3.OperationalError("synthetic")
            return super().execute(sql, parameters)

        def commit(self):
            if fault == "commit_after":
                super().commit()
            if fault in ("commit", "commit_after"):
                raise sqlite3.OperationalError("synthetic")
            return super().commit()

        def close(self):
            super().close()
            if fault == "close":
                raise sqlite3.OperationalError("synthetic")

    def connect(path, deadline):
        return sqlite3.connect(
            path.as_uri() + "?mode=rw",
            uri=True,
            isolation_level=None,
            factory=FaultConnection,
        )

    monkeypatch.setattr(storage, "_connect", connect)
    result = management.union_categories(target, ["new"])
    assert (
        result.status
        == {
            "begin": "failed",
            "commit": "unknown",
            "commit_after": "unknown",
            "close": "committed",
        }[fault]
    )
    assert result.attempted == (fault != "begin")
    assert result.inserted == (1 if fault == "close" else 0)
    assert result.close_failed == (fault == "close")
    with sqlite3.connect(target.path) as conn:
        assert conn.execute("SELECT * FROM known_categories").fetchall() == (
            [("new",)] if fault in ("close", "commit_after") else []
        )


def test_union_rollback_failure_is_unknown(tmp_path, monkeypatch):
    directory = tmp_path / "state"
    initialize(directory)
    target = management.select_target(directory, tmp_path)

    class FaultConnection(sqlite3.Connection):
        def execute(self, sql, parameters=()):
            if sql.startswith("INSERT OR IGNORE"):
                raise sqlite3.OperationalError("synthetic")
            return super().execute(sql, parameters)

        def rollback(self):
            raise sqlite3.OperationalError("synthetic")

    def connect(path, deadline):
        return sqlite3.connect(
            path.as_uri() + "?mode=rw",
            uri=True,
            isolation_level=None,
            factory=FaultConnection,
        )

    monkeypatch.setattr(storage, "_connect", connect)
    result = management.union_categories(target, ["new"])
    assert result.status == "unknown"
    assert result.attempted and result.inserted == 0
    with sqlite3.connect(target.path) as conn:
        assert conn.execute("SELECT * FROM known_categories").fetchall() == []


def test_union_rejects_bad_input_before_open(tmp_path, monkeypatch):
    directory = tmp_path / "state"
    initialize(directory)
    target = management.select_target(directory, tmp_path)
    monkeypatch.setattr(
        storage, "_connect", lambda *_: pytest.fail("unexpected write open")
    )
    assert management.union_categories(target, "scalar").status == "failed"
    assert management.union_categories(target, []).status == "skipped"


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


def test_clear_reports_migration_required_after_rollback(tmp_path, monkeypatch):
    directory = tmp_path / "state"
    initialize(directory)
    SQLiteStorage(directory).add_categories(["A/B"])
    target = management.select_target(directory, tmp_path)
    monkeypatch.setattr(storage, "DOMAIN_VERSION", 2)
    with pytest.raises(StateError, match="^repository migration required$"):
        management.clear_categories(target)
    with sqlite3.connect(target.path) as conn:
        assert conn.execute("SELECT path FROM known_categories").fetchall() == [
            ("A/B",)
        ]


def test_clear_reports_replacement_at_precommit_and_rolls_back(tmp_path, monkeypatch):
    directory = tmp_path / "state"
    initialize(directory)
    SQLiteStorage(directory).add_categories(["A/B"])
    target = management.select_target(directory, tmp_path)
    original = management.check_target
    calls = 0

    def check(value):
        nonlocal calls
        calls += 1
        if calls == 3:
            raise StateError("repository target changed")
        original(value)

    monkeypatch.setattr(management, "check_target", check)
    with pytest.raises(StateError, match="^repository target changed$"):
        management.clear_categories(target)
    assert calls == 3
    assert SQLiteStorage(directory).snapshot_categories() == ["A/B"]


@pytest.mark.parametrize(
    "failure,diagnostic",
    [
        ("migration", "repository migration required"),
        ("replacement", "repository target changed"),
    ],
)
def test_clear_cli_reports_specific_safe_error(
    tmp_path, monkeypatch, capsys, failure, diagnostic
):
    import sys

    from image_clarus import cli

    directory = tmp_path / "state"
    initialize(directory)
    SQLiteStorage(directory).add_categories(["A/B"])
    if failure == "migration":
        monkeypatch.setattr(storage, "DOMAIN_VERSION", 2)
    else:
        original = management.check_target
        calls = 0

        def check(target):
            nonlocal calls
            calls += 1
            if calls == 3:
                raise StateError("repository target changed")
            original(target)

        monkeypatch.setattr(management, "check_target", check)
    monkeypatch.setattr(
        sys,
        "argv",
        ["image-clarus", "state", "categories", "clear", "--state-dir", str(directory)],
    )
    assert cli.main() == 1
    output = capsys.readouterr()
    assert output.err == f"image-clarus: {diagnostic}\n"
    assert "deleted=" not in output.out
    with sqlite3.connect(directory / storage.DATABASE_NAME) as conn:
        assert conn.execute("SELECT path FROM known_categories").fetchall() == [
            ("A/B",)
        ]
