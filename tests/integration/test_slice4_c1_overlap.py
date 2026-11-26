"""Real CLI overlap probes against a controlled loopback provider.

Provider activity is measured at the HTTP boundary, not as a proxy for the
entire lifetime of a stage actor. Fixtures and responses are fictional.
"""

import base64
import json
import os
import subprocess
import sys
import threading
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from test_single_image_pipeline import METADATA, png

ROOT = Path(__file__).resolve().parents[2]


def run_case(tmp_path, mode, bypass=False):
    images = tmp_path / mode
    images.mkdir()
    # Distinguishable valid PNGs; trailing bytes do not change image decoding.
    paths = [images / "a.png", images / "b.png"]
    for i, path in enumerate(paths):
        path.write_bytes(png() + bytes([i]))
    if bypass:
        Path(str(paths[1]) + ".desc.txt").write_text("fictional-b")
    arrived = threading.Event()
    downstream = threading.Event()
    release = threading.Event()
    lock = threading.Lock()
    active = Counter()
    peak = Counter()
    events = []
    errors = []
    held = "a" if bypass else "b"

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            stage = "?"
            try:
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                stage = "json" if "response_format" in body else "desc"
                content = body["messages"][1]["content"][0]
                if stage == "desc":
                    raw = base64.b64decode(content["image_url"]["url"].split(",", 1)[1])
                    image = "ab"[raw[-1]]
                else:
                    image = json.loads(content["text"])["description"].split("-")[-1]
                with lock:
                    active[stage] += 1
                    peak[stage] = max(peak[stage], active[stage])
                    events.append(("enter", stage, image, dict(active)))
                if mode == "concurrent" and stage == "desc" and image == held:
                    arrived.set()
                    if not release.wait(12):
                        raise TimeoutError("held inference not released")
                if stage == "json" and image == ("b" if bypass else "a"):
                    if mode == "concurrent" and not bypass and not arrived.wait(8):
                        raise TimeoutError("upstream request never entered")
                    if arrived.is_set() and not release.is_set():
                        downstream.set()
                response = (
                    json.dumps(METADATA) if stage == "json" else "fictional-" + image
                )
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
            except (OSError, ValueError, KeyError, TimeoutError, IndexError) as exc:
                errors.append(repr(exc))
            finally:
                with lock:
                    if active[stage]:
                        active[stage] -= 1
                        events.append(
                            ("exit", stage, locals().get("image", "?"), dict(active))
                        )

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
    env = os.environ.copy()
    env.update(
        HOME=str(images), PYTHONPATH=str(ROOT / "src"), NO_PROXY="*", no_proxy="*"
    )
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
            "desc,json",
            "--inter-stage-concurrency"
            if mode == "concurrent"
            else "--no-inter-stage-concurrency",
        ],
        cwd=images,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    observed = False
    try:
        if mode == "concurrent":
            assert arrived.wait(10), "held upstream inference never entered"
            observed = downstream.wait(6)
        release.set()
        stdout, stderr = process.communicate(timeout=25)
        assert process.returncode == 0, (stdout, stderr, events, errors)
        assert not errors, errors
        assert peak == {"desc": 1, "json": 1}, (peak, events)
        for image in "ab":
            entries = [
                (kind, stage) for kind, stage, name, _ in events if name == image
            ]
            expected = (
                [("enter", "json"), ("exit", "json")]
                if bypass and image == "b"
                else [
                    ("enter", "desc"),
                    ("exit", "desc"),
                    ("enter", "json"),
                    ("exit", "json"),
                ]
            )
            assert entries == expected, (image, entries, events)
            assert Path(str(paths["ab".index(image)]) + ".desc.json").is_file()
        return observed, events
    finally:
        release.set()
        if process.poll() is None:
            process.kill()
        process.communicate(timeout=10)
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        assert not thread.is_alive()


def test_real_cli_stages_overlap_and_sequential_is_image_first(tmp_path):
    observed, concurrent = run_case(tmp_path, "concurrent")
    assert observed, concurrent
    _, sequential = run_case(tmp_path, "sequential")
    assert [(kind, stage, image) for kind, stage, image, _ in sequential] == [
        ("enter", "desc", "a"),
        ("exit", "desc", "a"),
        ("enter", "json", "a"),
        ("exit", "json", "a"),
        ("enter", "desc", "b"),
        ("exit", "desc", "b"),
        ("enter", "json", "b"),
        ("exit", "json", "b"),
    ]


def test_bypass_candidate_reaches_json_while_upstream_inference_is_held(tmp_path):
    observed, events = run_case(tmp_path, "concurrent", bypass=True)
    assert observed, events
