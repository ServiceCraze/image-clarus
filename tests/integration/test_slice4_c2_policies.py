"""C2 policies through the CLI and a fictional loopback provider.

The unsupported A suffix fails description before transport; its persisted
text remains usable by JSON. Sequential mode makes B's dispatch deterministic.
"""

import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
from test_single_image_pipeline import METADATA, ROOT, V2, rig  # noqa: F401


@pytest.mark.parametrize(
    "policy",
    [None, "stop", "continue", "abort"],
    ids=["default-stop", "stop", "continue", "abort"],
)
def test_two_image_failure_policy(rig, tmp_path, policy):  # noqa: F811
    first = rig.image.parent / "a.xyz"
    rig.image.rename(first)
    second = rig.image.parent / "b.png"
    second.write_bytes(rig.original)
    description = "Fictional persisted description."
    persisted = Path(str(first) + ".desc.txt")
    persisted.write_text(description, encoding="utf-8")
    config = rig.config("policy")
    env = dict(
        os.environ,
        HOME=str(tmp_path / "home"),
        PYTHONPATH=str(ROOT / "src"),
        NO_PROXY="*",
        no_proxy="*",
    )
    cmd = [
        sys.executable,
        "-m",
        "image_clarus",
        "process",
        str(first),
        str(second),
        "--config",
        str(config),
        "--stages",
        "desc,json",
        "--regenerate",
        "--no-inter-stage-concurrency",
        "--verbose",
    ]
    if policy is not None:
        cmd += ["--set", "pipeline.on_stage_failure=" + policy]
    result = subprocess.run(
        cmd,
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=45,
        check=False,
    )
    assert result.returncode == 1, (result.stdout, result.stderr)
    assert not result.stderr
    lines = result.stdout.splitlines()
    ends = {}
    for line in lines:
        match = re.match(
            r'^stage end image=("(?:[^"\\]|\\.)*") stage=(\w+) status=(\w+) reason=(\S+) ',
            line,
        )
        if match:
            key = (json.loads(match[1]), match[2])
            assert key not in ends
            ends[key] = (match[3], match[4])
    continuing = policy == "continue"
    aborted = policy == "abort"
    assert ends == {
        (str(first), "desc"): ("failed", "-"),
        (str(first), "json"): ("completed", "-")
        if continuing
        else ("not_attempted", "stage_not_run_after_failure"),
        (str(second), "desc"): ("not_attempted", "batch_aborted")
        if aborted
        else ("completed", "-"),
        (str(second), "json"): ("not_attempted", "batch_aborted")
        if aborted
        else ("completed", "-"),
    }
    assert "summary images=2 admitted=2 no_work=0 excluded=0" in lines
    assert "progress accounted=4/4 " in result.stdout
    desc_summary = (
        "actual stage=desc evaluated=1 transformed=1 completed=0 skipped=0 failed=1 interrupted=0 not_attempted=1"
        if aborted
        else "actual stage=desc evaluated=2 transformed=2 completed=1 skipped=0 failed=1 interrupted=0 not_attempted=0"
    )
    json_summary = (
        "actual stage=json evaluated=0 transformed=0 completed=0 skipped=0 failed=0 interrupted=0 not_attempted=2"
        if aborted
        else "actual stage=json evaluated=2 transformed=2 completed=2 skipped=0 failed=0 interrupted=0 not_attempted=0"
        if continuing
        else "actual stage=json evaluated=1 transformed=1 completed=1 skipped=0 failed=0 interrupted=0 not_attempted=1"
    )
    assert desc_summary in lines
    assert json_summary in lines
    assert first.read_bytes() == second.read_bytes() == rig.original
    assert persisted.read_text(encoding="utf-8") == description
    a_json = Path(str(first) + ".desc.json")
    b_desc = Path(str(second) + ".desc.txt")
    b_json = Path(str(second) + ".desc.json")
    assert a_json.exists() is continuing
    assert b_desc.exists() is not aborted
    assert b_json.exists() is not aborted
    if continuing:
        envelope = json.loads(a_json.read_text(encoding="utf-8"))
        assert envelope["metadata"] == METADATA
        assert (
            envelope["provenance"]["description_sha256"]
            == hashlib.sha256(description.encode()).hexdigest()
        )
    if not aborted:
        assert b_desc.read_text(encoding="utf-8") == V2
        envelope = json.loads(b_json.read_text(encoding="utf-8"))
        assert envelope["metadata"] == METADATA
        assert (
            envelope["provenance"]["description_sha256"]
            == hashlib.sha256(V2.encode()).hexdigest()
        )
    expected_requests = (
        []
        if aborted
        else (["json", "desc", "json"] if continuing else ["desc", "json"])
    )
    assert [request[0] for request in rig.requests] == expected_requests
    if continuing:
        body = rig.requests[0][1]
        assert (
            json.loads(body["messages"][1]["content"][0]["text"])["description"]
            == description
        )
    # A4 counts provider-boundary attempts, including the rejected .xyz request
    # that enters the adapter but fails before HTTP transport.
    work = next(line for line in lines if line.startswith("work "))
    count = len(expected_requests) + 1
    assert f"requests={count} first_requests={count} retries=0" in work
