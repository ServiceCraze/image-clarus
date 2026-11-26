"""Large progressive sequential execution with real stage decisions and local files.

The synthetic provider fails deliberately; no inference or ExifTool write is claimed.
"""

import json
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

from image_clarus.artifacts import ArtifactService
from image_clarus.batch_execution import run_sequential
from image_clarus.batch_plan import Admission, PlanningInput, build_plan, route


def test_progressive_ten_thousand_real_stage_evaluations(tmp_path):
    config = {
        "state": {"directory": None, "accumulate_categories": False},
        "pipeline": {"missing_prerequisite": "skip", "on_stage_failure": "continue"},
        "models": {"fixture": {"provider": "fixture"}},
        "providers": {"fixture": {}},
        "stages": {
            "desc": {
                "regenerate": False,
                "model": "fixture",
                "prompt_file": None,
                "reasoning_effort": None,
            },
            "json": {"regenerate": False},
            "xmp": {
                "regenerate": False,
                "tag_root": "",
                "tag_policy": "disabled",
                "tag_limit": 0,
                "title_policy": "disabled",
                "caption_policy": "disabled",
                "caption_author_policy": "disabled",
                "caption_author": "",
                "custom_title_property": None,
                "custom_caption_property": None,
                "custom_tags_property": None,
            },
        },
    }
    envelope = json.dumps(
        {
            "format_version": 1,
            "schema_id": "urn:image-clarus:custom-metadata-schema",
            "schema_version": "custom-sha256:" + "a" * 64,
            "metadata": {},
            "provenance": {
                "provider_alias": "fixture",
                "model_alias": "fixture",
                "model_id": "fixture",
                "prompt_id": "fixture",
                "description_sha256": "a" * 64,
            },
        }
    ).encode()
    paths = [tmp_path / f"{i:05}.jpg" for i in range(10_000)]
    for i, path in enumerate(paths):
        if i < 6000:
            Path(str(path) + ".desc.txt").write_text(
                "Fictional description", encoding="utf-8"
            )
            Path(str(path) + ".desc.json").write_bytes(envelope)
        elif i >= 9000:
            Path(str(path) + ".desc.txt").write_text(
                "Fictional description", encoding="utf-8"
            )
        elif i < 7000:
            path.write_bytes(b"synthetic image bytes")
    inputs = (
        PlanningInput(str(p), ("synthetic", str(tmp_path), "file")) for p in paths
    )
    plan = build_plan(inputs, config, selected=("desc", "json", "xmp"), limit=1000)
    assert len(plan.rows) == 10_000
    assert tuple(s.name for s in plan.stages) == ("desc", "json", "xmp")
    assert plan.counts == {
        Admission.NO_LLM_WORK: 6000,
        Admission.ADMITTED: 1000,
        Admission.KNOWN_EXCLUDED: 3000,
    }
    assert [len(q) for q in plan.queues] == [1000, 0, 9000]
    assert Counter(route(row, plan.stages)[0] for row in plan.rows) == {
        0: 1000,
        2: 9000,
    }

    class UnavailableProvider:
        def image(self, **_kwargs):
            raise RuntimeError("controlled provider failure")

    calls = []

    def provider_factory(*_args):
        calls.append(1)
        return UnavailableProvider()

    events = []
    result = run_sequential(
        plan,
        config,
        SimpleNamespace(artifacts=ArtifactService(), provider_factory=provider_factory),
        cwd=tmp_path,
        on_event=events.append,
    )
    assert len(result.images) == 10_000
    assert sum(len(image.stages) for image in result.images) == 30_000
    evaluated = [
        e.image_id for e in events if e.kind == "stage_evaluated" and e.stage == "xmp"
    ]
    assert sorted(evaluated) == list(range(10_000))
    assert len(calls) == 1000
    assert (
        sum(e.kind == "transform_started" and e.stage == "desc" for e in events) == 1000
    )
    for i, image in enumerate(result.images):
        actual = [
            (
                s.stage,
                s.disposition,
                s.reason_code,
                s.result.error_category if s.result else None,
            )
            for s in image.stages
        ]
        if i < 6000:
            expected = [
                ("desc", "skipped", "output_exists", None),
                ("json", "skipped", "output_exists", None),
                ("xmp", "skipped", "no_change", None),
            ]
        elif i < 7000:
            expected = [
                ("desc", "failed", None, "provider_unavailable"),
                ("json", "skipped", "missing_prerequisite", None),
                ("xmp", "skipped", "missing_prerequisite", None),
            ]
        elif i < 9000:
            expected = [
                ("desc", "skipped", "budget_excluded", None),
                ("json", "skipped", "budget_excluded", None),
                ("xmp", "skipped", "missing_prerequisite", None),
            ]
        else:
            expected = [
                ("desc", "skipped", "output_exists", None),
                ("json", "skipped", "budget_excluded", None),
                ("xmp", "skipped", "missing_prerequisite", None),
            ]
        assert actual == expected, (i, actual)
    assert not any(tmp_path.glob("*.xmp"))
    assert all(not Path(str(p) + ".desc.txt").exists() for p in paths[6000:9000])
