"""B5 black-box subprocess acceptance; synthetic data, no external provider calls.

Tests marked by the real_exiftool fixture need a real ExifTool on PATH. The
other tool scripts are explicitly doubles and do not demonstrate XMP mapping.
"""

import json
import os
import shutil
import signal
import struct
import subprocess
import sys
import threading
import zlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from xml.etree import ElementTree

import pytest
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]
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
    "title": "Blue square",
    "caption": "A blue square.",
    "tag_candidates": [["shape", "square"], ["color", "blue"]],
}
DESCRIPTION = "A fictional blue square.\n"


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


def envelope():
    return {
        "format_version": 1,
        "schema_id": "urn:image-clarus:metadata-schema:2.0.0",
        "schema_version": "2.0.0",
        "provenance": {
            "provider_alias": "fictional",
            "model_alias": "fictional",
            "model_id": "fictional",
            "prompt_id": "fictional",
            "prompt_sha256": "a" * 64,
            "description_sha256": "b" * 64,
        },
        "metadata": METADATA,
    }


@pytest.fixture
def real_exiftool():
    executable = shutil.which("exiftool")
    if executable is None:
        pytest.skip("real ExifTool unavailable on PATH")
    return executable


@pytest.fixture
def rig(tmp_path):
    requests = []
    arrived = threading.Event()
    release = threading.Event()
    hold = set()

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            stage = "json" if "response_format" in body else "desc"
            requests.append((stage, body))
            arrived.set()
            if stage in hold:
                release.wait(20)
            content = json.dumps(METADATA) if stage == "json" else DESCRIPTION
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
            try:
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def log_message(self, format, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    image = tmp_path / "synthetic.png"
    image.write_bytes(png())
    original = image.read_bytes()
    home = tmp_path / "home"
    home.mkdir()
    empty_path = tmp_path / "empty-path"
    empty_path.mkdir()
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        f"providers:\n  local:\n    base_url: http://127.0.0.1:{server.server_port}/v1\n"
        "models:\n  vision:\n    provider: local\n    model_id: vision-fictional\n"
        "  text:\n    provider: local\n    model_id: text-fictional\n"
        "stages:\n  desc:\n    model: vision\n  json:\n    model: text\n"
    )
    no_model_cfg = tmp_path / "no-model.yaml"
    no_model_cfg.write_text("{}\n")
    env = os.environ.copy()
    env.update(HOME=str(home), PYTHONPATH=str(ROOT / "src"), NO_PROXY="*", no_proxy="*")
    processes = []

    def start(*args, config=cfg, path=None):
        child_env = env.copy()
        if path is not None:
            child_env["PATH"] = str(path)
        proc = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "image_clarus",
                "process",
                str(image),
                "--config",
                str(config),
                *args,
            ],
            cwd=tmp_path,
            env=child_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        processes.append(proc)
        return proc

    def finish(proc, code=0):
        stdout, stderr = proc.communicate(timeout=30)
        assert proc.returncode == code, (proc.returncode, stdout, stderr)
        return stdout, stderr

    rig = SimpleNamespace(
        image=image,
        original=original,
        desc=Path(str(image) + ".desc.txt"),
        structured=Path(str(image) + ".desc.json"),
        xmp=Path(str(image) + ".xmp"),
        no_model_cfg=no_model_cfg,
        empty_path=empty_path,
        requests=requests,
        start=start,
        finish=finish,
        arrived=arrived,
        release=release,
        hold=hold,
    )
    try:
        yield rig
    finally:
        release.set()
        for proc in processes:
            if proc.poll() is None:
                proc.kill()
            proc.communicate(timeout=10)
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        assert not thread.is_alive()


def assert_source(rig):
    assert rig.image.read_bytes() == rig.original


def validate_json(rig):
    value = json.loads(rig.structured.read_bytes())
    schema = json.loads((ROOT / "schemas/image-structure.schema.json").read_bytes())
    Draft202012Validator(schema).validate(value["metadata"])
    assert value["metadata"] == METADATA
    assert value["format_version"] == 1
    assert value["schema_id"] == "urn:image-clarus:metadata-schema:2.0.0"
    assert value["schema_version"] == "2.0.0"
    return value


def assert_xmp(rig):
    root = ElementTree.fromstring(rig.xmp.read_bytes())
    ns = {
        "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
        "dc": "http://purl.org/dc/elements/1.1/",
        "dk": "http://www.digikam.org/ns/1.0/",
    }
    assert [x.text for x in root.findall(".//dk:TagsList/rdf:Seq/rdf:li", ns)] == [
        "ai/shape/square",
        "ai/color/blue",
    ]
    assert root.find(".//dc:title/rdf:Alt/rdf:li", ns).text == "Blue square"
    assert root.find(".//dc:description/rdf:Alt/rdf:li", ns).text == "A blue square."


def matching_xmp():
    return b"""<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
      xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dk="http://www.digikam.org/ns/1.0/">
      <rdf:Description rdf:about=""><dk:TagsList><rdf:Seq>
      <rdf:li>ai/shape/square</rdf:li><rdf:li>ai/color/blue</rdf:li>
      </rdf:Seq></dk:TagsList><dc:title><rdf:Alt>
      <rdf:li xml:lang="x-default">Blue square</rdf:li></rdf:Alt></dc:title>
      <dc:description><rdf:Alt><rdf:li xml:lang="x-default">A blue square.</rdf:li>
      </rdf:Alt></dc:description></rdf:Description></rdf:RDF>"""


def fake_exiftool(directory, *, fail_runtime=False):
    tool = directory / "exiftool"
    tool.write_text(
        '#!/bin/sh\nif [ "$3" = "-ver" ]; then printf "13.00\\n"; exit 0; fi\n'
        + (
            'printf "fictional-private-tool-output\\n" >&2\nexit 1\n'
            if fail_runtime
            else "exit 99\n"
        )
    )
    tool.chmod(0o755)


def test_selected_xmp_requires_exiftool_even_when_no_model_is_configured(rig):
    out, err = rig.finish(
        rig.start("--stages", "xmp", config=rig.no_model_cfg, path=rig.empty_path), 2
    )
    assert not out and "ExifTool" in err
    assert not rig.requests and not rig.xmp.exists()
    assert_source(rig)


@pytest.mark.parametrize("selection", ["desc", "json", "json,desc"])
def test_unselected_xmp_needs_no_exiftool(rig, selection):
    if selection == "json":
        rig.desc.write_text(DESCRIPTION)
    out, err = rig.finish(rig.start("--stages", selection, path=rig.empty_path))
    expected = [stage for stage in ("desc", "json") if stage in selection.split(",")]
    assert [line.split(":")[0] for line in out.splitlines()] == expected
    assert [request[0] for request in rig.requests] == expected
    assert not err and not rig.xmp.exists()
    if "json" in expected:
        validate_json(rig)
    assert_source(rig)


def test_xmp_alone_publishes_persisted_json_and_second_run_is_no_change(
    rig, real_exiftool
):
    rig.structured.write_text(json.dumps(envelope()))
    before = rig.structured.read_bytes()
    out, err = rig.finish(rig.start("--stages", "xmp", config=rig.no_model_cfg))
    assert out == f"xmp: completed — output={json.dumps(str(rig.xmp))}\n"
    assert not err and not rig.requests
    validate_json(rig)
    assert_xmp(rig)
    sidecar = rig.xmp.read_bytes()
    out, err = rig.finish(rig.start("--stages", "xmp", config=rig.no_model_cfg))
    assert out == "xmp: skipped — reason=no_change\n" and not err
    assert rig.xmp.read_bytes() == sidecar and rig.structured.read_bytes() == before
    assert not Path(str(rig.xmp) + ".bak").exists()
    assert not rig.requests
    assert_source(rig)


@pytest.mark.parametrize("selection", [None, "xmp,json,desc", "xmp,json", "xmp,desc"])
def test_registry_order_with_no_change_and_preflight_double(rig, selection):
    # The double supports only the version probe, proving no transform is invoked.
    fake_exiftool(rig.empty_path)
    rig.xmp.write_bytes(matching_xmp())
    if selection == "xmp,json":
        rig.desc.write_text(DESCRIPTION)
    if selection == "xmp,desc":
        rig.structured.write_text(json.dumps(envelope()))
    args = [] if selection is None else ["--stages", selection]
    out, err = rig.finish(rig.start(*args, path=rig.empty_path))
    expected = [
        stage
        for stage in ("desc", "json", "xmp")
        if selection is None or stage in selection.split(",")
    ]
    assert [line.split(":")[0] for line in out.splitlines()] == expected
    assert out.splitlines()[-1] == "xmp: skipped — reason=no_change"
    assert [request[0] for request in rig.requests] == [
        x for x in expected if x != "xmp"
    ]
    assert not err and rig.xmp.read_bytes() == matching_xmp()
    validate_json(rig)
    assert_source(rig)


def test_recovery_of_backup_only_sidecar_before_no_change(rig):
    fake_exiftool(rig.empty_path)
    rig.structured.write_text(json.dumps(envelope()))
    backup = Path(str(rig.xmp) + ".bak")
    backup.write_bytes(matching_xmp())
    out, err = rig.finish(
        rig.start("--stages", "xmp", config=rig.no_model_cfg, path=rig.empty_path)
    )
    assert out == "xmp: skipped — reason=no_change\n" and not err
    assert rig.xmp.read_bytes() == matching_xmp()
    assert not rig.requests
    assert_source(rig)


@pytest.mark.parametrize("mode", ["new", "disabled"])
def test_regenerate_does_not_override_xmp_policies(rig, mode):
    fake_exiftool(rig.empty_path)
    rig.structured.write_text(json.dumps(envelope()))
    original = (
        matching_xmp()
        .replace(b"ai/shape/square", b"ai/old")
        .replace(b"Blue square", b"Old title")
    )
    rig.xmp.write_bytes(original)
    opts = [
        "--stages",
        "xmp",
        "--regenerate",
        "--set",
        f"stages.xmp.tag_policy={mode}",
        "--set",
        f"stages.xmp.title_policy={mode}",
        "--set",
        f"stages.xmp.caption_policy={mode}",
    ]
    out, err = rig.finish(
        rig.start(*opts, config=rig.no_model_cfg, path=rig.empty_path)
    )
    assert out == "xmp: skipped — reason=no_change\n" and not err
    assert rig.xmp.read_bytes() == original
    assert not rig.requests
    assert_source(rig)


def test_invalid_json_fails_not_skips(rig):
    fake_exiftool(rig.empty_path)
    raw = b'{"fictional":'
    rig.structured.write_bytes(raw)
    out, err = rig.finish(
        rig.start(
            "--stages",
            "xmp",
            "--missing-prerequisite",
            "skip",
            config=rig.no_model_cfg,
            path=rig.empty_path,
        ),
        1,
    )
    assert out.startswith("xmp: failed — category=invalid_artifact") and not err
    assert rig.structured.read_bytes() == raw and not rig.xmp.exists()
    assert not rig.requests
    assert_source(rig)


@pytest.mark.parametrize("selection", [None, "xmp,json,desc", "xmp,json", "xmp,desc"])
def test_composed_stages_run_in_registry_order(rig, real_exiftool, selection):
    if selection == "xmp,json":
        rig.desc.write_text(DESCRIPTION)
    if selection == "xmp,desc":
        rig.structured.write_text(json.dumps(envelope()))
    args = [] if selection is None else ["--stages", selection]
    out, err = rig.finish(rig.start(*args))
    expected = [
        stage
        for stage in ("desc", "json", "xmp")
        if selection is None or stage in selection.split(",")
    ]
    assert [line.split(":")[0] for line in out.splitlines()] == expected
    assert all(": completed — output=" in line for line in out.splitlines())
    assert [request[0] for request in rig.requests] == [
        x for x in expected if x != "xmp"
    ]
    assert not err
    validate_json(rig)
    assert_xmp(rig)
    assert_source(rig)


@pytest.mark.parametrize(
    "policy,code,status",
    [
        ("fail", 1, "failed — category=missing_prerequisite"),
        ("skip", 0, "skipped — reason=missing_prerequisite"),
    ],
)
def test_missing_json_does_not_expand_prerequisites(rig, policy, code, status):
    fake_exiftool(rig.empty_path)
    out, err = rig.finish(
        rig.start(
            "--stages",
            "xmp",
            "--missing-prerequisite",
            policy,
            config=rig.no_model_cfg,
            path=rig.empty_path,
        ),
        code,
    )
    assert out.startswith("xmp: " + status) and not err
    assert not rig.requests and not rig.structured.exists() and not rig.xmp.exists()
    assert_source(rig)


def test_malformed_xmp_with_preflight_double_fails_closed(rig):
    fake_exiftool(rig.empty_path)
    rig.structured.write_text(json.dumps(envelope()))
    raw = b"<fictional-broken-xmp"
    rig.xmp.write_bytes(raw)
    out, err = rig.finish(
        rig.start("--stages", "xmp", config=rig.no_model_cfg, path=rig.empty_path), 1
    )
    assert out.startswith("xmp: failed — category=invalid_artifact") and not err
    assert rig.xmp.read_bytes() == raw and not rig.requests
    assert_source(rig)


def test_unusable_xmp_destination_fails_without_removing_contents(rig):
    fake_exiftool(rig.empty_path)
    rig.structured.write_text(json.dumps(envelope()))
    rig.xmp.mkdir()
    sentinel = rig.xmp / "fictional-sentinel"
    sentinel.write_bytes(b"unchanged")
    out, err = rig.finish(
        rig.start("--stages", "xmp", config=rig.no_model_cfg, path=rig.empty_path), 1
    )
    assert out.startswith("xmp: failed — category=file_io") and not err
    assert sentinel.read_bytes() == b"unchanged" and not rig.requests
    assert_source(rig)


def test_malformed_xmp_fails_without_deleting_existing_sidecar(rig, real_exiftool):
    rig.structured.write_text(json.dumps(envelope()))
    raw = b"<fictional-broken-xmp"
    rig.xmp.write_bytes(raw)
    out, err = rig.finish(rig.start("--stages", "xmp", config=rig.no_model_cfg), 1)
    assert out.startswith("xmp: failed — category=invalid_artifact") and not err
    assert rig.xmp.read_bytes() == raw and not rig.requests
    assert_source(rig)


def test_runtime_tool_failure_preserves_existing_sidecar(rig):
    fake_exiftool(rig.empty_path, fail_runtime=True)
    rig.structured.write_text(json.dumps(envelope()))
    raw = b'<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"><rdf:Description rdf:about=""/></rdf:RDF>'
    rig.xmp.write_bytes(raw)
    out, err = rig.finish(
        rig.start("--stages", "xmp", config=rig.no_model_cfg, path=rig.empty_path), 1
    )
    assert out.startswith("xmp: failed — category=invalid_artifact")
    assert "fictional-private-tool-output" not in out + err
    assert rig.xmp.read_bytes() == raw and not rig.requests
    assert_source(rig)


@pytest.mark.parametrize("sig", [signal.SIGINT, signal.SIGTERM])
def test_signal_during_description_does_not_start_xmp(rig, sig):
    fake_exiftool(rig.empty_path)
    rig.hold.add("desc")
    proc = rig.start("--stages", "desc,xmp", path=rig.empty_path)
    assert rig.arrived.wait(20), "local description request did not arrive"
    proc.send_signal(sig)
    out, _err = rig.finish(proc, 128 + sig)
    assert not rig.release.is_set(), "response must remain held until the CLI exits"
    assert [x[0] for x in rig.requests] == ["desc"]
    assert not rig.xmp.exists() and not rig.structured.exists()
    assert "xmp: completed" not in out
    assert_source(rig)
