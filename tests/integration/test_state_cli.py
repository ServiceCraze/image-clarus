import subprocess
import sys

import pytest


def run(cwd, *args):
    return subprocess.run(
        [sys.executable, "-m", "image_clarus", *map(str, args)],
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )


def test_init_help_and_idempotence(tmp_path):
    assert run(tmp_path, "init", "--help").returncode == 0
    assert not (tmp_path / ".image-clarus").exists()
    assert run(tmp_path, "init").returncode == 0
    assert run(tmp_path, "init").returncode == 0
    assert (tmp_path / ".image-clarus" / "state.sqlite3").is_file()


def test_init_refuses_existing_uninitialized_directory(tmp_path):
    directory = tmp_path / ".image-clarus"
    directory.mkdir()
    marker = directory / "unrelated"
    marker.write_text("keep")
    result = run(tmp_path, "init")
    assert result.returncode != 0
    assert "state error" in result.stderr
    assert marker.read_text() == "keep"
    assert not (directory / "state.sqlite3").exists()


@pytest.mark.parametrize("level", ["DEBUG", "INFO", "WARNING", "ERROR"])
def test_invalid_selected_state_does_not_block_real_cli_skip(tmp_path, level):
    image = tmp_path / "photo.png"
    image.write_bytes(b"synthetic")
    sidecar = tmp_path / "photo.png.desc.txt"
    sidecar.write_text("existing")
    config = tmp_path / "config.yaml"
    config.write_text(
        f"logging:\n  level: {level}\nproviders:\n  local:\n    base_url: http://127.0.0.1:1234/v1\nmodels:\n  vision:\n    provider: local\n    model_id: fictional\nstages:\n  desc:\n    model: vision\n"
    )
    private = tmp_path / "private-sentinel"
    result = run(
        tmp_path,
        "process",
        image,
        "--config",
        config,
        "--stages",
        "desc",
        "--state-dir",
        private,
    )
    assert result.returncode == 0, result.stderr
    assert "desc: skipped" in result.stdout
    assert "state error" in result.stderr
    assert "private-sentinel" not in result.stderr
    assert sidecar.read_text() == "existing"
    assert not (tmp_path / ".image-clarus").exists()
