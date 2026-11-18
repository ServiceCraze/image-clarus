"""C1 persisted publication via independent CLI invocations and real ExifTool.

The provider and one-pixel PNG are fictional fixtures from the B5 integration rig.
"""

import hashlib
import json
import os
import subprocess
import sys

import pytest

pytest_plugins = ("test_xmp_cli_b5",)


def read_fields(tool, sidecar):
    result = subprocess.run(
        [
            tool,
            "-config",
            "",
            "-j",
            "-G1",
            "-s",
            "-XMP-digiKam:TagsList",
            "-XMP-dc:Title",
            "-XMP-dc:Description",
            "-XMP-digiKam:CaptionsAuthorNames",
            "--",
            str(sidecar),
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=20,
    )
    return json.loads(result.stdout)[0]


def source_hash(r):
    return hashlib.sha256(r.image.read_bytes()).hexdigest()


@pytest.mark.parametrize(
    "root,expected",
    [
        (
            "stages.xmp.tag_root=fictional",
            ["fictional/one/first", "fictional/two/second"],
        ),
        ('stages.xmp.tag_root=""', ["one/first", "two/second"]),
    ],
)
def test_independent_xmp_consumes_swapped_persisted_json(
    rig, real_exiftool, root, expected
):
    before = source_hash(rig)
    rig.desc.write_text("Fictional persisted description.\n")
    out, err = rig.finish(rig.start("--stages", "json"))
    assert out.startswith("json: completed") and not err
    assert [request[0] for request in rig.requests] == ["json"]
    data = json.loads(rig.structured.read_bytes())
    assert data["metadata"]["title"] == "Blue square"
    data["metadata"].update(
        {
            "title": "Swapped fictional title",
            "caption": "Swapped fictional caption",
            "tag_candidates": [
                ["one", "first"],
                ["two", "second"],
                ["three", "cutoff"],
            ],
        }
    )
    rig.structured.write_text(json.dumps(data))
    persisted = rig.structured.read_bytes()
    out, err = rig.finish(
        rig.start(
            "--stages",
            "xmp",
            "--set",
            root,
            "--set",
            "stages.xmp.tag_limit=2",
            "--set",
            'stages.xmp.caption_author="Fictional Writer"',
            config=rig.no_model_cfg,
        )
    )
    assert out.startswith("xmp: completed") and not err
    assert [request[0] for request in rig.requests] == ["json"]
    assert rig.structured.read_bytes() == persisted
    fields = read_fields(real_exiftool, rig.xmp)
    assert fields["XMP-digiKam:TagsList"] == expected
    assert fields["XMP-dc:Title"] == "Swapped fictional title"
    assert fields["XMP-dc:Description"] == "Swapped fictional caption"
    assert fields["XMP-digiKam:CaptionsAuthorNames"] == "Fictional Writer"
    assert source_hash(rig) == before


@pytest.mark.parametrize(
    "title_policy,caption_policy,author_policy,expected",
    [
        (
            "overwrite",
            "new",
            "disabled",
            ("Swapped title", "Old caption", "Old author"),
        ),
        (
            "disabled",
            "overwrite",
            "new",
            ("Old title", "Swapped caption", "Old author"),
        ),
        ("new", "disabled", "overwrite", ("Old title", "Old caption", "New author")),
    ],
)
def test_independent_field_policies_on_existing_sidecar(
    rig, real_exiftool, title_policy, caption_policy, author_policy, expected
):
    from test_xmp_cli_b5 import envelope

    before = source_hash(rig)
    data = envelope()
    data["metadata"] = dict(
        data["metadata"], title="Swapped title", caption="Swapped caption"
    )
    rig.structured.write_text(json.dumps(data))
    rig.xmp.write_text("""<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
      xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dk="http://www.digikam.org/ns/1.0/">
      <rdf:Description rdf:about=""><dc:title><rdf:Alt><rdf:li xml:lang="x-default">Old title</rdf:li></rdf:Alt></dc:title>
      <dc:description><rdf:Alt><rdf:li xml:lang="x-default">Old caption</rdf:li></rdf:Alt></dc:description>
      <dk:CaptionsAuthorNames><rdf:Alt><rdf:li xml:lang="x-default">Old author</rdf:li></rdf:Alt></dk:CaptionsAuthorNames>
      </rdf:Description></rdf:RDF>""")
    out, err = rig.finish(
        rig.start(
            "--stages",
            "xmp",
            "--set",
            "stages.xmp.tag_policy=disabled",
            "--set",
            f"stages.xmp.title_policy={title_policy}",
            "--set",
            f"stages.xmp.caption_policy={caption_policy}",
            "--set",
            f"stages.xmp.caption_author_policy={author_policy}",
            "--set",
            'stages.xmp.caption_author="New author"',
            config=rig.no_model_cfg,
        )
    )
    assert out.startswith("xmp: completed") and not err
    fields = read_fields(real_exiftool, rig.xmp)
    assert (
        fields["XMP-dc:Title"],
        fields["XMP-dc:Description"],
        fields["XMP-digiKam:CaptionsAuthorNames"],
    ) == expected
    assert not rig.requests
    assert source_hash(rig) == before


def test_composed_pipeline_rereads_json_from_disk_at_stage_boundary(
    rig, real_exiftool, tmp_path
):
    """Instrument the stage boundary, not the JSON writer or XMP reader."""
    from test_xmp_cli_b5 import ROOT, envelope

    before = source_hash(rig)
    rig.desc.write_text("Fictional persisted description.\n")
    replacement = envelope()
    replacement["metadata"] = dict(
        replacement["metadata"],
        title="Boundary title",
        caption="Boundary caption",
        tag_candidates=[["boundary", "first"]],
    )
    replacement_bytes = json.dumps(replacement).encode()
    marker = tmp_path / "boundary-reached"
    (tmp_path / "sitecustomize.py").write_text(
        "from pathlib import Path\n"
        "from image_clarus.stages import xmp\n"
        "original = xmp.run_xmp\n"
        "def wrapped(image, config, services):\n"
        f"    Path(str(image) + '.desc.json').write_bytes({replacement_bytes!r})\n"
        f"    Path({str(marker)!r}).touch()\n"
        "    return original(image, config, services)\n"
        "xmp.run_xmp = wrapped\n"
    )
    env = dict(os.environ)
    env.update(
        HOME=str(tmp_path / "home"),
        PYTHONPATH=os.pathsep.join((str(tmp_path), str(ROOT / "src"))),
        NO_PROXY="*",
        no_proxy="*",
    )
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "image_clarus",
            "process",
            str(rig.image),
            "--config",
            str(tmp_path / "config.yaml"),
            "--stages",
            "json,xmp",
        ],
        cwd=tmp_path,
        env=env,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, (result.stdout, result.stderr)
    assert [line.split(":")[0] for line in result.stdout.splitlines()] == [
        "json",
        "xmp",
    ]
    assert marker.exists() and rig.structured.read_bytes() == replacement_bytes
    fields = read_fields(real_exiftool, rig.xmp)
    assert fields["XMP-dc:Title"] == "Boundary title"
    assert fields["XMP-dc:Description"] == "Boundary caption"
    assert fields["XMP-digiKam:TagsList"] in (
        "ai/boundary/first",
        ["ai/boundary/first"],
    )
    assert [request[0] for request in rig.requests] == ["json"]
    assert source_hash(rig) == before


def test_xmp_only_ignores_invalid_unselected_json_settings_and_credentials(
    rig, real_exiftool, tmp_path
):
    from test_xmp_cli_b5 import ROOT, envelope

    config = tmp_path / "unused-config.yaml"
    config.write_text(
        "providers:\n  example:\n    base_url: https://provider.example/v1\n"
        "    api_key_env: FICTIONAL_UNUSED_KEY\n"
        "models:\n  text:\n    provider: example\n    model_id: fictional\n"
        "stages:\n  json:\n    model: missing-model\n    validation_retries: -1\n"
    )
    rig.structured.write_text(json.dumps(envelope()))
    before = source_hash(rig)
    env = dict(os.environ, HOME=str(tmp_path / "home"), PYTHONPATH=str(ROOT / "src"))
    env.pop("FICTIONAL_UNUSED_KEY", None)
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "image_clarus",
            "process",
            str(rig.image),
            "--stages",
            "xmp",
            "--config",
            str(config),
        ],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, (result.stdout, result.stderr)
    assert result.stdout.startswith("xmp: completed") and not result.stderr
    assert read_fields(real_exiftool, rig.xmp)["XMP-dc:Title"] == "Blue square"
    assert not rig.requests and source_hash(rig) == before
