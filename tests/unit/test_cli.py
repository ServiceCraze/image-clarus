import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def run_cli(*args):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")
    return subprocess.run(
        [sys.executable, "-m", "image_clarus", *args],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


def test_top_level_help_lists_subcommands():
    result = run_cli("--help")
    assert result.returncode == 0
    assert "process" in result.stdout and "search" in result.stdout


def test_process_help_describes_frozen_options():
    result = run_cli("process", "--help")
    assert result.returncode == 0
    for expected in (
        "IMAGE",
        "--config",
        "--stages",
        "--set",
        "--desc-prompt",
        "--json-prompt",
        "--json-schema",
        "--regenerate",
        "--missing-prerequisite",
        "desc,json",
        "fail",
        "create-only",
        "search",
    ):
        assert expected in result.stdout


def test_search_help_works():
    assert run_cli("search", "--help").returncode == 0


def test_search_stub_and_unknown_arguments():
    result = run_cli("search")
    assert (result.returncode, result.stdout, result.stderr) == (
        3,
        "",
        "search is not implemented in Slice 1\n",
    )
    assert run_cli("search", "unexpected").returncode == 2


def test_version_uses_installed_metadata():
    result = run_cli("--version")
    assert (result.returncode, result.stdout, result.stderr) == (
        0,
        "image-clarus 0.1.0\n",
        "",
    )


def test_version_missing_metadata_is_configuration_error(tmp_path):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")
    result = subprocess.run(
        [sys.executable, "-S", "-m", "image_clarus", "--version"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2
    assert result.stdout == ""
    assert (
        result.stderr
        == "image-clarus: installation error: version metadata unavailable\n"
    )
