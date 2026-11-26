import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def help_output(*command):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")
    result = subprocess.run(
        [sys.executable, "-m", "image_clarus", *command, "--help"],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert result.returncode == 0
    assert result.stderr == ""
    return " ".join(result.stdout.split())


@pytest.mark.parametrize(
    ("command", "phrases"),
    [
        ((), ("structured metadata", "process", "search", "not implemented", "state")),
        (("init",), (".image-clarus", "current directory")),
        (("search",), ("not implemented",)),
        (("state",), ("categories", "state")),
        (
            ("state", "categories"),
            ("list", "clear", "rebuild", "current directory", "--state-dir"),
        ),
        (
            ("state", "categories", "list"),
            ("read-only", "JSON string", "current directory", "--state-dir"),
        ),
        (
            ("state", "categories", "clear"),
            ("Delete", "categories", "other state", "not atomic"),
        ),
        (
            ("state", "categories", "rebuild"),
            (
                "additive",
                ".desc.json",
                "directories",
                "patterns",
                "current directory",
                "not atomic",
                "--max-depth",
                "--ignore-case",
                "Examples:",
            ),
        ),
        (
            ("process",),
            (
                "directories",
                "patterns",
                "--max-depth",
                "root",
                "--max-work-files",
                "--inter-stage-concurrency",
                "--extensions",
                "--set",
                "--state-dir",
                "--desc-prompt",
                "--json-prompt",
                "--json-schema",
                "--missing-prerequisite",
                "--dry-run",
                "Examples:",
            ),
        ),
    ],
)
def test_help_explains_command_purpose_and_behavior(command, phrases):
    output = help_output(*command)
    for phrase in phrases:
        assert phrase in output


@pytest.mark.parametrize("operation", ["list", "clear", "rebuild"])
def test_category_help_explains_configuration_and_repository_selection(operation):
    output = help_output("state", "categories", operation)
    for phrase in ("--config", "--set", "--state-dir", "state.directory"):
        assert phrase in output


@pytest.mark.parametrize(
    "command",
    [
        ("process",),
        ("state", "categories", "list"),
        ("state", "categories", "clear"),
        ("state", "categories", "rebuild"),
    ],
)
def test_config_help_distinguishes_configuration_file_discovery(command):
    assert "automatic configuration-file discovery" in help_output(*command)


def test_work_allowance_help_distinguishes_initial_admission_from_total_work():
    output = help_output("process")
    assert "Maximum images initially admitted for predicted model work" in output
    assert "does not limit total files processed or provider requests" in output
