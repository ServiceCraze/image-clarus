"""Real CLI signal tests with a local provider and a controlled write barrier."""

import json
import os
import signal
import subprocess
import sys
import threading
import time
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SOURCE = b"synthetic image bytes\x00\xff"
NEW_DESCRIPTION = "synthetic generated description"


@contextmanager
def provider(*, stall=False):
    entered = threading.Event()
    release = threading.Event()
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = self.rfile.read(int(self.headers["Content-Length"]))
            requests.append((self.path, body))
            entered.set()
            if stall and not release.wait(30):
                return
            data = json.dumps(
                {
                    "choices": [
                        {
                            "index": 0,
                            "message": {
                                "role": "assistant",
                                "content": NEW_DESCRIPTION,
                            },
                            "finish_reason": "stop",
                        }
                    ]
                }
            ).encode()
            try:
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def log_message(self, format, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_port, entered, release, requests
    finally:
        release.set()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def setup_cli(tmp_path, port, *, injection=None, existing_description=None):
    image = tmp_path / "image.png"
    image.write_bytes(SOURCE)
    if existing_description is not None:
        Path(str(image) + ".desc.txt").write_bytes(existing_description)
    config = tmp_path / "config.yaml"
    config.write_text(
        f"providers:\n  local:\n    base_url: http://127.0.0.1:{port}/v1\n"
        "models:\n  m:\n    provider: local\n    model_id: synthetic\n"
        "stages:\n  desc:\n    model: m\n  json:\n    model: m\n"
        "pipeline:\n  backup_retention: retain\n"
    )
    pythonpath = [str(ROOT / "src")]
    if injection is not None:
        (tmp_path / "sitecustomize.py").write_text(injection)
        pythonpath.insert(0, str(tmp_path))
    # Only the default XMP stage's preflight is expected to run here.
    tools = tmp_path / "tools"
    tools.mkdir()
    executable = tools / "exiftool"
    executable.write_text(
        '#!/bin/sh\nif [ "$3" = "-ver" ]; then printf "13.00\\n"; exit 0; fi\nexit 99\n'
    )
    executable.chmod(0o700)
    env = dict(
        os.environ,
        PYTHONPATH=os.pathsep.join(pythonpath),
        PATH=str(tools) + os.pathsep + os.environ.get("PATH", ""),
    )
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "image_clarus",
            "process",
            str(image),
            "--config",
            str(config),
            "--regenerate",
        ],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return process, image


def wait_for_marker(marker, process):
    deadline = time.monotonic() + 15
    while (
        not marker.exists() and process.poll() is None and time.monotonic() < deadline
    ):
        time.sleep(0.01)
    assert marker.exists(), "CLI failed to reach the write checkpoint"


def stop_process(process):
    if process.poll() is None:
        process.kill()
    process.communicate(timeout=5)


@pytest.mark.parametrize("signum", [signal.SIGINT, signal.SIGTERM])
def test_signal_cancels_inflight_request_before_provider_releases(tmp_path, signum):
    with provider(stall=True) as (port, entered, release, requests):
        process, image = setup_cli(tmp_path, port)
        try:
            assert entered.wait(15), "CLI did not reach provider"
            process.send_signal(signum)
            try:
                stdout, stderr = process.communicate(timeout=4)
            except subprocess.TimeoutExpired:
                pytest.fail(
                    "CLI did not exit while the provider response remained held"
                )
            assert not release.is_set()
            assert process.returncode == 128 + signum, stderr
            assert (
                stdout
                == "desc: skipped — reason=interrupted\njson: skipped — reason=interrupted\nxmp: skipped — reason=interrupted\n"
            )
            assert len(requests) == 1
            assert requests[0][0] == "/v1/chat/completions"
            assert image.read_bytes() == SOURCE
            assert not Path(str(image) + ".desc.txt").exists()
            assert not Path(str(image) + ".desc.json").exists()
        finally:
            stop_process(process)


@pytest.mark.parametrize("signum", [signal.SIGINT, signal.SIGTERM])
@pytest.mark.parametrize(
    "checkpoint", ["output_write", "backup_replace", "destination_replace"]
)
def test_signal_during_actual_write_finishes_before_stopping(
    tmp_path, signum, checkpoint
):
    marker = tmp_path / "write-entered"
    received = tmp_path / "signal-received"
    release = tmp_path / "write-release"
    injection = f"""\
import signal
import time
from pathlib import Path
from image_clarus.artifacts import ArtifactService
real_signal = signal.signal
def install(sig, handler):
    if callable(handler) and handler.__name__ == 'request':
        def observed(signum, frame):
            handler(signum, frame)
            Path({str(received)!r}).touch()
        return real_signal(sig, observed)
    return real_signal(sig, handler)
signal.signal = install
original = ArtifactService._point
def point(self, name):
    if name == {checkpoint!r}:
        Path({str(marker)!r}).touch()
        deadline = time.monotonic() + 20
        while not Path({str(release)!r}).exists():
            if time.monotonic() > deadline:
                raise RuntimeError("write barrier timed out")
            time.sleep(0.01)
    return original(self, name)
ArtifactService._point = point
"""
    with provider() as (port, entered, _, requests):
        process, image = setup_cli(
            tmp_path, port, injection=injection, existing_description=b"old description"
        )
        destination = Path(str(image) + ".desc.txt")
        try:
            assert entered.wait(15), "CLI did not reach provider"
            wait_for_marker(marker, process)
            process.send_signal(signum)
            wait_for_marker(received, process)
            assert process.poll() is None, "write did not wait for its safe boundary"
            release.touch()
            stdout, stderr = process.communicate(timeout=8)
            assert process.returncode == 128 + signum, stderr
            assert (
                stdout
                == f"desc: completed — output={json.dumps(str(destination))}\njson: skipped — reason=interrupted\nxmp: skipped — reason=interrupted\n"
            )
            assert destination.read_bytes() == NEW_DESCRIPTION.encode()
            assert Path(str(destination) + ".bak").read_bytes() == b"old description"
            assert image.read_bytes() == SOURCE
            assert len(requests) == 1
            assert not Path(str(image) + ".desc.json").exists()
            assert not list(tmp_path.glob(".*.image-clarus-*.tmp"))
        finally:
            release.touch()
            stop_process(process)
