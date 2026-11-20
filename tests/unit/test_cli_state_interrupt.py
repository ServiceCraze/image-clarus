"""CLI interruption at the state macro boundary using injected stop requests."""

import signal
import sys
from pathlib import Path

import pytest

from image_clarus import cli
from image_clarus.state.service import StateService


@pytest.mark.parametrize("signum", [signal.SIGINT, signal.SIGTERM])
@pytest.mark.parametrize("stage", ["desc", "json"])
def test_state_macro_stop_returns_signal_exit_and_skips_later_stage(
    tmp_path, monkeypatch, capsys, signum, stage
):
    image = tmp_path / "fiction.png"
    image.write_bytes(b"fictional image")
    if stage == "json":
        Path(str(image) + ".desc.txt").write_text("fictional description")
    prompt = tmp_path / "prompt.txt"
    prompt.write_text("{{state.categories.known}}")
    config = tmp_path / "config.yaml"
    config.write_text(
        "providers:\n  local:\n    base_url: http://127.0.0.1:1234/v1\n"
        "models:\n  m:\n    provider: local\n    model_id: fictional\n"
        "stages:\n  desc:\n    model: m\n  json:\n    model: m\n"
    )
    seen = []
    original_snapshot = StateService.snapshot_categories
    original_close = StateService.close

    def interrupted_snapshot(service):
        seen.append("snapshot")
        service.stop.request(signum)
        return original_snapshot(service)

    def closed(service):
        seen.append("close")
        return original_close(service)

    def no_provider(*args, **kwargs):
        pytest.fail("provider must not start after interruption")

    monkeypatch.setattr(StateService, "snapshot_categories", interrupted_snapshot)
    monkeypatch.setattr(StateService, "close", closed)
    monkeypatch.setattr(
        "image_clarus.providers.openai_compatible.OpenAICompatible", no_provider
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "image-clarus",
            "process",
            str(image),
            "--config",
            str(config),
            "--stages",
            "desc,json" if stage == "desc" else "json",
            "--desc-prompt" if stage == "desc" else "--json-prompt",
            str(prompt),
        ],
    )
    assert cli.main() == 128 + signum
    assert seen == ["snapshot", "close"]
    output = capsys.readouterr().out
    assert f"{stage}: skipped — reason=interrupted" in output
    if stage == "desc":
        assert "json: skipped — reason=interrupted" in output
    assert not Path(str(image) + ".desc.json").exists()
    if stage == "desc":
        assert not Path(str(image) + ".desc.txt").exists()
