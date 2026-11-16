"""Supplemental black-box artifact coverage; not historical RED evidence."""

import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SECRET = "synthetic-credential-987654"


@pytest.fixture
def harness(tmp_path):
    requests = []
    state = {"fail": False, "description": "first description", "caption": "first"}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            requests.append((body, dict(self.headers)))
            if state["fail"]:
                status = 500
                payload = json.dumps(
                    {"error": {"message": f"{SECRET}\nforged line"}}
                ).encode()
            else:
                status = 200
                content = (
                    json.dumps({"caption": state["caption"]})
                    if body.get("response_format")
                    else state["description"]
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
            self.send_response(status)
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
        f"providers:\n  local:\n    api_key_env: ARTIFACT_TEST_KEY\n    base_url: http://127.0.0.1:{server.server_port}/v1\n"
        "models:\n  m:\n    provider: local\n    model_id: synthetic\n"
        "stages:\n  desc:\n    model: m\n    regenerate: false\n  json:\n    model: m\n    regenerate: false\n"
    )
    schema = tmp_path / "schema.json"
    schema.write_text('{"type":"object","required":["caption"]}')
    home = tmp_path / "home"
    home.mkdir()

    def run(*args):
        env = os.environ.copy()
        env.update(
            HOME=str(home),
            PYTHONPATH=str(ROOT / "src"),
            NO_PROXY="*",
            no_proxy="*",
            ARTIFACT_TEST_KEY=SECRET,
        )
        return subprocess.run(
            [
                sys.executable,
                "-m",
                "image_clarus",
                "process",
                str(image),
                "--config",
                str(config),
                "--json-schema",
                str(schema),
                *args,
            ],
            cwd=tmp_path,
            env=env,
            capture_output=True,
            text=True,
            timeout=25,
            check=False,
        )

    try:
        yield run, image, requests, state
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()
        assert not thread.is_alive()


def output(image, extension):
    return Path(str(image) + ".desc." + extension)


def test_regenerate_flag_replaces_both_outputs_despite_false_layers(harness):
    run, image, requests, state = harness
    first = run()
    assert first.returncode == 0, first.stderr
    desc, structured = output(image, "txt"), output(image, "json")
    old_desc, old_json = desc.read_bytes(), structured.read_bytes()
    state.update(description="replacement description", caption="replacement")
    result = run(
        "--regenerate",
        "--set",
        "stages.desc.regenerate=false",
        "--set",
        "stages.json.regenerate=false",
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == (
        f"desc: completed — output={json.dumps(str(desc))}\n"
        f"json: completed — output={json.dumps(str(structured))}\n"
    )
    assert desc.read_bytes() == b"replacement description" != old_desc
    assert structured.read_bytes() != old_json
    assert json.loads(structured.read_bytes())["metadata"] == {"caption": "replacement"}
    assert len(requests) == 4
    assert "replacement description" in json.dumps(requests[-1][0])
    assert image.read_bytes() == b"synthetic image"


@pytest.mark.parametrize(
    "stage,extension,invalid",
    [("desc", "txt", b" \n\t"), ("json", "json", b"{invalid json")],
)
def test_invalid_existing_output_fails_without_overwrite(
    harness, stage, extension, invalid
):
    run, image, requests, _ = harness
    artifact = output(image, extension)
    artifact.write_bytes(invalid)
    if stage == "json":
        output(image, "txt").write_text("valid prerequisite")
    result = run("--stages", stage)
    assert result.returncode == 1, result.stderr
    assert result.stdout.startswith(
        f"{stage}: failed — category=invalid_artifact; message="
    )
    assert len(result.stdout.splitlines()) == 1
    assert artifact.read_bytes() == invalid
    assert not requests


def test_valid_json_is_skipped_before_missing_description_check(harness):
    run, image, requests, _ = harness
    first = run()
    assert first.returncode == 0, first.stderr
    desc, structured = output(image, "txt"), output(image, "json")
    original = structured.read_bytes()
    assert json.loads(original)["metadata"] == {"caption": "first"}
    desc.unlink()
    requests.clear()
    result = run("--stages", "json")
    assert result.returncode == 0, result.stderr
    assert result.stdout == "json: skipped — reason=output_exists\n"
    assert not desc.exists() and structured.read_bytes() == original
    assert not requests


def test_real_provider_failure_does_not_expose_credential_or_forge_lines(harness):
    run, image, requests, state = harness
    state["fail"] = True
    result = run("--stages", "desc", "--set", "logging.level=DEBUG")
    assert result.returncode == 1, result.stderr
    assert (
        result.stdout
        == "desc: failed — category=provider_unavailable; message=Description provider request failed\n"
    )
    assert SECRET not in result.stdout + result.stderr
    assert "forged line" not in result.stdout + result.stderr
    assert len(requests) == 1
    assert requests[0][1]["Authorization"] == "Bearer " + SECRET
    assert not output(image, "txt").exists()
