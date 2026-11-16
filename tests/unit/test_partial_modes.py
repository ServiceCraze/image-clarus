"""Regression tests for partially representable permission modes."""

import errno
import os

import pytest

from image_clarus.artifacts import ArtifactError, ArtifactService


def test_partial_mode_support_does_not_prevent_valid_write(
    tmp_path, monkeypatch, capsys
):
    target = tmp_path / "artifact"
    real_fchmod = os.fchmod

    def partial(fd, mode):
        real_fchmod(fd, mode & 0o640)

    monkeypatch.setattr(os, "fchmod", partial)
    ArtifactService().write(target, b"valid", lambda data: data == b"valid")
    assert target.read_bytes() == b"valid"
    assert "privacy" in capsys.readouterr().err.lower()


def test_bad_mode_operation_value_error_is_sanitized(tmp_path, monkeypatch):
    def invalid(fd, mode):
        raise ValueError("private-path-sentinel")

    monkeypatch.setattr(os, "fchmod", invalid)
    with pytest.raises(ArtifactError) as error:
        ArtifactService().write(tmp_path / "artifact", b"valid", lambda _: True)
    assert error.value.category == "file_io"
    assert "private-path-sentinel" not in str(error.value)
    assert not (tmp_path / "artifact").exists()


def test_access_denied_is_still_failure(tmp_path, monkeypatch):
    def denied(fd, mode):
        raise OSError(errno.EACCES, "private-path-sentinel")

    monkeypatch.setattr(os, "fchmod", denied)
    with pytest.raises(ArtifactError) as error:
        ArtifactService().write(tmp_path / "artifact", b"valid", lambda _: True)
    assert error.value.error_number == errno.EACCES
    assert not (tmp_path / "artifact").exists()
