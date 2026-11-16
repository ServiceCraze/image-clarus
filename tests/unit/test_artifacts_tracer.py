import importlib.util

import pytest

from image_clarus.artifacts import ArtifactError, ArtifactService


def test_artifact_service_is_available():
    assert importlib.util.find_spec("image_clarus.artifacts") is not None


def test_staged_bytes_must_match_payload(tmp_path):
    dest = tmp_path / "x.desc.txt"
    dest.write_bytes(b"old")

    def corrupt(point):
        if point == "output_read":
            next(tmp_path.glob("*.tmp")).write_bytes(b"other")

    with pytest.raises(ArtifactError):
        ArtifactService(checkpoint=corrupt).write(dest, b"new", lambda data: True)
    assert dest.read_bytes() == b"old"


def test_single_writer_mismatched_published_bytes_fail(tmp_path):
    dest = tmp_path / "x.desc.txt"

    def corrupt(point):
        if point == "destination_read":
            dest.write_bytes(b"other")

    with pytest.raises(ArtifactError):
        ArtifactService(checkpoint=corrupt).write(dest, b"new", lambda data: True)


def test_validator_exception_is_sanitized(tmp_path):
    def validator(data):
        raise ValueError("secret")

    with pytest.raises(ArtifactError) as error:
        ArtifactService().write(tmp_path / "x.desc.txt", b"new", validator)
    assert "secret" not in str(error.value)


def test_failed_replace_restores_missing_original_and_retains_backup(tmp_path):
    dest = tmp_path / "x.desc.txt"
    backup = tmp_path / "x.desc.txt.bak"
    dest.write_bytes(b"original")
    dest.chmod(0o640)

    def disappear(point):
        if point == "destination_replace":
            dest.unlink()
            raise OSError("replacement failed")

    with pytest.raises(ArtifactError) as error:
        ArtifactService(checkpoint=disappear).write(dest, b"new", lambda _: True)
    assert error.value.category == "file_io"
    assert dest.read_bytes() == backup.read_bytes() == b"original"
    assert dest.stat().st_mode & 0o777 == 0o640


def test_cleanup_attempts_all_owned_temps_after_one_unlink_fails(tmp_path, monkeypatch):
    from pathlib import Path

    paths = [tmp_path / "a.tmp", tmp_path / "b.tmp"]
    for path in paths:
        path.write_bytes(b"temp")
    unlink = Path.unlink
    attempts = []

    def fail_first(path, *args, **kwargs):
        attempts.append(path)
        if len(attempts) == 1:
            raise OSError("synthetic failure")
        return unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", fail_first)
    with pytest.raises(OSError):
        ArtifactService()._cleanup(set(paths))
    assert len(attempts) == 2
    assert sum(path.exists() for path in paths) == 1
