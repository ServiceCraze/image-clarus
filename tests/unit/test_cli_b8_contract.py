"""Black-box checks for the frozen B8 CLI grammar."""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_unknown_abbreviated_option_is_rejected(tmp_path):
    image = tmp_path / "sample.png"
    image.write_bytes(b"synthetic")
    Path(str(image) + ".desc.txt").write_text("existing")
    config = tmp_path / "config.yaml"
    config.write_text(
        "providers:\n  p:\n    base_url: http://127.0.0.1:1234/v1\n"
        "models:\n  m:\n    provider: p\n    model_id: synthetic\n"
        "stages:\n  desc:\n    model: m\n"
    )
    prompt = tmp_path / "prompt.txt"
    prompt.write_text("prompt")
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "image_clarus",
            "process",
            str(image),
            "--config",
            str(config),
            "--stages",
            "desc",
            "--desc-p",
            str(prompt),
        ],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2
    assert result.stdout == ""
    assert "unrecognized arguments" in result.stderr


def test_credential_in_completed_path_is_redacted(tmp_path):
    import json
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    secret = "sYnThEtIc_CrEdEnTiAl_8642"

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers["Content-Length"]))
            data = json.dumps(
                {
                    "choices": [
                        {
                            "index": 0,
                            "finish_reason": "stop",
                            "message": {"role": "assistant", "content": "description"},
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
        image = tmp_path / f"{secret}.png"
        image.write_bytes(b"synthetic")
        config = tmp_path / "config.yaml"
        config.write_text(
            f"providers:\n  p:\n    base_url: http://127.0.0.1:{server.server_port}/v1\n"
            "    api_key_env: IMAGE_CLARUS_B8_SYNTHETIC_KEY\n"
            "models:\n  m:\n    provider: p\n    model_id: synthetic\n"
            "stages:\n  desc:\n    model: m\n"
        )
        env = os.environ.copy()
        env["PYTHONPATH"] = str(ROOT / "src")
        env["IMAGE_CLARUS_B8_SYNTHETIC_KEY"] = secret
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "image_clarus",
                "process",
                str(image),
                "--config",
                str(config),
                "--stages",
                "desc",
            ],
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0
        assert secret not in result.stdout + result.stderr
        assert json.loads(result.stdout.split("output=", 1)[1])
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


def test_configured_logging_level_controls_console_diagnostics(tmp_path):
    image = tmp_path / "sample.png"
    image.write_bytes(b"synthetic")
    Path(str(image) + ".desc.txt").write_text("existing")
    config = tmp_path / "config.yaml"
    config.write_text(
        "providers:\n  p:\n    base_url: http://127.0.0.1:1234/v1\n"
        "models:\n  m:\n    provider: p\n    model_id: synthetic\n"
        "stages:\n  desc:\n    model: m\nlogging:\n  level: INFO\n"
    )
    (tmp_path / "sitecustomize.py").write_text(
        "import logging\n"
        "from image_clarus.stages import description\n"
        "original = description.run_description\n"
        "def stage(*args):\n"
        "    logging.getLogger('image_clarus.probe').info('synthetic diagnostic')\n"
        "    return original(*args)\n"
        "description.run_description = stage\n"
    )
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join((str(tmp_path), str(ROOT / "src")))
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "image_clarus",
            "process",
            str(image),
            "--config",
            str(config),
            "--stages",
            "desc",
        ],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert result.stdout == "desc: skipped — reason=output_exists\n"
    assert "synthetic diagnostic" in result.stderr
