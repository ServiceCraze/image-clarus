"""C2 POSIX CLI signals at instrumented planning and real HTTP boundaries.

sitecustomize only holds entry to real discovery/planning and observes the real
handler; it does not generate signals. The provider is local and synthetic.
A held response demonstrates cancellation while work remains outstanding, not
remote-server cancellation. These tests do not cover signals inside filesystem
syscalls, SQLite commit, or every scheduler interleaving.
"""

import json
import os
import signal
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.skipif(os.name != "posix", reason="POSIX signals")


def wait_file(path, process):
    deadline = time.monotonic() + 20
    while not path.exists() and process.poll() is None and time.monotonic() < deadline:
        time.sleep(0.01)
    assert path.exists(), f"missing {path.name}; child exit={process.poll()}"


def cleanup(process):
    if process.poll() is None:
        process.kill()
    process.communicate(timeout=10)


def config(path, port):
    path.write_text(
        f"providers:\n  local:\n    base_url: http://127.0.0.1:{port}/v1\n"
        "models:\n  m:\n    provider: local\n    model_id: synthetic\n"
        "stages:\n  desc:\n    model: m\n  json:\n    model: m\n"
    )


@pytest.mark.parametrize("signum", [signal.SIGINT, signal.SIGTERM])
@pytest.mark.parametrize("boundary", ["discovery", "planning"])
def test_signal_at_discovery_or_planning_entry(tmp_path, signum, boundary):
    images = tmp_path / "images"
    images.mkdir()
    image = images / "sample.jpg"
    image.write_bytes(b"synthetic image")
    cfg = tmp_path / "config.yaml"
    config(cfg, 1234)
    entered, received, release = (
        tmp_path / name for name in ("entered", "received", "release")
    )
    (tmp_path / "sitecustomize.py").write_text(f"""\
import signal, time
from pathlib import Path
from image_clarus import discovery, batch_plan
real_signal = signal.signal
def install(sig, handler):
    if callable(handler) and handler.__name__ == "request":
        def observed(signum, frame):
            handler(signum, frame)
            Path({str(received)!r}).touch()
        return real_signal(sig, observed)
    return real_signal(sig, handler)
signal.signal = install
module = discovery if {boundary!r} == "discovery" else batch_plan
name = "discover_images" if {boundary!r} == "discovery" else "build_plan"
original = getattr(module, name)
def wrapped(*args, **kwargs):
    Path({str(entered)!r}).touch()
    deadline = time.monotonic() + 30
    while not Path({str(release)!r}).exists():
        if time.monotonic() > deadline: raise RuntimeError("barrier timeout")
        time.sleep(.01)
    return original(*args, **kwargs)
setattr(module, name, wrapped)
""")
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "image_clarus",
            "process",
            str(images),
            "--stages",
            "desc",
            "--config",
            str(cfg),
        ],
        env={
            **os.environ,
            "PYTHONPATH": os.pathsep.join([str(tmp_path), str(ROOT / "src")]),
        },
        cwd=tmp_path,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        wait_file(entered, process)
        process.send_signal(signum)
        wait_file(received, process)
        release.touch()
        out, err = process.communicate(timeout=20)
        assert process.returncode == 128 + signum, (out, err)
        assert image.read_bytes() == b"synthetic image"
        assert not list(images.glob("*.desc.*"))
    finally:
        release.touch()
        cleanup(process)


@pytest.mark.parametrize("signum", [signal.SIGINT, signal.SIGTERM])
@pytest.mark.parametrize("stage", ["desc", "json"])
def test_signal_with_inflight_stage_and_queued_images(tmp_path, signum, stage):
    entered, release = threading.Event(), threading.Event()
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            requests.append(self.rfile.read(int(self.headers["Content-Length"])))
            entered.set()
            if not release.wait(30):
                return
            body = json.dumps(
                {
                    "choices": [
                        {
                            "message": {"role": "assistant", "content": "fictional"},
                            "finish_reason": "stop",
                        }
                    ]
                }
            ).encode()
            try:
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def log_message(self, format, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    images = tmp_path / "images"
    images.mkdir()
    for i in range(3):
        image = images / f"{i}.jpg"
        image.write_bytes(b"synthetic image")
        if stage == "json":
            Path(str(image) + ".desc.txt").write_text("synthetic description")
    cfg = tmp_path / "config.yaml"
    config(cfg, server.server_port)
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "image_clarus",
            "process",
            str(images),
            "--stages",
            stage,
            "--config",
            str(cfg),
        ],
        cwd=tmp_path,
        env={**os.environ, "PYTHONPATH": str(ROOT / "src")},
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert entered.wait(20), "provider was not reached"
        process.send_signal(signum)
        out, err = process.communicate(timeout=15)
        assert not release.is_set()
        assert process.returncode == 128 + signum, (out, err)
        assert len(requests) == 1
        assert not list(images.glob("*.desc.json"))
        assert all(p.read_bytes() == b"synthetic image" for p in images.glob("*.jpg"))
        if stage == "desc":
            assert not list(images.glob("*.desc.txt"))
    finally:
        release.set()
        cleanup(process)
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
