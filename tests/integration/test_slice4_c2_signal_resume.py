"""Real CLI interruption and fresh rescan against a synthetic loopback provider."""

import json
import os
import signal
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.skipif(os.name != "posix", reason="POSIX signals")


@pytest.mark.parametrize("signum", [signal.SIGINT, signal.SIGTERM])
def test_interrupted_batch_rescans_and_reuses_completed(tmp_path, signum):
    entered = threading.Event()
    release = threading.Event()
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = self.rfile.read(int(self.headers["Content-Length"]))
            requests.append(body)
            if len(requests) == 2:
                entered.set()
                if not release.wait(40):
                    return
            response = json.dumps(
                {
                    "choices": [
                        {
                            "index": 0,
                            "message": {
                                "role": "assistant",
                                "content": "Fictional description.",
                            },
                            "finish_reason": "stop",
                        }
                    ]
                }
            ).encode()
            try:
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(response)))
                self.end_headers()
                self.wfile.write(response)
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
    paths = [images / f"{n}.jpg" for n in range(3)]
    for path in paths:
        path.write_bytes(b"fictional image")
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        f"providers:\n  local:\n    base_url: http://127.0.0.1:{server.server_port}/v1\nmodels:\n  m:\n    provider: local\n    model_id: synthetic\nstages:\n  desc:\n    model: m\n"
    )
    cmd = [
        sys.executable,
        "-m",
        "image_clarus",
        "process",
        str(images),
        "--config",
        str(cfg),
        "--stages",
        "desc",
        "--no-inter-stage-concurrency",
        "--verbose",
    ]
    env = dict(
        os.environ,
        HOME=str(tmp_path / "home"),
        PYTHONPATH=str(ROOT / "src"),
        NO_PROXY="*",
        no_proxy="*",
    )
    process = None
    try:
        process = subprocess.Popen(
            cmd,
            cwd=tmp_path,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        assert entered.wait(20), "second request did not start"
        process.send_signal(signum)
        out, err = process.communicate(timeout=15)
        assert process.returncode == 128 + signum, (out, err)
        assert not release.is_set()
        artifacts = [Path(str(path) + ".desc.txt") for path in paths]
        assert (
            artifacts[0].exists()
            and not artifacts[1].exists()
            and not artifacts[2].exists()
        ), (out, err, [p.exists() for p in artifacts])
        before = artifacts[0].read_bytes()
        assert len(requests) == 2
        release.set()
        resumed = subprocess.run(
            cmd,
            cwd=tmp_path,
            env=env,
            capture_output=True,
            text=True,
            timeout=45,
            check=False,
        )
        assert resumed.returncode == 0, (resumed.stdout, resumed.stderr)
        assert len(requests) == 4
        assert artifacts[0].read_bytes() == before
        assert all(p.read_text() == "Fictional description." for p in artifacts)
        assert all(p.read_bytes() == b"fictional image" for p in paths)
    finally:
        release.set()
        if process is not None:
            if process.poll() is None:
                process.kill()
            process.communicate(timeout=10)
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
