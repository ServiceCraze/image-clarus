"""Independent CLI processes with test-only transaction/scan barriers.

The child executes the real module; instrumentation pauses after a real SQL write
or a completed union. No provider or external service is involved.
"""

import json
import os
import signal
import sqlite3
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path

import pytest

from image_clarus.state.storage import DATABASE_NAME, SQLiteStorage, initialize

ROOT = Path(__file__).resolve().parents[2]
CHILD = r"""
import os, runpy, sys, time
from pathlib import Path
from image_clarus.state import storage, rebuild
marker, release, kind = map(str, sys.argv[1:4])
sys.argv = ["image-clarus", "state", "categories", *sys.argv[4:]]
def barrier():
    Path(marker).write_text("ready")
    deadline = time.monotonic() + 12
    while not Path(release).exists():
        if time.monotonic() >= deadline:
            raise RuntimeError("test barrier timed out")
        time.sleep(.005)
if kind == "union":
    original = rebuild.union_categories
    def union(*args, **kwargs):
        result = original(*args, **kwargs)
        if not Path(marker).exists():
            barrier()
        return result
    rebuild.union_categories = union
elif kind == "write":
    original = storage._connect
    class Connection:
        def __init__(self, conn): self.conn = conn
        def __getattr__(self, name): return getattr(self.conn, name)
        def execute(self, sql, *args):
            result = self.conn.execute(sql, *args)
            if sql.startswith(("INSERT OR IGNORE INTO known_categories", "DELETE FROM known_categories")) and not Path(marker).exists():
                barrier()
            return result
    storage._connect = lambda *args, **kwargs: Connection(original(*args, **kwargs))
runpy.run_module("image_clarus", run_name="__main__")
"""


def sidecar(path, category):
    path.write_text(
        json.dumps(
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
        )
    )


def launch(cwd, *args, kind="none", name="child"):
    marker = cwd / (name + ".ready")
    release = cwd / (name + ".release")
    env = dict(os.environ, PYTHONPATH=str(ROOT / "src"))
    proc = subprocess.Popen(
        [sys.executable, "-c", CHILD, str(marker), str(release), kind, *map(str, args)],
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return proc, marker, release


def wait_ready(proc, marker):
    deadline = time.monotonic() + 10
    while not marker.exists():
        if proc.poll() is not None:
            out, err = proc.communicate()
            pytest.fail(
                f"child exited before barrier: {proc.returncode} {out!r} {err!r}"
            )
        if time.monotonic() >= deadline:
            pytest.fail("child failed to reach barrier")
        time.sleep(0.005)


def finish(proc):
    out, err = proc.communicate(timeout=15)
    return proc.returncode, out, err


@contextmanager
def children():
    processes = []
    try:
        yield processes
    finally:
        for proc in processes:
            if proc.poll() is None:
                proc.kill()
            proc.communicate(timeout=5)


def run(cwd, processes, *args, **kwargs):
    proc, marker, release = launch(cwd, *args, **kwargs)
    processes.append(proc)
    return proc, marker, release


def successful(result):
    code, out, err = result
    assert code == 0, (code, out, err)
    assert not err, err
    return out


@pytest.fixture
def store(tmp_path):
    directory = tmp_path / ".image-clarus"
    initialize(directory)
    return directory


def test_rebuilds_overlap_between_transactions_without_lost_unions(tmp_path, store):
    source = tmp_path / "source"
    source.mkdir()
    sidecar(source / "a.desc.json", "Alpha")
    sidecar(source / "b.desc.json", "Beta")
    other = tmp_path / "other.desc.json"
    sidecar(other, "Gamma")
    with children() as procs:
        first, ready, release = run(
            tmp_path, procs, "rebuild", source, kind="union", name="first"
        )
        wait_ready(first, ready)
        second, _, _ = run(tmp_path, procs, "rebuild", other, name="second")
        out2 = successful(finish(second))
        assert "confirmed_inserted=1" in out2
        assert first.poll() is None
        release.touch()
        out1 = successful(finish(first))
    assert "success=2" in out1 and "confirmed_inserted=2" in out1
    assert SQLiteStorage(store).snapshot_categories() == ["Alpha", "Beta", "Gamma"]


@pytest.mark.parametrize("clear_after_first", [True, False])
def test_clear_rebuild_transaction_order(tmp_path, store, clear_after_first):
    SQLiteStorage(store).add_categories(["Old"])
    source = tmp_path / "source"
    source.mkdir()
    sidecar(source / "a.desc.json", "Alpha")
    sidecar(source / "b.desc.json", "Beta")
    with children() as procs:
        if clear_after_first:
            first, ready, release = run(
                tmp_path, procs, "rebuild", source, kind="union", name="first"
            )
            wait_ready(first, ready)
            clear, _, _ = run(tmp_path, procs, "clear", name="clear")
            assert "deleted=2" in successful(finish(clear))
            release.touch()
            out = successful(finish(first))
            assert "success=2" in out and "confirmed_inserted=2" in out
            expected = ["Beta"]
        else:
            clear, ready, release = run(
                tmp_path, procs, "clear", kind="write", name="clear"
            )
            wait_ready(clear, ready)
            # A separate list sees the old committed snapshot while clear is uncommitted.
            listing, _, _ = run(tmp_path, procs, "list", name="list")
            assert successful(finish(listing)) == '"Old"\n'
            release.touch()
            assert "deleted=1" in successful(finish(clear))
            rebuilt, _, _ = run(tmp_path, procs, "rebuild", source, name="rebuild")
            assert "confirmed_inserted=2" in successful(finish(rebuilt))
            expected = ["Alpha", "Beta"]
    assert SQLiteStorage(store).snapshot_categories() == expected


def test_list_during_uncommitted_rebuild_observes_old_snapshot(tmp_path, store):
    SQLiteStorage(store).add_categories(["Old"])
    source = tmp_path / "one.desc.json"
    sidecar(source, "New")
    with children() as procs:
        writer, ready, release = run(
            tmp_path, procs, "rebuild", source, kind="write", name="writer"
        )
        wait_ready(writer, ready)
        listing, _, _ = run(tmp_path, procs, "list", name="list")
        assert successful(finish(listing)) == '"Old"\n'
        assert writer.poll() is None
        release.touch()
        assert "confirmed_inserted=1" in successful(finish(writer))
    assert SQLiteStorage(store).snapshot_categories() == ["New", "Old"]


@pytest.mark.skipif(os.name == "nt", reason="POSIX SIGTERM handling")
def test_signal_before_commit_rolls_back_current_union(tmp_path, store):
    source = tmp_path / "source"
    source.mkdir()
    sidecar(source / "a.desc.json", "Alpha")
    sidecar(source / "b.desc.json", "Beta")
    with children() as procs:
        writer, ready, release = run(
            tmp_path, procs, "rebuild", source, kind="write", name="writer"
        )
        wait_ready(writer, ready)
        writer.send_signal(signal.SIGTERM)
        # Keep the child at the barrier while the handler receives SIGTERM.
        time.sleep(0.1)
        release.touch()
        code, out, err = finish(writer)
        assert code == 128 + signal.SIGTERM, (code, out, err)
        assert "interrupted=1" in out and "not_attempted=1" in out
        assert "confirmed_committed=0" in out and "confirmed_inserted=0" in out
    assert SQLiteStorage(store).snapshot_categories() == []


def test_contended_rebuild_fails_without_claiming_commit(tmp_path, store):
    source = tmp_path / "one.desc.json"
    sidecar(source, "New")
    with sqlite3.connect(store / DATABASE_NAME, timeout=1) as lock:
        lock.execute("BEGIN IMMEDIATE")
        with children() as procs:
            proc, _, _ = run(tmp_path, procs, "rebuild", source)
            code, out, err = finish(proc)
            assert code == 1, (code, out, err)
            assert "storage_failure=1" in out
            assert "confirmed_committed=0" in out and "confirmed_inserted=0" in out
            assert err
        lock.rollback()
    assert SQLiteStorage(store).snapshot_categories() == []
