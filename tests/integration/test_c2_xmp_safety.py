"""C2 XMP preservation, recovery, and process-overlap checks.

Fixtures contain fictional metadata and a synthetic image. ExifTool is used
locally; no external service, personal image, or digiKam operation is involved.
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from test_xmp_cli_b5 import envelope, matching_xmp

from image_clarus.xmp_backend import FIELDS, ExifToolBackend

pytest_plugins = ("test_xmp_cli_b5",)


@pytest.fixture
def real_exiftool():
    tool = shutil.which("exiftool")
    if tool is None:
        pytest.skip("C2 requires real ExifTool on PATH")
    return tool


def rich_xmp():
    return b"""<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
      xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dk="http://www.digikam.org/ns/1.0/"
      xmlns:lr="http://ns.adobe.com/lightroom/1.0/"
      xmlns:tiff="http://ns.adobe.com/tiff/1.0/" xmlns:exif="http://ns.adobe.com/exif/1.0/"
      xmlns:fiction="urn:fictional:camera">
      <rdf:Description rdf:about="">
        <dk:TagsList><rdf:Seq><rdf:li>ai/old</rdf:li><rdf:li>manual/pear</rdf:li>
          <rdf:li>auto/pear</rdf:li><rdf:li>aisle/plant</rdf:li><rdf:li>ai/food/old</rdf:li>
        </rdf:Seq></dk:TagsList>
        <dc:subject><rdf:Bag><rdf:li>pear</rdf:li><rdf:li>ai/old</rdf:li>
          <rdf:li>manual keyword</rdf:li></rdf:Bag></dc:subject>
        <lr:hierarchicalSubject><rdf:Bag><rdf:li>ai|old</rdf:li>
          <rdf:li>manual|pear</rdf:li></rdf:Bag></lr:hierarchicalSubject>
        <dc:title><rdf:Alt><rdf:li xml:lang="x-default">Original title</rdf:li>
          <rdf:li xml:lang="fr">Titre original</rdf:li></rdf:Alt></dc:title>
        <dc:description><rdf:Alt><rdf:li xml:lang="x-default">Original caption</rdf:li>
          <rdf:li xml:lang="fr">Description originale</rdf:li></rdf:Alt></dc:description>
        <dk:CaptionsAuthorNames><rdf:Alt><rdf:li xml:lang="x-default">Original author</rdf:li>
          <rdf:li xml:lang="fr">Auteur original</rdf:li></rdf:Alt></dk:CaptionsAuthorNames>
        <tiff:Make>Fictional Camera</tiff:Make>
        <exif:ExposureTime>1/60</exif:ExposureTime>
        <fiction:note>Unrelated fictional property</fiction:note>
      </rdf:Description>
    </rdf:RDF>"""


def configured_metadata(
    *, title="Updated title", caption="Updated caption", paths=None
):
    data = envelope()
    data["metadata"] = dict(
        data["metadata"],
        title=title,
        caption=caption,
        tag_candidates=paths
        if paths is not None
        else [["food", "pear"], ["weather", "sunny"]],
    )
    return data


def run_xmp(rig, *args, code=0):
    out, err = rig.finish(
        rig.start("--stages", "xmp", *args, config=rig.no_model_cfg), code
    )
    assert not err, err
    assert not rig.requests
    return out


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def exiftool_fields(tool, sidecar):
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
            "-XMP-dc:Title-fr",
            "-XMP-dc:Description",
            "-XMP-dc:Description-fr",
            "-XMP-digiKam:CaptionsAuthorNames",
            "-XMP-digiKam:CaptionsAuthorNames-fr",
            "--",
            str(sidecar),
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=20,
    )
    return json.loads(result.stdout)[0]


def non_default_alternatives(properties, name):
    value = properties.get(name)
    if value is None:
        return None
    return value[0], tuple(
        (lang, text) for lang, text in value[1] if lang != "x-default"
    )


def assert_unrelated_properties_preserved(before, after, changed_fields=()):
    changed = {FIELDS[field][0] for field in changed_fields}
    for name, value in before["properties"].items():
        if name not in changed:
            assert after["properties"].get(name) == value, name
    for field in changed_fields:
        if field == "tags":
            continue
        name = FIELDS[field][0]
        assert non_default_alternatives(
            before["properties"], name
        ) == non_default_alternatives(after["properties"], name), field


def test_nonempty_overwrite_preserves_ambiguous_tags_and_unrelated_xmp(
    rig, real_exiftool
):
    rig.structured.write_text(json.dumps(configured_metadata()))
    original = rich_xmp()
    rig.xmp.write_bytes(original)
    before_hash = sha256(rig.image)
    before = ExifToolBackend(rig.image.parent).read(original)

    out = run_xmp(
        rig,
        "--set",
        "stages.xmp.tag_policy=overwrite",
        "--set",
        "stages.xmp.title_policy=overwrite",
        "--set",
        "stages.xmp.caption_policy=overwrite",
    )

    assert out.startswith("xmp: completed")
    after = ExifToolBackend(rig.image.parent).read(rig.xmp.read_bytes())
    assert after["tags"] == [
        "manual/pear",
        "auto/pear",
        "aisle/plant",
        "ai/food/pear",
        "ai/weather/sunny",
    ]
    assert after["title"] == "Updated title"
    assert after["caption"] == "Updated caption"
    assert after["author"] == "Original author"
    assert_unrelated_properties_preserved(before, after, ("tags", "title", "caption"))
    fields = exiftool_fields(real_exiftool, rig.xmp)
    assert fields["XMP-digiKam:TagsList"] == after["tags"]
    assert fields["XMP-dc:Title"] == "Updated title"
    assert fields["XMP-dc:Title-fr"] == "Titre original"
    assert fields["XMP-dc:Description"] == "Updated caption"
    assert fields["XMP-dc:Description-fr"] == "Description originale"
    assert fields["XMP-digiKam:CaptionsAuthorNames"] == "Original author"
    assert fields["XMP-digiKam:CaptionsAuthorNames-fr"] == "Auteur original"
    assert sha256(rig.image) == before_hash


@pytest.mark.parametrize("policy", ["add", "new", "overwrite", "disabled"])
def test_explicit_empty_root_never_deletes_existing_tag_assignments(
    rig, real_exiftool, policy
):
    rig.structured.write_text(
        json.dumps(configured_metadata(paths=[["food", "pepper"], ["food", "pizza"]]))
    )
    original = rich_xmp()
    rig.xmp.write_bytes(original)
    before = ExifToolBackend(rig.image.parent).read(original)
    before_hash = sha256(rig.image)

    out = run_xmp(
        rig,
        "--set",
        'stages.xmp.tag_root=""',
        "--set",
        f"stages.xmp.tag_policy={policy}",
        "--set",
        "stages.xmp.title_policy=disabled",
        "--set",
        "stages.xmp.caption_policy=disabled",
    )

    after = ExifToolBackend(rig.image.parent).read(rig.xmp.read_bytes())
    expected = (
        before["tags"]
        if policy == "disabled"
        else before["tags"] + ["food/pepper", "food/pizza"]
    )
    assert after["tags"] == expected
    assert len(after["tags"]) == len(set(after["tags"]))
    assert_unrelated_properties_preserved(before, after, ("tags",))
    assert ("skipped — reason=no_change" in out) == (policy == "disabled")
    assert sha256(rig.image) == before_hash
    fields = exiftool_fields(real_exiftool, rig.xmp)
    assert fields["XMP-digiKam:TagsList"] == expected


def test_configured_author_overwrite_changes_only_x_default(rig, real_exiftool):
    rig.structured.write_text(json.dumps(configured_metadata()))
    original = rich_xmp()
    rig.xmp.write_bytes(original)
    before = ExifToolBackend(rig.image.parent).read(original)
    before_hash = sha256(rig.image)

    out = run_xmp(
        rig,
        "--set",
        "stages.xmp.tag_policy=disabled",
        "--set",
        "stages.xmp.title_policy=disabled",
        "--set",
        "stages.xmp.caption_policy=disabled",
        "--set",
        'stages.xmp.caption_author="Fictional Editor"',
        "--set",
        "stages.xmp.caption_author_policy=overwrite",
    )

    assert out.startswith("xmp: completed")
    after = ExifToolBackend(rig.image.parent).read(rig.xmp.read_bytes())
    assert after["author"] == "Fictional Editor"
    assert_unrelated_properties_preserved(before, after, ("author",))
    fields = exiftool_fields(real_exiftool, rig.xmp)
    assert fields["XMP-digiKam:CaptionsAuthorNames"] == "Fictional Editor"
    assert fields["XMP-digiKam:CaptionsAuthorNames-fr"] == "Auteur original"
    assert sha256(rig.image) == before_hash


def test_new_policy_respects_nondefault_only_language_alternative(rig, real_exiftool):
    rig.structured.write_text(json.dumps(configured_metadata()))
    original = rich_xmp().replace(
        b'<rdf:li xml:lang="x-default">Original title</rdf:li>', b""
    )
    rig.xmp.write_bytes(original)

    out = run_xmp(
        rig,
        "--set",
        "stages.xmp.tag_policy=disabled",
        "--set",
        "stages.xmp.title_policy=new",
        "--set",
        "stages.xmp.caption_policy=disabled",
    )

    assert out == "xmp: skipped — reason=no_change\n"
    assert rig.xmp.read_bytes() == original
    fields = exiftool_fields(real_exiftool, rig.xmp)
    assert "XMP-dc:Title" not in fields
    assert fields["XMP-dc:Title-fr"] == "Titre original"


def test_absent_xmp_recovers_valid_backup_before_no_change(rig, real_exiftool):
    rig.structured.write_text(json.dumps(envelope()))
    backup = Path(str(rig.xmp) + ".bak")
    backup.write_bytes(matching_xmp())
    before_hash = sha256(rig.image)

    out = run_xmp(rig)

    assert out == "xmp: skipped — reason=no_change\n"
    assert rig.xmp.read_bytes() == matching_xmp()
    assert not backup.exists()
    assert exiftool_fields(real_exiftool, rig.xmp)["XMP-dc:Title"] == "Blue square"
    assert sha256(rig.image) == before_hash


def test_valid_destination_remains_authoritative_over_valid_backup(rig, real_exiftool):
    rig.structured.write_text(json.dumps(envelope()))
    destination = rich_xmp()
    backup = matching_xmp()
    rig.xmp.write_bytes(destination)
    backup_path = Path(str(rig.xmp) + ".bak")
    backup_path.write_bytes(backup)
    before_hash = sha256(rig.image)

    out = run_xmp(
        rig,
        "--set",
        "pipeline.backup_retention=retain",
        "--set",
        "stages.xmp.tag_policy=disabled",
        "--set",
        "stages.xmp.title_policy=disabled",
        "--set",
        "stages.xmp.caption_policy=disabled",
    )

    assert out == "xmp: skipped — reason=no_change\n"
    assert rig.xmp.read_bytes() == destination
    assert backup_path.read_bytes() == backup
    assert exiftool_fields(real_exiftool, rig.xmp)["XMP-dc:Title"] == "Original title"
    assert sha256(rig.image) == before_hash


def test_xmp_writers_overlap_in_separate_processes_without_corrupting_sidecar(
    rig, real_exiftool, tmp_path
):
    from test_xmp_cli_b5 import ROOT as PROJECT_ROOT

    rig.structured.write_text(
        json.dumps(configured_metadata(title="", caption="", paths=[["leaf"]]))
    )
    initial = rich_xmp()
    rig.xmp.write_bytes(initial)
    config = tmp_path / "xmp-concurrency.yaml"
    config.write_text(
        "pipeline:\n  backup_retention: retain\n"
        "stages:\n  xmp:\n    tag_policy: add\n"
        "    title_policy: disabled\n    caption_policy: disabled\n"
    )
    marker = tmp_path / "xmp-writer-barrier"
    marker.mkdir()
    (tmp_path / "sitecustomize.py").write_text(
        "from pathlib import Path\n"
        "import os, time\n"
        "from image_clarus.artifacts import ArtifactService\n"
        "original = ArtifactService._point\n"
        "def barrier(self, name):\n"
        "    if name == 'destination_replace':\n"
        f"        Path({str(marker)!r}, 'ready-' + str(os.getpid())).touch()\n"
        "        deadline = time.monotonic() + 25\n"
        f"        while len(list(Path({str(marker)!r}).glob('ready-*'))) < 2:\n"
        "            if time.monotonic() >= deadline:\n"
        "                raise RuntimeError('test barrier timeout')\n"
        "            time.sleep(0.01)\n"
        "    return original(self, name)\n"
        "ArtifactService._point = barrier\n"
    )
    env = dict(os.environ)
    env.update(
        PYTHONPATH=os.pathsep.join((str(tmp_path), str(PROJECT_ROOT / "src"))),
        PATH=os.pathsep.join(
            (str(Path(real_exiftool).parent), os.environ.get("PATH", ""))
        ),
        NO_PROXY="*",
        no_proxy="*",
    )
    before_hash = sha256(rig.image)
    processes = []
    try:
        for root in ("alpha", "beta"):
            processes.append(
                subprocess.Popen(
                    [
                        sys.executable,
                        "-m",
                        "image_clarus",
                        "process",
                        str(rig.image),
                        "--config",
                        str(config),
                        "--stages",
                        "xmp",
                        "--set",
                        f"stages.xmp.tag_root={root}",
                    ],
                    cwd=tmp_path,
                    env=env,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
            )
        reports = [process.communicate(timeout=45) for process in processes]
        assert [process.returncode for process in processes] == [0, 0], reports
        assert all(
            stdout.startswith("xmp: completed") and not stderr
            for stdout, stderr in reports
        )
    finally:
        for process in processes:
            if process.poll() is None:
                process.kill()
            process.communicate(timeout=10)

    assert len(list(marker.glob("ready-*"))) == 2
    backend = ExifToolBackend(rig.image.parent)
    after = backend.read(rig.xmp.read_bytes())
    candidates = {
        (
            "ai/old",
            "manual/pear",
            "auto/pear",
            "aisle/plant",
            "ai/food/old",
            "alpha/leaf",
        ),
        (
            "ai/old",
            "manual/pear",
            "auto/pear",
            "aisle/plant",
            "ai/food/old",
            "beta/leaf",
        ),
    }
    assert tuple(after["tags"]) in candidates
    assert backend.validate(rig.xmp.read_bytes()) is True
    assert backend.validate(Path(str(rig.xmp) + ".bak").read_bytes()) is True
    assert tuple(
        backend.read(Path(str(rig.xmp) + ".bak").read_bytes())["tags"]
    ) == tuple(backend.read(initial)["tags"])
    fields = exiftool_fields(real_exiftool, rig.xmp)
    assert fields["XMP-digiKam:TagsList"] == after["tags"]
    assert sha256(rig.image) == before_hash
    assert not [path for path in tmp_path.iterdir() if "image-clarus-" in path.name]
