"""C1 request acceptance through separate CLIs and a loopback synthetic provider."""

import base64
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from test_single_image_pipeline import METADATA, png

ROOT = Path(__file__).resolve().parents[2]
INLINE = "fictional-inline-secret-482"
ENV_SECRET = "fictional-env-secret-932"


@pytest.fixture
def local(tmp_path):
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            requests.append((body, self.headers.get("Authorization")))
            content = (
                json.dumps(METADATA)
                if "response_format" in body
                else "Fictional description."
            )
            data = json.dumps(
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
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, format, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    home = tmp_path / "home"
    home.mkdir()
    env = os.environ.copy()
    env.update(
        HOME=str(home),
        PYTHONPATH=str(ROOT / "src"),
        NO_PROXY="*",
        no_proxy="*",
        FICTIONAL_C1_KEY=ENV_SECRET,
    )
    image = tmp_path / "sample.png"
    image.write_bytes(png())
    config = tmp_path / "config.yaml"
    config.write_text(
        f"providers:\n  local:\n    base_url: http://127.0.0.1:{server.server_port}/v1\n"
        f"    api_key_env: FICTIONAL_C1_KEY\n  spare:\n    base_url: http://127.0.0.1:{server.server_port}/v1\n    api_key: {INLINE}\n"
        "models:\n  vision: {provider: local, model_id: fictional-vision}\n  text: {provider: local, model_id: fictional-text}\n"
        "stages:\n  desc: {model: vision}\n  json:\n    model: text\n    preferred_categories: [fiction, fiction/forest/trees]\n"
    )

    def run(*args):
        return subprocess.run(
            [sys.executable, "-m", "image_clarus", *map(str, args)],
            cwd=tmp_path,
            check=False,
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )

    assert run("init").returncode == 0
    state = tmp_path / ".image-clarus"
    with sqlite3.connect(state / "state.sqlite3") as db:
        db.executemany(
            "insert into known_categories(path) values (?)",
            [("fiction",), ("fiction/forest/trees",)],
        )
    try:
        yield requests, image, config, state, run
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        assert not thread.is_alive()


@pytest.mark.parametrize("stage", ["desc", "json"])
@pytest.mark.parametrize("namespace", ["config", "state"])
def test_authored_namespace_requests_and_hash(local, tmp_path, stage, namespace):
    requests, image, config, state, run = local
    if stage == "json":
        Path(str(image) + ".desc.txt").write_text("Fictional persisted description.")
    macro = (
        "config.stages.json.preferred_categories"
        if namespace == "config"
        else "state.categories.known"
    )
    source = f"Authored café: {{{{{macro}}}}}\r\n".encode()
    prompt = tmp_path / "authored.txt"
    prompt.write_bytes(source)
    args = [
        "process",
        image,
        "--config",
        config,
        "--state-dir",
        state,
        "--stages",
        stage,
        f"--{stage}-prompt",
        prompt,
    ]
    if stage == "json":
        args += ["--set", "stages.json.include_prompt_sha256=true"]
    result = run(*args)
    assert result.returncode == 0, (result.stdout, result.stderr)
    assert not result.stderr
    assert len(requests) == 1
    body, auth = requests[0]
    assert auth == f"Bearer {ENV_SECRET}"
    expected = 'Authored café: ["fiction","fiction/forest/trees"]\r\n'
    if stage == "desc":
        user_content = [
            {
                "type": "image_url",
                "image_url": {
                    "url": "data:image/png;base64,"
                    + base64.b64encode(image.read_bytes()).decode("ascii")
                },
            }
        ]
    else:
        user_content = body["messages"][1]["content"]
        assert len(user_content) == 1
        assert set(user_content[0]) == {"type", "text"}
        assert user_content[0]["type"] == "text"
        assert json.loads(user_content[0]["text"]) == {
            "description": "Fictional persisted description.",
            "schema": json.loads(
                (ROOT / "schemas/image-structure.schema.json").read_bytes()
            ),
        }
    expected_body = {
        "model": "fictional-vision" if stage == "desc" else "fictional-text",
        "messages": [
            {"role": "system", "content": expected},
            {"role": "user", "content": user_content},
        ],
        "stream": False,
        "n": 1,
    }
    if stage == "json":
        expected_body["response_format"] = {"type": "json_object"}
    assert body == expected_body
    if stage == "json":
        envelope = json.loads(Path(str(image) + ".desc.json").read_bytes())
        assert (
            envelope["provenance"]["prompt_sha256"]
            == hashlib.sha256(source).hexdigest()
        )
        assert (
            hashlib.sha256(source).hexdigest()
            != hashlib.sha256(expected.encode()).hexdigest()
        )
    assert INLINE not in json.dumps(body) + result.stdout + result.stderr
    assert ENV_SECRET not in json.dumps(body) + result.stdout + result.stderr


def test_omitted_advice_and_parent_snapshot_secrets(local, tmp_path):
    requests, image, config, state, run = local
    Path(str(image) + ".desc.txt").write_text("Fictional persisted description.")
    prompt = tmp_path / "snapshot.txt"
    prompt.write_text("Only provider configuration: {{config.providers}}")
    result = run(
        "process",
        image,
        "--config",
        config,
        "--state-dir",
        state,
        "--stages",
        "json",
        "--json-prompt",
        prompt,
    )
    assert result.returncode == 0, (result.stdout, result.stderr)
    assert not result.stderr
    assert len(requests) == 1
    body, auth = requests[0]
    assert auth == f"Bearer {ENV_SECRET}"
    system = body["messages"][0]["content"]
    assert system.startswith("Only provider configuration: ")
    assert "fiction/forest/trees" not in json.dumps(body)
    assert "preferred_categories" not in system and "known_categories" not in system
    for sentinel in (INLINE, ENV_SECRET, "FICTIONAL_C1_KEY"):
        assert sentinel not in json.dumps(body) + result.stdout + result.stderr
    envelope = json.loads(Path(str(image) + ".desc.json").read_bytes())
    assert "prompt_sha256" not in envelope["provenance"]


@pytest.mark.parametrize(
    "reference",
    ["config.providers.spare.api_key", "config.providers.local.api_key_env"],
)
def test_direct_secret_reference_fails_without_request(local, tmp_path, reference):
    requests, image, config, state, run = local
    prompt = tmp_path / "secret-reference.txt"
    prompt.write_text("{{" + reference + "}}")
    result = run(
        "process",
        image,
        "--config",
        config,
        "--state-dir",
        state,
        "--stages",
        "desc",
        "--desc-prompt",
        prompt,
    )
    assert result.returncode != 0
    assert not requests
    assert result.stderr or "failed" in result.stdout.lower()
    for sentinel in (INLINE, ENV_SECRET, "FICTIONAL_C1_KEY"):
        assert sentinel not in result.stdout + result.stderr


@pytest.mark.parametrize(
    "namespace", ["config.stages.json.preferred_categories", "state.categories.known"]
)
def test_negative_macro_depth_rejected_before_request(local, namespace):
    requests, image, config, state, run = local
    Path(str(image) + ".desc.txt").write_text("Fictional persisted description.")
    result = run(
        "process",
        image,
        "--config",
        config,
        "--state-dir",
        state,
        "--stages",
        "json",
        "--set",
        f'prompt_expansion.macros["{namespace}"].max_depth=-1',
    )
    assert result.returncode != 0
    assert "max_depth" in result.stdout + result.stderr
    assert not requests


@pytest.mark.parametrize(
    "depth,expected",
    [(None, '["fiction","fiction/forest/trees"]'), (1, '["fiction"]'), (0, "[]")],
)
def test_authored_json_guidance_depth(local, tmp_path, depth, expected):
    requests, image, config, state, run = local
    Path(str(image) + ".desc.txt").write_text("Fictional persisted description.")
    prompt = tmp_path / "guidance.txt"
    prompt.write_text(
        "Fictional guidance: {{config.stages.json.preferred_categories}}.\n"
    )
    args = [
        "process",
        image,
        "--config",
        config,
        "--state-dir",
        state,
        "--stages",
        "json",
        "--json-prompt",
        prompt,
    ]
    if depth is not None:
        args += [
            "--set",
            f'prompt_expansion.macros["config.stages.json.preferred_categories"].max_depth={depth}',
        ]
    result = run(*args)
    assert result.returncode == 0, (result.stdout, result.stderr)
    assert not result.stderr
    assert len(requests) == 1
    system = requests[0][0]["messages"][0]["content"]
    assert system == f"Fictional guidance: {expected}.\n"
