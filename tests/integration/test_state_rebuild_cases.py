"""Black-box rebuild acceptance scenarios using fictional sidecars only."""

import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from image_clarus.state.storage import SQLiteStorage, initialize

ROOT = Path(__file__).resolve().parents[2]


def envelope(
    paths=None, *, schema_id="urn:image-clarus:metadata-schema:2.0.0", version="2.0.0"
):
    return json.dumps(
        {
            "format_version": 1,
            "schema_id": schema_id,
            "schema_version": version,
            "provenance": {
                "provider_alias": "demo",
                "model_alias": "demo",
                "model_id": "demo",
                "prompt_id": "demo",
                "description_sha256": "a" * 64,
            },
            "metadata": {} if paths is None else {"tag_candidates": paths},
        }
    ).encode()


def run_rebuild(cwd, *args):
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "image_clarus",
            "state",
            "categories",
            "rebuild",
            *map(str, args),
        ],
        cwd=cwd,
        env={**os.environ, "PYTHONPATH": str(ROOT / "src")},
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


def counts(result, **expected):
    for name, value in expected.items():
        assert f"{name}={value}" in result.stdout.split(), (
            result.stdout,
            result.stderr,
        )


def database_snapshot(store):
    databases = list(store.glob("*.sqlite*")) + list(store.glob("*.db"))
    assert len(databases) == 1, databases
    with sqlite3.connect(databases[0]) as connection:
        return tuple(connection.iterdump())


def test_997_valid_and_three_invalid_continue_and_preserve_sources(tmp_path):
    store = tmp_path / ".image-clarus"
    initialize(store)
    SQLiteStorage(store).add_categories(["Existing"])
    sources = tmp_path / "sources"
    sources.mkdir()
    originals = {}
    for index in range(1000):
        path = sources / f"{index:04}.desc.json"
        if index in {1, 500, 998}:
            data = (
                b"{broken" if index != 500 else envelope([["valid"], ["bad/segment"]])
            )
        else:
            data = envelope([["Group", f"Item{index:04}"], ["Shared"], ["Shared"]])
        path.write_bytes(data)
        originals[path] = data
    result = run_rebuild(tmp_path, sources)
    assert result.returncode == 1, (result.stdout, result.stderr)
    counts(
        result,
        discovered=1000,
        inspected=1000,
        success=997,
        input_failure=3,
        category_bearing=997,
        eligible_paths=1994,
        confirmed_committed=997,
        confirmed_inserted=998,
        not_attempted=0,
    )
    expected = {"Existing", "Shared"} | {
        f"Group/Item{index:04}" for index in range(1000) if index not in {1, 500, 998}
    }
    assert set(SQLiteStorage(store).snapshot_categories()) == expected
    assert all(path.read_bytes() == data for path, data in originals.items())
    assert "bad/segment" not in result.stderr


def test_no_category_inputs_are_successful_and_leave_database_logically_unchanged(
    tmp_path,
):
    store = tmp_path / ".image-clarus"
    initialize(store)
    SQLiteStorage(store).add_categories(["Existing"])
    sources = tmp_path / "sources"
    sources.mkdir()
    (sources / "missing.desc.json").write_bytes(envelope())
    (sources / "empty.desc.json").write_bytes(envelope([]))
    (sources / "old.desc.json").write_bytes(
        envelope(
            [["Ignored"]],
            schema_id="urn:image-clarus:metadata-schema:1.0.0",
            version="1.0.0",
        )
    )
    before = database_snapshot(store)
    result = run_rebuild(tmp_path, sources)
    assert result.returncode == 0, (result.stdout, result.stderr)
    counts(
        result,
        discovered=3,
        inspected=3,
        skip=3,
        category_bearing=0,
        transactions_attempted=0,
        confirmed_inserted=0,
    )
    assert database_snapshot(store) == before


def test_explicit_file_symlink_is_followed_but_discovered_links_are_not(tmp_path):
    store = tmp_path / ".image-clarus"
    initialize(store)
    sources = tmp_path / "sources"
    sources.mkdir()
    external = tmp_path / "external"
    external.mkdir()
    target = external / "target.desc.json"
    target.write_bytes(envelope([["Explicit"]]))
    (external / "nested.desc.json").write_bytes(envelope([["NotDiscovered"]]))
    (sources / "regular.desc.json").write_bytes(envelope([["Regular"]]))
    try:
        (sources / "linked.desc.json").symlink_to(target)
        (sources / "linked-dir").symlink_to(external, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation unavailable")
    result = run_rebuild(tmp_path, sources)
    assert result.returncode == 0, (result.stdout, result.stderr)
    counts(result, discovered=1, success=1)
    assert SQLiteStorage(store).snapshot_categories() == ["Regular"]
    result = run_rebuild(tmp_path, sources / "linked.desc.json", target)
    assert result.returncode == 0, (result.stdout, result.stderr)
    counts(result, discovered=1, success=1, confirmed_inserted=1)
    assert SQLiteStorage(store).snapshot_categories() == ["Explicit", "Regular"]


def test_cwd_target_and_explicit_target_are_independent_of_source(tmp_path):
    cwd = tmp_path / "cwd"
    source_root = tmp_path / "other"
    cwd.mkdir()
    source_root.mkdir()
    cwd_store = cwd / ".image-clarus"
    source_store = source_root / ".image-clarus"
    initialize(cwd_store)
    initialize(source_store)
    sidecar = source_root / "orphan.desc.json"
    sidecar.write_bytes(envelope([["FromSource"]]))
    result = run_rebuild(cwd, sidecar)
    assert result.returncode == 0, (result.stdout, result.stderr)
    assert SQLiteStorage(cwd_store).snapshot_categories() == ["FromSource"]
    assert SQLiteStorage(source_store).snapshot_categories() == []
    sidecar.write_bytes(envelope([["ExplicitTarget"]]))
    result = run_rebuild(cwd, sidecar, "--state-dir", source_store)
    assert result.returncode == 0, (result.stdout, result.stderr)
    assert SQLiteStorage(cwd_store).snapshot_categories() == ["FromSource"]
    assert SQLiteStorage(source_store).snapshot_categories() == ["ExplicitTarget"]
    missing = tmp_path / "missing-state"
    result = run_rebuild(cwd, sidecar, "--state-dir", missing)
    assert result.returncode != 0
    assert not missing.exists()
    assert SQLiteStorage(cwd_store).snapshot_categories() == ["FromSource"]
    assert SQLiteStorage(source_store).snapshot_categories() == ["ExplicitTarget"]
