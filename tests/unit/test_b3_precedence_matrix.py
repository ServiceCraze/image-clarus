"""B3 state selection across configuration and repository discovery layers."""

import pytest

from image_clarus.config import resolve_config
from image_clarus.state.resolution import select_directory
from image_clarus.state.service import StateService
from image_clarus.state.storage import initialize


def make_repository(path, marker):
    initialize(path)
    service = StateService.select(path, path.parent, path.parent / "image.jpg")
    try:
        service.add_categories([marker])
    finally:
        service.close()
    return path.resolve()


@pytest.mark.parametrize(
    ("flag", "override", "yaml_value", "cwd_repo", "image_repo", "expected"),
    [
        (True, True, True, True, True, "flag"),
        (False, True, True, True, True, "override"),
        (False, False, True, True, True, "yaml"),
        (False, False, False, True, True, "cwd"),
        (False, False, False, False, True, "image"),
        (False, False, False, False, False, None),
    ],
)
def test_selection_precedence_matrix(
    tmp_path, monkeypatch, flag, override, yaml_value, cwd_repo, image_repo, expected
):
    cwd = tmp_path / "work"
    images = tmp_path / "photos"
    config_dir = tmp_path / "config"
    for path in (cwd, images, config_dir):
        path.mkdir()
    monkeypatch.chdir(cwd)
    paths = {
        "flag": cwd / "flag-state",
        "override": cwd / "set-state",
        "yaml": config_dir / "yaml-state",
        "cwd": cwd / ".image-clarus",
        "image": images / ".image-clarus",
    }
    for key in ("flag", "override", "yaml"):
        make_repository(paths[key], key)
    for key, enabled in (("cwd", cwd_repo), ("image", image_repo)):
        if enabled:
            make_repository(paths[key], key)
    config_file = config_dir / "config.yaml"
    config_file.write_text(
        "state:\n  directory: yaml-state\n" if yaml_value else "{}\n",
        encoding="utf-8",
    )
    config = resolve_config(
        config_file=config_file,
        overrides=["state.directory=set-state"] if override else [],
        state_dir="flag-state" if flag else None,
    )
    explicit = config["state"]["directory"]
    image = images / "photo.jpg"
    selected = paths[expected].resolve() if expected is not None else None
    assert select_directory(explicit, cwd, image) == selected
    service = StateService.select(explicit, cwd, image)
    try:
        assert service.snapshot_categories() == ([] if expected is None else [expected])
        if expected is None:
            service.add_categories(["temporary"])
            assert service.snapshot_categories() == ["temporary"]
    finally:
        service.close()
    if expected is None:
        again = StateService.select(explicit, cwd, image)
        try:
            assert again.snapshot_categories() == []
        finally:
            again.close()
        assert not (cwd / ".image-clarus").exists()
        assert not (images / ".image-clarus").exists()


@pytest.mark.parametrize("source", ["cwd", "image"])
def test_nearest_nested_initialized_repository(tmp_path, source):
    cwd = tmp_path / "work" / "nested"
    images = tmp_path / "photos" / "nested"
    cwd.mkdir(parents=True)
    images.mkdir(parents=True)
    root = cwd if source == "cwd" else images
    make_repository(root.parent / ".image-clarus", "outer")
    nearest = make_repository(root / ".image-clarus", "inner")
    image = images / "photo.jpg"
    assert select_directory(None, cwd, image) == nearest
    service = StateService.select(None, cwd, image)
    try:
        assert service.snapshot_categories() == ["inner"]
    finally:
        service.close()


def test_explicit_shared_repository_across_unrelated_images(tmp_path):
    cwd = tmp_path / "work"
    cwd.mkdir()
    images = [tmp_path / "collection-a", tmp_path / "collection-b"]
    shared = make_repository(tmp_path / "shared", "shared")
    for index, directory in enumerate(images):
        directory.mkdir()
        make_repository(directory / ".image-clarus", f"local-{index}")
        image = directory / "photo.jpg"
        assert select_directory(shared, cwd, image) == shared
        service = StateService.select(shared, cwd, image)
        try:
            if index == 0:
                service.add_categories(["from-first"])
            else:
                assert set(service.snapshot_categories()) == {"shared", "from-first"}
        finally:
            service.close()


def test_set_null_clears_yaml_and_resumes_discovery(tmp_path, monkeypatch):
    cwd = tmp_path / "work"
    images = tmp_path / "images"
    config_dir = tmp_path / "config"
    for path in (cwd, images, config_dir):
        path.mkdir()
    monkeypatch.chdir(cwd)
    make_repository(config_dir / "yaml-state", "yaml")
    discovered = make_repository(cwd / ".image-clarus", "cwd")
    config_file = config_dir / "config.yaml"
    config_file.write_text("state:\n  directory: yaml-state\n", encoding="utf-8")
    config = resolve_config(config_file=config_file, overrides=["state.directory=null"])
    explicit = config["state"]["directory"]
    assert explicit is None
    assert select_directory(explicit, cwd, images / "photo.jpg") == discovered
    service = StateService.select(explicit, cwd, images / "photo.jpg")
    try:
        assert service.snapshot_categories() == ["cwd"]
    finally:
        service.close()
