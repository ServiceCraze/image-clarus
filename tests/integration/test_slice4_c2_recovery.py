"""C2 CLI recovery and fresh-rescan checks using a loopback provider."""

import os
import subprocess
import sys
from pathlib import Path

import pytest
from test_single_image_pipeline import ROOT

pytest_plugins = ("test_single_image_pipeline",)


def run_batch(fixture, tmp_path, config, *args):
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "image_clarus",
            "process",
            str(fixture.image.parent),
            "--config",
            str(config),
            "--stages",
            "desc,json",
            "--no-inter-stage-concurrency",
            "--verbose",
            *args,
        ],
        cwd=tmp_path,
        env=dict(
            os.environ,
            HOME=str(tmp_path / "home"),
            PYTHONPATH=str(ROOT / "src"),
            NO_PROXY="*",
            no_proxy="*",
        ),
        capture_output=True,
        text=True,
        timeout=45,
        check=False,
    )


def test_fresh_rescan_reuses_completed_and_does_not_regenerate_invalid(rig, tmp_path):
    second = rig.image.parent / "z.png"
    second.write_bytes(rig.original)
    config = rig.config("resume")
    rig.desc.write_text("existing description", encoding="utf-8")
    rig.structured.write_bytes(b"invalid json sentinel")
    first = run_batch(rig, tmp_path, config)
    assert first.returncode == 1, (first.stdout, first.stderr)
    assert rig.structured.read_bytes() == b"invalid json sentinel"
    assert Path(str(second) + ".desc.json").exists()
    assert [stage for stage, _, _ in rig.requests] == ["desc", "json"]
    before = Path(str(second) + ".desc.json").read_bytes()
    count = len(rig.requests)
    again = run_batch(rig, tmp_path, config)
    assert again.returncode == 1, (again.stdout, again.stderr)
    assert rig.structured.read_bytes() == b"invalid json sentinel"
    assert Path(str(second) + ".desc.json").read_bytes() == before
    assert len(rig.requests) == count
    assert "failed=1" in again.stdout
    rig.structured.unlink()
    repaired = run_batch(rig, tmp_path, config)
    assert repaired.returncode == 0, (repaired.stdout, repaired.stderr)
    assert [stage for stage, _, _ in rig.requests[count:]] == ["json"]
    assert rig.structured.exists()
    assert Path(str(second) + ".desc.json").read_bytes() == before
    assert rig.image.read_bytes() == second.read_bytes() == rig.original


def test_missing_prerequisite_does_not_call_provider(rig, tmp_path):
    config = rig.config("missing")
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "image_clarus",
            "process",
            str(rig.image.parent),
            "--config",
            str(config),
            "--stages",
            "json",
            "--verbose",
        ],
        cwd=tmp_path,
        env=dict(
            os.environ,
            HOME=str(tmp_path / "home"),
            PYTHONPATH=str(ROOT / "src"),
            NO_PROXY="*",
            no_proxy="*",
        ),
        capture_output=True,
        text=True,
        timeout=45,
        check=False,
    )
    assert result.returncode == 0, (result.stdout, result.stderr)
    assert "missing_prerequisite" in result.stdout
    assert not rig.requests and not rig.structured.exists()
    assert rig.image.read_bytes() == rig.original


@pytest.mark.parametrize("valid", [True, False])
def test_json_backup_recovery(rig, tmp_path, valid):
    config = rig.config("backup")
    rig.desc.write_text("fixture description", encoding="utf-8")
    generated = run_batch(rig, tmp_path, config)
    assert generated.returncode == 0, (generated.stdout, generated.stderr)
    previous = rig.structured.read_bytes()
    rig.structured.unlink()
    backup = Path(str(rig.structured) + ".bak")
    backup.write_bytes(previous if valid else b"invalid backup sentinel")
    count = len(rig.requests)
    result = run_batch(rig, tmp_path, config)
    assert len(rig.requests) == count
    assert rig.image.read_bytes() == rig.original
    if valid:
        assert result.returncode == 0, (result.stdout, result.stderr)
        assert rig.structured.read_bytes() == previous
    else:
        assert result.returncode == 1, (result.stdout, result.stderr)
        assert backup.read_bytes() == b"invalid backup sentinel"
        assert not rig.structured.exists()
