"""List and clear through the real CLI, using fictional local repositories."""

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

from image_clarus.state.storage import DATABASE_NAME, SQLiteStorage, initialize

ROOT = Path(__file__).resolve().parents[2]


def run_cli(cwd, *args):
    env = dict(os.environ, PYTHONPATH=str(ROOT / "src"))
    return subprocess.run(
        [sys.executable, "-m", "image_clarus", "state", "categories", *args],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=15,
    )


def test_list_and_clear_use_cwd_and_preserve_other_data(tmp_path):
    directory = tmp_path / ".image-clarus"
    initialize(directory)
    SQLiteStorage(directory).add_categories(["Nature/Birds", "line\nbreak"])
    with sqlite3.connect(directory / DATABASE_NAME) as conn:
        conn.execute("CREATE TABLE other (value TEXT)")
        conn.execute("INSERT INTO other VALUES ('retained')")
    listing = run_cli(tmp_path, "list")
    assert (listing.returncode, listing.stdout, listing.stderr) == (
        0,
        '"Nature/Birds"\n"line\\nbreak"\n',
        "",
    )
    clear = run_cli(tmp_path, "clear")
    assert (clear.returncode, clear.stdout, clear.stderr) == (
        0,
        "clear target=cwd\nclear deleted=2\n",
        "",
    )
    with sqlite3.connect(directory / DATABASE_NAME) as conn:
        assert conn.execute("SELECT * FROM other").fetchall() == [("retained",)]
        assert conn.execute("SELECT * FROM known_categories").fetchall() == []


def test_explicit_invalid_target_never_falls_back(tmp_path):
    initialize(tmp_path / ".image-clarus")
    missing = tmp_path / "sensitive-path"
    for operation in ("list", "clear"):
        result = run_cli(tmp_path, operation, "--state-dir", str(missing))
        assert result.returncode == 1
        assert str(missing) not in result.stderr
        assert "state operation failed" in result.stderr
        assert "deleted=" not in result.stdout
    assert not missing.exists()


def test_configured_target_overrides_cwd(tmp_path):
    cwd_store = tmp_path / ".image-clarus"
    configured = tmp_path / "other"
    initialize(cwd_store)
    initialize(configured)
    SQLiteStorage(cwd_store).add_categories(["cwd"])
    SQLiteStorage(configured).add_categories(["chosen"])
    config = tmp_path / "config.yaml"
    config.write_text("state:\n  directory: other\n")
    listing = run_cli(tmp_path, "list", "--config", str(config))
    assert listing.returncode == 0, listing.stderr
    assert listing.stdout == '"chosen"\n'
    clear = run_cli(tmp_path, "clear", "--config", str(config))
    assert clear.returncode == 0, clear.stderr
    assert clear.stdout == "clear target=configured\nclear deleted=1\n"
    assert SQLiteStorage(cwd_store).snapshot_categories() == ["cwd"]
