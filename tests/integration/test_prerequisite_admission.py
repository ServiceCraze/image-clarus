"""CLI budget admission with fictional sidecars and a loopback provider."""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
from test_single_image_pipeline import rig  # noqa: F401

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("budget", [1, 2])
@pytest.mark.parametrize("policy", ["skip", "fail"])
@pytest.mark.parametrize("concurrency", ["false", "true"])
def test_json_only_missing_description_does_not_consume_budget(
    rig,  # noqa: F811
    tmp_path,
    policy,
    concurrency,
    budget,
):
    first = rig.image.with_name("a-missing.png")
    second = rig.image.with_name("b-ready.png")
    rig.image.rename(first)
    second.write_bytes(rig.original)
    description = "Fictional ready image description."
    Path(str(second) + ".desc.txt").write_text(description)
    config = rig.config("admission")
    prompt = tmp_path / "json-prompt.txt"
    prompt.write_text("Produce structured fictional metadata.")
    env = dict(
        os.environ,
        HOME=str(tmp_path / "home"),
        PYTHONPATH=str(ROOT / "src"),
        NO_PROXY="*",
        no_proxy="*",
    )
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "image_clarus",
            "process",
            str(first.parent),
            "--config",
            str(config),
            "--stages",
            "json",
            "--verbose",
            "--json-prompt",
            str(prompt),
            "--max-work-files",
            str(budget),
            "--set",
            f"pipeline.missing_prerequisite={policy}",
            "--set",
            "pipeline.on_stage_failure=continue",
            "--set",
            f"pipeline.inter_stage_concurrency={concurrency}",
        ],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=45,
        check=False,
    )
    assert result.returncode == (0 if policy == "skip" else 1), (
        result.stdout,
        result.stderr,
    )
    assert len(rig.requests) == 1, (result.stdout, result.stderr, rig.requests)
    stage, body, path = rig.requests[0]
    assert stage == "json" and path == "/v1/chat/completions"
    assert description in json.dumps(body)
    assert not Path(str(first) + ".desc.json").exists()
    output = Path(str(second) + ".desc.json")
    assert json.loads(output.read_text())["metadata"]["title"] == "Blue square"
    assert first.read_bytes() == second.read_bytes() == rig.original
    ends = {}
    for line in result.stdout.splitlines():
        match = re.match(
            r'^stage end image=("(?:[^"\\]|\\.)*") stage=json status=(\w+) reason=([\w-]+) ',
            line,
        )
        if match:
            image, status, reason = match.groups()
            ends[Path(json.loads(image)).name] = (status, reason)
    assert ends == {
        first.name: (
            "skipped" if policy == "skip" else "failed",
            "missing_prerequisite",
        ),
        second.name: ("completed", "-"),
    }, (result.stdout, result.stderr)


def test_desc_then_json_still_admits_first_image(rig, tmp_path):  # noqa: F811
    first = rig.image.with_name("a-missing.png")
    second = rig.image.with_name("b-ready.png")
    rig.image.rename(first)
    second.write_bytes(rig.original)
    Path(str(second) + ".desc.txt").write_text("Fictional ready description.")
    config = rig.config("both-stages")
    prompt = tmp_path / "prompt.txt"
    prompt.write_text("Describe the fictional scene.")
    env = dict(
        os.environ,
        HOME=str(tmp_path / "home"),
        PYTHONPATH=str(ROOT / "src"),
        NO_PROXY="*",
        no_proxy="*",
    )
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "image_clarus",
            "process",
            str(first.parent),
            "--config",
            str(config),
            "--stages",
            "desc,json",
            "--verbose",
            "--desc-prompt",
            str(prompt),
            "--json-prompt",
            str(prompt),
            "--max-work-files",
            "1",
            "--no-inter-stage-concurrency",
        ],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=45,
        check=False,
    )
    assert result.returncode == 0, (result.stdout, result.stderr)
    assert [request[0] for request in rig.requests] == ["desc", "json"]
    assert Path(str(first) + ".desc.txt").exists()
    assert (
        json.loads(Path(str(first) + ".desc.json").read_text())["metadata"]["title"]
        == "Blue square"
    )
    assert not Path(str(second) + ".desc.json").exists()
    assert "summary images=2 admitted=1 no_work=0 excluded=1" in result.stdout


@pytest.mark.parametrize("valid", [True, False])
def test_json_only_description_backup_is_admitted_and_recovered(rig, tmp_path, valid):  # noqa: F811
    first = rig.image.with_name("a-backup.png")
    second = rig.image.with_name("b-excluded.png")
    rig.image.rename(first)
    second.write_bytes(rig.original)
    description = "Fictional recovered description."
    backup = Path(str(first) + ".desc.txt.bak")
    backup_bytes = description.encode() if valid else b"\xffinvalid"
    backup.write_bytes(backup_bytes)
    Path(str(second) + ".desc.txt").write_text("Excluded fictional description.")
    prompt = tmp_path / "prompt.txt"
    prompt.write_text("Produce fictional structured metadata.")
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "image_clarus",
            "process",
            str(first.parent),
            "--config",
            str(rig.config("backup")),
            "--stages",
            "json",
            "--verbose",
            "--json-prompt",
            str(prompt),
            "--max-work-files",
            "1",
            "--set",
            "pipeline.on_stage_failure=continue",
            "--no-inter-stage-concurrency",
        ],
        cwd=tmp_path,
        env=dict(
            os.environ,
            HOME=str(tmp_path / "home"),
            PYTHONPATH=str(ROOT / "src"),
            NO_PROXY="*",
            no_proxy="*",
        ),
        capture_output=True,
        text=True,
        timeout=45,
        check=False,
    )
    assert result.returncode == (0 if valid else 1), (result.stdout, result.stderr)
    assert "summary images=2 admitted=1 no_work=0 excluded=1" in result.stdout
    assert (
        f"stage end image={json.dumps(str(second))} stage=json status=skipped reason=budget_excluded "
        in result.stdout
    )
    assert not Path(str(second) + ".desc.json").exists()
    if valid:
        assert Path(str(first) + ".desc.txt").read_bytes() == backup_bytes
        assert len(rig.requests) == 1
        assert description in json.dumps(rig.requests[0][1])
        assert (
            json.loads(Path(str(first) + ".desc.json").read_text())["metadata"]["title"]
            == "Blue square"
        )
    else:
        assert backup.read_bytes() == backup_bytes
        assert not Path(str(first) + ".desc.txt").exists()
        assert not Path(str(first) + ".desc.json").exists()
        assert not rig.requests
        assert (
            f"stage end image={json.dumps(str(first))} stage=json status=failed "
            in result.stdout
        )


@pytest.mark.parametrize("concurrency", ["false", "true"])
def test_frozen_no_work_plan_allows_corrective_request_without_reopening_exclusion(
    rig,  # noqa: F811
    tmp_path,
    concurrency,
):
    first = rig.image.with_name("a-corrective.png")
    admitted = rig.image.with_name("b-admitted.png")
    excluded = rig.image.with_name("c-excluded.png")
    rig.image.rename(first)
    for image in (admitted, excluded):
        image.write_bytes(rig.original)
        Path(str(image) + ".desc.txt").write_text(
            f"Fictional description for {image.name}."
        )
    description = "Fictional description arriving after plan freeze."
    prompt = tmp_path / "prompt.txt"
    prompt.write_text("Produce fictional structured metadata.")
    snapshot = tmp_path / "plan.json"
    # Instrument only the planner return: capture the real immutable admission rows,
    # then introduce the prerequisite before the actual executor is entered.
    script = """
import json, os, sys
from pathlib import Path
import image_clarus.cli as cli
import image_clarus.batch_plan as batch_plan
original = batch_plan.build_plan
def build(*args, **kwargs):
    plan = original(*args, **kwargs)
    if plan.rows:
        Path(os.environ["PLAN_SNAPSHOT"]).write_text(json.dumps([[row[0], row[4].value] for row in plan.rows]))
        Path(os.environ["LATE_DESC"]).write_text(os.environ["LATE_TEXT"])
    return plan
batch_plan.build_plan = build
sys.argv = ["image_clarus", *sys.argv[1:]]
raise SystemExit(cli.main())
"""
    env = dict(
        os.environ,
        HOME=str(tmp_path / "home"),
        PYTHONPATH=str(ROOT / "src"),
        NO_PROXY="*",
        no_proxy="*",
        PLAN_SNAPSHOT=str(snapshot),
        LATE_DESC=str(first) + ".desc.txt",
        LATE_TEXT=description,
    )
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            script,
            "process",
            str(first.parent),
            "--config",
            str(rig.config("corrective")),
            "--stages",
            "json",
            "--verbose",
            "--json-prompt",
            str(prompt),
            "--max-work-files",
            "1",
            "--set",
            f"pipeline.inter_stage_concurrency={concurrency}",
        ],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=45,
        check=False,
    )
    assert result.returncode == 0, (result.stdout, result.stderr)
    assert json.loads(snapshot.read_text()) == [
        [str(first), "NO_LLM_WORK"],
        [str(admitted), "ADMITTED"],
        [str(excluded), "KNOWN_EXCLUDED"],
    ]
    assert "summary images=3 admitted=1 no_work=1 excluded=1" in result.stdout
    assert (
        "work llm_images=2 corrective_images=1 requests=2 first_requests=2 retries=0"
        in result.stdout
    )
    assert (
        f"stage end image={json.dumps(str(excluded))} stage=json status=skipped reason=budget_excluded "
        in result.stdout
    )
    assert len(rig.requests) == 2
    request_bodies = [json.dumps(request[1]) for request in rig.requests]
    assert sum(description in body for body in request_bodies) == 1
    assert (
        sum(
            f"Fictional description for {admitted.name}." in body
            for body in request_bodies
        )
        == 1
    )
    assert all(
        f"Fictional description for {excluded.name}." not in body
        for body in request_bodies
    )
    for image in (first, admitted):
        assert (
            json.loads(Path(str(image) + ".desc.json").read_text())["metadata"]["title"]
            == "Blue square"
        )
    assert not Path(str(excluded) + ".desc.json").exists()
