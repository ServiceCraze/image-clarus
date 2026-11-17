"""Supplemental black-box verification of configuration diagnostics."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    ("contents", "expected"),
    [
        ("stages: {desc: {model: missing_value_sentinel}}", "stages.desc.model"),
        ("logging:\n  level: [private_yaml_sentinel\n", "invalid YAML"),
        (
            (
                "providers: {p: {base_url: 'http://user:private_url_sentinel@service.test'}}\n"
                "models: {m: {provider: p, model_id: example}}\n"
                "stages: {desc: {model: m}}\n"
            ),
            "providers.<name>.base_url",
        ),
    ],
)
def test_process_reports_safe_actionable_error(tmp_path, contents, expected):
    config = tmp_path / "config.yaml"
    config.write_text(contents)
    image = tmp_path / "image.jpg"
    image.write_bytes(b"synthetic image")
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
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 2
    assert result.stdout == ""
    assert expected in result.stderr
    assert any(word in result.stderr.lower() for word in ("set", "correct"))
    for sentinel in (
        "missing_value_sentinel",
        "private_yaml_sentinel",
        "private_url_sentinel",
    ):
        assert sentinel not in result.stderr


@pytest.mark.parametrize(
    ("config_text", "override", "env_key", "env_value", "expected", "sentinels"),
    [
        (
            (
                "providers: {p: {base_url: http://127.0.0.1:1/v1, "
                "api_key_env: SYNTHETIC_PROVIDER_KEY}}\n"
                "models: {m: {provider: p, model_id: sample-model}}\n"
                "stages: {desc: {model: m}}\n"
            ),
            None,
            True,
            "SYNTHETIC_KEY_SENTINEL\r\nX-Probe: 1",
            "providers.<name>.api_key_env",
            ("SYNTHETIC_KEY_SENTINEL", "X-Probe"),
        ),
        (
            (
                "providers: {p: {base_url: http://127.0.0.1:1/v1, "
                "api_key_env: SYNTHETIC_PROVIDER_KEY}}\n"
                "models: {m: {provider: p, model_id: sample-model}}\n"
                "stages: {desc: {model: m}}\n"
            ),
            None,
            True,
            "SYNTHETIC_KEY_é",
            "providers.<name>.api_key_env",
            ("SYNTHETIC_KEY_é",),
        ),
        (
            (
                "providers: {p: {base_url: http://127.0.0.1:1/v1}}\n"
                "models: {m: {provider: p, model_id: sample-model}}\n"
                "stages: {desc: {model: m}}\n"
            ),
            'models.m.model_id="\\uD800"',
            False,
            None,
            "models.<name>.model_id",
            ("D800",),
        ),
    ],
)
def test_process_rejects_unserializable_provider_values(
    tmp_path, config_text, override, env_key, env_value, expected, sentinels
):
    config = tmp_path / "config.yaml"
    config.write_text(config_text)
    image = tmp_path / "image.jpg"
    image.write_bytes(b"synthetic image")
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")
    if env_key:
        env["SYNTHETIC_PROVIDER_KEY"] = env_value
    args = [
        sys.executable,
        "-m",
        "image_clarus",
        "process",
        str(image),
        "--config",
        str(config),
        "--stages",
        "desc",
    ]
    if override is not None:
        args.extend(("--set", override))
    result = subprocess.run(
        args,
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 2
    assert result.stdout == ""
    assert expected in result.stderr
    assert "set" in result.stderr.lower()
    assert "provider_unavailable" not in result.stderr
    for sentinel in sentinels:
        assert sentinel not in result.stderr
