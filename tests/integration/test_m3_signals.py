"""Real OS signals at rebuild's SQLite transaction boundaries.

The child runs the actual CLI; a trace barrier only pauses execution, without
replacing the transaction or signal handler. The post-commit barrier is after
commit returned, not inside SQLite's commit syscall.
"""

import json
import os
import selectors
import signal
import subprocess
import sys
from pathlib import Path

import pytest

from image_clarus.state.storage import SQLiteStorage, initialize

ROOT = Path(__file__).resolve().parents[2]

# Trace the actual function, at the final stop check or just after commit returns.
CHILD = r"""
import inspect, os, runpy, signal, sys
from image_clarus.state import management

function = management.union_categories
lines, start = inspect.getsourcelines(function)
commit = next(i for i, line in enumerate(lines) if line.strip() == "conn.commit()")
if sys.argv[1] == "before":
    offset = max(i for i in range(commit) if lines[i].strip() == "storage._check_stop(stop)")
else:
    offset = next(i for i in range(commit + 1, len(lines)) if lines[i].strip() == "check_target(target)")
target_line = start + offset
ready, release = int(sys.argv[2]), int(sys.argv[3])
triggered = False
def trace(frame, event, arg):
    global triggered
    if not triggered and frame.f_code is function.__code__ and event == "line" and frame.f_lineno == target_line:
        triggered = True
        for sig in (signal.SIGINT, signal.SIGTERM):
            original = signal.getsignal(sig)
            def acknowledge(signum, frame, handler=original):
                handler(signum, frame)
                os.write(ready, b"S")
            signal.signal(sig, acknowledge)
        os.write(ready, b"R")
        if os.read(release, 1) != b"G":
            raise RuntimeError("barrier closed")
    return trace
sys.settrace(trace)
sys.argv = ["image_clarus", "state", "categories", "rebuild", sys.argv[4]]
runpy.run_module("image_clarus", run_name="__main__")
"""


def _sidecar(path, category):
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
            "metadata": {"tag_candidates": [[category]]},
        }
    ).encode()
    path.write_bytes(data)
    return data


@pytest.mark.skipif(os.name != "posix", reason="POSIX signal and inherited-fd test")
@pytest.mark.parametrize("signum", [signal.SIGINT, signal.SIGTERM])
@pytest.mark.parametrize("barrier", ["before", "after"])
def test_rebuild_signal_transaction_boundary(tmp_path, signum, barrier):
    store = tmp_path / ".image-clarus"
    initialize(store)
    SQLiteStorage(store).add_categories(["Existing"])
    sources = tmp_path / "sources"
    sources.mkdir()
    originals = {
        sources / f"{i}.desc.json": _sidecar(sources / f"{i}.desc.json", value)
        for i, value in enumerate(("First", "Second", "Third"))
    }
    ready_r, ready_w = os.pipe()
    release_r, release_w = os.pipe()
    child = None
    try:
        child = subprocess.Popen(
            [
                sys.executable,
                "-c",
                CHILD,
                barrier,
                str(ready_w),
                str(release_r),
                str(sources),
            ],
            cwd=tmp_path,
            env={**os.environ, "PYTHONPATH": str(ROOT / "src")},
            pass_fds=(ready_w, release_r),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        os.close(ready_w)
        ready_w = None
        os.close(release_r)
        release_r = None
        with selectors.DefaultSelector() as selector:
            selector.register(ready_r, selectors.EVENT_READ)
            assert selector.select(timeout=20), (
                "child did not reach transaction barrier"
            )
            assert os.read(ready_r, 1) == b"R", (
                "child exited before transaction barrier"
            )
            os.kill(child.pid, signum)
            assert selector.select(timeout=10), "signal handler did not run"
            assert os.read(ready_r, 1) == b"S", (
                "child exited before acknowledging signal"
            )
        os.write(release_w, b"G")
        stdout, stderr = child.communicate(timeout=20)
        assert child.returncode == 128 + signum, (child.returncode, stdout, stderr)
        expected = (
            {
                "inspected": 1,
                "success": 0,
                "interrupted": 1,
                "transactions_attempted": 1,
                "confirmed_committed": 0,
                "confirmed_inserted": 0,
            }
            if barrier == "before"
            else {
                "inspected": 1,
                "success": 1,
                "interrupted": 0,
                "transactions_attempted": 1,
                "confirmed_committed": 1,
                "confirmed_inserted": 1,
            }
        )
        expected.update(
            discovered=3,
            category_bearing=1,
            eligible_paths=1,
            not_attempted=2,
            storage_failure=0,
            commit_unknown=0,
        )
        for key, value in expected.items():
            assert f"{key}={value}" in stdout.split(), (key, stdout, stderr)
        assert "confirmed_inserted_complete=true" in stdout.split()
        assert SQLiteStorage(store).snapshot_categories() == (
            ["Existing"] if barrier == "before" else ["Existing", "First"]
        )
        assert all(path.read_bytes() == data for path, data in originals.items())
    finally:
        for fd in (ready_r, ready_w, release_r, release_w):
            if fd is not None:
                os.close(fd)
        if child is not None:
            if child.poll() is None:
                child.kill()
            child.communicate(timeout=10)
            assert child.returncode is not None
