import shutil
import stat

import pytest

from image_clarus.xmp_backend import EMPTY, ExifToolBackend, XmpBackendError


def test_missing_backend_reports_sanitized_error(tmp_path):
    backend = ExifToolBackend(tmp_path, executable="fictional-missing-executable")
    with pytest.raises(XmpBackendError, match="executable") as exc:
        backend.transform(None, {"title": "Fictional title"})
    assert str(tmp_path) not in str(exc.value)
    assert list(tmp_path.iterdir()) == []


def fake(tmp_path, body):
    path = tmp_path / "fake-tool"
    path.write_text("#!/usr/bin/env python3\n" + body)
    path.chmod(0o700)
    return str(path)


def test_process_failure_is_redacted_and_cleans_owned_files(tmp_path):
    executable = fake(
        tmp_path,
        "import sys\nprint('fictional secret', file=sys.stderr)\nsys.exit(3)\n",
    )
    backend = ExifToolBackend(tmp_path, executable=executable)
    with pytest.raises(XmpBackendError) as exc:
        backend.transform(None, {"title": "fictional secret"})
    assert "fictional secret" not in str(exc.value)
    assert list(tmp_path.iterdir()) == [tmp_path / "fake-tool"]


def test_timeout_and_output_are_bounded(tmp_path):
    executable = fake(tmp_path, "import time\ntime.sleep(5)\n")
    with pytest.raises(XmpBackendError, match="timeout"):
        ExifToolBackend(tmp_path, executable=executable, timeout=0.1).transform(
            None, {"title": "a"}
        )
    executable = fake(tmp_path, "print('a' * 100000)\n")
    with pytest.raises(XmpBackendError, match="output limit"):
        ExifToolBackend(tmp_path, executable=executable, output_limit=100).transform(
            None, {"title": "a"}
        )


def test_malformed_and_unsupported_are_rejected(tmp_path):
    backend = ExifToolBackend(tmp_path)
    for data in (
        b"<broken",
        b'<!DOCTYPE x [<!ENTITY a "b">]><x/>',
        EMPTY.replace(
            b'<rdf:Description rdf:about=""/>',
            b'<rdf:Description rdf:about="urn:other"/>',
        ),
    ):
        with pytest.raises(XmpBackendError):
            backend.validate(data)


def test_valid_xmp_is_accepted_by_artifact_validator(tmp_path):
    from image_clarus.artifacts import ArtifactService

    backend = ExifToolBackend(tmp_path)
    target = tmp_path / "example.xmp"
    ArtifactService().write(target, EMPTY, backend.validate)
    assert target.read_bytes() == EMPTY


def test_malformed_tool_output_is_rejected(tmp_path):
    executable = fake(
        tmp_path,
        "import pathlib,sys\npathlib.Path(sys.argv[-1]).write_bytes(b'<broken')\n",
    )
    with pytest.raises(XmpBackendError, match="malformed"):
        ExifToolBackend(tmp_path, executable=executable).transform(None, {"title": "a"})
    assert list(tmp_path.iterdir()) == [tmp_path / "fake-tool"]


def test_language_alternative_loss_is_rejected(tmp_path):
    packet = b"""<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" xmlns:dc="http://purl.org/dc/elements/1.1/"><rdf:Description rdf:about=""><dc:title><rdf:Alt><rdf:li xml:lang="x-default">Old</rdf:li><rdf:li xml:lang="fr">Bonjour</rdf:li></rdf:Alt></dc:title></rdf:Description></rdf:RDF>"""
    executable = fake(
        tmp_path,
        """import pathlib,sys\np=pathlib.Path(sys.argv[-1])\ns=p.read_bytes().replace(b'Old',b'New').replace(b'<rdf:li xml:lang="fr">Bonjour</rdf:li>',b'')\np.write_bytes(s)\n""",
    )
    with pytest.raises(XmpBackendError, match="preservation"):
        ExifToolBackend(tmp_path, executable=executable).transform(
            packet, {"title": "New"}
        )


def test_rdf_description_property_attributes_are_preserved(tmp_path):
    packet = b"""<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" xmlns:f="urn:fiction"><rdf:Description rdf:about="" f:note="Keep"/></rdf:RDF>"""
    backend = ExifToolBackend(tmp_path)
    assert backend.read(packet)["properties"]["{urn:fiction}note"] == (
        "literal",
        (),
        "Keep",
    )


@pytest.mark.parametrize("value", ["bad\x00value", "bad\ud800value"])
def test_unrepresentable_updates_are_rejected_without_tool(tmp_path, value):
    backend = ExifToolBackend(tmp_path, executable="fictional-missing-executable")
    with pytest.raises(XmpBackendError, match="invalid XMP updates"):
        backend.transform(None, {"title": value})
    assert list(tmp_path.iterdir()) == []


def test_unsafe_rdf_structures_are_rejected(tmp_path):
    backend = ExifToolBackend(tmp_path)
    packet = b"""<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" xmlns:f="urn:fiction"><rdf:Description rdf:about=""><f:node rdf:parseType="Resource"><f:detail>Keep</f:detail></f:node></rdf:Description></rdf:RDF>"""
    with pytest.raises(XmpBackendError, match="unsupported"):
        backend.transform(packet, {"title": "New"})


def test_foreign_mutation_is_rejected(tmp_path):
    packet = b"""<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:f="urn:fiction"><rdf:Description rdf:about=""><dc:title><rdf:Alt><rdf:li xml:lang="x-default">Old</rdf:li></rdf:Alt></dc:title><f:note>Keep</f:note></rdf:Description></rdf:RDF>"""
    executable = fake(
        tmp_path,
        "import pathlib,sys\np=pathlib.Path(sys.argv[-1])\ns=p.read_bytes().replace(b'Old',b'New').replace(b'Keep',b'Lost')\np.write_bytes(s)\n",
    )
    with pytest.raises(XmpBackendError, match="preservation"):
        ExifToolBackend(tmp_path, executable=executable).transform(
            packet, {"title": "New"}
        )


def test_working_file_is_private_and_in_destination(tmp_path):
    executable = fake(
        tmp_path,
        "import os,sys\np=sys.argv[-1]\nassert p.endswith('.xmp')\nassert os.stat(p).st_mode & 0o077 == 0\nsys.exit(2)\n",
    )
    with pytest.raises(XmpBackendError, match="processing failed"):
        ExifToolBackend(tmp_path, executable=executable).transform(None, {"title": "a"})
    assert stat.S_IMODE((tmp_path / "fake-tool").stat().st_mode) == 0o700


@pytest.mark.skipif(shutil.which("exiftool") is None, reason="ExifTool unavailable")
def test_real_exiftool_mapping_and_preservation(tmp_path):
    backend = ExifToolBackend(tmp_path)
    image = tmp_path / "synthetic.jpg"
    image.write_bytes(b"synthetic image bytes")
    initial = backend.transform(
        None,
        {
            "tags": ["manual/flower", "ai/tree"],
            "title": "Old",
            "caption": "Caption",
            "author": "Person",
        },
    )
    # ExifTool creates synthetic language and foreign metadata in the private fixture.
    import subprocess

    source = tmp_path / "- fiction é.xmp"
    source.write_bytes(initial)
    subprocess.run(
        [
            "exiftool",
            "-config",
            "",
            "-overwrite_original",
            "-XMP-dc:Title-fr=Bonjour",
            "-XMP-dc:Description-fr=Salut",
            "-XMP-digiKam:CaptionsAuthorNames-fr=Quelquun",
            "-XMP-dc:Subject+=flower",
            "-XMP-lr:HierarchicalSubject+=manual|flower",
            "--",
            str(source),
        ],
        check=True,
        capture_output=True,
    )
    snapshot = source.read_bytes()
    result = backend.transform(
        snapshot,
        {
            "tags": ["manual/flower", "ai/leaf"],
            "title": "New",
            "caption": "New caption",
            "author": "New author",
        },
    )
    before, after = backend.read(snapshot), backend.read(result)
    assert after["tags"] == ["manual/flower", "ai/leaf"]
    assert after["title"] == "New"
    assert after["caption"] == "New caption" and after["author"] == "New author"
    assert ("fr", "Salut") in after["properties"][
        "{http://purl.org/dc/elements/1.1/}description"
    ][1]
    assert ("fr", "Quelquun") in after["properties"][
        "{http://www.digikam.org/ns/1.0/}CaptionsAuthorNames"
    ][1]
    assert ("fr", "Bonjour") in after["properties"][
        "{http://purl.org/dc/elements/1.1/}title"
    ][1]
    assert (
        before["properties"]["{http://purl.org/dc/elements/1.1/}subject"]
        == after["properties"]["{http://purl.org/dc/elements/1.1/}subject"]
    )
    assert (
        before["properties"]["{http://ns.adobe.com/lightroom/1.0/}hierarchicalSubject"]
        == after["properties"][
            "{http://ns.adobe.com/lightroom/1.0/}hierarchicalSubject"
        ]
    )
    verified = tmp_path / "verified.xmp"
    verified.write_bytes(result)
    import json

    independent = subprocess.run(
        [
            "exiftool",
            "-config",
            "",
            "-j",
            "-XMP-digiKam:TagsList",
            "-XMP-dc:Title",
            "-XMP-dc:Title-fr",
            "-XMP-dc:Description-fr",
            "-XMP-dc:Description",
            "-XMP-digiKam:CaptionsAuthorNames",
            "-XMP-digiKam:CaptionsAuthorNames-fr",
            "--",
            str(verified),
        ],
        check=True,
        capture_output=True,
    )
    values = json.loads(independent.stdout)[0]
    assert values["TagsList"] == ["manual/flower", "ai/leaf"]
    assert values["Title"] == "New" and values["Title-fr"] == "Bonjour"
    assert values["Description"] == "New caption"
    assert values["CaptionsAuthorNames"] == "New author"
    assert (
        values["Description-fr"] == "Salut"
        and values["CaptionsAuthorNames-fr"] == "Quelquun"
    )
    verified.unlink()
    assert source.read_bytes() == snapshot
    assert image.read_bytes() == b"synthetic image bytes"
    assert sorted(p.name for p in tmp_path.iterdir()) == sorted(
        [source.name, image.name]
    )
