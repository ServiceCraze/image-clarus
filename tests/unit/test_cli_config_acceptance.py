"""Supplemental B8 subprocess coverage; not historical RED evidence.

Discovery tests inject only discovery_locations via sitecustomize: they exercise
CLI selection/layering with temporary paths, not OS-specific path construction.
"""

import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SECRET = "B8_SYNTHETIC_SECRET_82631"


@pytest.fixture
def cli(tmp_path):
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            requests.append(
                json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            )
            content = json.dumps(
                {
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "content": "synthetic description",
                            },
                            "finish_reason": "stop",
                            "index": 0,
                        }
                    ]
                }
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

        def log_message(self, format, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    image = tmp_path / "image.png"
    image.write_bytes(b"synthetic image")
    config = tmp_path / "config.yaml"
    text = (
        f"providers:\n  p:\n    base_url: http://127.0.0.1:{server.server_port}/v1\n"
        "models:\n  m:\n    provider: p\n    model_id: original\n"
        "stages:\n  desc:\n    model: m\n"
    )
    config.write_text(text)
    home = tmp_path / "home"
    home.mkdir()
    # Only discovery_locations is replaced; all configuration processing and CLI
    # behavior remain real. This avoids any access to the machine's /etc.
    inject = tmp_path / "inject"
    inject.mkdir()
    (inject / "sitecustomize.py").write_text(
        "import os\nfrom pathlib import Path\nimport image_clarus.config as c\n"
        "c.discovery_locations = lambda: (Path(os.environ['B8_USER_CONFIG']), Path(os.environ['B8_SYSTEM_CONFIG']))\n"
    )
    user = tmp_path / "user.yaml"
    system = tmp_path / "system.yaml"

    def run(*args):
        env = os.environ.copy()
        env.update(
            HOME=str(home),
            PYTHONPATH=os.pathsep.join((str(inject), str(ROOT / "src"))),
            B8_USER_CONFIG=str(user),
            B8_SYSTEM_CONFIG=str(system),
            NO_PROXY="*",
            no_proxy="*",
        )
        return subprocess.run(
            [
                sys.executable,
                "-m",
                "image_clarus",
                "process",
                str(image),
                "--stages",
                "desc",
                *map(str, args),
            ],
            cwd=tmp_path,
            env=env,
            capture_output=True,
            text=True,
            timeout=25,
            check=False,
        )

    try:
        yield run, image, config, text, user, system, requests
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def assert_rejected(result, requests):
    assert result.returncode == 2, (result.stdout, result.stderr)
    assert result.stdout == ""
    assert "invalid" in result.stderr.lower()
    assert SECRET not in result.stdout + result.stderr
    assert not requests


def test_typed_values_mapping_and_equals_reach_provider(cli):
    run, image, config, _, _, _, requests = cli
    # Existing output demonstrates the YAML boolean actually enables regeneration.
    output = Path(str(image) + ".desc.txt")
    output.write_text("old")
    result = run(
        "--config",
        config,
        "--set",
        "stages.desc.regenerate=true",
        "--set",
        "providers.p.timeout_seconds=2.5",
        "--set",
        "stages.json.validation_retries=2",
        "--set",
        "models.m.model_id=synthetic=variant",
        "--set",
        "stages.desc.reasoning_effort=high",
        "--set",
        "models.m.reasoning_effort_mapping={parameter: effort, values: {high: 7}}",
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == f"desc: completed — output={json.dumps(str(output))}\n"
    assert output.read_text() == "synthetic description"
    assert len(requests) == 1
    assert requests[0]["model"] == "synthetic=variant"
    assert requests[0]["effort"] == 7 and type(requests[0]["effort"]) is int
    assert SECRET not in result.stdout + result.stderr


@pytest.mark.parametrize(
    "assignment",
    [
        "stages.desc.regenerate='true'",  # string, not boolean
        "providers.p.timeout_seconds=true",  # boolean, not number
        "stages.desc.model=[m]",
        "stages.desc.regenerate={value: true}",
        "models.m.reasoning_effort_mapping=[parameter, values]",
        "models.m.reasoning_effort_mapping={parameter: effort, values: {high: [7]}}",
        "stages.desc.model.0=m",
        "stages..model=m",
        "stages.desc.model",
        "stages.desc.model=",
        "providers.p.api_key=" + SECRET,
        "providers.p={api_key: " + SECRET + "}",
        "stages.desc.unknown=" + SECRET,
        "stages.desc.model=!!python/object/apply:os.system ['touch " + SECRET + "']",
    ],
)
def test_invalid_overrides_are_sanitized_and_do_not_run(cli, assignment):
    run, image, config, _, _, _, requests = cli
    result = run("--config", config, "--set", assignment)
    assert_rejected(result, requests)
    assert not Path(str(image) + ".desc.txt").exists()
    assert not (image.parent / SECRET).exists()


def test_unselected_json_value_does_not_block_desc_cli(cli):
    run, image, config, _, _, _, requests = cli
    result = run("--config", config, "--set", "stages.json.validation_retries='2'")
    assert result.returncode == 0, result.stderr
    assert Path(str(image) + ".desc.txt").exists()
    assert len(requests) == 1


def test_discovery_user_precedes_system_without_merge(cli):
    run, _, _, text, user, system, requests = cli
    user.write_text(text.replace("model_id: original", "model_id: user"))
    system.write_text(text.replace("model_id: original", "model_id: system"))
    result = run()
    assert result.returncode == 0, result.stderr
    assert requests[-1]["model"] == "user"
    # A user file missing models cannot borrow them from the system file.
    user.write_text("stages:\n  desc:\n    model: m\n")
    requests.clear()
    result = run()
    assert_rejected(result, requests)


def test_discovery_fallback_and_invalid_user_does_not_fallback(cli):
    run, image, _, text, user, system, requests = cli
    system.write_text(text.replace("model_id: original", "model_id: system"))
    result = run()
    assert result.returncode == 0, result.stderr
    assert requests[-1]["model"] == "system"
    Path(str(image) + ".desc.txt").unlink()
    requests.clear()
    user.write_text("invalid: [")
    result = run()
    assert result.returncode == 2 and result.stdout == ""
    assert "cannot load configuration" in result.stderr.lower()
    assert not requests


def test_explicit_config_overrides_discovery(cli):
    run, _, config, text, user, system, requests = cli
    user.write_text("invalid: [")
    system.write_text(text.replace("model_id: original", "model_id: system"))
    result = run("--config", config)
    assert result.returncode == 0, result.stderr
    assert len(requests) == 1 and requests[0]["model"] == "original"
