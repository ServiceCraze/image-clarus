"""E19 CLI startup boundaries, with child-process I/O guards."""

import os
import runpy
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
HELPERS = runpy.run_path(
    str(Path(__file__).with_name("test_c1_dry_run_safety_matrix.py"))
)
GUARD = HELPERS["GUARD"]
snapshot = HELPERS["snapshot"]


def run_cli(tmp_path, inputs, state, config, *, dry_run, guard_exif):
    audit = tmp_path / "audit"
    audit.mkdir()
    guard = GUARD
    if not guard_exif:
        guard = guard.replace('if "exiftool" in str(name).lower():', "if False:")
    (audit / "sitecustomize.py").write_text(guard)
    home = tmp_path / "home"
    home.mkdir()
    env = os.environ.copy()
    env.update(
        HOME=str(home),
        PYTHONPATH=os.pathsep.join((str(audit), str(ROOT / "src"))),
        PYTHONDONTWRITEBYTECODE="1",
        DRY_GUARD_ROOT=str(inputs),
        PATH=str(tmp_path / "missing-bin"),
    )
    before = snapshot(tmp_path)
    args = [
        sys.executable,
        "-m",
        "image_clarus",
        "process",
        str(inputs),
        "--config",
        str(config),
        "--state-dir",
        str(state),
        "--stages",
        "xmp",
    ]
    if dry_run:
        args.append("--dry-run")
    result = subprocess.run(
        args,
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert snapshot(tmp_path) == before
    assert "GUARD:" not in result.stdout + result.stderr, (result.stdout, result.stderr)
    return result


def setup_case(tmp_path):
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    state = inputs / "state"
    state.mkdir()
    config = tmp_path / "config.yaml"
    config.write_text("{}\n")
    return inputs, state, config


def test_empty_real_batch_skips_runtime_preflight_and_reports_zero(tmp_path):
    inputs, state, config = setup_case(tmp_path)
    result = run_cli(tmp_path, inputs, state, config, dry_run=False, guard_exif=True)
    assert result.returncode == 0, (result.stdout, result.stderr)
    assert "progress accounted=0/0 (no work)" in result.stdout
    assert "100%" not in result.stdout


def test_empty_real_batch_still_rejects_invalid_static_config(tmp_path):
    inputs, state, config = setup_case(tmp_path)
    config.write_text("selection:\n  max_depth: -1\n")
    result = run_cli(tmp_path, inputs, state, config, dry_run=False, guard_exif=True)
    assert result.returncode == 2, (result.stdout, result.stderr)
    assert "selection.max_depth" in result.stderr


def test_nonempty_real_batch_fails_missing_exiftool_before_content_or_writes(tmp_path):
    inputs, state, config = setup_case(tmp_path)
    (inputs / "a.jpg").write_bytes(b"fictional image")
    result = run_cli(tmp_path, inputs, state, config, dry_run=False, guard_exif=False)
    assert result.returncode == 2, (result.stdout, result.stderr)
    assert "exiftool" in result.stderr.lower()


@pytest.mark.parametrize("state_kind", ["corrupt", "old"])
def test_dry_run_ignores_selected_bad_or_old_state_without_content_access(
    tmp_path, state_kind
):
    inputs, state, config = setup_case(tmp_path)
    (inputs / "a.jpg").write_bytes(b"fictional image")
    (inputs / "a.xmp").write_bytes(b"fictional sidecar")
    database = state / "state.sqlite3"
    if state_kind == "corrupt":
        database.write_bytes(b"not sqlite")
    else:
        with sqlite3.connect(database) as conn:
            conn.execute("PRAGMA application_id = 1229147218")
            conn.execute("PRAGMA user_version = 0")
            conn.execute("CREATE TABLE legacy_state (value TEXT)")
            conn.execute("INSERT INTO legacy_state VALUES ('sentinel')")
    result = run_cli(tmp_path, inputs, state, config, dry_run=True, guard_exif=True)
    assert result.returncode == 0, (result.stdout, result.stderr)
    assert "plan complete images=1 " in result.stdout
    assert "runtime_dependencies=not_checked" in result.stdout
    assert result.stderr == ""
