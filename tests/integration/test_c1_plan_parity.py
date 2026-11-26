"""Compare CLI dry-run rows with the execution plan at runner entry."""

import json
import os
import re
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("concurrency", ["false", "true"])
def test_multiroot_initial_plan_parity(tmp_path, concurrency):
    calls = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            calls.append(self.rfile.read(int(self.headers["Content-Length"])))
            body = json.dumps(
                {
                    "choices": [
                        {
                            "index": 0,
                            "finish_reason": "stop",
                            "message": {
                                "role": "assistant",
                                "content": "Fictional description.",
                            },
                        }
                    ]
                }
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        first, second = tmp_path / "first", tmp_path / "second"
        first.mkdir()
        second.mkdir()
        for root, names in ((first, ("a.jpg", "b.jpg")), (second, ("c.jpg", "d.jpg"))):
            for name in names:
                (root / name).write_bytes(b"synthetic image bytes")
        (first / "a.jpg.desc.txt").write_text("already present")
        config = tmp_path / "config.yaml"
        config.write_text(
            f"providers:\n  sample:\n    base_url: http://127.0.0.1:{server.server_port}/v1\n"
            "models:\n  sample:\n    provider: sample\n    model_id: fictional\n"
            "stages:\n  desc:\n    model: sample\n"
        )
        home = tmp_path / "home"
        home.mkdir()
        hook = tmp_path / "hook"
        hook.mkdir()
        # Opt-in child instrumentation snapshots immutable row values before the
        # real runner can consume/mutate its queues; it never changes the plan.
        (hook / "sitecustomize.py").write_text(
            "import json, os\n"
            "if os.environ.get('C1_PLAN_CAPTURE'):\n"
            "    import image_clarus.batch_execution as execution\n"
            "    def wrap(original):\n"
            "        def capture(plan, *args, **kwargs):\n"
            "            rows = [(row[0], row[4].value) for row in plan.rows]\n"
            "            with open(os.environ['C1_PLAN_CAPTURE'], 'x', encoding='utf-8') as f:\n"
            "                json.dump(rows, f)\n"
            "            return original(plan, *args, **kwargs)\n"
            "        return capture\n"
            "    execution.run_sequential = wrap(execution.run_sequential)\n"
            "    execution.run_concurrent = wrap(execution.run_concurrent)\n"
        )
        env = os.environ.copy()
        env.update(
            HOME=str(home),
            PYTHONPATH=os.pathsep.join((str(hook), str(ROOT / "src"))),
            NO_PROXY="*",
            no_proxy="*",
        )
        command = [
            sys.executable,
            "-m",
            "image_clarus",
            "process",
            str(first),
            str(second),
            "--config",
            str(config),
            "--stages",
            "desc",
            "--max-work-files",
            "2",
            "--set",
            f"pipeline.inter_stage_concurrency={concurrency}",
        ]
        dry = subprocess.run(
            [*command, "--dry-run"],
            check=False,
            cwd=tmp_path,
            env=env,
            capture_output=True,
            text=True,
            timeout=20,
        )
        assert dry.returncode == 0, (dry.stdout, dry.stderr)
        lines = [
            line
            for line in dry.stdout.splitlines()
            if line.startswith("plan provisional ")
        ]
        planned = []
        for line in lines:
            match = re.match(
                r'plan provisional image=("(?:[^"\\]|\\.)*") class=(\w+)', line
            )
            assert match, line
            planned.append([json.loads(match.group(1)), match.group(2)])
        expected = [
            [str(first / "a.jpg"), "NO_LLM_WORK"],
            [str(first / "b.jpg"), "ADMITTED"],
            [str(second / "c.jpg"), "ADMITTED"],
            [str(second / "d.jpg"), "KNOWN_EXCLUDED"],
        ]
        assert planned == expected
        assert "admission=1 budget=not_reached" in lines[1]
        assert "admission=2 budget=reached" in lines[2]
        assert calls == []
        capture = tmp_path / "initial-plan.json"
        env["C1_PLAN_CAPTURE"] = str(capture)
        actual = subprocess.run(
            command,
            check=False,
            cwd=tmp_path,
            env=env,
            capture_output=True,
            text=True,
            timeout=20,
        )
        assert actual.returncode == 0, (actual.stdout, actual.stderr)
        assert json.loads(capture.read_text()) == planned
        assert "summary images=4 admitted=2 no_work=1 excluded=1" in actual.stdout
        assert len(calls) == 2
        assert (first / "a.jpg.desc.txt").read_text() == "already present"
        assert (first / "b.jpg.desc.txt").exists()
        assert (second / "c.jpg.desc.txt").exists()
        assert not (second / "d.jpg.desc.txt").exists()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
