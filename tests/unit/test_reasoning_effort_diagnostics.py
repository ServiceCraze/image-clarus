"""Reasoning effort errors explain YAML boolean coercion without guessing intent."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from image_clarus.config import ConfigurationError, resolve_config

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    ("configuration", "field"),
    [
        ("stages: {desc: {reasoning_effort: off}}", "stages.desc.reasoning_effort"),
        ("stages: {json: {reasoning_effort: false}}", "stages.json.reasoning_effort"),
        ("models: {m: {reasoning_effort: off}}", "models.<name>.reasoning_effort"),
    ],
)
def test_boolean_reasoning_effort_suggests_quoted_off(tmp_path, configuration, field):
    path = tmp_path / "config.yaml"
    path.write_text(configuration)
    with pytest.raises(ConfigurationError) as exc:
        stage = field.split(".")[1] if field.startswith("stages.") else None
        resolve_config(config_file=path, stages=(stage,) if stage else ())
    message = str(exc.value)
    assert field in message
    assert "boolean" in message.lower()
    assert '"off"' in message
    assert "yaml" in message.lower()


def test_cli_reasoning_error_suggests_quoted_off(tmp_path):
    config = tmp_path / "config.yaml"
    config.write_text(
        "stages:\n  desc:\n    model: example\n    reasoning_effort: off\n"
    )
    image = tmp_path / "image.jpg"
    image.write_bytes(b"synthetic")
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "image_clarus",
            "process",
            str(image),
            "--config",
            str(config),
            "--stages",
            "desc",
        ],
        capture_output=True,
        text=True,
        env=env,
        cwd=tmp_path,
        timeout=15,
        check=False,
    )
    assert result.returncode == 2 and result.stdout == ""
    assert "stages.desc.reasoning_effort" in result.stderr
    assert "boolean" in result.stderr.lower()
    assert '"off"' in result.stderr


def test_quoted_off_remains_a_string(tmp_path):
    config = tmp_path / "config.yaml"
    config.write_text('stages: {desc: {reasoning_effort: "off"}}')
    assert (
        resolve_config(config_file=config)["stages"]["desc"]["reasoning_effort"]
        == "off"
    )
