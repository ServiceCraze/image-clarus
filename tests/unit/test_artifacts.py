import multiprocessing
import os
import stat

import pytest

from image_clarus.artifacts import ArtifactError, ArtifactService


def valid(data):
    return data.startswith(b"valid:")


def mode(path):
    return stat.S_IMODE(path.stat().st_mode)


def test_create_private_sidecar(tmp_path):
    image = tmp_path / "photo.jpg"
    image.write_bytes(b"image")
    dest = tmp_path / "photo.jpg.desc.txt"
    ArtifactService().write(dest, b"valid:new", valid)
    assert dest.read_bytes() == b"valid:new"
    assert mode(dest) == 0o600
    assert not (tmp_path / "photo.jpg.desc.txt.bak").exists()
    assert image.read_bytes() == b"image"


def test_replace_refreshes_backup_and_preserves_modes(tmp_path):
    dest = tmp_path / "photo.desc.json"
    backup = tmp_path / "photo.desc.json.bak"
    dest.write_bytes(b"valid:old")
    dest.chmod(0o640)
    backup.write_bytes(b"stale")

    def before_publish(point):
        if point == "destination_replace":
            assert dest.read_bytes() == b"valid:old"
            assert backup.read_bytes() == b"valid:old"
            assert mode(backup) == 0o640

    ArtifactService("retain", checkpoint=before_publish).write(
        dest, b"valid:new", valid
    )
    assert dest.read_bytes() == b"valid:new"
    assert backup.read_bytes() == b"valid:old"
    assert mode(dest) == mode(backup) == 0o640


def test_recovery_and_retention(tmp_path):
    dest = tmp_path / "x.desc.txt"
    backup = tmp_path / "x.desc.txt.bak"
    backup.write_bytes(b"valid:backup")
    backup.chmod(0o604)
    assert ArtifactService().recover(dest, valid)
    assert dest.read_bytes() == b"valid:backup"
    assert mode(dest) == 0o604
    assert not backup.exists()


def test_invalid_destination_remains_authoritative(tmp_path):
    dest = tmp_path / "x.desc.txt"
    backup = tmp_path / "x.desc.txt.bak"
    dest.write_bytes(b"invalid")
    backup.write_bytes(b"valid:backup")
    with pytest.raises(ArtifactError) as error:
        ArtifactService().recover(dest, valid, validation_category="invalid_artifact")
    assert error.value.category == "invalid_artifact"
    assert dest.read_bytes() == b"invalid"
    assert backup.read_bytes() == b"valid:backup"


def test_valid_destination_remains_authoritative_over_valid_backup(tmp_path):
    dest = tmp_path / "x.desc.txt"
    backup = tmp_path / "x.desc.txt.bak"
    dest.write_bytes(b"valid:current")
    backup.write_bytes(b"valid:older")
    assert ArtifactService("retain").recover(dest, valid)
    assert dest.read_bytes() == b"valid:current"
    assert backup.read_bytes() == b"valid:older"


@pytest.mark.parametrize(
    "point",
    [
        "output_create",
        "output_write",
        "output_mode",
        "output_fsync",
        "output_read",
        "output_validate",
        "backup_read",
        "backup_create",
        "backup_write",
        "backup_mode",
        "backup_fsync",
        "backup_verify",
        "backup_replace",
        "destination_replace",
        "destination_read",
        "destination_validate",
        "backup_remove",
    ],
)
def test_faults_preserve_recoverable_original(tmp_path, point):
    image = tmp_path / "image.jpg"
    image.write_bytes(b"image")
    dest = tmp_path / "image.jpg.desc.txt"
    backup = tmp_path / "image.jpg.desc.txt.bak"
    dest.write_bytes(b"valid:old")
    backup.write_bytes(b"prior backup")
    orphan = tmp_path / ".image.jpg.desc.txt.image-clarus-orphan.tmp"
    orphan.write_bytes(b"orphan")

    def fault(name):
        if name == point:
            raise OSError("sensitive detail")

    with pytest.raises(ArtifactError) as error:
        ArtifactService(checkpoint=fault).write(dest, b"valid:new", valid)
    assert error.value.category == "file_io"
    assert "sensitive detail" not in str(error.value)
    assert image.read_bytes() == b"image"
    assert orphan.read_bytes() == b"orphan"
    assert sorted(p.name for p in tmp_path.iterdir()) == sorted(
        [image.name, dest.name, backup.name, orphan.name]
    )
    if point in ("destination_read", "destination_validate", "backup_remove"):
        assert dest.read_bytes() == b"valid:new"
        assert backup.read_bytes() == b"valid:old"
    elif point == "destination_replace":
        assert dest.read_bytes() == b"valid:old"
        assert backup.read_bytes() == b"valid:old"
    else:
        assert dest.read_bytes() == b"valid:old"
        assert backup.read_bytes() == b"prior backup"


def test_failed_write_does_not_publish_original_that_fails_validation(
    tmp_path, monkeypatch
):
    dest = tmp_path / "image.desc.txt"
    backup = tmp_path / "image.desc.txt.bak"
    original = b"invalid-original"
    dest.write_bytes(original)
    real_replace = os.replace
    failed = False

    def fail_after_removing_destination(source, target):
        nonlocal failed
        if target == dest and not failed:
            failed = True
            dest.unlink()
            raise OSError("simulated replacement failure")
        return real_replace(source, target)

    monkeypatch.setattr(
        "image_clarus.artifacts.os.replace", fail_after_removing_destination
    )
    with pytest.raises(ArtifactError) as error:
        ArtifactService("retain").write(dest, b"valid:new", valid)

    assert error.value.category == "file_io"
    assert failed
    assert not dest.exists()
    assert backup.read_bytes() == original


def writer(dest, barrier, payload, queue):
    try:

        def at_publication(point):
            if point == "destination_replace":
                barrier.wait(timeout=10)

        ArtifactService("retain", checkpoint=at_publication).write(dest, payload, valid)
        queue.put("ok")
    except Exception as exc:  # noqa: BLE001 - report child failure to parent
        queue.put(type(exc).__name__)


def test_concurrent_processes_publish_complete_payload(tmp_path):
    dest = tmp_path / "x.desc.txt"
    payloads = [b"valid:" + bytes([65 + i]) * 200000 for i in range(2)]
    context = multiprocessing.get_context("spawn")
    barrier = context.Barrier(2)
    queue = context.Queue()
    processes = [
        context.Process(target=writer, args=(dest, barrier, p, queue)) for p in payloads
    ]
    for process in processes:
        process.start()
    for process in processes:
        process.join(20)
        assert process.exitcode == 0
    assert [queue.get(timeout=2) for _ in processes] == ["ok", "ok"]
    assert dest.read_bytes() in payloads


@pytest.mark.parametrize(
    "point",
    [
        "recovery_backup_read",
        "recovery_create",
        "recovery_write",
        "recovery_mode",
        "recovery_fsync",
        "recovery_read",
        "recovery_replace",
        "destination_read",
        "destination_validate",
        "backup_remove",
    ],
)
def test_recovery_failure_preserves_backup(tmp_path, point):
    image = tmp_path / "image.jpg"
    image.write_bytes(b"image")
    dest = tmp_path / "image.jpg.desc.txt"
    backup = tmp_path / "image.jpg.desc.txt.bak"
    backup.write_bytes(b"valid:backup")
    backup.chmod(0o640)
    calls = 0

    def fault(name):
        nonlocal calls
        if name == point:
            calls += 1
            if point != "destination_read" or calls == 2:
                raise OSError("secret")

    with pytest.raises(ArtifactError) as error:
        ArtifactService(checkpoint=fault).recover(dest, valid)
    assert error.value.category == "file_io"
    assert backup.read_bytes() == b"valid:backup"
    assert image.read_bytes() == b"image"
    assert not list(tmp_path.glob("*.tmp"))
    if point in ("destination_read", "destination_validate", "backup_remove"):
        assert dest.read_bytes() == b"valid:backup"
        assert mode(dest) == 0o640
    else:
        assert not dest.exists()


def test_owned_cleanup_failure_preserves_files_and_reports_failure(tmp_path):
    dest = tmp_path / "image.desc.txt"
    backup = tmp_path / "image.desc.txt.bak"
    dest.write_bytes(b"valid:old")
    backup.write_bytes(b"prior")

    def fault(name):
        if name in ("output_write", "temp_cleanup"):
            raise OSError("secret")

    with pytest.raises(ArtifactError) as error:
        ArtifactService(checkpoint=fault).write(dest, b"valid:new", valid)
    assert error.value.category == "file_io"
    assert dest.read_bytes() == b"valid:old"
    assert backup.read_bytes() == b"prior"
    assert len(list(tmp_path.glob("*.tmp"))) == 1
    assert ArtifactService("retain").recover(dest, valid)
    assert len(list(tmp_path.glob("*.tmp"))) == 1


def test_staged_validation_failure_preserves_original_and_backup(tmp_path):
    dest = tmp_path / "image.desc.txt"
    backup = tmp_path / "image.desc.txt.bak"
    dest.write_bytes(b"valid:old")
    backup.write_bytes(b"prior")
    with pytest.raises(ArtifactError) as error:
        ArtifactService().write(
            dest, b"invalid", valid, validation_category="invalid_artifact"
        )
    assert error.value.category == "invalid_artifact"
    assert dest.read_bytes() == b"valid:old"
    assert backup.read_bytes() == b"prior"
    assert not list(tmp_path.glob("*.tmp"))


def test_missing_destination_and_backup_ignores_orphan(tmp_path):
    dest = tmp_path / "image.desc.txt"
    orphan = tmp_path / ".image.desc.txt.image-clarus-orphan.tmp"
    orphan.write_bytes(b"valid:orphan")
    assert not ArtifactService().recover(dest, valid)
    assert not dest.exists()
    assert orphan.read_bytes() == b"valid:orphan"


def test_post_publication_validation_failure_keeps_backup(tmp_path):
    dest = tmp_path / "image.desc.txt"
    backup = tmp_path / "image.desc.txt.bak"
    dest.write_bytes(b"valid:old")
    calls = 0

    def validator(data):
        nonlocal calls
        calls += 1
        return calls == 1

    with pytest.raises(ArtifactError) as error:
        ArtifactService().write(
            dest, b"valid:new", validator, validation_category="invalid_artifact"
        )
    assert error.value.category == "invalid_artifact"
    assert dest.read_bytes() == b"valid:new"
    assert backup.read_bytes() == b"valid:old"


def test_actual_fsync_failure_keeps_original(tmp_path, monkeypatch):
    dest = tmp_path / "image.desc.txt"
    backup = tmp_path / "image.desc.txt.bak"
    dest.write_bytes(b"valid:old")
    backup.write_bytes(b"prior")

    def fail(fd):
        raise OSError("sensitive")

    monkeypatch.setattr("image_clarus.artifacts.os.fsync", fail)
    with pytest.raises(ArtifactError) as error:
        ArtifactService().write(dest, b"valid:new", valid)
    assert error.value.category == "file_io"
    assert dest.read_bytes() == b"valid:old"
    assert backup.read_bytes() == b"prior"
    assert not list(tmp_path.glob("*.tmp"))
