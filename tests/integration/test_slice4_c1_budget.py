"""C1 budget acceptance with synthetic local inputs and a loopback provider.

The large test exercises actual XMP prerequisite decisions, not XMP writes.
"""

import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

from test_single_image_pipeline import rig  # noqa: F401

from image_clarus.artifacts import ArtifactService
from image_clarus.batch_execution import run_sequential
from image_clarus.batch_plan import Admission, PlanningInput, build_plan

ROOT = Path(__file__).resolve().parents[2]


def test_ten_thousand_xmp_only_actual_missing_prerequisite_evaluations(tmp_path):
    config = {
        "state": {"directory": None, "accumulate_categories": False},
        "pipeline": {"missing_prerequisite": "skip", "on_stage_failure": "continue"},
        "stages": {
            "desc": {"regenerate": False},
            "json": {"regenerate": False},
            "xmp": {"regenerate": False},
        },
    }
    inputs = (
        PlanningInput(str(tmp_path / f"{i}.jpg"), ("synthetic", str(tmp_path), "file"))
        for i in range(10_000)
    )
    plan = build_plan(inputs, config, selected=("xmp",), limit=0)
    assert plan.counts[Admission.NO_LLM_WORK] == 10_000
    assert [len(queue) for queue in plan.queues] == [10_000]
    seen = []
    services = SimpleNamespace(artifacts=ArtifactService(), provider_factory=None)
    result = run_sequential(plan, config, services, cwd=tmp_path, on_event=seen.append)
    evaluated = [
        e.image_id for e in seen if e.kind == "stage_evaluated" and e.stage == "xmp"
    ]
    assert len(evaluated) == 10_000 and len(set(evaluated)) == 10_000
    assert len(result.images) == 10_000
    assert all(
        len(image.stages) == 1 and image.stages[0].reason_code == "missing_prerequisite"
        for image in result.images
    )
    assert not any(e.kind == "transform_started" for e in seen)


def test_cli_budget_exclusion_and_regeneration(rig, tmp_path):  # noqa: F811
    second = rig.image.parent / "z-other.png"
    second.write_bytes(rig.original)
    config = rig.config("budget")
    env = dict(
        os.environ,
        HOME=str(tmp_path / "home"),
        PYTHONPATH=str(ROOT / "src"),
        NO_PROXY="*",
        no_proxy="*",
    )

    def run(*args):
        return subprocess.run(
            [
                sys.executable,
                "-m",
                "image_clarus",
                "process",
                str(rig.image.parent),
                "--config",
                str(config),
                "--stages",
                "desc",
                "--no-inter-stage-concurrency",
                *args,
            ],
            cwd=tmp_path,
            env=env,
            capture_output=True,
            text=True,
            timeout=45,
            check=False,
        )

    first = run("--max-work-files", "1")
    assert first.returncode == 0, (first.stdout, first.stderr)
    assert len(rig.requests) == 1
    assert rig.desc.exists() and not Path(str(second) + ".desc.txt").exists()
    rig.desc.write_text("fictional previous description")
    regenerate = run("--max-work-files", "1", "--regenerate")
    assert regenerate.returncode == 0, (regenerate.stdout, regenerate.stderr)
    assert len(rig.requests) == 2
    assert rig.desc.read_text() != "fictional previous description"
    assert rig.desc.exists() and not Path(str(second) + ".desc.txt").exists()
