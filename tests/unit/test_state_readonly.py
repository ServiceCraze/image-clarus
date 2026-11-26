"""Focused logical read-only access tests using fictitious repositories."""

import sqlite3

import pytest

from image_clarus.state import readonly, storage
from image_clarus.state.storage import DATABASE_NAME, StateError, initialize


def connect(directory):
    return sqlite3.connect(directory / DATABASE_NAME, isolation_level=None)


def test_recognition_old_registered_is_read_only(tmp_path, monkeypatch):
    from image_clarus.state import management

    directory = tmp_path / "repo"
    initialize(directory)
    target = management.select_target(directory, tmp_path)
    before = contents(directory)
    monkeypatch.setattr(storage, "DOMAIN_VERSION", 2)

    def forbidden(_conn):
        pytest.fail("recognition must not migrate")

    result = readonly.recognize_target(target, migrations={(1, 1): forbidden})
    assert result.version == (1, 1)
    assert result.migration_required
    assert contents(directory) == before
    with pytest.raises(StateError, match="migration required"):
        readonly.recognize_target(target)
    assert contents(directory) == before


def test_recognition_detects_replacement(tmp_path):
    from image_clarus.state import management

    directory = tmp_path / "repo"
    initialize(directory)
    target = management.select_target(directory, tmp_path)
    other = tmp_path / "other"
    initialize(other)
    target.path.rename(tmp_path / "original")
    (other / DATABASE_NAME).replace(target.path)
    if target.identity is None:
        pytest.skip("filesystem identity unavailable")
    with pytest.raises(StateError, match="target changed"):
        readonly.recognize_target(target)


@pytest.fixture
def repository(tmp_path):
    directory = tmp_path / "repo ? # ü"
    initialize(directory)
    with connect(directory) as conn:
        conn.executemany(
            "INSERT INTO known_categories VALUES (?)", [("z",), ("A|leaf",), ("é",)]
        )
        conn.execute("INSERT INTO domain_versions VALUES ('other', 3)")
    return directory


def contents(directory):
    with connect(directory) as conn:
        return (
            conn.execute(
                "SELECT type, name, sql FROM sqlite_master ORDER BY name"
            ).fetchall(),
            conn.execute("SELECT * FROM domain_versions ORDER BY domain").fetchall(),
            conn.execute("SELECT * FROM known_categories ORDER BY path").fetchall(),
            conn.execute("PRAGMA application_id").fetchone(),
            conn.execute("PRAGMA user_version").fetchone(),
        )


@pytest.mark.parametrize("journal", ["delete", "wal"])
def test_list_preserves_application_state(repository, journal):
    with connect(repository) as conn:
        assert conn.execute(f"PRAGMA journal_mode={journal}").fetchone()[0] == journal
        before = contents(repository)
        assert readonly.list_categories(repository) == ["A|leaf", "z", "é"]
        assert contents(repository) == before


@pytest.mark.parametrize("journal", ["delete", "wal"])
def test_live_writer_exposes_only_committed_categories(repository, journal):
    writer = connect(repository)
    try:
        writer.execute(f"PRAGMA journal_mode={journal}")
        writer.execute("BEGIN IMMEDIATE")
        writer.execute("DELETE FROM known_categories")
        writer.execute("INSERT INTO known_categories VALUES ('new')")
        assert readonly.list_categories(repository) == ["A|leaf", "z", "é"]
        writer.commit()
        assert readonly.list_categories(repository) == ["new"]
    finally:
        writer.close()


def test_wal_recognition_and_enumeration_share_snapshot(repository, monkeypatch):
    writer = connect(repository)
    writer.execute("PRAGMA journal_mode=wal")
    original = readonly._validate

    def validate_then_commit(conn):
        result = original(conn)
        writer.execute("BEGIN IMMEDIATE")
        writer.execute("DELETE FROM known_categories")
        writer.execute("INSERT INTO known_categories VALUES ('new')")
        writer.commit()
        return result

    monkeypatch.setattr(readonly, "_validate", validate_then_commit)
    try:
        assert readonly.list_categories(repository) == ["A|leaf", "z", "é"]
    finally:
        writer.close()


def test_missing_and_corrupt_fail_without_creation_or_disclosure(tmp_path):
    missing = tmp_path / "fictional-private-name"
    with pytest.raises(StateError) as error:
        readonly.list_categories(missing)
    assert "fictional-private-name" not in str(error.value)
    assert not missing.exists()
    missing.mkdir()
    (missing / DATABASE_NAME).write_bytes(b"fictional corrupt bytes")
    with pytest.raises(StateError) as error:
        readonly.list_categories(missing)
    assert "fictional" not in str(error.value)
    assert (missing / DATABASE_NAME).read_bytes() == b"fictional corrupt bytes"


def test_recognized_old_store_reports_migration_without_mutation(
    repository, monkeypatch
):
    before = contents(repository)
    monkeypatch.setattr(storage, "FORMAT_VERSION", 2)
    monkeypatch.setattr(readonly, "FORMAT_VERSION", 2)
    with pytest.raises(StateError, match="migration required"):
        readonly.list_categories(repository)
    assert contents(repository) == before


@pytest.mark.parametrize(
    "mutation",
    [
        "PRAGMA application_id=0",
        "PRAGMA user_version=99",
        "UPDATE domain_versions SET version=99 WHERE domain='categories'",
        "CREATE TRIGGER forbidden AFTER INSERT ON known_categories BEGIN SELECT 1; END",
        "INSERT INTO known_categories VALUES (x'6162')",
        "INSERT INTO known_categories VALUES (CAST(x'80' AS TEXT))",
    ],
)
def test_invalid_identity_version_schema_or_data_fails_closed(repository, mutation):
    with connect(repository) as conn:
        conn.execute(mutation)
    # Invalid UTF-8 prevents reading the data through a normal connection.
    with connect(repository) as conn:
        conn.text_factory = bytes
        before = conn.execute(
            "SELECT path FROM known_categories ORDER BY path"
        ).fetchall()
    with pytest.raises(StateError):
        readonly.list_categories(repository)
    with connect(repository) as conn:
        conn.text_factory = bytes
        assert (
            conn.execute("SELECT path FROM known_categories ORDER BY path").fetchall()
            == before
        )


def test_exclusive_writer_fails_sanitized(repository):
    writer = connect(repository)
    try:
        writer.execute("BEGIN EXCLUSIVE")
        with pytest.raises(StateError) as error:
            readonly.list_categories(repository)
        assert str(error.value) == "repository read failed"
    finally:
        writer.rollback()
        writer.close()
