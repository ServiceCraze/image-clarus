import errno
import os

import pytest

from image_clarus.artifacts import ArtifactError, ArtifactService


@pytest.mark.parametrize("reported", [0o777, 0o600])
def test_ignored_simulated_modes_warn_once_before_any_payload(
    tmp_path, monkeypatch, capsys, reported
):
    dest = tmp_path / "sidecar"
    dest.write_bytes(b"old")
    real_fstat = os.fstat

    def simulated(fd):
        result = list(real_fstat(fd))
        result[0] = (int(result[0]) & ~0o7777) | reported
        return os.stat_result(result)

    monkeypatch.setattr(os, "fstat", simulated)
    monkeypatch.setattr(os, "fchmod", lambda fd, mode: None)
    points = []

    def checkpoint(point):
        if point in ("output_write", "backup_write"):
            points.append(capsys.readouterr().err)

    ArtifactService("retain", checkpoint).write(dest, b"new", lambda _: True)
    assert "privacy" in points[0].lower()
    assert points[1] == ""
    assert dest.read_bytes() == b"new"
    assert (tmp_path / "sidecar.bak").read_bytes() == b"old"


def test_partial_probe_change_warns_and_preserves_content(
    tmp_path, monkeypatch, capsys
):
    dest = tmp_path / "sidecar"
    dest.write_bytes(b"old")
    chmod = os.fchmod
    calls = 0

    def partial(fd, mode):
        nonlocal calls
        calls += 1
        chmod(fd, 0o620 if calls == 2 else mode)

    monkeypatch.setattr(os, "fchmod", partial)
    ArtifactService().write(dest, b"new", lambda _: True)
    assert "privacy" in capsys.readouterr().err.lower()
    assert dest.read_bytes() == b"new"
    assert list(tmp_path.iterdir()) == [dest]


def test_access_denied_after_unsupported_probe_is_not_masked(tmp_path, monkeypatch):
    calls = 0

    def fail(fd, mode):
        nonlocal calls
        calls += 1
        raise OSError(errno.ENOTSUP if calls == 1 else errno.EACCES, "private")

    monkeypatch.setattr(os, "fchmod", fail)
    dest = tmp_path / "sidecar"
    with pytest.raises(ArtifactError) as failure:
        ArtifactService().write(dest, b"new", lambda _: True)
    assert failure.value.error_number == errno.EACCES
    assert not dest.exists()


def test_recovery_on_ignored_modes_warns_before_writing(tmp_path, monkeypatch, capsys):
    dest = tmp_path / "sidecar"
    backup = tmp_path / "sidecar.bak"
    backup.write_bytes(b"original")
    monkeypatch.setattr(os, "fchmod", lambda fd, mode: None)
    messages = []

    def checkpoint(point):
        if point == "recovery_write":
            messages.append(capsys.readouterr().err)

    assert ArtifactService("retain", checkpoint).recover(dest, lambda _: True)
    assert "privacy" in messages[0].lower()
    assert dest.read_bytes() == backup.read_bytes() == b"original"


def test_backup_probe_denial_preserves_destination_and_existing_backup(
    tmp_path, monkeypatch
):
    dest = tmp_path / "sidecar"
    backup = tmp_path / "sidecar.bak"
    dest.write_bytes(b"old")
    backup.write_bytes(b"prior")
    chmod = os.fchmod
    calls = 0

    def deny_backup(fd, mode):
        nonlocal calls
        calls += 1
        if calls == 4:
            raise OSError(errno.EACCES, "private")
        chmod(fd, mode)

    monkeypatch.setattr(os, "fchmod", deny_backup)
    with pytest.raises(ArtifactError) as failure:
        ArtifactService().write(dest, b"new", lambda _: True)
    assert failure.value.checkpoint == "backup_mode"
    assert failure.value.error_number == errno.EACCES
    assert dest.read_bytes() == b"old"
    assert backup.read_bytes() == b"prior"
    assert set(tmp_path.iterdir()) == {dest, backup}


def test_probe_cleanup_error_stops_before_payload_and_preserves_errno(
    tmp_path, monkeypatch
):
    from pathlib import Path

    dest = tmp_path / "sidecar"
    dest.write_bytes(b"old")

    def fail_unlink(self, *args, **kwargs):
        raise OSError(errno.EIO, "private cleanup")

    monkeypatch.setattr(Path, "unlink", fail_unlink)
    with pytest.raises(ArtifactError) as failure:
        ArtifactService().write(dest, b"new", lambda _: True)
    assert failure.value.error_number == errno.EIO
    assert dest.read_bytes() == b"old"
    assert all(path.read_bytes() in (b"old", b"") for path in tmp_path.iterdir())


def test_probe_cleanup_failure_does_not_mask_primary_error(tmp_path, monkeypatch):
    from pathlib import Path

    dest = tmp_path / "sidecar"
    dest.write_bytes(b"old")

    def deny(fd, mode):
        raise OSError(errno.EACCES, "private")

    def fail_unlink(self, *args, **kwargs):
        raise OSError(errno.EIO, "private cleanup")

    monkeypatch.setattr(os, "fchmod", deny)
    monkeypatch.setattr(Path, "unlink", fail_unlink)
    with pytest.raises(ArtifactError) as failure:
        ArtifactService().write(dest, b"new", lambda _: True)
    assert failure.value.error_number == errno.EACCES
    assert failure.value.checkpoint == "output_mode"
    assert dest.read_bytes() == b"old"


def test_capable_probe_but_ignored_actual_mode_fails_before_publication(
    tmp_path, monkeypatch
):
    dest = tmp_path / "sidecar"
    dest.write_bytes(b"old")
    dest.chmod(0o640)
    chmod = os.fchmod
    calls = 0

    def ignore_payload(fd, mode):
        nonlocal calls
        calls += 1
        if calls <= 2:
            chmod(fd, mode)

    monkeypatch.setattr(os, "fchmod", ignore_payload)
    with pytest.raises(ArtifactError):
        ArtifactService("retain").write(dest, b"new", lambda _: True)
    assert dest.read_bytes() == b"old"
    assert not (tmp_path / "sidecar.bak").exists()


def test_ignored_modes_allow_synthetic_write_with_privacy_warning(
    tmp_path, monkeypatch, capsys
):
    dest = tmp_path / "sidecar"
    dest.write_bytes(b"old")
    dest.chmod(0o640)
    monkeypatch.setattr(os, "fchmod", lambda fd, mode: None)
    ArtifactService("retain").write(dest, b"new", lambda _: True)
    assert "privacy" in capsys.readouterr().err.lower()
    assert dest.read_bytes() == b"new"
    assert (tmp_path / "sidecar.bak").read_bytes() == b"old"


@pytest.mark.parametrize("code", [errno.ENOTSUP, errno.ENOSYS])
def test_unsupported_chmod_warns_and_writes(tmp_path, monkeypatch, capsys, code):
    def unsupported(fd, mode):
        raise OSError(code, "sensitive")

    monkeypatch.setattr(os, "fchmod", unsupported)
    dest = tmp_path / "artifact"
    ArtifactService().write(dest, b"new", lambda _: True)
    assert dest.read_bytes() == b"new"
    assert "privacy" in capsys.readouterr().err.lower()


def test_missing_fchmod_warns_and_writes(tmp_path, monkeypatch, capsys):
    monkeypatch.delattr(os, "fchmod")
    dest = tmp_path / "artifact"
    ArtifactService().write(dest, b"new", lambda _: True)
    assert dest.read_bytes() == b"new"
    assert "privacy" in capsys.readouterr().err.lower()


@pytest.mark.parametrize("code", [errno.EACCES, errno.EPERM, errno.EIO])
def test_real_chmod_failure_has_sanitized_checkpoint_and_errno(
    tmp_path, monkeypatch, code
):
    dest = tmp_path / "sensitive-path"
    backup = tmp_path / "sensitive-path.bak"
    dest.write_bytes(b"old")
    backup.write_bytes(b"prior")

    def fail(fd, mode):
        raise OSError(code, "sensitive-detail", str(dest))

    monkeypatch.setattr(os, "fchmod", fail)
    with pytest.raises(ArtifactError) as failure:
        ArtifactService().write(dest, b"new", lambda _: True)
    assert failure.value.category == "file_io"
    assert "output_mode" in str(failure.value)
    assert str(code) in str(failure.value)
    assert "sensitive" not in str(failure.value)
    assert dest.read_bytes() == b"old"
    assert backup.read_bytes() == b"prior"


@pytest.mark.parametrize("stage", ["desc", "json"])
def test_stage_recovery_failure_surfaces_sanitized_diagnostic(tmp_path, stage):
    from types import SimpleNamespace

    from image_clarus.stages.description import run_description
    from image_clarus.stages.structure import run_structure

    def fail(point):
        if point == "destination_read":
            raise OSError(errno.EIO, "sensitive-path")

    services = SimpleNamespace(artifacts=ArtifactService(checkpoint=fail))
    config = {"stages": {stage: {"regenerate": False}}}
    result = (run_description if stage == "desc" else run_structure)(
        tmp_path / "image", config, services
    )
    assert result.error_category == "file_io"
    assert "destination_read" in result.message
    assert "errno=5" in result.message
    assert "sensitive" not in result.message
