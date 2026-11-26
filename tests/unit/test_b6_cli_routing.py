"""B6 CLI routing and parser-diagnostic regression coverage."""

import sys

import pytest

from image_clarus import cli


def _config(path):
    path.write_text(
        "providers:\n"
        "  sample:\n"
        "    base_url: http://127.0.0.1:1/v1\n"
        "models:\n"
        "  sample:\n"
        "    provider: sample\n"
        "    model_id: fictional-model\n"
        "stages:\n"
        "  desc:\n"
        "    model: sample\n"
        "pipeline:\n"
        "  on_stage_failure: abort\n"
    )


def test_argument_error_dry_run_marks_plan_incomplete(tmp_path, monkeypatch, capsys):
    image = tmp_path / "one.jpg"
    image.write_bytes(b"synthetic")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "image-clarus",
            "process",
            str(image),
            "--dry-run",
            "--max-depth",
            "invalid",
        ],
    )

    with pytest.raises(SystemExit) as error:
        cli.main()

    assert error.value.code == 2
    output = capsys.readouterr()
    assert "plan incomplete" in output.err
    assert "estimate unavailable: incomplete plan" in output.err


def test_single_file_uses_effective_configured_abort_policy(
    tmp_path, monkeypatch, capsys
):
    image = tmp_path / "one.jpg"
    image.write_bytes(b"synthetic")
    (tmp_path / "one.jpg.desc.txt").write_text("existing")
    settings = tmp_path / "settings.yaml"
    _config(settings)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "image-clarus",
            "process",
            str(image),
            "--stages",
            "desc",
            "--config",
            str(settings),
        ],
    )

    assert cli.main() == 0
    output = capsys.readouterr()
    assert output.out == "desc: skipped — reason=output_exists\n"
    assert "not implemented" not in output.err


def test_single_file_uses_effective_override_abort_policy(
    tmp_path, monkeypatch, capsys
):
    image = tmp_path / "one.jpg"
    image.write_bytes(b"synthetic")
    (tmp_path / "one.jpg.desc.txt").write_text("existing")
    settings = tmp_path / "settings.yaml"
    _config(settings)
    settings.write_text(settings.read_text().replace("  on_stage_failure: abort\n", ""))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "image-clarus",
            "process",
            str(image),
            "--stages",
            "desc",
            "--config",
            str(settings),
            "--set",
            "pipeline.on_stage_failure=abort",
        ],
    )

    assert cli.main() == 0
    output = capsys.readouterr()
    assert output.out == "desc: skipped — reason=output_exists\n"
    assert "not implemented" not in output.err
