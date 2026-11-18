"""Direct stage orchestration tests using fictional persisted artifacts."""

import json
import os
import shutil
import time
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

from image_clarus.artifacts import ArtifactService
from image_clarus.config import DEFAULTS
from image_clarus.pipeline import StopToken
from image_clarus.stages import xmp
from image_clarus.xmp_backend import EMPTY, ExifToolBackend, XmpBackendError


def setup_stage(tmp_path, *, metadata=None, retention="remove"):
    image = tmp_path / "fictional.jpg"
    image.write_bytes(b"fictional image bytes")
    config = deepcopy(DEFAULTS)
    config["stages"]["xmp"]["custom_title_property"] = "headline"
    if metadata is not None:
        envelope = {
            "format_version": 1,
            "schema_id": "urn:image-clarus:custom-metadata-schema",
            "schema_version": "custom-sha256:" + "a" * 64,
            "provenance": {
                "provider_alias": "fictional",
                "model_alias": "fictional",
                "model_id": "fictional",
                "prompt_id": "fictional",
                "prompt_sha256": "a" * 64,
                "description_sha256": "b" * 64,
            },
            "metadata": metadata,
        }
        (tmp_path / "fictional.jpg.desc.json").write_text(json.dumps(envelope))

    def no_provider(*args, **kwargs):
        raise AssertionError("XMP must not invoke a provider")

    return (
        image,
        config,
        SimpleNamespace(
            artifacts=ArtifactService(retention), provider_factory=no_provider
        ),
    )


def sidecars(image):
    return tuple(
        Path(str(image) + suffix)
        for suffix in (".desc.json", ".desc.json.bak", ".xmp", ".xmp.bak")
    )


def test_missing_json_reports_configured_prerequisite_policy(tmp_path):
    image, config, services = setup_stage(tmp_path)
    result = xmp.run_xmp(image, config, services)
    assert (result.status, result.error_category) == ("failed", "missing_prerequisite")
    config["pipeline"]["missing_prerequisite"] = "skip"
    result = xmp.run_xmp(image, config, services)
    assert (result.status, result.reason_code) == ("skipped", "missing_prerequisite")
    assert image.read_bytes() == b"fictional image bytes"


def test_real_exiftool_publication_replacement_and_idempotence(tmp_path):
    if not shutil.which("exiftool"):
        pytest.skip("real ExifTool not on PATH")
    image, config, services = setup_stage(
        tmp_path, metadata={"headline": "Fictional title"}, retention="retain"
    )
    source, _, output, backup = sidecars(image)
    before_json = source.read_bytes()
    first = xmp.run_xmp(image, config, services)
    assert (first.status, first.output_path) == ("completed", output)
    assert (
        ExifToolBackend(tmp_path).read(output.read_bytes())["title"]
        == "Fictional title"
    )
    previous = output.read_bytes()
    config["stages"]["xmp"]["title_policy"] = "overwrite"
    value = json.loads(before_json)
    value["metadata"]["headline"] = "Another fictional title"
    source.write_text(json.dumps(value))
    assert xmp.run_xmp(image, config, services).status == "completed"
    assert backup.read_bytes() == previous
    assert (
        ExifToolBackend(tmp_path).read(output.read_bytes())["title"]
        == "Another fictional title"
    )
    assert xmp.run_xmp(image, config, services).reason_code == "no_change"
    assert backup.read_bytes() == previous
    assert image.read_bytes() == b"fictional image bytes"
    assert not list(tmp_path.glob(".*image-clarus*"))


@pytest.mark.parametrize("retention", ["remove", "retain"])
def test_no_change_recovers_backup_and_obeys_retention(tmp_path, retention):
    image, config, services = setup_stage(tmp_path, metadata={}, retention=retention)
    _, _, output, backup = sidecars(image)
    backup.write_bytes(EMPTY)
    result = xmp.run_xmp(image, config, services)
    assert (result.status, result.reason_code) == ("skipped", "no_change")
    assert output.read_bytes() == EMPTY
    assert backup.exists() == (retention == "retain")


@pytest.mark.parametrize("retention", ["remove", "retain"])
def test_no_change_validates_destination_and_cleans_stale_backup(tmp_path, retention):
    image, config, services = setup_stage(tmp_path, metadata={}, retention=retention)
    _, _, output, backup = sidecars(image)
    output.write_bytes(EMPTY)
    backup.write_bytes(b"stale backup")
    result = xmp.run_xmp(image, config, services)
    assert result.reason_code == "no_change"
    assert output.read_bytes() == EMPTY
    assert backup.exists() == (retention == "retain")


def test_missing_json_is_recovered_before_planning(tmp_path):
    image, config, services = setup_stage(tmp_path, metadata={})
    source, backup, output, _ = sidecars(image)
    original = source.read_bytes()
    source.rename(backup)
    result = xmp.run_xmp(image, config, services)
    assert result.reason_code == "no_change"
    assert source.read_bytes() == original
    assert not backup.exists() and not output.exists()


@pytest.mark.parametrize("which", ["json", "xmp", "xmp_backup"])
def test_malformed_artifact_fails_without_replacing_it(tmp_path, which):
    image, config, services = setup_stage(tmp_path, metadata={"headline": "Fictional"})
    source, _, output, backup = sidecars(image)
    target = {"json": source, "xmp": output, "xmp_backup": backup}[which]
    target.write_bytes(b"broken fictional data")
    result = xmp.run_xmp(image, config, services)
    assert (result.status, result.error_category) == ("failed", "invalid_artifact")
    assert target.read_bytes() == b"broken fictional data"
    assert image.read_bytes() == b"fictional image bytes"


def test_structurally_valid_foreign_backup_restores_but_transform_fails_closed(
    tmp_path,
):
    image, config, services = setup_stage(
        tmp_path, metadata={"headline": "Fictional"}, retention="retain"
    )
    _, _, output, backup = sidecars(image)
    foreign = (
        b'<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" xmlns:f="urn:fictional">'
        b'<rdf:Description rdf:about=""><f:complex rdf:parseType="Resource"><f:nested>value</f:nested>'
        b"</f:complex></rdf:Description></rdf:RDF>"
    )
    backup.write_bytes(foreign)
    result = xmp.run_xmp(image, config, services)
    assert (result.status, result.error_category) == ("failed", "invalid_artifact")
    assert output.read_bytes() == foreign and backup.read_bytes() == foreign


@pytest.mark.parametrize("link_kind", ["hard", "symlink"])
@pytest.mark.parametrize("target_index", [1, 2, 3, 4])
def test_sidecar_and_backup_aliases_to_image_are_rejected(
    tmp_path, link_kind, target_index
):
    image, config, services = setup_stage(tmp_path, metadata={})
    paths = (image, *sidecars(image))
    target = paths[target_index]
    target.unlink(missing_ok=True)
    if link_kind == "hard":
        os.link(image, target)
    else:
        target.symlink_to(image)
    result = xmp.run_xmp(image, config, services)
    assert (result.status, result.error_category) == ("failed", "file_io")
    assert image.read_bytes() == b"fictional image bytes"


@pytest.mark.parametrize("link_kind", ["hard", "symlink"])
def test_output_alias_to_json_is_rejected_before_any_recovery(tmp_path, link_kind):
    image, config, services = setup_stage(tmp_path, metadata={})
    source, _, output, _ = sidecars(image)
    original = source.read_bytes()
    if link_kind == "hard":
        os.link(source, output)
    else:
        output.symlink_to(source)
    result = xmp.run_xmp(image, config, services)
    assert (result.status, result.error_category) == ("failed", "file_io")
    assert source.read_bytes() == original


@pytest.mark.parametrize(
    "error,category",
    [
        ("ExifTool timeout", "file_io"),
        ("ExifTool processing failed", "invalid_artifact"),
        ("XMP working file failure", "file_io"),
    ],
)
def test_backend_failure_is_sanitized_and_preserves_original(
    tmp_path, monkeypatch, error, category
):
    image, config, services = setup_stage(tmp_path, metadata={"headline": "Fictional"})
    _, _, output, _ = sidecars(image)
    output.write_bytes(EMPTY)

    def fail(*args):
        raise XmpBackendError(error)

    monkeypatch.setattr(ExifToolBackend, "transform", fail)
    result = xmp.run_xmp(image, config, services)
    assert (result.status, result.error_category) == ("failed", category)
    assert "Fictional" not in result.message
    assert output.read_bytes() == EMPTY


def test_publication_failure_preserves_original_and_cleans_owned_temps(tmp_path):
    if not shutil.which("exiftool"):
        pytest.skip("real ExifTool not on PATH")
    image, config, services = setup_stage(
        tmp_path, metadata={"headline": "Fictional"}, retention="retain"
    )
    _, _, output, backup = sidecars(image)
    output.write_bytes(EMPTY)

    def fail(point):
        if point == "destination_replace":
            raise OSError("simulated failure")

    services.artifacts = ArtifactService("retain", checkpoint=fail)
    result = xmp.run_xmp(image, config, services)
    assert (result.status, result.error_category) == ("failed", "file_io")
    assert output.read_bytes() == EMPTY and backup.read_bytes() == EMPTY
    assert not list(tmp_path.glob(".*image-clarus*"))


def test_cooperative_stop_after_transform_prevents_publication(tmp_path, monkeypatch):
    image, config, services = setup_stage(tmp_path, metadata={"headline": "Fictional"})
    services.stop = StopToken()

    def transform(self, snapshot, updates):
        services.stop.request(15)
        return EMPTY

    monkeypatch.setattr(ExifToolBackend, "transform", transform)
    result = xmp.run_xmp(image, config, services)
    assert (result.status, result.reason_code) == ("skipped", "interrupted")
    assert not sidecars(image)[2].exists()


def test_stop_during_started_write_reaches_safe_boundary(tmp_path):
    if not shutil.which("exiftool"):
        pytest.skip("real ExifTool not on PATH")
    image, config, services = setup_stage(tmp_path, metadata={"headline": "Fictional"})
    services.stop = StopToken()

    def checkpoint(point):
        if point == "output_write":
            services.stop.request(2)

    services.artifacts = ArtifactService(checkpoint=checkpoint)
    result = xmp.run_xmp(image, config, services)
    assert result.status == "completed"
    assert (
        ExifToolBackend(tmp_path).read(sidecars(image)[2].read_bytes())["title"]
        == "Fictional"
    )


def test_actual_tool_timeout_is_file_io_and_reaps_process(tmp_path, monkeypatch):
    image, config, services = setup_stage(tmp_path, metadata={"headline": "Fictional"})
    script = tmp_path / "fictional-tool"
    pidfile = tmp_path / "child-pid"
    script.write_text(f"#!/bin/sh\nprintf '%s' $$ > '{pidfile}'\nexec sleep 5\n")
    script.chmod(0o700)
    original_run = ExifToolBackend._run

    def short_timeout(self, args):
        self.executable = str(script)
        self.timeout = 0.3
        return original_run(self, args)

    monkeypatch.setattr(ExifToolBackend, "_run", short_timeout)
    start = time.monotonic()
    result = xmp.run_xmp(image, config, services)
    assert time.monotonic() - start < 3
    assert (result.status, result.error_category, result.message) == (
        "failed",
        "file_io",
        "ExifTool timeout",
    )
    with pytest.raises(ProcessLookupError):
        os.kill(int(pidfile.read_text()), 0)
    assert not sidecars(image)[2].exists()
    assert not list(tmp_path.glob(".*image-clarus*"))


def test_recovery_cancellation_does_not_return_no_change(tmp_path):
    image, config, services = setup_stage(tmp_path, metadata={})
    services.stop = StopToken()
    _, _, output, _ = sidecars(image)
    output.write_bytes(EMPTY)

    validations = []

    def checkpoint(point):
        if point == "destination_validate":
            validations.append(point)
            if len(validations) == 2:
                services.stop.request(2)

    services.artifacts = ArtifactService(checkpoint=checkpoint)
    result = xmp.run_xmp(image, config, services)
    assert (result.status, result.reason_code) == ("skipped", "interrupted")


def test_actual_tool_preserves_foreign_and_localized_metadata(tmp_path):
    if not shutil.which("exiftool"):
        pytest.skip("real ExifTool not on PATH")
    image, config, services = setup_stage(
        tmp_path, metadata={"headline": "New title", "paths": [["food", "pear"]]}
    )
    settings = config["stages"]["xmp"]
    settings.update(
        custom_tags_property="paths", tag_policy="overwrite", title_policy="overwrite"
    )
    _, _, output, _ = sidecars(image)
    output.write_bytes(
        b'<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" '
        b'xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dk="http://www.digikam.org/ns/1.0/" '
        b'xmlns:f="urn:fictional"><rdf:Description rdf:about="">'
        b"<dk:TagsList><rdf:Seq><rdf:li>ai/old</rdf:li><rdf:li>manual/pear</rdf:li>"
        b'</rdf:Seq></dk:TagsList><dc:title><rdf:Alt><rdf:li xml:lang="x-default">Old</rdf:li>'
        b'<rdf:li xml:lang="fr">Bonjour</rdf:li></rdf:Alt></dc:title>'
        b"<dc:subject><rdf:Bag><rdf:li>pear</rdf:li></rdf:Bag></dc:subject>"
        b"<f:note>unrelated</f:note></rdf:Description></rdf:RDF>"
    )
    backend = ExifToolBackend(tmp_path)
    before = backend.read(output.read_bytes())
    result = xmp.run_xmp(image, config, services)
    assert result.status == "completed"
    after = backend.read(output.read_bytes())
    assert after["tags"] == ["manual/pear", "ai/food/pear"]
    assert after["title"] == "New title"
    assert ("fr", "Bonjour") in after["properties"][
        "{http://purl.org/dc/elements/1.1/}title"
    ][1]
    for key in ("{http://purl.org/dc/elements/1.1/}subject", "{urn:fictional}note"):
        assert after["properties"][key] == before["properties"][key]


def test_candidate_is_validated_by_artifact_service_before_publication(
    tmp_path, monkeypatch
):
    image, config, services = setup_stage(tmp_path, metadata={"headline": "Fictional"})
    _, _, output, backup = sidecars(image)
    output.write_bytes(EMPTY)
    monkeypatch.setattr(ExifToolBackend, "transform", lambda *args: b"not xmp")
    result = xmp.run_xmp(image, config, services)
    assert (result.status, result.error_category) == ("failed", "invalid_artifact")
    assert output.read_bytes() == EMPTY and not backup.exists()
    assert not list(tmp_path.glob(".*image-clarus*"))
