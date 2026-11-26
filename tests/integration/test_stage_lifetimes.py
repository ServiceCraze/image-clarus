"""CLI stage-call lifetime probe, using real stages and a loopback provider."""

import base64
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from test_single_image_pipeline import METADATA, png

ROOT = Path(__file__).resolve().parents[2]

# Loaded only by the disposable CLI interpreter. Wrap the actual stage driver,
# including inspection, validation, and publication. A provider await parks
# the outer call while the same actor may synchronously inspect another image.
SITE = """
import json, os, threading, time
from pathlib import Path
import image_clarus.batch_execution as batch
original = batch._run_stage
lock = threading.Lock()
log = Path(os.environ["LIFETIME_LOG"])
release = Path(os.environ["LIFETIME_RELEASE"])
def event(kind, stage, image):
    with lock:
        with log.open("a") as f:
            f.write(json.dumps([kind, stage, image, threading.get_ident(), threading.current_thread().name]) + "\\n")
def wrapped(**kwargs):
    stage = kwargs["stage"].name
    image = Path(kwargs["row"][0]).stem
    event("enter", stage, image)
    await_provider = kwargs.get("await_provider")
    if await_provider is not None:
        def await_wrapped(pending):
            event("park", stage, image)
            try:
                return await_provider(pending)
            finally:
                event("resume", stage, image)
        kwargs["await_provider"] = await_wrapped
    try:
        if stage == "desc" and image == "b" and not kwargs.get("defer_transformation"):
            deadline = time.monotonic() + 15
            while not release.exists():
                if time.monotonic() > deadline:
                    raise RuntimeError("stage barrier timed out")
                time.sleep(.01)
        return original(**kwargs)
    finally:
        event("exit", stage, image)
batch._run_stage = wrapped
"""


@pytest.mark.parametrize("include_xmp", [False, True])
def test_cli_full_stage_lifetimes(tmp_path, include_xmp):
    if include_xmp and not shutil.which("exiftool"):
        pytest.skip("real ExifTool unavailable")
    images = tmp_path / "images"
    images.mkdir()
    paths = [images / f"{name}.png" for name in "ab"]
    for i, path in enumerate(paths):
        path.write_bytes(png() + bytes([i]))
    errors = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            try:
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                stage = "json" if "response_format" in body else "desc"
                content = body["messages"][1]["content"][0]
                if stage == "desc":
                    raw = base64.b64decode(content["image_url"]["url"].split(",", 1)[1])
                    image = "ab"[raw[-1]]
                    response = "fictional-" + image
                else:
                    response = json.dumps(METADATA)
                payload = json.dumps(
                    {
                        "choices": [
                            {
                                "index": 0,
                                "finish_reason": "stop",
                                "message": {"role": "assistant", "content": response},
                            }
                        ]
                    }
                ).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
            except (OSError, ValueError, KeyError, IndexError) as exc:
                errors.append(repr(exc))

        def log_message(self, format, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    config = images / "config.yaml"
    config.write_text(
        f"providers:\n  local:\n    base_url: http://127.0.0.1:{server.server_port}/v1\nmodels:\n  vision:\n    provider: local\n    model_id: fictional-vision\n  text:\n    provider: local\n    model_id: fictional-text\nstages:\n  desc:\n    model: vision\n  json:\n    model: text\n"
    )
    hook = tmp_path / "hook"
    hook.mkdir()
    (hook / "sitecustomize.py").write_text(SITE)
    log, release = tmp_path / "events", tmp_path / "release"
    env = os.environ.copy()
    env.update(
        HOME=str(images),
        PYTHONPATH=os.pathsep.join([str(hook), str(ROOT / "src")]),
        NO_PROXY="*",
        no_proxy="*",
        LIFETIME_LOG=str(log),
        LIFETIME_RELEASE=str(release),
    )
    stages = ["desc", "json"] + (["xmp"] if include_xmp else [])
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "image_clarus",
            "process",
            *map(str, paths),
            "--config",
            str(config),
            "--stages",
            ",".join(stages),
            "--inter-stage-concurrency",
        ],
        cwd=images,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        deadline = time.monotonic() + 12
        events = []
        triples = []
        while time.monotonic() < deadline:
            events = (
                [json.loads(line) for line in log.read_text().splitlines()]
                if log.exists()
                else []
            )
            triples = [event[:3] for event in events]
            if ["enter", "json", "a"] in triples and triples.count(
                ["enter", "desc", "b"]
            ) > triples.count(["exit", "desc", "b"]):
                break
            if process.poll() is not None:
                break
            time.sleep(0.01)
        assert ["enter", "json", "a"] in triples and triples.count(
            ["enter", "desc", "b"]
        ) > triples.count(["exit", "desc", "b"]), events
        release.touch()
        stdout, stderr = process.communicate(timeout=30)
        assert process.returncode == 0, (stdout, stderr, events, errors)
        assert not errors, errors
        events = [json.loads(line) for line in log.read_text().splitlines()]
        active_stage, active_image, peak = Counter(), Counter(), Counter()
        actors = {stage: set() for stage in stages}
        image_order = {image: [] for image in "ab"}
        overlap = False
        for kind, stage, image, ident, name in events:
            actors[stage].add((ident, name))
            if kind in ("enter", "resume"):
                active_stage[stage] += 1
                if kind == "enter":
                    active_image[image] += 1
                    if stage not in image_order[image]:
                        image_order[image].append(stage)
                peak[stage] = max(peak[stage], active_stage[stage])
                assert active_stage[stage] == 1, events
                assert active_image[image] == 1, events
                overlap |= sum(active_stage.values()) > 1
            else:
                assert active_stage[stage] == active_image[image] == 1, events
                active_stage[stage] -= 1
                if kind == "exit":
                    active_image[image] -= 1
        assert overlap and peak == {stage: 1 for stage in stages}, events
        assert not any(active_stage.values()) and not any(active_image.values())
        assert all(len(threads) == 1 for threads in actors.values()), actors
        assert len({next(iter(threads))[0] for threads in actors.values()}) == len(
            stages
        ), actors
        assert all(order == stages for order in image_order.values()), image_order
        for path in paths:
            assert Path(str(path) + ".desc.txt").is_file()
            assert Path(str(path) + ".desc.json").is_file()
            if include_xmp:
                assert Path(str(path) + ".xmp").is_file()
    finally:
        release.touch()
        if process.poll() is None:
            process.kill()
        process.communicate(timeout=10)
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        assert not thread.is_alive()
