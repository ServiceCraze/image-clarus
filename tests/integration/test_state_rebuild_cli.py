"""Actual CLI rebuild tests with synthetic sidecars and local state."""

import json
import os
import subprocess
import sys
from pathlib import Path

from image_clarus.state.storage import SQLiteStorage, initialize

ROOT = Path(__file__).resolve().parents[2]


def sidecar(path, paths):
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
                "metadata": {"tag_candidates": paths},
            }
        )
    )


def run_cli(cwd, *args):
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
        env=dict(os.environ, PYTHONPATH=str(ROOT / "src")),
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


def test_rebuild_additive_partial_and_orphan(tmp_path):
    store = tmp_path / ".image-clarus"
    initialize(store)
    SQLiteStorage(store).add_categories(["existing"])
    sources = tmp_path / "sources"
    sources.mkdir()
    first = sources / "a.desc.json"
    sidecar(first, [["A", "Leaf"], ["A", "Leaf"]])
    (sources / "b.desc.json").write_text("invalid")
    sidecar(sources / "c.desc.json", [["C"]])
    original = first.read_bytes()
    result = run_cli(tmp_path, sources)
    assert result.returncode == 1, result.stderr
    for part in (
        "discovered=3",
        "inspected=3",
        "success=2",
        "input_failure=1",
        "confirmed_inserted=2",
    ):
        assert part in result.stdout
    assert SQLiteStorage(store).snapshot_categories() == ["A/Leaf", "C", "existing"]
    assert first.read_bytes() == original
    assert "invalid" not in result.stderr


def test_rebuild_depth_pattern_case_and_dedup(tmp_path):
    store = tmp_path / ".image-clarus"
    initialize(store)
    sources = tmp_path / "sources"
    sources.mkdir()
    nested = sources / "nested"
    nested.mkdir()
    first = sources / "ONE.desc.json"
    sidecar(first, [["Root"]])
    sidecar(nested / "two.desc.json", [["Nested"]])
    result = run_cli(tmp_path, sources, first, "--max-depth", "0")
    assert result.returncode == 0, result.stderr
    assert "discovered=1" in result.stdout
    assert SQLiteStorage(store).snapshot_categories() == ["Root"]
    result = run_cli(tmp_path, str(sources / "o*.desc.json"), "-i")
    assert result.returncode == 0, result.stderr
    assert "discovered=1" in result.stdout


def test_rebuild_empty_selection_and_invalid_selection(tmp_path):
    store = tmp_path / ".image-clarus"
    initialize(store)
    SQLiteStorage(store).add_categories(["existing"])
    sources = tmp_path / "empty"
    sources.mkdir()
    result = run_cli(tmp_path, sources)
    assert result.returncode == 0, result.stderr
    assert "discovered=0" in result.stdout
    invalid = run_cli(tmp_path, sources, tmp_path / "missing")
    assert invalid.returncode == 2
    assert SQLiteStorage(store).snapshot_categories() == ["existing"]
