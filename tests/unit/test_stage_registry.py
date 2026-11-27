"""Registry capabilities stay lazy and reference real stage entry points."""

import subprocess
import sys
from dataclasses import FrozenInstanceError
from pathlib import Path
from types import SimpleNamespace

import pytest

from image_clarus.stage_registry import STAGES, StageDescriptor, predicted_bypass


def test_stage_references_and_order():
    from image_clarus.stages import description, structure, xmp

    desc, json, xmp_stage = STAGES
    assert [stage.name for stage in STAGES] == ["desc", "json", "xmp"]
    assert (desc.inspect, desc.start_or_resume, desc.run) == (
        description.inspect,
        description.start_or_resume,
        description.run_description,
    )
    assert (json.inspect, json.start_or_resume, json.run) == (
        structure.inspect,
        structure.start_or_resume,
        structure.run_structure,
    )
    assert (xmp_stage.inspect, xmp_stage.start_or_resume) == (
        xmp.inspect,
        xmp.start_or_resume,
    )
    assert xmp_stage.run is xmp.run_xmp
    with pytest.raises(FrozenInstanceError):
        desc.name = "other"


def test_registry_inspection_uses_real_stage_decision(tmp_path):
    from image_clarus.stage_protocol import Terminal, WorkRequired

    class Artifacts:
        def recover(self, output, validator, **kwargs):
            return output.exists() and validator(output.read_bytes())

    image = tmp_path / "image.jpg"
    config = {"stages": {"desc": {"regenerate": False}}}
    services = SimpleNamespace(artifacts=Artifacts())
    desc = STAGES[0]
    assert isinstance(desc.inspect(image, config, services), WorkRequired)
    excluded = desc.inspect(image, config, services, inference_allowed=False)
    assert isinstance(excluded, Terminal)
    assert excluded.result.reason_code == "budget_excluded"
    (tmp_path / "image.jpg.desc.txt").write_text("valid", encoding="utf-8")
    assert predicted_bypass(desc, image, config)
    assert desc.inspect(image, config, services).result.reason_code == "output_exists"
    (tmp_path / "image.jpg.desc.txt").write_bytes(b"")
    assert predicted_bypass(desc, image, config)
    assert isinstance(desc.inspect(image, config, services), WorkRequired)


def test_xmp_descriptor_executes_real_non_llm_stage_seam(tmp_path):
    from copy import deepcopy

    from image_clarus.artifacts import ArtifactService
    from image_clarus.config import DEFAULTS
    from image_clarus.stage_protocol import Terminal, WorkRequired

    image = tmp_path / "fictional.jpg"
    image.write_bytes(b"fictional image")
    config = deepcopy(DEFAULTS)
    config["pipeline"]["missing_prerequisite"] = "skip"
    services = SimpleNamespace(
        artifacts=ArtifactService(),
        provider_factory=lambda *args, **kwargs: pytest.fail(
            "non-LLM XMP must not invoke a provider"
        ),
    )
    stage = STAGES[2]
    inspect_stage = stage.inspect
    execute_stage = stage.start_or_resume
    assert callable(inspect_stage) and callable(execute_stage)

    work = inspect_stage(image, config, services, inference_allowed=False)
    assert isinstance(work, WorkRequired)
    assert work.stage == "xmp"
    assert stage.uses_llm is False
    assert stage.skip_if_valid_output_exists is False
    outcome = execute_stage(work.context, None)
    assert isinstance(outcome, Terminal)
    assert (outcome.result.status, outcome.result.reason_code) == (
        "skipped",
        "missing_prerequisite",
    )
    assert image.read_bytes() == b"fictional image"


def test_generic_descriptor_needs_no_execution_or_name_special_case(tmp_path):
    stage = StageDescriptor("other", True, True, lambda _: True)
    assert stage.inspect is None and stage.start_or_resume is None and stage.run is None
    assert predicted_bypass(
        stage, tmp_path, {"stages": {"other": {"regenerate": False}}}
    )
    assert not predicted_bypass(
        stage, tmp_path, {"stages": {"other": {"regenerate": True}}}
    )


@pytest.mark.parametrize("suffix", [".desc.txt", ".desc.txt.bak"])
def test_structure_prerequisite_capability_is_metadata_only(
    tmp_path, monkeypatch, suffix
):
    image = tmp_path / "fictional.jpg"
    predict = STAGES[1].predicted_prerequisites
    assert predict is not None
    assert not predict(image, ())
    assert predict(image, ("desc",))
    assert not predict(image, ("xmp",))
    sidecar = Path(str(image) + suffix)
    sidecar.symlink_to(tmp_path / "missing-target")
    monkeypatch.setattr(Path, "read_bytes", lambda *_: pytest.fail("content read"))
    monkeypatch.setattr(Path, "read_text", lambda *_: pytest.fail("content read"))
    assert predict(image, ())  # A dangling symlink is uncertain, not absent.


@pytest.mark.parametrize("suffix", [".desc.txt", ".desc.txt.bak"])
def test_structure_prerequisite_metadata_error_is_uncertain(
    tmp_path, monkeypatch, suffix
):
    image = tmp_path / "fictional.jpg"
    original = Path.lstat

    def lstat(path, *args, **kwargs):
        if str(path).endswith(suffix):
            raise PermissionError("synthetic metadata error")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "lstat", lstat)
    predict = STAGES[1].predicted_prerequisites
    assert predict is not None and predict(image, ())


def test_planning_import_does_not_load_stages():
    script = """\
import sys
from image_clarus.batch_plan import build_plan
build_plan([], {'stages': {}})
assert not any(name.startswith('image_clarus.stages.') for name in sys.modules)
"""
    subprocess.run([sys.executable, "-c", script], check=True)
