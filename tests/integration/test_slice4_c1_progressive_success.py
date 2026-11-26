"""Large progressive run with real stages and controlled successful providers.

No network, real model inference, or ExifTool write is claimed.
"""

import base64
import hashlib
import json
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

from image_clarus.artifacts import ArtifactService
from image_clarus.batch_execution import run_sequential
from image_clarus.batch_plan import Admission, PlanningInput, build_plan

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGNgYGAAAAAEAAH2FzhVAAAAAElFTkSuQmCC"
)
DESCRIPTION = "A fictional blue tile on a plain background."
METADATA = {"caption": "A blue tile."}


def test_progressive_success_ten_thousand(tmp_path):
    desc_prompt = tmp_path / "desc-prompt.txt"
    desc_prompt.write_text("Describe the fictional image.\n", encoding="utf-8")
    json_prompt = tmp_path / "json-prompt.txt"
    json_prompt.write_text("Extract the caption as JSON.\n", encoding="utf-8")
    schema = tmp_path / "schema.json"
    schema.write_text(
        json.dumps(
            {
                "type": "object",
                "properties": {"caption": {"type": "string", "minLength": 1}},
                "required": ["caption"],
                "additionalProperties": False,
            }
        ),
        encoding="utf-8",
    )
    config = {
        "state": {"directory": None, "accumulate_categories": False},
        "pipeline": {"missing_prerequisite": "skip", "on_stage_failure": "continue"},
        "models": {"fixture": {"provider": "fixture", "model_id": "synthetic"}},
        "providers": {"fixture": {}},
        "stages": {
            "desc": {
                "regenerate": False,
                "model": "fixture",
                "prompt_file": desc_prompt,
                "reasoning_effort": None,
            },
            "json": {
                "regenerate": False,
                "model": "fixture",
                "prompt_file": json_prompt,
                "schema_file": schema,
                "reasoning_effort": None,
                "validation_retries": 0,
                "preferred_categories": [],
            },
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
            "schema_version": "custom-sha256:"
            + hashlib.sha256(schema.read_bytes()).hexdigest(),
            "metadata": METADATA,
            "provenance": {
                "provider_alias": "fixture",
                "model_alias": "fixture",
                "model_id": "synthetic",
                "prompt_id": "custom",
                "description_sha256": hashlib.sha256(DESCRIPTION.encode()).hexdigest(),
            },
        }
    ).encode()
    paths = [tmp_path / f"{i:05}.png" for i in range(10_000)]
    for i, path in enumerate(paths):
        if i < 6000:
            Path(str(path) + ".desc.txt").write_text(DESCRIPTION, encoding="utf-8")
            Path(str(path) + ".desc.json").write_bytes(envelope)
        elif i < 7000:
            path.write_bytes(PNG)
        elif i >= 9000:
            Path(str(path) + ".desc.txt").write_text(DESCRIPTION, encoding="utf-8")
    plan = build_plan(
        (PlanningInput(str(p), ("synthetic", str(tmp_path), "file")) for p in paths),
        config,
        selected=("desc", "json", "xmp"),
        limit=1000,
    )
    assert plan.counts == {
        Admission.NO_LLM_WORK: 6000,
        Admission.ADMITTED: 1000,
        Admission.KNOWN_EXCLUDED: 3000,
    }
    assert [len(queue) for queue in plan.queues] == [1000, 0, 9000]
    calls = Counter()

    class Provider:
        def image(self, *, prompt, image_bytes, suffix, effort):
            assert prompt == desc_prompt.read_text(encoding="utf-8")
            assert image_bytes == PNG and suffix == ".png" and effort is None
            calls["image"] += 1
            return DESCRIPTION

        def structured(self, *, prompt, description, schema, effort, history):
            assert prompt == json_prompt.read_text(encoding="utf-8")
            assert description == DESCRIPTION and schema == json.loads(
                Path(config["stages"]["json"]["schema_file"]).read_text()
            )
            assert effort is None and history == []
            calls["structured"] += 1
            return json.dumps(METADATA)

    events = []
    result = run_sequential(
        plan,
        config,
        SimpleNamespace(
            artifacts=ArtifactService(), provider_factory=lambda *_: Provider()
        ),
        cwd=tmp_path,
        on_event=events.append,
    )
    assert calls == {"image": 1000, "structured": 1000}
    assert len(result.images) == 10_000
    assert sum(len(image.stages) for image in result.images) == 30_000
    evaluated = [
        event.image_id
        for event in events
        if event.kind == "stage_evaluated" and event.stage == "xmp"
    ]
    assert sorted(evaluated) == list(range(10_000))
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
                ("desc", "completed", None, None),
                ("json", "completed", None, None),
                ("xmp", "skipped", "no_change", None),
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
    for path in paths[6000:7000]:
        desc = Path(str(path) + ".desc.txt")
        structure = Path(str(path) + ".desc.json")
        assert desc.read_text(encoding="utf-8") == DESCRIPTION
        value = json.loads(structure.read_text(encoding="utf-8"))
        assert value["metadata"] == METADATA
        assert (
            value["schema_version"]
            == "custom-sha256:" + hashlib.sha256(schema.read_bytes()).hexdigest()
        )
        assert (
            value["provenance"]["description_sha256"]
            == hashlib.sha256(DESCRIPTION.encode()).hexdigest()
        )
        assert path.read_bytes() == PNG
    assert all(not Path(str(p) + ".desc.txt").exists() for p in paths[7000:9000])
    assert all(not Path(str(p) + ".desc.json").exists() for p in paths[7000:])
    assert not any(tmp_path.glob("*.xmp"))
