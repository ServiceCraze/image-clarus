"""Recovery must not publish a known-invalid backup."""

import pytest

from image_clarus.artifacts import ArtifactError, ArtifactService


def test_invalid_backup_is_not_published(tmp_path):
    destination = tmp_path / "sample.desc.txt"
    backup = tmp_path / "sample.desc.txt.bak"
    backup.write_bytes(b"invalid")
    with pytest.raises(ArtifactError) as error:
        ArtifactService().recover(destination, lambda data: data == b"valid")
    assert error.value.category == "invalid_artifact"
    assert not destination.exists()
    assert backup.read_bytes() == b"invalid"
    assert set(tmp_path.iterdir()) == {backup}
