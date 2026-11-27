"""Verbose accounting through the real batch CLI and a loopback provider."""

import json
import os
import re
import subprocess
import sys
import threading
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from test_single_image_pipeline import METADATA

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("concurrency", ["false", "true"])
@pytest.mark.parametrize("failure", [False, True])
def test_verbose_execution_reconciles_outcomes(tmp_path, concurrency, failure):
    requests = []
    authorization = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            requests.append(body)
            authorization.append(self.headers.get("Authorization"))
            if failure:
                data = b'{"error":{"message":"fictional-private-provider-detail"}}'
                self.send_response(400)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return
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

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        images = tmp_path / "images"
        images.mkdir()
        for name in ("a.jpg", "b.jpg", "c.jpg"):
            (images / name).write_bytes(b"fictional image bytes")
        (images / "a.jpg.desc.txt").write_text("Fictional existing description.")
        config = tmp_path / "config.yaml"
        config.write_text(
            f"providers:\n  local:\n    api_key: fictional-private-credential\n    base_url: http://127.0.0.1:{server.server_port}/v1\n"
            "models:\n  sample: {provider: local, model_id: fictional}\n"
            "stages:\n  desc: {model: sample}\n  json: {model: sample}\n"
        )
        prompt = tmp_path / "prompt.txt"
        prompt.write_text("Describe the fictional scene.")
        home = tmp_path / "home"
        home.mkdir()
        env = os.environ.copy()
        env.update(
            HOME=str(home), PYTHONPATH=str(ROOT / "src"), NO_PROXY="*", no_proxy="*"
        )
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "image_clarus",
                "process",
                str(images),
                "--config",
                str(config),
                "--stages",
                "desc,json",
                "--verbose",
                "--desc-prompt",
                str(prompt),
                "--json-prompt",
                str(prompt),
                "--max-work-files",
                "1",
                "--set",
                f"pipeline.inter_stage_concurrency={concurrency}",
            ],
            cwd=tmp_path,
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        assert result.returncode == (1 if failure else 0), (
            result.stdout,
            result.stderr,
        )
        lines = result.stdout.splitlines()
        pattern = re.compile(
            r'^stage (start|end) image=("(?:[^"\\]|\\.)*") stage=(\w+) (.*)$'
        )
        starts = {}
        ends = {}
        progress = []
        for line in lines:
            match = pattern.match(line)
            if not match:
                continue
            kind, path, stage, details = match.groups()
            key = (Path(json.loads(path)).name, stage)
            if kind == "start":
                assert key not in starts
                assert re.fullmatch(r"elapsed=\d+\.\d{3}s", details)
                starts[key] = float(details.removeprefix("elapsed=").removesuffix("s"))
            else:
                assert key not in ends
                terminal = re.fullmatch(
                    r"status=(\w+) reason=([\w-]+) progress=(\d+)/(\d+) accounted elapsed=(\d+\.\d{3})s",
                    details,
                )
                assert terminal, line
                status, reason, done, total, elapsed = terminal.groups()
                ends[key] = (status, reason)
                progress.append((int(done), int(total)))
                if key in starts:
                    assert float(elapsed) >= starts[key]
        expected_keys = {
            (name, stage)
            for name in ("a.jpg", "b.jpg", "c.jpg")
            for stage in ("desc", "json")
        }
        assert set(ends) == expected_keys, (result.stdout, result.stderr)
        assert progress == [(i, 6) for i in range(1, 7)]
        assert re.search(
            r"^progress accounted=6/6 elapsed_seconds=\d+\.\d{3}$",
            result.stdout,
            re.MULTILINE,
        )
        assert "summary images=3 admitted=1 no_work=0 excluded=2" in lines
        for stage in ("desc", "json"):
            counts = Counter(
                status
                for (name, item_stage), (status, reason) in ends.items()
                if item_stage == stage
            )
            line = next(
                line for line in lines if line.startswith(f"actual stage={stage} ")
            )
            for status in (
                "completed",
                "skipped",
                "failed",
                "interrupted",
                "not_attempted",
            ):
                assert f"{status}={counts[status]}" in line
        assert starts.keys() == {("a.jpg", "desc"), ("a.jpg", "json")}
        assert ends == {
            ("a.jpg", "desc"): ("skipped", "output_exists"),
            ("a.jpg", "json"): ("failed", "configuration")
            if failure
            else ("completed", "-"),
            **{
                (name, stage): ("skipped", "budget_excluded")
                for name in ("b.jpg", "c.jpg")
                for stage in ("desc", "json")
            },
        }
        for stage in ("desc", "json"):
            assert f"skip stage={stage} reason=budget_excluded count=2" in lines
            assert (
                f"actual stage={stage} evaluated=1 transformed={int(stage == 'json' and not failure)} "
                in result.stdout
            )
        assert "skip stage=desc reason=output_exists count=1" in lines
        assert (
            "work llm_images=1 corrective_images=0 requests=1 first_requests=1 retries=0"
            in lines
        )
        assert len(requests) == 1 and "response_format" in requests[0]
        assert authorization == ["Bearer fictional-private-credential"]
        assert result.stderr == ""
        assert "fictional-private-provider-detail" not in result.stdout + result.stderr
        assert "fictional-private-credential" not in result.stdout + result.stderr
        assert (
            images / "a.jpg.desc.txt"
        ).read_text() == "Fictional existing description."
        assert (images / "a.jpg.desc.json").exists() is (not failure)
        for name in ("b.jpg", "c.jpg"):
            assert not (images / f"{name}.desc.txt").exists()
            assert not (images / f"{name}.desc.json").exists()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
