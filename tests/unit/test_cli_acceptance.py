"""Supplemental black-box A2 acceptance coverage; no historical TDD RED claimed."""

import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def harness(tmp_path):
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            requests.append((body, dict(self.headers)))
            content = (
                '{"caption":"ok"}'
                if body.get("response_format")
                else "stub description"
            )
            payload = json.dumps(
                {
                    "choices": [
                        {
                            "index": 0,
                            "finish_reason": "stop",
                            "message": {"role": "assistant", "content": content},
                        }
                    ]
                }
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    image = tmp_path / "image.png"
    image.write_bytes(b"synthetic image")
    config = tmp_path / "config.yaml"
    config.write_text(
        f"providers:\n  local:\n    base_url: http://127.0.0.1:{server.server_port}/v1\nmodels:\n  m:\n    provider: local\n    model_id: synthetic\nstages:\n  desc:\n    model: m\n  json:\n    model: m\n"
    )
    home = tmp_path / "home"
    home.mkdir()

    def run(*args, cwd=tmp_path, extra_env=None):
        env = os.environ.copy()
        env.update(
            HOME=str(home), PYTHONPATH=str(ROOT / "src"), NO_PROXY="*", no_proxy="*"
        )
        env.pop("IMAGE_CLARUS_ACCEPTANCE_KEY", None)
        if extra_env:
            env.update(extra_env)
        return subprocess.run(
            [sys.executable, "-m", "image_clarus", *map(str, args)],
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
            timeout=25,
            check=False,
        )

    try:
        yield run, image, config, requests, home
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def test_reverse_selection_runs_registry_order_and_json_uses_description(
    harness, tmp_path
):
    run, image, config, requests, _ = harness
    schema = tmp_path / "schema.json"
    schema.write_text('{"type":"object","required":["caption"]}')
    result = run(
        "process",
        image,
        "--config",
        config,
        "--stages",
        " json , desc ",
        "--json-schema",
        schema,
    )
    assert result.returncode == 0, result.stderr
    assert (
        result.stdout
        == f"desc: completed — output={json.dumps(str(image) + '.desc.txt')}\njson: completed — output={json.dumps(str(image) + '.desc.json')}\n"
    )
    assert len(requests) == 2
    assert "stub description" in json.dumps(requests[1][0])
    assert image.read_bytes() == b"synthetic image"


def test_json_only_executes_without_description_request(harness, tmp_path):
    run, image, config, requests, _ = harness
    Path(str(image) + ".desc.txt").write_text("existing desc")
    schema = tmp_path / "schema.json"
    schema.write_text('{"type":"object"}')
    result = run(
        "process",
        image,
        "--config",
        config,
        "--stages=json",
        "--json-schema=" + str(schema),
    )
    assert result.returncode == 0, result.stderr
    assert (
        result.stdout
        == f"json: completed — output={json.dumps(str(image) + '.desc.json')}\n"
    )
    assert len(requests) == 1 and "existing desc" in json.dumps(requests[0][0])


def test_json_prompt_override_reaches_selected_provider_request(harness, tmp_path):
    run, image, config, requests, _ = harness
    Path(str(image) + ".desc.txt").write_text("existing desc")
    schema = tmp_path / "schema.json"
    schema.write_text('{"type":"object"}')
    prompt = tmp_path / "prompt.txt"
    prompt.write_text("CUSTOM JSON INSTRUCTION")
    result = run(
        "process",
        image,
        "--config",
        config,
        "--stages",
        "json",
        "--json-schema",
        schema,
        "--json-prompt",
        prompt,
    )
    assert result.returncode == 0, result.stderr
    assert len(requests) == 1
    assert "CUSTOM JSON INSTRUCTION" in json.dumps(requests[0][0])


def test_later_selected_stage_preflight_blocks_earlier_write(harness):
    run, image, config, requests, _ = harness
    result = run(
        "process", image, "--config", config, "--set", "stages.json.model=missing"
    )
    assert result.returncode == 2 and result.stdout == ""
    assert "configuration" in result.stderr.lower()
    assert not requests and not Path(str(image) + ".desc.txt").exists()


def test_unselected_stage_bad_paths_do_not_block_desc(harness, tmp_path):
    run, image, config, requests, _ = harness
    result = run(
        "process",
        image,
        "--config",
        config,
        "--stages",
        "desc",
        "--json-prompt",
        tmp_path / "absent-prompt",
        "--json-schema",
        tmp_path / "absent-schema",
        "--set",
        "stages.json.model=missing",
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.startswith("desc: completed")
    assert len(requests) == 1


def test_path_layer_precedence_and_dedicated_flag_order(harness, tmp_path):
    run, image, config, requests, _ = harness
    sub = tmp_path / "settings"
    sub.mkdir()
    (sub / "file.txt").write_text("YAML PROMPT")
    (tmp_path / "set.txt").write_text("SET PROMPT")
    (tmp_path / "flag.txt").write_text("FLAG PROMPT")
    config.rename(sub / "config.yaml")
    # The YAML path must work when resolved against the config directory.
    text = (
        (sub / "config.yaml")
        .read_text()
        .replace(
            "  desc:\n    model: m", "  desc:\n    model: m\n    prompt_file: file.txt"
        )
    )
    (sub / "config.yaml").write_text(text)
    base = ["process", image, "--config", "settings/config.yaml", "--stages", "desc"]
    first = run(*base)
    assert first.returncode == 0, first.stderr
    assert "YAML PROMPT" in json.dumps(requests[-1][0])
    second = run(
        *base,
        "--regenerate",
        "--set",
        "stages.desc.prompt_file=missing.txt",
        "--set",
        "stages.desc.prompt_file=set.txt",
    )
    assert second.returncode == 0, second.stderr
    assert "SET PROMPT" in json.dumps(requests[-1][0])
    third = run(
        *base,
        "--regenerate",
        "--desc-prompt",
        "flag.txt",
        "--set",
        "stages.desc.prompt_file=missing.txt",
    )
    assert third.returncode == 0, third.stderr
    assert "FLAG PROMPT" in json.dumps(requests[-1][0])
    assert len(requests) == 3


def test_explicit_config_disables_broken_user_discovery(harness):
    run, image, config, requests, home = harness
    discovered = home / ".config/image-clarus/config.yaml"
    discovered.parent.mkdir(parents=True)
    discovered.write_text("invalid: [")
    result = run("process", image, "--config", config, "--stages", "desc")
    assert result.returncode == 0, result.stderr
    assert len(requests) == 1


def test_invalid_discovered_config_is_not_silently_ignored(harness):
    run, image, _, requests, home = harness
    discovered = home / ".config/image-clarus/config.yaml"
    discovered.parent.mkdir(parents=True)
    discovered.write_text("invalid: [")
    result = run("process", image, "--stages", "desc")
    assert result.returncode == 2 and result.stdout == ""
    assert "configuration" in result.stderr.lower()
    assert not requests


@pytest.mark.parametrize(
    "arguments",
    [("--sta", "desc"), ("--regenerat",), ("--version",), ("--json",), ("extra.png",)],
)
def test_unknown_or_extra_arguments_are_usage_errors(harness, arguments):
    run, image, config, requests, _ = harness
    result = run("process", image, "--config", config, "--stages", "desc", *arguments)
    assert result.returncode == 2 and result.stdout == ""
    assert "unrecognized arguments" in result.stderr
    assert not requests


@pytest.mark.parametrize(
    "assignment",
    [
        "providers.local.api_key=SECRET_SENTINEL_621",
        "stages.desc.model=",
        "stages.desc.not_a_field=SECRET_SENTINEL_621",
    ],
)
def test_invalid_set_is_preflight_error_without_secret_disclosure(harness, assignment):
    run, image, config, requests, _ = harness
    result = run(
        "process", image, "--config", config, "--stages", "desc", "--set", assignment
    )
    assert result.returncode == 2 and result.stdout == ""
    assert "invalid override" in result.stderr.lower()
    assert "SECRET_SENTINEL_621" not in result.stderr
    assert not requests


def test_environment_secret_is_used_only_in_authorization(harness):
    run, image, config, requests, _ = harness
    text = config.read_text().replace(
        "    base_url:", "    api_key_env: IMAGE_CLARUS_ACCEPTANCE_KEY\n    base_url:"
    )
    config.write_text(text)
    secret = "synthetic-secret-746"
    result = run(
        "process",
        image,
        "--config",
        config,
        "--stages",
        "desc",
        "--set",
        "logging.level=DEBUG",
        extra_env={"IMAGE_CLARUS_ACCEPTANCE_KEY": secret},
    )
    assert result.returncode == 0, result.stderr
    assert len(requests) == 1
    assert requests[0][1]["Authorization"] == "Bearer " + secret
    assert secret not in result.stdout + result.stderr + json.dumps(requests[0][0])


def test_completed_path_is_json_escaped_and_resolves_symlink(harness, tmp_path):
    run, image, config, requests, _ = harness
    target = tmp_path / 'odd\n"image.png'
    image.rename(target)
    link = tmp_path / "link.png"
    link.symlink_to(target)
    result = run("process", "link.png", "--config", config, "--stages", "desc")
    assert result.returncode == 0, result.stderr
    assert (
        result.stdout
        == f"desc: completed — output={json.dumps(str(target) + '.desc.txt')}\n"
    )
    assert len(result.stdout.splitlines()) == 1 and len(requests) == 1


@pytest.mark.parametrize(
    "policy,expected",
    [("stop", "stage_not_run_after_failure"), ("continue", "completed")],
)
def test_failure_policy_controls_later_stage(harness, tmp_path, policy, expected):
    run, image, config, requests, _ = harness
    unsupported = image.with_suffix(".xyz")
    image.rename(unsupported)
    Path(str(unsupported) + ".desc.txt").write_text("persisted")
    schema = tmp_path / "schema.json"
    schema.write_text('{"type":"object"}')
    result = run(
        "process",
        unsupported,
        "--config",
        config,
        "--regenerate",
        "--json-schema",
        schema,
        "--stages",
        "desc,json",
        "--set",
        "pipeline.on_stage_failure=" + policy,
    )
    assert result.returncode == 1, result.stderr
    lines = result.stdout.splitlines()
    assert len(lines) == 2 and "desc: failed — category=unsupported_image;" in lines[0]
    assert expected in lines[1] and lines[1].startswith("json: ")
    assert len(requests) == (1 if policy == "continue" else 0)


def test_whitespace_env_credential_fails_before_any_stage(harness):
    run, image, config, requests, _ = harness
    config.write_text(
        config.read_text().replace(
            "    base_url:",
            "    api_key_env: IMAGE_CLARUS_ACCEPTANCE_KEY\n    base_url:",
        )
    )
    result = run(
        "process",
        image,
        "--config",
        config,
        "--stages",
        "desc",
        extra_env={"IMAGE_CLARUS_ACCEPTANCE_KEY": "   "},
    )
    assert result.returncode == 1
    assert result.stdout == ""
    assert "credential unavailable" in result.stderr.lower()
    assert not requests and not Path(str(image) + ".desc.txt").exists()
