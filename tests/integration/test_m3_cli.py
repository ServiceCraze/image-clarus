"""M3 category CLI boundaries with synthetic persistent state."""

import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

from image_clarus.state.storage import DATABASE_NAME, SQLiteStorage, initialize

ROOT = Path(__file__).resolve().parents[2]


def run(cwd, *arguments):
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "image_clarus",
            "state",
            "categories",
            *map(str, arguments),
        ],
        cwd=cwd,
        env=dict(os.environ, PYTHONPATH=str(ROOT / "src")),
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )


def sidecar(path):
    path.write_text(
        json.dumps(
            {
                "format_version": 1,
                "schema_id": "urn:image-clarus:metadata-schema:2.0.0",
                "schema_version": "2.0.0",
                "provenance": {
                    "provider_alias": "demo",
                    "model_alias": "demo",
                    "model_id": "demo",
                    "prompt_id": "demo",
                    "description_sha256": "a" * 64,
                },
                "metadata": {"tag_candidates": [["Nature", "Leaf"]]},
            }
        )
    )


def test_explicit_clear_then_rebuild_preserves_other_domain_and_source(tmp_path):
    store = tmp_path / ".image-clarus"
    initialize(store)
    SQLiteStorage(store).add_categories(["Previously"])
    with sqlite3.connect(store / DATABASE_NAME) as connection:
        connection.execute("CREATE TABLE other (value TEXT)")
        connection.execute("INSERT INTO other VALUES ('retained')")
    source = tmp_path / "orphan.desc.json"
    sidecar(source)
    before = source.read_bytes()
    listing = run(tmp_path, "list")
    assert (listing.returncode, listing.stdout) == (0, '"Previously"\n')
    clearing = run(tmp_path, "clear")
    assert clearing.returncode == 0 and "deleted=1" in clearing.stdout
    rebuilt = run(tmp_path, "rebuild", source)
    assert rebuilt.returncode == 0, rebuilt.stderr
    assert "confirmed_inserted=1" in rebuilt.stdout
    assert SQLiteStorage(store).snapshot_categories() == ["Nature/Leaf"]
    with sqlite3.connect(store / DATABASE_NAME) as connection:
        assert connection.execute("SELECT * FROM other").fetchall() == [("retained",)]
    assert source.read_bytes() == before


def test_corrupt_and_missing_list_are_errors_without_fallback(tmp_path):
    missing = tmp_path / "missing"
    result = run(tmp_path, "list", "--state-dir", missing)
    assert result.returncode == 1 and not result.stdout
    assert str(missing) not in result.stderr and not missing.exists()
    corrupt = tmp_path / "corrupt"
    corrupt.mkdir()
    db = corrupt / DATABASE_NAME
    db.write_bytes(b"fictional invalid data")
    result = run(tmp_path, "list", "--state-dir", corrupt)
    assert result.returncode == 1 and not result.stdout
    assert str(corrupt) not in result.stderr
    assert db.read_bytes() == b"fictional invalid data"
