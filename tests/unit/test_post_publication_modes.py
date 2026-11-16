"""Verify content and conditional mode checks after artifact publication."""

import pytest

from image_clarus.artifacts import ArtifactError, ArtifactService


@pytest.mark.parametrize("operation", ["write", "recover"])
@pytest.mark.parametrize("mode_capable", [False, True])
def test_post_publication_mode_verification_respects_capability(
    tmp_path, monkeypatch, operation, mode_capable
):
    target = tmp_path / "synthetic.desc.txt"
    backup = tmp_path / "synthetic.desc.txt.bak"
    payload = b"complete payload"
    if operation == "recover":
        backup.write_bytes(payload)
    service = ArtifactService("retain")
    monkeypatch.setattr(service, "_mode_capable", lambda *_args: mode_capable)
    original_read = service._read
    published = False

    def read(path):
        data, mode, identity = original_read(path)
        if path == target and published:
            return data, mode ^ 0o040, identity
        return data, mode, identity

    def checkpoint(point):
        nonlocal published
        if point == (
            "destination_replace" if operation == "write" else "recovery_replace"
        ):
            published = True

    service.checkpoint = checkpoint
    monkeypatch.setattr(service, "_read", read)

    def run():
        if operation == "write":
            return service.write(target, payload, lambda data: data == payload)
        return service.recover(target, lambda data: data == payload)

    if mode_capable:
        with pytest.raises(ArtifactError) as exc:
            run()
        assert exc.value.category == "file_io"
    else:
        run()
    assert target.read_bytes() == payload
    if operation == "recover":
        assert backup.read_bytes() == payload


@pytest.mark.parametrize("operation", ["write", "recover"])
def test_post_publication_bytes_checked_even_without_mode_capability(
    tmp_path, monkeypatch, operation
):
    target = tmp_path / "synthetic.desc.txt"
    backup = tmp_path / "synthetic.desc.txt.bak"
    payload = b"complete payload"
    if operation == "recover":
        backup.write_bytes(payload)
    service = ArtifactService("retain")
    monkeypatch.setattr(service, "_mode_capable", lambda *_args: False)
    original_read = service._read
    published = False

    def read(path):
        data, mode, identity = original_read(path)
        if path == target and published:
            return b"different", mode, identity
        return data, mode, identity

    def checkpoint(point):
        nonlocal published
        if point == (
            "destination_replace" if operation == "write" else "recovery_replace"
        ):
            published = True

    service.checkpoint = checkpoint
    monkeypatch.setattr(service, "_read", read)
    with pytest.raises(ArtifactError) as exc:
        if operation == "write":
            service.write(target, payload, lambda _: True)
        else:
            service.recover(target, lambda _: True)
    assert exc.value.category == "file_io"
    if operation == "recover":
        assert backup.read_bytes() == payload
