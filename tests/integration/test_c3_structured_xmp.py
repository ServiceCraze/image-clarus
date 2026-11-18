"""Synthetic CLI regression for a digiKam-style structured EXIF sidecar."""

import json

from test_c2_xmp_safety import (
    assert_unrelated_properties_preserved,
    configured_metadata,
    rich_xmp,
    run_xmp,
    sha256,
)

from image_clarus.xmp_backend import ExifToolBackend

pytest_plugins = ("test_xmp_cli_b5", "test_c2_xmp_safety")


def test_cli_preserves_digikam_style_structured_metadata(rig, real_exiftool):
    del real_exiftool
    packet = rich_xmp().replace(
        b'<rdf:Description rdf:about="">',
        b'<rdf:Description rdf:about="" '
        b'xmlns:mp="http://ns.microsoft.com/photo/1.0/" '
        b'xmlns:media="http://ns.iview-multimedia.com/mediapro/1.0/">'
        b'<exif:Flash exif:Fired="False" exif:Return="0" exif:Mode="3" '
        b'exif:Function="False" exif:RedEyeMode="False"/>'
        b"<mp:LastKeywordXMP><rdf:Bag><rdf:li>manual/pear</rdf:li></rdf:Bag></mp:LastKeywordXMP>"
        b"<media:CatalogSets><rdf:Bag><rdf:li>manual|pear</rdf:li></rdf:Bag></media:CatalogSets>",
    )
    rig.structured.write_text(json.dumps(configured_metadata(caption="New caption")))
    rig.xmp.write_bytes(packet)
    source_hash = sha256(rig.image)
    backend = ExifToolBackend(rig.image.parent)
    before = backend.read(packet)
    run_xmp(
        rig,
        "--set",
        "stages.xmp.caption_policy=overwrite",
        "--set",
        "stages.xmp.title_policy=disabled",
        "--set",
        "stages.xmp.tag_policy=disabled",
    )
    after = backend.read(rig.xmp.read_bytes())
    assert after["caption"] == "New caption"
    assert after["tags"] == before["tags"]
    assert_unrelated_properties_preserved(before, after, changed_fields=("caption",))
    assert sha256(rig.image) == source_hash
