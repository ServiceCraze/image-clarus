"""Independent initializers observe, but never repair, another creator's work."""

import multiprocessing
import os
import sqlite3
import time
from pathlib import Path

import pytest

from image_clarus.state import storage


# Only the creator is patched. Events hold it at real filesystem/SQLite boundaries;
# the observer still executes the complete production initialize path.
def _creator(directory, checkpoint, ready, release, reports):
    directory = Path(directory)
    if checkpoint == "before_file":
        real_open = os.open

        def held_open(path, flags, *args, **kwargs):
            if Path(path) == directory / storage.DATABASE_NAME:
                ready.set()
                if not release.poll(5):
                    raise RuntimeError("creator barrier timed out")
                release.recv()
            return real_open(path, flags, *args, **kwargs)

        storage.os.open = held_open
    else:

        class HeldConnection(sqlite3.Connection):
            def execute(self, sql, parameters=()):
                if sql == "BEGIN IMMEDIATE":
                    ready.set()
                    if not release.poll(5):
                        raise RuntimeError("creator barrier timed out")
                    release.recv()
                return super().execute(sql, parameters)

        def held_connect(path, deadline):
            conn = sqlite3.connect(
                path.resolve().as_uri() + "?mode=rw",
                uri=True,
                timeout=0,
                isolation_level=None,
                factory=HeldConnection,
            )
            storage._busy(conn, deadline)
            return conn

        storage._connect = held_connect
    try:
        storage.initialize(directory)
        reports.put(("creator", "ok"))
    except (storage.StateError, OSError, sqlite3.Error, RuntimeError) as exc:
        reports.put(("creator", type(exc).__name__, str(exc)))


def _observer(directory, attempted, reports, launch=None, launched=None):
    if launch is not None:
        assert launched is not None
        launched.set()
        if not launch.wait(5):
            raise RuntimeError("observer launch timed out")
    real_connect = storage._connect
    real_validate = storage._validate

    def observed_connect(path, deadline):
        try:
            return real_connect(path, deadline)
        except (storage.StateError, sqlite3.Error, OSError):
            attempted.set()
            raise

    def observed_validate(conn):
        try:
            return real_validate(conn)
        except (storage.StateError, sqlite3.Error, OSError):
            attempted.set()
            raise

    storage._connect = observed_connect
    storage._validate = observed_validate
    started = time.monotonic()
    try:
        storage.initialize(Path(directory))
        reports.put(("observer", "ok", time.monotonic() - started))
    except (storage.StateError, sqlite3.Error, OSError, RuntimeError) as exc:
        reports.put(
            ("observer", type(exc).__name__, time.monotonic() - started, str(exc))
        )


def _snapshot(directory):
    return {p.name: (p.stat().st_mode, p.read_bytes()) for p in directory.iterdir()}


def _cleanup(children, release, reports):
    if release is not None:
        release.close()
    for child in children:
        if child.pid is not None:
            if child.is_alive():
                child.terminate()
            child.join(5)
            if child.is_alive():
                child.kill()
                child.join(5)
    reports.close()
    reports.join_thread()


def _start_creator(ctx, directory, checkpoint, reports):
    ready = ctx.Event()
    receive, release = ctx.Pipe(duplex=False)
    creator = ctx.Process(
        target=_creator, args=(str(directory), checkpoint, ready, receive, reports)
    )
    creator.start()
    receive.close()
    return creator, ready, release


@pytest.mark.parametrize("checkpoint", ["before_file", "before_begin"])
def test_observer_recognizes_concurrently_committed_repository(tmp_path, checkpoint):
    directory = tmp_path / "state"
    ctx = multiprocessing.get_context("spawn")
    reports = ctx.Queue()
    attempted, launch, launched = ctx.Event(), ctx.Event(), ctx.Event()
    observer = ctx.Process(
        target=_observer, args=(str(directory), attempted, reports, launch, launched)
    )
    observer.start()
    children = [observer]
    release = None
    try:
        assert launched.wait(5), "observer did not start"
        creator, ready, release = _start_creator(ctx, directory, checkpoint, reports)
        children.append(creator)
        assert ready.wait(5), "creator did not reach checkpoint"
        assert directory.is_dir()
        assert (directory / storage.DATABASE_NAME).exists() == (
            checkpoint == "before_begin"
        )
        launch.set()
        assert attempted.wait(5), "observer never attempted recognition"
        assert creator.is_alive() and observer.is_alive()
        release.send(True)
        messages = [reports.get(timeout=5) for _ in range(2)]
        for child in children:
            child.join(5)
            assert child.exitcode == 0
        assert ("creator", "ok") in messages
        assert any(m[:2] == ("observer", "ok") for m in messages), messages
        store = storage.SQLiteStorage(directory)
        assert store.snapshot_categories() == []
        store.close()
    finally:
        _cleanup(children, release, reports)


@pytest.mark.parametrize("checkpoint", ["before_file", "before_begin"])
@pytest.mark.parametrize("creator_crashes", [False, True], ids=["held", "crashed"])
def test_unfinished_creator_times_out_without_modifying_residue(
    tmp_path, checkpoint, creator_crashes
):
    directory = tmp_path / "state"
    ctx = multiprocessing.get_context("spawn")
    reports = ctx.Queue()
    creator, ready, release = _start_creator(ctx, directory, checkpoint, reports)
    children = [creator]
    try:
        assert ready.wait(5), "creator did not reach checkpoint"
        assert directory.is_dir()
        before = _snapshot(directory)
        assert set(before) == (
            {storage.DATABASE_NAME} if checkpoint == "before_begin" else set()
        )
        if creator_crashes:
            creator.kill()
            creator.join(5)
            assert creator.exitcode is not None and creator.exitcode != 0
        attempted = ctx.Event()
        observer = ctx.Process(
            target=_observer, args=(str(directory), attempted, reports)
        )
        children.append(observer)
        observer.start()
        assert attempted.wait(5), "observer never attempted recognition"
        result = reports.get(timeout=5)
        observer.join(5)
        assert observer.exitcode == 0
        assert result[:2] == ("observer", "StateError"), result
        assert 0.15 <= result[2] < 1.5, result
        assert _snapshot(directory) == before
        if not creator_crashes:
            assert creator.is_alive()
    finally:
        _cleanup(children, release, reports)
