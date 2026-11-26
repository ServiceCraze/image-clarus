"""Rebuild accounting and interruption at the orchestration boundary."""

from types import SimpleNamespace

from image_clarus.state import rebuild as module
from image_clarus.state.management import UnionResult


def test_rebuild_reports_partial_unknown_and_stops(monkeypatch):
    candidates = [SimpleNamespace(path=str(n)) for n in range(3)]
    monkeypatch.setattr(module, "recognize_target", lambda *a, **k: None)
    monkeypatch.setattr(
        module,
        "discover_sidecars",
        lambda *a, **k: SimpleNamespace(candidates=candidates),
    )
    monkeypatch.setattr(module, "extract_sidecar", lambda *_: ["A", "B"])
    outcomes = iter(
        [
            UnionResult("committed", attempted=True, inserted=2),
            UnionResult("unknown", attempted=True),
        ]
    )
    monkeypatch.setattr(module, "union_categories", lambda *a, **k: next(outcomes))
    result = module.rebuild(
        SimpleNamespace(origin="cwd"),
        ["fictional"],
        max_depth=None,
        ignore_case=False,
        read_envelope=None,
    )
    assert (result.discovered, result.inspected, result.not_attempted) == (3, 2, 1)
    assert (result.success, result.commit_unknown, result.transactions_attempted) == (
        1,
        1,
        2,
    )
    assert (
        result.category_bearing,
        result.eligible_paths,
        result.confirmed_inserted,
    ) == (2, 4, 2)
    assert not result.confirmed_inserted_complete
    assert result.exit_code == 1


def test_rebuild_reports_interrupted_input_and_retains_commits(monkeypatch):
    candidates = [SimpleNamespace(path=str(n)) for n in range(3)]
    monkeypatch.setattr(module, "recognize_target", lambda *a, **k: None)
    monkeypatch.setattr(
        module,
        "discover_sidecars",
        lambda *a, **k: SimpleNamespace(candidates=candidates),
    )
    monkeypatch.setattr(module, "extract_sidecar", lambda *_: ["A"])
    outcomes = iter(
        [
            UnionResult("committed", attempted=True, inserted=1),
            UnionResult("interrupted", attempted=True),
        ]
    )
    monkeypatch.setattr(module, "union_categories", lambda *a, **k: next(outcomes))
    result = module.rebuild(
        SimpleNamespace(origin="cwd"),
        ["fictional"],
        max_depth=None,
        ignore_case=False,
        read_envelope=None,
    )
    assert (result.success, result.interrupted, result.not_attempted) == (1, 1, 1)
    assert (result.confirmed_committed, result.confirmed_inserted) == (1, 1)


def test_confirmed_commit_with_close_error_remains_success(monkeypatch):
    monkeypatch.setattr(module, "recognize_target", lambda *a, **k: None)
    monkeypatch.setattr(
        module,
        "discover_sidecars",
        lambda *a, **k: SimpleNamespace(
            candidates=[SimpleNamespace(path="first"), SimpleNamespace(path="second")]
        ),
    )
    monkeypatch.setattr(module, "extract_sidecar", lambda *_: ["A"])
    monkeypatch.setattr(
        module,
        "union_categories",
        lambda *a, **k: UnionResult(
            "committed", attempted=True, inserted=1, close_failed=True
        ),
    )
    result = module.rebuild(
        SimpleNamespace(origin="cwd"),
        ["fictional"],
        max_depth=None,
        ignore_case=False,
        read_envelope=None,
    )
    assert (result.success, result.confirmed_inserted, result.not_attempted) == (
        1,
        1,
        1,
    )
    assert result.close_failed and result.exit_code == 1


def test_no_category_rebuild_does_not_migrate_older_store(tmp_path, monkeypatch):
    import sqlite3

    from image_clarus.state import storage
    from image_clarus.state.management import select_target

    directory = tmp_path / "state"
    storage.initialize(directory)
    target = select_target(directory, tmp_path)
    source = tmp_path / "empty.desc.json"
    source.write_bytes(b"fictional")
    monkeypatch.setattr(storage, "DOMAIN_VERSION", 2)
    calls = []

    def migrate(conn):
        calls.append(True)
        conn.execute("UPDATE domain_versions SET version=2 WHERE domain='categories'")

    result = module.rebuild(
        target,
        [str(source)],
        max_depth=None,
        ignore_case=False,
        read_envelope=lambda _: {
            "schema_id": "urn:image-clarus:metadata-schema:2.0.0",
            "schema_version": "2.0.0",
            "metadata": {},
        },
        migrations={(1, 1): migrate},
    )
    assert result.skip == 1 and result.transactions_attempted == 0
    assert calls == []
    with sqlite3.connect(target.path) as conn:
        assert conn.execute("SELECT version FROM domain_versions").fetchone() == (1,)
