from image_clarus.state.service import StateService
from image_clarus.state.storage import StateError


class Broken:
    def __init__(self):
        self.writes = 0
        self.closed = False

    def snapshot_categories(self):
        raise StateError("private sentinel")

    def add_categories(self, paths):
        self.writes += 1
        raise StateError("private sentinel")

    def close(self):
        self.closed = True


def test_failed_write_not_retried_and_falls_back(capsys):
    broken = Broken()
    service = StateService(broken)
    service.add_categories(["fictional"])
    assert broken.closed and broken.writes == 1
    assert service.snapshot_categories() == []
    service.add_categories(["later"])
    assert service.snapshot_categories() == ["later"]
    assert "private sentinel" not in capsys.readouterr().err
    service.close()


def test_failed_read_returns_empty(capsys):
    broken = Broken()
    service = StateService(broken)
    assert service.snapshot_categories() == []
    assert broken.closed
    assert "state error" in capsys.readouterr().err
    service.close()


def test_stop_propagates_without_fallback_or_diagnostic(capsys):
    import pytest

    from image_clarus.pipeline import StopToken
    from image_clarus.state.storage import MemoryStorage, StateStopped

    token = StopToken()
    service = StateService(MemoryStorage(stop=token), stop=token)
    token.request(15)
    with pytest.raises(StateStopped):
        service.snapshot_categories()
    with pytest.raises(StateStopped):
        service.add_categories(["fictional"])
    assert not capsys.readouterr().err
    service.close()


def test_no_creation_on_discovery(tmp_path, monkeypatch):
    from pathlib import Path

    def forbidden(*args, **kwargs):
        raise AssertionError("unexpected creation")

    monkeypatch.setattr(Path, "mkdir", forbidden)
    service = StateService.select(None, tmp_path, tmp_path / "image")
    service.add_categories(["fictional"])
    assert service.snapshot_categories() == ["fictional"]
    service.close()


def test_cli_closes_state_if_stage_setup_fails(tmp_path, monkeypatch):
    import sys

    import pytest

    from image_clarus import artifacts, cli, config

    image = tmp_path / "image.png"
    image.write_bytes(b"synthetic")
    service = StateService(Broken())
    monkeypatch.setattr(StateService, "select", lambda *args, **kwargs: service)
    monkeypatch.setattr(
        config,
        "resolve_config",
        lambda **kwargs: {
            "logging": {"level": "WARNING"},
            "pipeline": {"backup_retention": "remove"},
            "state": {"directory": None},
        },
    )

    def fail_setup(self, *args, **kwargs):
        raise RuntimeError("synthetic setup failure")

    monkeypatch.setattr(artifacts.ArtifactService, "__init__", fail_setup)
    monkeypatch.setattr(
        sys, "argv", ["image-clarus", "process", str(image), "--stages", "desc"]
    )
    with pytest.raises(RuntimeError, match="synthetic setup failure"):
        cli.main()
    assert service.storage.closed
