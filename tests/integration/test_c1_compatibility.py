"""C1 supplemental black-box compatibility tests with synthetic artifacts only."""

import copy
import json
import shutil
from xml.etree import ElementTree

import pytest
from test_xmp_cli_b5 import METADATA, assert_source, envelope, matching_xmp

pytest_plugins = ("test_xmp_cli_b5",)


@pytest.fixture
def exiftool():
    tool = shutil.which("exiftool")
    if tool is None:
        pytest.skip("C1 real ExifTool unavailable on PATH")
    return tool


def old_envelope():
    value = copy.deepcopy(envelope())
    value["schema_id"] = "urn:image-clarus:metadata-schema:1.0.0"
    value["schema_version"] = "1.0.0"
    for key in ("title", "caption", "tag_candidates"):
        del value["metadata"][key]
    return value


def custom(metadata):
    value = copy.deepcopy(envelope())
    value.update(
        schema_id="urn:image-clarus:custom-metadata-schema",
        schema_version="custom-sha256:" + "a" * 64,
        metadata=metadata,
    )
    return value


def mapping():
    return [
        "--set",
        "stages.xmp.custom_title_property=headline",
        "--set",
        "stages.xmp.custom_caption_property=summary",
        "--set",
        "stages.xmp.custom_tags_property=paths",
    ]


def run_xmp(rig, *args, code=0):
    out, err = rig.finish(
        rig.start("--stages", "xmp", *args, config=rig.no_model_cfg), code
    )
    assert not err and not rig.requests
    assert_source(rig)
    return out


def test_historical_v1_and_unmapped_custom_are_noops(rig, exiftool):
    for value in (
        old_envelope(),
        custom({"title": "Not inferred", "tag_candidates": [["hidden"]]}),
    ):
        raw = json.dumps(value).encode()
        rig.structured.write_bytes(raw)
        assert run_xmp(rig) == "xmp: skipped — reason=no_change\n"
        assert rig.structured.read_bytes() == raw and not rig.xmp.exists()


def test_custom_partial_mapping_writes_only_supplied_fields(rig, exiftool):
    value = custom({"headline": "Fictional title", "paths": [["shape", "square"]]})
    raw = json.dumps(value).encode()
    rig.structured.write_bytes(raw)
    out = run_xmp(rig, *mapping())
    assert out.startswith("xmp: completed")
    root = ElementTree.fromstring(rig.xmp.read_bytes())
    ns = {
        "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
        "dc": "http://purl.org/dc/elements/1.1/",
        "dk": "http://www.digikam.org/ns/1.0/",
    }
    title = root.find(".//dc:title/rdf:Alt/rdf:li", ns)
    assert title is not None and title.text == "Fictional title"
    assert [n.text for n in root.findall(".//dk:TagsList/rdf:Seq/rdf:li", ns)] == [
        "ai/shape/square"
    ]
    assert root.find(".//dc:description", ns) is None
    assert rig.structured.read_bytes() == raw
    sidecar = rig.xmp.read_bytes()
    assert run_xmp(rig, *mapping()) == "xmp: skipped — reason=no_change\n"
    assert rig.xmp.read_bytes() == sidecar


@pytest.mark.parametrize("metadata", [{}, {"headline": "", "summary": "", "paths": []}])
def test_missing_and_empty_mapped_values_are_noops(rig, exiftool, metadata):
    rig.structured.write_text(json.dumps(custom(metadata)))
    assert run_xmp(rig, *mapping()) == "xmp: skipped — reason=no_change\n"
    assert not rig.xmp.exists()


@pytest.mark.parametrize(
    "metadata",
    [{"headline": None}, {"summary": 4}, {"paths": None}, {"paths": [["bad/path"]]}],
)
def test_present_invalid_mapped_values_fail_not_skip(rig, exiftool, metadata):
    raw = json.dumps(custom(metadata)).encode()
    rig.structured.write_bytes(raw)
    out = run_xmp(rig, *mapping(), "--missing-prerequisite", "skip", code=1)
    assert out.startswith("xmp: failed — category=invalid_artifact")
    assert rig.structured.read_bytes() == raw and not rig.xmp.exists()


@pytest.mark.parametrize(
    "raw",
    [
        b'{"broken":',
        json.dumps({**old_envelope(), "schema_version": "9.0.0"}).encode(),
        json.dumps({**old_envelope(), "metadata": {}}).encode(),
    ],
)
def test_malformed_or_incompatible_artifact_fails(rig, exiftool, raw):
    rig.structured.write_bytes(raw)
    out = run_xmp(rig, "--missing-prerequisite", "skip", code=1)
    assert out.startswith("xmp: failed — category=invalid_artifact")
    assert rig.structured.read_bytes() == raw and not rig.xmp.exists()


@pytest.mark.parametrize(
    "policy,code,result",
    [
        ("fail", 1, "failed — category=missing_prerequisite"),
        ("skip", 0, "skipped — reason=missing_prerequisite"),
    ],
)
def test_missing_prerequisite_policy(rig, exiftool, policy, code, result):
    assert run_xmp(rig, "--missing-prerequisite", policy, code=code).startswith(
        "xmp: " + result
    )
    assert (
        not rig.structured.exists() and not rig.desc.exists() and not rig.xmp.exists()
    )


def test_old_json_skips_without_description_then_full_regenerate(rig, exiftool):
    raw = json.dumps(old_envelope(), indent=2).encode()
    rig.structured.write_bytes(raw)
    out, err = rig.finish(rig.start("--stages", "json"))
    assert out == "json: skipped — reason=output_exists\n" and not err
    assert (
        not rig.requests
        and not rig.desc.exists()
        and rig.structured.read_bytes() == raw
    )
    out, err = rig.finish(rig.start("--regenerate"))
    assert not err
    assert [line.split(":")[0] for line in out.splitlines()] == ["desc", "json", "xmp"]
    assert all(": completed — output=" in line for line in out.splitlines())
    assert [r[0] for r in rig.requests] == ["desc", "json"]
    new = json.loads(rig.structured.read_bytes())
    assert new["schema_id"] == "urn:image-clarus:metadata-schema:2.0.0"
    assert new["schema_version"] == "2.0.0" and new["metadata"] == METADATA
    assert rig.structured.read_bytes() != raw and rig.xmp.exists()
    assert_source(rig)


def test_empty_optional_values_under_overwrite_do_not_clear_existing_xmp(rig, exiftool):
    rig.structured.write_text(
        json.dumps(custom({"headline": "", "summary": "", "paths": []}))
    )
    original = matching_xmp()
    rig.xmp.write_bytes(original)
    out = run_xmp(
        rig,
        *mapping(),
        "--set",
        "stages.xmp.title_policy=overwrite",
        "--set",
        "stages.xmp.caption_policy=overwrite",
        "--set",
        "stages.xmp.tag_policy=overwrite",
    )
    assert out == "xmp: skipped — reason=no_change\n"
    assert rig.xmp.read_bytes() == original


def test_custom_duplicate_paths_deduplicate_before_rank_cutoff(rig, exiftool):
    rig.structured.write_text(
        json.dumps(custom({"paths": [["one"], ["one"], ["two"], ["three"]]}))
    )
    out = run_xmp(rig, *mapping(), "--set", "stages.xmp.tag_limit=2")
    assert out.startswith("xmp: completed")
    root = ElementTree.fromstring(rig.xmp.read_bytes())
    ns = {
        "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
        "dk": "http://www.digikam.org/ns/1.0/",
    }
    assert [n.text for n in root.findall(".//dk:TagsList/rdf:Seq/rdf:li", ns)] == [
        "ai/one",
        "ai/two",
    ]


def test_invalid_path_after_rank_cutoff_fails_before_publication(rig, exiftool):
    rig.structured.write_text(json.dumps(custom({"paths": [["one"], ["bad/path"]]})))
    out = run_xmp(rig, *mapping(), "--set", "stages.xmp.tag_limit=1", code=1)
    assert out.startswith("xmp: failed — category=invalid_artifact")
    assert not rig.xmp.exists()


def test_json_only_missing_description_can_skip_without_running_desc(rig):
    out, err = rig.finish(
        rig.start("--stages", "json", "--missing-prerequisite", "skip")
    )
    assert out == "json: skipped — reason=missing_prerequisite\n" and not err
    assert not rig.requests and not rig.desc.exists() and not rig.structured.exists()
    assert_source(rig)


@pytest.mark.parametrize("digest", [None, "a" * 64, "invalid"])
def test_xmp_cli_accepts_optional_hash_and_rejects_invalid(rig, exiftool, digest):
    value = copy.deepcopy(envelope())
    value["provenance"].pop("prompt_sha256", None)
    if digest is not None:
        value["provenance"]["prompt_sha256"] = digest
    raw = json.dumps(value).encode()
    rig.structured.write_bytes(raw)
    out = run_xmp(rig, code=1 if digest == "invalid" else 0)
    if digest == "invalid":
        assert out.startswith("xmp: failed — category=invalid_artifact")
        assert not rig.xmp.exists()
    else:
        assert out.startswith("xmp: completed")
        assert rig.xmp.exists()
    assert rig.structured.read_bytes() == raw
