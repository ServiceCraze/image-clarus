"""Provider-boundary accounting and outstanding-request regressions."""

from __future__ import annotations

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
sys.path.insert(0, str(ROOT / "tests" / "integration"))

from test_single_image_pipeline import METADATA, V2, png

pytestmark = pytest.mark.skipif(os.name != "posix", reason="POSIX provider children")


def _rig(tmp_path, handler):
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        "providers:\n"
        "  local:\n"
        f"    base_url: http://127.0.0.1:{server.server_port}/v1\n"
        "    timeout_seconds: 20\n"
        "models:\n"
        "  v:\n"
        "    provider: local\n"
        "    model_id: synthetic\n"
        "stages:\n"
        "  desc:\n"
        "    model: v\n"
        "  json:\n"
        "    model: v\n"
    )
    env = dict(
        os.environ,
        HOME=str(tmp_path / "home"),
        PYTHONPATH=str(ROOT / "src"),
        NO_PROXY="*",
        no_proxy="*",
    )
    return server, cfg, env


def _run(cfg, env, tmp_path, *paths, extra=()):
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "image_clarus",
            "process",
            *map(str, paths),
            "--config",
            str(cfg),
            "--stages",
            "desc,json",
            "--regenerate",
            "--no-inter-stage-concurrency",
            "--verbose",
            *extra,
        ],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )


class _Upstream:
    """Answer one stage; fail the first N description requests by HTTP status."""

    def __init__(self, fail_first_desc=0, status=503):
        self.fail_first_desc = fail_first_desc
        self.status = status
        self.seen = []

    def handler(self):
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                stage = "json" if "response_format" in body else "desc"
                owner.seen.append(stage)
                failed = (
                    stage == "desc"
                    and owner.seen.count("desc") <= owner.fail_first_desc
                )
                if failed:
                    payload = b'{"error":{"message":"synthetic upstream failure"}}'
                    self.send_response(owner.status)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(payload)))
                    self.end_headers()
                    self.wfile.write(payload)
                    return
                content = json.dumps(METADATA) if stage == "json" else V2
                payload = json.dumps(
                    {
                        "choices": [
                            {
                                "index": 0,
                                "message": {"role": "assistant", "content": content},
                                "finish_reason": "stop",
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

        return Handler


def _work_line(stdout):
    return next(line for line in stdout.splitlines() if line.startswith("work "))


def test_real_provider_failure_is_counted_once(tmp_path):
    upstream = _Upstream(fail_first_desc=1)
    server, cfg, env = _rig(tmp_path, upstream.handler())
    try:
        first = tmp_path / "a.png"
        first.write_bytes(png())
        (tmp_path / "a.png.desc.txt").write_text("persisted description")
        second = tmp_path / "b.png"
        second.write_bytes(png())
        result = _run(cfg, env, tmp_path, first, second)
    finally:
        server.shutdown()
        server.server_close()

    assert result.returncode == 1, (result.stdout, result.stderr)
    assert upstream.seen == ["desc", "desc", "json"], upstream.seen
    work = _work_line(result.stdout)
    assert "requests=3 first_requests=3 retries=0" in work, work
    assert (
        "actual stage=desc evaluated=2 transformed=2 completed=1 skipped=0 failed=1"
        in (result.stdout)
    )


def test_local_adapter_rejection_counts_provider_boundary_not_http(tmp_path):
    upstream = _Upstream()
    server, cfg, env = _rig(tmp_path, upstream.handler())
    try:
        image = tmp_path / "image.xyz"
        image.write_bytes(png())
        result = _run(cfg, env, tmp_path, image)
    finally:
        server.shutdown()
        server.server_close()
    assert result.returncode == 1, (result.stdout, result.stderr)
    assert upstream.seen == []
    assert "requests=1 first_requests=1 retries=0" in _work_line(result.stdout)


@pytest.mark.parametrize("signum", [signal.SIGINT, signal.SIGTERM])
def test_held_request_is_single_consume_under_concurrent_confirmations(
    tmp_path, signum
):
    """One image-stage pair may never hold two live requests at once."""

    entered = threading.Event()
    release = threading.Event()
    seen = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            stage = "json" if "response_format" in body else "desc"
            seen.append(stage)
            if len(seen) == 1:
                entered.set()
            if len(seen) == 2:
                # A second description request for the same image would arrive
                # here while the first is still held.
                release.wait(1.0)
            content = json.dumps(METADATA) if stage == "json" else V2
            payload = json.dumps(
                {
                    "choices": [
                        {
                            "index": 0,
                            "message": {"role": "assistant", "content": content},
                            "finish_reason": "stop",
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

    server, cfg, env = _rig(tmp_path, Handler)
    images = tmp_path / "images"
    images.mkdir()
    paths = []
    for index in range(3):
        path = images / f"{index}.png"
        path.write_bytes(png())
        paths.append(path)
    (images / "0.png.desc.txt").write_text("persisted description")
    process = None
    try:
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "image_clarus",
                "process",
                str(images),
                "--config",
                str(cfg),
                "--stages",
                "desc,json",
                "--regenerate",
                "--no-inter-stage-concurrency",
                "--verbose",
            ],
            cwd=tmp_path,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        assert entered.wait(25), "no description request arrived"
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline and len(seen) < 2:
            time.sleep(0.02)
        # Exactly one live request for the first image-stage pair: a second
        # description request before the first resolves is a double request.
        assert seen.count("desc") == 1, seen
        process.send_signal(signum)
        out, err = process.communicate(timeout=30)
        assert process.returncode == 128 + signum, (out, err)
    finally:
        release.set()
        if process is not None:
            if process.poll() is None:
                process.kill()
            process.communicate(timeout=15)
        server.shutdown()
        server.server_close()
