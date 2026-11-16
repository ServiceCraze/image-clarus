"""C1 black-box CLI acceptance; supplemental coverage, not historical RED."""

import base64
import hashlib
import json
import os
import struct
import subprocess
import sys
import threading
import zlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

import pytest
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]
V1 = "Sentinel v1: café\r\nSecond line.\n"
V2 = "Complete replacement v2: a blue square.\n"
METADATA = {
    "subjects": ["square"],
    "objects": [],
    "actions": [],
    "setting": {"type": "", "context": ""},
    "visual_characteristics": {
        "colors": ["blue"],
        "composition": "centered",
        "lighting": "",
        "visual_style": "",
    },
    "keywords": ["synthetic"],
}


def png():
    def chunk(kind, data):
        return (
            struct.pack(">I", len(data))
            + kind
            + data
            + struct.pack(">I", zlib.crc32(kind + data))
        )

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(b"\x00\x00\x00\xff"))
        + chunk(b"IEND", b"")
    )


@pytest.fixture
def rig(tmp_path):
    requests = []
    arrived = {stage: threading.Event() for stage in ("desc", "json")}
    release = {stage: threading.Event() for stage in ("desc", "json")}
    hold = set()
    errors = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            try:
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                stage = "json" if "response_format" in body else "desc"
                requests.append((stage, body, self.path))
                arrived[stage].set()
                if stage in hold and not release[stage].wait(20):
                    raise TimeoutError(f"{stage} release timed out")
                content = json.dumps(METADATA) if stage == "json" else V2
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
            except (OSError, ValueError, KeyError, TimeoutError) as exc:
                errors.append(repr(exc))

        def log_message(self, format, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    images = tmp_path / "images"
    images.mkdir()
    image = images / "synthetic.png"
    image.write_bytes(png())
    original = image.read_bytes()
    home = tmp_path / "home"
    home.mkdir()
    env = os.environ.copy()
    env.update(HOME=str(home), PYTHONPATH=str(ROOT / "src"), NO_PROXY="*", no_proxy="*")
    processes = []

    def config(name, desc_model="vision-model", json_model="text-model"):
        path = tmp_path / f"{name}.yaml"
        path.write_text(
            f"providers:\n  local:\n    base_url: http://127.0.0.1:{server.server_port}/v1\n"
            f"models:\n  vision:\n    provider: local\n    model_id: {desc_model}\n"
            f"  text:\n    provider: local\n    model_id: {json_model}\n"
            "stages:\n  desc:\n    model: vision\n  json:\n    model: text\n"
        )
        return path

    def start(cfg, *args):
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "image_clarus",
                "process",
                str(image),
                "--config",
                str(cfg),
                *args,
            ],
            cwd=tmp_path,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        processes.append(process)
        return process

    def finish(process, expected=0):
        stdout, stderr = process.communicate(timeout=30)
        assert process.returncode == expected, (stdout, stderr)
        assert not stderr, stderr
        return stdout

    r = SimpleNamespace()
    r.image, r.original, r.requests, r.hold = image, original, requests, hold
    r.arrived, r.release, r.config, r.start, r.finish = (
        arrived,
        release,
        config,
        start,
        finish,
    )
    r.desc = Path(str(image) + ".desc.txt")
    r.structured = Path(str(image) + ".desc.json")
    try:
        yield r
        assert not errors, errors
    finally:
        for event in release.values():
            event.set()
        for process in processes:
            if process.poll() is None:
                process.kill()
            process.communicate(timeout=10)
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        assert not thread.is_alive()


def assert_files(r, *names):
    assert r.image.read_bytes() == r.original
    assert (
        hashlib.sha256(r.image.read_bytes()).digest()
        == hashlib.sha256(r.original).digest()
    )
    assert {p.name for p in r.image.parent.iterdir()} == {r.image.name, *names}


def check_envelope(r, description, model="text-model"):
    result = json.loads(r.structured.read_bytes())
    schema = json.loads((ROOT / "schemas/image-structure.schema.json").read_bytes())
    Draft202012Validator(schema).validate(result["metadata"])
    assert result["metadata"] == METADATA
    assert set(result) == {
        "format_version",
        "schema_id",
        "schema_version",
        "provenance",
        "metadata",
    }
    assert result["format_version"] == 1
    assert result["schema_id"] == "urn:image-clarus:metadata-schema:1.0.0"
    assert result["schema_version"] == "1.0.0"
    assert result["provenance"]["model_id"] == model
    assert (
        result["provenance"]["description_sha256"]
        == hashlib.sha256(description.encode()).hexdigest()
    )
    return result


def check_request(request, description, model="text-model"):
    stage, body, path = request
    assert stage == "json" and path == "/v1/chat/completions"
    assert body["model"] == model
    assert body["response_format"] == {"type": "json_object"}
    assert body["messages"][1]["content"][0] == {
        "type": "text",
        "text": "Persisted description:\n" + description,
    }
    selected = body["messages"][1]["content"][1]["text"]
    assert selected.startswith("Selected JSON Schema:\n")
    assert json.loads(selected.removeprefix("Selected JSON Schema:\n")) == json.loads(
        (ROOT / "schemas/image-structure.schema.json").read_bytes()
    )


@pytest.mark.parametrize("selection", [None, "desc,json"])
def test_combined_and_default_persisted_handoff(rig, selection):
    args = [] if selection is None else ["--stages", selection]
    stdout = rig.finish(rig.start(rig.config("both"), *args))
    assert (
        stdout
        == f"desc: completed — output={json.dumps(str(rig.desc))}\njson: completed — output={json.dumps(str(rig.structured))}\n"
    )
    assert [x[0] for x in rig.requests] == ["desc", "json"]
    assert rig.requests[0][1]["model"] == "vision-model"
    image_url = rig.requests[0][1]["messages"][1]["content"][0]["image_url"]["url"]
    assert (
        image_url == "data:image/png;base64," + base64.b64encode(rig.original).decode()
    )
    assert rig.desc.read_bytes() == V2.encode()
    check_request(rig.requests[1], rig.desc.read_bytes().decode())
    check_envelope(rig, V2)
    assert_files(rig, rig.desc.name, rig.structured.name)


def test_desc_only(rig):
    stdout = rig.finish(rig.start(rig.config("desc"), "--stages", "desc"))
    assert stdout == f"desc: completed — output={json.dumps(str(rig.desc))}\n"
    assert rig.desc.read_bytes() == V2.encode()
    assert [x[0] for x in rig.requests] == ["desc"]
    assert_files(rig, rig.desc.name)


def test_json_only_existing_description(rig):
    rig.desc.write_bytes(V1.encode())
    stdout = rig.finish(rig.start(rig.config("json"), "--stages", "json"))
    assert stdout == f"json: completed — output={json.dumps(str(rig.structured))}\n"
    assert len(rig.requests) == 1
    check_request(rig.requests[0], V1)
    check_envelope(rig, V1)
    assert rig.desc.read_bytes() == V1.encode()
    assert_files(rig, rig.desc.name, rig.structured.name)


def test_json_only_missing_description(rig):
    stdout = rig.finish(
        rig.start(rig.config("missing"), "--stages", "json"), expected=1
    )
    assert stdout.startswith("json: failed — category=missing_prerequisite")
    assert not rig.requests
    assert_files(rig)


def test_skip_and_explicit_regeneration(rig):
    cfg = rig.config("regenerate")
    rig.finish(rig.start(cfg))
    old_desc, old_json = rig.desc.read_bytes(), rig.structured.read_bytes()
    assert (
        rig.finish(rig.start(cfg))
        == "desc: skipped — reason=output_exists\njson: skipped — reason=output_exists\n"
    )
    assert len(rig.requests) == 2
    assert (rig.desc.read_bytes(), rig.structured.read_bytes()) == (old_desc, old_json)
    rig.desc.write_bytes(V1.encode())
    stdout = rig.finish(rig.start(cfg, "--regenerate"))
    assert (
        stdout
        == f"desc: completed — output={json.dumps(str(rig.desc))}\njson: completed — output={json.dumps(str(rig.structured))}\n"
    )
    assert [x[0] for x in rig.requests] == ["desc", "json", "desc", "json"]
    assert rig.desc.read_bytes() == V2.encode()
    check_request(rig.requests[-1], V2)
    check_envelope(rig, V2)
    assert_files(rig, rig.desc.name, rig.structured.name)


def test_independent_processes_consume_persisted_snapshot(rig):
    rig.desc.write_bytes(V1.encode())
    desc_cfg = rig.config(
        "desc-independent", desc_model="independent-vision", json_model="unused-json"
    )
    json_cfg = rig.config(
        "json-independent", desc_model="unused-vision", json_model="independent-text"
    )
    rig.hold.update(("desc", "json"))
    desc = rig.start(desc_cfg, "--stages", "desc", "--regenerate")
    assert rig.arrived["desc"].wait(20), "description request did not arrive"
    assert desc.poll() is None and rig.desc.read_bytes() == V1.encode()
    structured = rig.start(json_cfg, "--stages", "json")
    assert desc.pid != structured.pid
    assert rig.arrived["json"].wait(20), "JSON request did not arrive"
    assert desc.poll() is None and structured.poll() is None
    assert rig.desc.read_bytes() == V1.encode()
    assert [x[0] for x in rig.requests] == ["desc", "json"]
    assert rig.requests[0][1]["model"] == "independent-vision"
    check_request(rig.requests[1], V1, "independent-text")
    rig.release["desc"].set()
    assert rig.finish(desc) == f"desc: completed — output={json.dumps(str(rig.desc))}\n"
    assert rig.desc.read_bytes() == V2.encode()
    assert structured.poll() is None and not rig.structured.exists()
    rig.release["json"].set()
    assert (
        rig.finish(structured)
        == f"json: completed — output={json.dumps(str(rig.structured))}\n"
    )
    check_envelope(rig, V1, "independent-text")
    assert rig.desc.read_bytes() == V2.encode()
    assert_files(rig, rig.desc.name, rig.structured.name)
