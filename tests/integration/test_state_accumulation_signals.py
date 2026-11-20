"""OS signals at real SQLite accumulation boundaries in independent CLI processes."""

import json
import os
import signal
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def wait_marker(path, process):
    deadline = time.monotonic() + 15
    while not path.exists() and process.poll() is None and time.monotonic() < deadline:
        time.sleep(0.01)
    assert path.exists(), (
        f"child did not reach {path.name}; returncode={process.poll()}"
    )


@pytest.mark.parametrize("signum", [signal.SIGINT, signal.SIGTERM])
@pytest.mark.parametrize(
    "checkpoint", ["before_begin", "before_commit", "after_commit"]
)
def test_signal_at_accumulation_transaction(tmp_path, signum, checkpoint):
    repo = tmp_path / "repo"
    repo.mkdir()
    init = subprocess.run(
        [sys.executable, "-m", "image_clarus", "init"],
        cwd=repo,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert init.returncode == 0, (init.stdout, init.stderr)
    state = repo / ".image-clarus"
    database = state / "state.sqlite3"
    with sqlite3.connect(database) as conn:
        conn.execute("INSERT INTO known_categories(path) VALUES (?)", ("existing",))
    image = tmp_path / "sample.jpg"
    image.write_bytes(b"synthetic image")
    artifact = tmp_path / "sample.jpg.desc.json"
    data = json.dumps(
        {
            "format_version": 1,
            "schema_id": "urn:image-clarus:metadata-schema:2.0.0",
            "schema_version": "2.0.0",
            "provenance": {
                "provider_alias": "demo",
                "model_alias": "demo",
                "model_id": "demo",
                "prompt_id": "demo",
                "description_sha256": "a" * 64,
            },
            "metadata": {"tag_candidates": [["new", "category"]]},
        }
    ).encode()
    artifact.write_bytes(data)
    config = tmp_path / "config.yaml"
    config.write_text(
        "providers:\n  local:\n    base_url: http://127.0.0.1:1234/v1\n"
        "models:\n  text:\n    provider: local\n    model_id: fictional\n"
        "stages:\n  json:\n    model: text\n"
    )
    marker = tmp_path / "entered"
    received = tmp_path / "received"
    release = tmp_path / "release"
    # The wrapper pauses immediately before BEGIN, before the last stop check
    # (via _busy), or immediately after SQLite commit returns, respectively.
    (tmp_path / "sitecustomize.py").write_text(
        f"""\
import signal
import time
from pathlib import Path
from image_clarus.state import storage
real_signal = signal.signal
def install(sig, handler):
    if callable(handler) and handler.__name__ == "request":
        def observed(signum, frame):
            handler(signum, frame)
            Path({str(received)!r}).touch()
        return real_signal(sig, observed)
    return real_signal(sig, handler)
signal.signal = install
def barrier():
    Path({str(marker)!r}).touch()
    deadline = time.monotonic() + 20
    while not Path({str(release)!r}).exists():
        if time.monotonic() > deadline:
            raise RuntimeError("barrier timeout")
        time.sleep(0.01)
class Proxy:
    def __init__(self, conn):
        self.conn = conn
        self.wrote = False
    def __getattr__(self, name):
        return getattr(self.conn, name)
    def execute(self, sql, *args):
        if sql == "BEGIN IMMEDIATE" and {checkpoint!r} == "before_begin":
            barrier()
        return self.conn.execute(sql, *args)
    def executemany(self, sql, *args):
        result = self.conn.executemany(sql, *args)
        if sql.startswith("INSERT OR IGNORE INTO known_categories"):
            self.wrote = True
        return result
    def commit(self):
        result = self.conn.commit()
        if self.wrote and {checkpoint!r} == "after_commit":
            barrier()
        return result
original_connect = storage._connect
def connect(*args, **kwargs):
    return Proxy(original_connect(*args, **kwargs))
storage._connect = connect
original_busy = storage._busy
def busy(conn, deadline):
    if isinstance(conn, Proxy) and conn.wrote and {checkpoint!r} == "before_commit":
        barrier()
    return original_busy(conn, deadline)
storage._busy = busy
"""
    )
    env = dict(
        os.environ, PYTHONPATH=os.pathsep.join([str(tmp_path), str(ROOT / "src")])
    )
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "image_clarus",
            "process",
            str(image),
            "--stages",
            "json",
            "--config",
            str(config),
            "--state-dir",
            str(state),
        ],
        cwd=tmp_path,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        wait_marker(marker, process)
        process.send_signal(signum)
        wait_marker(received, process)
        assert process.poll() is None
        release.touch()
        stdout, stderr = process.communicate(timeout=10)
        assert process.returncode == 128 + signum, (stdout, stderr)
        assert stdout == "json: skipped — reason=output_exists\n"
        assert "state error" not in stderr
        assert artifact.read_bytes() == data
        assert image.read_bytes() == b"synthetic image"
        with sqlite3.connect(database, timeout=2) as conn:
            rows = conn.execute(
                "SELECT path FROM known_categories ORDER BY path"
            ).fetchall()
        assert rows == (
            [("existing",), ("new/category",)]
            if checkpoint == "after_commit"
            else [("existing",)]
        )
    finally:
        release.touch()
        if process.poll() is None:
            process.kill()
        process.communicate(timeout=5)
