from image_clarus.state.resolution import select_directory
from image_clarus.state.storage import initialize


def test_cwd_precedes_image_and_skips_uninitialized(tmp_path):
    cwd = tmp_path / "work" / "nested"
    image = tmp_path / "pictures"
    cwd.mkdir(parents=True)
    image.mkdir()
    initialize(tmp_path / "work" / ".image-clarus")
    initialize(image / ".image-clarus")
    (cwd / ".image-clarus").mkdir()
    assert (
        select_directory(None, cwd, image / "photo.jpg")
        == tmp_path / "work" / ".image-clarus"
    )


def test_image_discovery_explicit_and_memory(tmp_path):
    cwd = tmp_path / "work"
    image = tmp_path / "images"
    cwd.mkdir()
    image.mkdir()
    assert select_directory(None, cwd, image / "x") is None
    initialize(image / ".image-clarus")
    assert select_directory(None, cwd, image / "x") == image / ".image-clarus"
    initialize(cwd / ".image-clarus")
    assert (
        select_directory("../images/.image-clarus", cwd, image / "x")
        == image / ".image-clarus"
    )


def test_dangling_and_inaccessible_candidates_are_errors(tmp_path, monkeypatch):
    from pathlib import Path

    import pytest

    from image_clarus.state.storage import StateError

    cwd = tmp_path / "work"
    cwd.mkdir()
    candidate = cwd / ".image-clarus"
    candidate.symlink_to(tmp_path / "missing")
    with pytest.raises(StateError):
        select_directory(None, cwd, tmp_path / "image")
    candidate.unlink()
    original = Path.lstat

    def denied(self):
        if self == candidate:
            raise PermissionError("private sentinel")
        return original(self)

    monkeypatch.setattr(Path, "lstat", denied)
    with pytest.raises(StateError):
        select_directory(None, cwd, tmp_path / "image")


def test_symlink_and_broken_nearest_are_selected(tmp_path, capsys):
    from image_clarus.state.service import StateService

    cwd = tmp_path / "work"
    cwd.mkdir()
    target = tmp_path / "other"
    initialize(target)
    (cwd / ".image-clarus").symlink_to(target)
    assert select_directory(None, cwd, tmp_path / "x") == target
    (target / "state.sqlite3").write_bytes(b"broken")
    service = StateService.select(None, cwd, tmp_path / "x")
    assert service.snapshot_categories() == []
    assert "state error" in capsys.readouterr().err
    service.close()


def test_explicit_uninitialized_does_not_fall_through_to_discovered_repo(
    tmp_path, capsys
):
    from image_clarus.state.service import StateService

    cwd = tmp_path / "work"
    cwd.mkdir()
    alternate = cwd / ".image-clarus"
    initialize(alternate)
    explicit = cwd / "uninitialized"
    explicit.mkdir()
    service = StateService.select(explicit, cwd, cwd / "image")
    service.add_categories(["fictional/category"])
    assert "state error" in capsys.readouterr().err
    service.close()
    check = StateService.select(alternate, cwd, cwd / "image")
    assert check.snapshot_categories() == []
    check.close()


def test_selected_symlink_dangling_does_not_fall_through(tmp_path, capsys):
    from image_clarus.state.service import StateService

    cwd = tmp_path / "work"
    cwd.mkdir()
    alternate = tmp_path / ".image-clarus"
    initialize(alternate)
    (cwd / ".image-clarus").symlink_to(tmp_path / "missing")
    service = StateService.select(None, cwd, tmp_path / "image")
    service.add_categories(["fictional/category"])
    assert "state error" in capsys.readouterr().err
    service.close()
    check = StateService.select(alternate, cwd, tmp_path / "image")
    assert check.snapshot_categories() == []
    check.close()


def test_missing_component_before_parent_does_not_select_alternate(tmp_path, capsys):
    from image_clarus.state.service import StateService

    alternate = tmp_path / "repo"
    initialize(alternate)
    service = StateService.select(
        tmp_path / "missing" / ".." / "repo", tmp_path, tmp_path / "image"
    )
    service.add_categories(["fictional/category"])
    assert "state error" in capsys.readouterr().err
    service.close()
    check = StateService.select(alternate, tmp_path, tmp_path / "image")
    assert check.snapshot_categories() == []
    check.close()
