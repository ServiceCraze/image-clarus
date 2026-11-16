"""Supplemental process-death, overlapping publication, and OS-fault evidence."""

import multiprocessing as mp
import os
import signal
import stat
from pathlib import Path

import pytest

from image_clarus.artifacts import ArtifactError, ArtifactService

OLD = b"valid:old"
STALE = b"valid:stale"
NEW = b"valid:new"
IMAGE = b"synthetic image"


def valid(data):
    return data.startswith(b"valid:")


def writer(dest, payload, point, ready, release):
    def checkpoint(name):
        if name == point:
            ready.put(os.getpid())
            if not release.wait(15):
                raise RuntimeError("publication barrier timed out")

    ArtifactService("retain", checkpoint=checkpoint).write(dest, payload, valid)


def recover(dest, result):
    try:
        result.put(("ok", ArtifactService("retain").recover(dest, valid)))
    except Exception as exc:  # noqa: BLE001 - return child errors to parent
        result.put(("error", repr(exc)))


def interrupted_recovery(dest, ready, release):
    def checkpoint(name):
        if name == "recovery_replace":
            ready.put(os.getpid())
            if not release.wait(15):
                raise RuntimeError("recovery barrier timed out")

    ArtifactService("retain", checkpoint=checkpoint).recover(dest, valid)


def stop_all(processes):
    for process in processes:
        if process.pid is not None and process.is_alive():
            process.kill()
        if process.pid is not None:
            process.join(5)
            assert not process.is_alive()


def files(directory):
    return {
        p.name: (p.read_bytes(), stat.S_IMODE(p.stat().st_mode))
        for p in directory.iterdir()
    }


def seed(tmp_path):
    image = tmp_path / "image.jpg"
    dest = tmp_path / "image.jpg.desc.txt"
    backup = tmp_path / "image.jpg.desc.txt.bak"
    image.write_bytes(IMAGE)
    image.chmod(0o600)
    dest.write_bytes(OLD)
    dest.chmod(0o640)
    backup.write_bytes(STALE)
    backup.chmod(0o600)
    return image, dest, backup


def test_two_processes_overlap_at_publication(tmp_path):
    image, dest, backup = seed(tmp_path)
    context = mp.get_context("spawn")
    ready = context.Queue()
    release = context.Event()
    payloads = [b"valid:" + ch * 200_000 for ch in (b"A", b"B")]
    processes = [
        context.Process(
            target=writer, args=(dest, p, "destination_replace", ready, release)
        )
        for p in payloads
    ]
    try:
        for process in processes:
            process.start()
        arrivals = {ready.get(timeout=15) for _ in processes}
        assert arrivals == {p.pid for p in processes}
        assert dest.read_bytes() == OLD
        assert backup.read_bytes() == OLD
        staged = list(tmp_path.glob(f".{dest.name}.image-clarus-*.tmp"))
        assert {p.read_bytes() for p in staged} == set(payloads)
        release.set()
        for process in processes:
            process.join(15)
            assert process.exitcode == 0
        assert dest.read_bytes() in payloads
        assert stat.S_IMODE(dest.stat().st_mode) == 0o640
        assert backup.read_bytes() == OLD
        assert image.read_bytes() == IMAGE
        assert set(files(tmp_path)) == {image.name, dest.name, backup.name}
    finally:
        stop_all(processes)
        ready.close()
        ready.join_thread()


@pytest.mark.parametrize(
    "point", ["output_read", "backup_verify", "destination_replace", "destination_read"]
)
def test_sigkill_then_restart_recovery_ignores_orphan_temps(tmp_path, point):
    image, dest, backup = seed(tmp_path)
    context = mp.get_context("spawn")
    ready = context.Queue()
    release = context.Event()
    process = context.Process(target=writer, args=(dest, NEW, point, ready, release))
    processes = [process]
    try:
        process.start()
        assert ready.get(timeout=15) == process.pid
        assert process.pid is not None
        os.kill(process.pid, signal.SIGKILL)
        process.join(15)
        assert process.exitcode == -signal.SIGKILL
        snapshot = files(tmp_path)
        temp_names = set(snapshot) - {image.name, dest.name, backup.name}
        expected_temp_count = {
            "output_read": 1,
            "backup_verify": 2,
            "destination_replace": 1,
            "destination_read": 0,
        }[point]
        assert len(temp_names) == expected_temp_count
        for name in temp_names:
            assert name.endswith(".tmp")
            if name.startswith(f".{backup.name}.image-clarus-"):
                assert point == "backup_verify"
                assert snapshot[name] == (OLD, 0o640)
            else:
                assert name.startswith(f".{dest.name}.image-clarus-")
                assert snapshot[name] == (NEW, 0o640)
        assert snapshot[image.name] == (IMAGE, 0o600)
        assert snapshot[dest.name] == (
            NEW if point == "destination_read" else OLD,
            0o640,
        )
        assert snapshot[backup.name] == (
            (STALE, 0o600)
            if point in ("output_read", "backup_verify")
            else (OLD, 0o640)
        )

        result = context.Queue()
        restart = context.Process(target=recover, args=(dest, result))
        processes.append(restart)
        restart.start()
        assert result.get(timeout=15) == ("ok", True)
        restart.join(15)
        assert restart.exitcode == 0
        assert files(tmp_path) == snapshot
        result.close()
        result.join_thread()
    finally:
        stop_all(processes)
        ready.close()
        ready.join_thread()


def test_sigkill_during_restore_then_restart_restores_backup_not_temp(tmp_path):
    image, dest, backup = seed(tmp_path)
    dest.unlink()
    context = mp.get_context("spawn")
    ready = context.Queue()
    release = context.Event()
    process = context.Process(target=interrupted_recovery, args=(dest, ready, release))
    processes = [process]
    try:
        process.start()
        assert ready.get(timeout=15) == process.pid
        assert process.pid is not None
        os.kill(process.pid, signal.SIGKILL)
        process.join(15)
        assert process.exitcode == -signal.SIGKILL
        snapshot = files(tmp_path)
        temp_names = set(snapshot) - {image.name, backup.name}
        assert len(temp_names) == 1
        orphan = next(iter(temp_names))
        assert orphan.startswith(f".{dest.name}.image-clarus-")
        assert snapshot[orphan] == (STALE, 0o600)
        assert snapshot[backup.name] == (STALE, 0o600)
        # Distinguish the orphan: recovery must use the backup instead.
        (tmp_path / orphan).write_bytes(b"valid:orphan")
        result = context.Queue()
        restart = context.Process(target=recover, args=(dest, result))
        processes.append(restart)
        restart.start()
        assert result.get(timeout=15) == ("ok", True)
        restart.join(15)
        assert restart.exitcode == 0
        assert files(tmp_path) == {
            image.name: (IMAGE, 0o600),
            dest.name: (STALE, 0o600),
            backup.name: (STALE, 0o600),
            orphan: (b"valid:orphan", 0o600),
        }
        result.close()
        result.join_thread()
    finally:
        stop_all(processes)
        ready.close()
        ready.join_thread()


@pytest.mark.parametrize(
    "operation",
    ["backup_replace", "destination_replace", "backup_unlink", "backup_fchmod"],
)
def test_actual_filesystem_faults_preserve_exact_state(
    tmp_path, monkeypatch, operation
):
    image, dest, backup = seed(tmp_path)
    real_replace = os.replace
    real_unlink = Path.unlink
    real_fchmod = os.fchmod
    chmod_calls = 0
    hit = []

    def replace(src, target):
        if (operation == "backup_replace" and Path(target) == backup) or (
            operation == "destination_replace" and Path(target) == dest
        ):
            hit.append(operation)
            raise OSError("synthetic secret")
        return real_replace(src, target)

    def unlink(path, *args, **kwargs):
        if operation == "backup_unlink" and path == backup:
            hit.append(operation)
            raise OSError("synthetic secret")
        return real_unlink(path, *args, **kwargs)

    def fchmod(fd, mode):
        nonlocal chmod_calls
        chmod_calls += 1
        if operation == "backup_fchmod" and chmod_calls == 2:
            hit.append(operation)
            raise OSError("synthetic secret")
        return real_fchmod(fd, mode)

    monkeypatch.setattr(os, "replace", replace)
    monkeypatch.setattr(Path, "unlink", unlink)
    monkeypatch.setattr(os, "fchmod", fchmod)
    with pytest.raises(ArtifactError) as error:
        ArtifactService().write(dest, NEW, valid)
    assert hit == [operation]
    assert error.value.category == "file_io"
    assert "synthetic secret" not in str(error.value)
    snapshot = files(tmp_path)
    assert set(snapshot) == {image.name, dest.name, backup.name}
    assert snapshot[image.name][0] == IMAGE
    assert snapshot[dest.name] == (NEW if operation == "backup_unlink" else OLD, 0o640)
    assert snapshot[backup.name] == (
        (OLD, 0o640)
        if operation in ("destination_replace", "backup_unlink")
        else (STALE, 0o600)
    )
