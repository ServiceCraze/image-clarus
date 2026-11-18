"""Regression coverage for attribute-encoded structured XMP properties."""

import shutil

import pytest

from image_clarus.xmp_backend import (
    ExifToolBackend,
    XmpBackendError,
    _restore_microsoft_photo_namespace,
)

PACKET = b"""<x:xmpmeta xmlns:x="adobe:ns:meta/">
<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
 xmlns:exif="http://ns.adobe.com/exif/1.0/"
 xmlns:dc="http://purl.org/dc/elements/1.1/"
 xmlns:digiKam="http://www.digikam.org/ns/1.0/"
 xmlns:lr="http://ns.adobe.com/lightroom/1.0/"
 xmlns:MicrosoftPhoto="http://ns.microsoft.com/photo/1.0/"
 xmlns:mediapro="http://ns.iview-multimedia.com/mediapro/1.0/"
 xmlns:f="urn:fiction">
<rdf:Description rdf:about="" f:note="Keep">
<exif:Flash exif:Fired="False" exif:Return="0" exif:Mode="3"
 exif:Function="False" exif:RedEyeMode="False"/>
<digiKam:TagsList><rdf:Seq><rdf:li>manual/flower</rdf:li><rdf:li>ai/leaf</rdf:li></rdf:Seq></digiKam:TagsList>
<dc:subject><rdf:Bag><rdf:li>flower</rdf:li></rdf:Bag></dc:subject>
<lr:hierarchicalSubject><rdf:Bag><rdf:li>manual|flower</rdf:li></rdf:Bag></lr:hierarchicalSubject>
<MicrosoftPhoto:LastKeywordXMP><rdf:Bag><rdf:li>manual/flower</rdf:li></rdf:Bag></MicrosoftPhoto:LastKeywordXMP>
<mediapro:CatalogSets><rdf:Bag><rdf:li>manual|flower</rdf:li></rdf:Bag></mediapro:CatalogSets>
<dc:description><rdf:Alt><rdf:li xml:lang="x-default">Old caption</rdf:li><rdf:li xml:lang="fr">Ancien</rdf:li></rdf:Alt></dc:description>
</rdf:Description></rdf:RDF></x:xmpmeta>"""


def test_attribute_structure_is_read_and_member_changes_are_visible(tmp_path):
    backend = ExifToolBackend(tmp_path)
    before = backend.read(PACKET)
    changed = backend.read(PACKET.replace(b'exif:Mode="3"', b'exif:Mode="2"'))
    assert (
        before["properties"]["{http://ns.adobe.com/exif/1.0/}Flash"]
        != changed["properties"]["{http://ns.adobe.com/exif/1.0/}Flash"]
    )
    assert before["tags"] == ["manual/flower", "ai/leaf"]


@pytest.mark.parametrize(
    "replacement",
    [
        b'exif:Mode="3" rdf:resource="urn:fiction"',
        b'exif:Mode="3" xml:lang="en"',
        b'exif:Mode="3" plain="value"',
    ],
)
def test_ambiguous_structure_attributes_are_rejected(tmp_path, replacement):
    with pytest.raises(XmpBackendError, match="unsupported"):
        ExifToolBackend(tmp_path).read(PACKET.replace(b'exif:Mode="3"', replacement))


def test_namespace_restoration_does_not_conflate_two_existing_namespaces():
    both = PACKET.replace(
        b'<rdf:Description rdf:about="" f:note="Keep">',
        b'<rdf:Description rdf:about="" f:note="Keep" '
        b'xmlns:other="http://ns.microsoft.com/photo/1.0" other:note="Keep">',
    )
    candidate = PACKET.replace(
        b'xmlns:MicrosoftPhoto="http://ns.microsoft.com/photo/1.0/"',
        b'xmlns:MicrosoftPhoto="http://ns.microsoft.com/photo/1.0"',
    )
    assert _restore_microsoft_photo_namespace(both, candidate) == candidate


@pytest.mark.parametrize(
    "replacement",
    [b'exif:Mode="2"', b"", b'exif:Mode="3" exif:Extra="fictional"'],
)
def test_attribute_structure_mutation_by_tool_is_rejected(tmp_path, replacement):
    executable = tmp_path / "fake-tool"
    original = b'exif:Mode="3"'
    executable.write_text(
        "#!/usr/bin/env python3\nimport pathlib,sys\n"
        "p=pathlib.Path(sys.argv[-1])\n"
        "p.write_bytes(p.read_bytes().replace(b'Old caption', b'New caption')"
        f".replace({original!r}, {replacement!r}))\n"
    )
    executable.chmod(0o700)
    with pytest.raises(XmpBackendError, match="preservation"):
        ExifToolBackend(tmp_path, executable=str(executable)).transform(
            PACKET, {"caption": "New caption"}
        )


def test_equivalent_resource_form_and_unsupported_nested_resource(tmp_path):
    backend = ExifToolBackend(tmp_path)
    expanded = PACKET.replace(
        b'<exif:Flash exif:Fired="False" exif:Return="0" exif:Mode="3"\n'
        b' exif:Function="False" exif:RedEyeMode="False"/>',
        b'<exif:Flash rdf:parseType="Resource"><exif:Fired>False</exif:Fired>'
        b"<exif:Return>0</exif:Return><exif:Mode>3</exif:Mode>"
        b"<exif:Function>False</exif:Function>"
        b"<exif:RedEyeMode>False</exif:RedEyeMode></exif:Flash>",
    )
    assert expanded != PACKET
    assert backend.read(expanded)["properties"] == backend.read(PACKET)["properties"]
    nested = expanded.replace(
        b"<exif:Mode>3</exif:Mode>",
        b"<exif:Mode><exif:other>3</exif:other></exif:Mode>",
    )
    with pytest.raises(XmpBackendError, match="unsupported"):
        backend.read(nested)


@pytest.mark.skipif(shutil.which("exiftool") is None, reason="ExifTool unavailable")
def test_real_tool_caption_update_preserves_structured_and_parallel_tags(tmp_path):
    backend = ExifToolBackend(tmp_path)
    before = backend.read(PACKET)
    result = backend.transform(PACKET, {"caption": "New caption"})
    after = backend.read(result)
    assert after["caption"] == "New caption"
    assert after["tags"] == before["tags"]
    for name, value in before["properties"].items():
        if name != "{http://purl.org/dc/elements/1.1/}description":
            assert after["properties"][name] == value
    assert ("fr", "Ancien") in after["properties"][
        "{http://purl.org/dc/elements/1.1/}description"
    ][1]
