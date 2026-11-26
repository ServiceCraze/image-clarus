import json
import subprocess
import sys
from pathlib import Path

import pytest

from image_clarus.pipeline import StopToken
from image_clarus.results import PipelineResult, StageResult
from image_clarus.stages.structure import _read_envelope
from image_clarus.state.accumulation import (
    SidecarExtractionError,
    accumulate_categories,
    extract_sidecar,
)
from image_clarus.state.service import StateService
from image_clarus.state.storage import MemoryStorage


def envelope(
    paths=None, *, schema_id="urn:image-clarus:metadata-schema:2.0.0", version="2.0.0"
):
    metadata = {} if paths is None else {"tag_candidates": paths}
    return json.dumps(
        {
            "format_version": 1,
            "schema_id": schema_id,
            "schema_version": version,
            "provenance": {
                "provider_alias": "demo",
                "model_alias": "demo",
                "model_id": "demo",
                "prompt_id": "demo",
                "description_sha256": "a" * 64,
            },
            "metadata": metadata,
        }
    ).encode()


@pytest.mark.parametrize(
    "data,expected",
    [
        (envelope([["B"], ["A", "leaf"], ["B"]]), ["A/leaf", "B"]),
        (
            envelope(
                [["A"]],
                schema_id="urn:image-clarus:metadata-schema:1.0.0",
                version="1.0.0",
            ),
            [],
        ),
        (
            envelope(
                [["A"]],
                schema_id="urn:image-clarus:custom-metadata-schema",
                version="custom-sha256:" + "a" * 64,
            ),
            ["A"],
        ),
        (envelope(), []),
        (envelope([]), []),
    ],
)
def test_extract_sidecar_returns_categories_or_valid_empty(tmp_path, data, expected):
    path = tmp_path / "sample.desc.json"
    path.write_bytes(data)
    assert extract_sidecar(path, _read_envelope) == expected


@pytest.mark.parametrize(
    "data",
    [
        b"not json",
        envelope([["A"], []]),
        envelope([["bad/segment"]]),
        envelope("bad"),
        envelope([["A"]], schema_id="unknown"),
        envelope(
            [["A"]],
            schema_id="urn:image-clarus:custom-metadata-schema",
            version="custom-sha256:" + "A" * 64,
        ),
    ],
)
def test_extract_sidecar_rejects_invalid_data(tmp_path, data):
    path = tmp_path / "sample.desc.json"
    path.write_bytes(data)
    with pytest.raises(SidecarExtractionError, match="^sidecar extraction failed$"):
        extract_sidecar(path, _read_envelope)


def test_extract_sidecar_reads_once_and_passes_exact_snapshot(tmp_path, monkeypatch):
    path = tmp_path / "sample.desc.json"
    data = envelope([["A"]])
    path.write_bytes(data)
    original = Path.read_bytes
    reads = []
    received = []

    def read_once(self):
        reads.append(self)
        return original(self)

    def reader(snapshot):
        received.append(snapshot)
        return _read_envelope(snapshot)

    monkeypatch.setattr(Path, "read_bytes", read_once)
    assert extract_sidecar(path, reader) == ["A"]
    assert reads == [path]
    assert received == [data]


def test_extract_sidecar_sanitizes_read_and_reader_failures(tmp_path):
    import traceback

    path = tmp_path / "private-sentinel.desc.json"
    with pytest.raises(SidecarExtractionError) as missing:
        extract_sidecar(path, _read_envelope)
    assert "private-sentinel" not in "".join(traceback.format_exception(missing.value))

    path.write_bytes(b"snapshot")

    def broken_reader(data):
        raise RuntimeError("private-sentinel")

    with pytest.raises(SidecarExtractionError) as invalid:
        extract_sidecar(path, broken_reader)
    assert "private-sentinel" not in "".join(traceback.format_exception(invalid.value))


def test_state_accumulation_import_does_not_depend_on_stages():
    probe = """
import builtins
original = builtins.__import__
def guarded(name, *args, **kwargs):
    if name == 'image_clarus.stages' or name.startswith('image_clarus.stages.'):
        raise ImportError('stage imports forbidden')
    return original(name, *args, **kwargs)
builtins.__import__ = guarded
import image_clarus.state.accumulation
"""
    result = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr


def invoke(tmp_path, data, stage=None, *, enabled=True, stop=None):
    image = tmp_path / "sample.jpg"
    Path(str(image) + ".desc.json").write_bytes(data)
    service = StateService(MemoryStorage(), stop=stop)
    result = PipelineResult(image, (stage or StageResult("json", "completed"),))
    accumulate_categories(
        result, service, enabled=enabled, stop=stop, read_envelope=_read_envelope
    )
    return service.snapshot_categories()


@pytest.mark.parametrize(
    "data",
    [
        b'{"format_version":1,"format_version":1}',
        b"\xff",
        envelope([["A"]]).replace(b'"metadata":', b'"unexpected": 1, "metadata":'),
        envelope([["A"]]).replace(b'"A"', b'"\\ud800"'),
        envelope([["A"]]).replace(b'"A"', b"1e9999"),
    ],
)
def test_invalid_envelope_never_accumulates(tmp_path, data):
    assert invoke(tmp_path, data) == []


def test_valid_envelope_without_unrelated_fields_contributes_complete_paths(tmp_path):
    assert invoke(tmp_path, envelope([["A", "Leaf"], ["Single"], ["A", "Leaf"]])) == [
        "A/Leaf",
        "Single",
    ]


@pytest.mark.parametrize(
    "schema_id,version,expected",
    [
        ("urn:image-clarus:metadata-schema:1.0.0", "1.0.0", []),
        ("urn:image-clarus:metadata-schema:2.0.0", "1.0.0", []),
        ("urn:image-clarus:custom-metadata-schema", "custom-sha256:" + "a" * 64, ["A"]),
        ("urn:image-clarus:custom-metadata-schema", "custom-sha256:" + "A" * 64, []),
        ("unknown", "2.0.0", []),
    ],
)
def test_strict_identity(tmp_path, schema_id, version, expected):
    assert (
        invoke(tmp_path, envelope([["A"]], schema_id=schema_id, version=version))
        == expected
    )


@pytest.mark.parametrize(
    "paths", [[["good"], []], [["good"], ["bad/part"]], [["good"], [1]], "bad", None]
)
def test_invalid_or_missing_contribution_is_empty(tmp_path, paths):
    assert invoke(tmp_path, envelope(paths)) == []


@pytest.mark.parametrize(
    "stage,enabled,expected",
    [
        (StageResult("json", "skipped", reason_code="output_exists"), True, ["A"]),
        (StageResult("json", "skipped", reason_code="missing_prerequisite"), True, []),
        (StageResult("json", "failed"), True, []),
        (StageResult("desc", "completed"), True, []),
        (StageResult("json", "completed"), False, []),
        (StageResult("json", "skipped", reason_code="output_exists"), False, []),
    ],
)
def test_eligibility(tmp_path, stage, enabled, expected):
    assert invoke(tmp_path, envelope([["A"]]), stage, enabled=enabled) == expected


def test_stopped_skips_optional_work(tmp_path):
    stop = StopToken()
    stop.request(2)
    image = tmp_path / "sample.jpg"

    class Never:
        def add_categories(self, paths):
            pytest.fail("unexpected write")

    accumulate_categories(
        PipelineResult(image, (StageResult("json", "completed"),)),
        Never(),
        enabled=True,
        read_envelope=_read_envelope,
        stop=stop,
    )


def test_missing_file_reports_sanitized_error(tmp_path, capsys):
    image = tmp_path / "private-sentinel.jpg"
    service = StateService(MemoryStorage())
    accumulate_categories(
        PipelineResult(image, (StageResult("json", "completed"),)),
        service,
        enabled=True,
        read_envelope=_read_envelope,
    )
    assert service.snapshot_categories() == []
    error = capsys.readouterr().err
    assert "state error" in error and "private-sentinel" not in error


def test_disabled_does_not_read(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("disabled accumulation read a file")

    monkeypatch.setattr(Path, "read_bytes", forbidden)
    result = PipelineResult(
        tmp_path / "sample.jpg", (StageResult("json", "completed"),)
    )
    accumulate_categories(result, object(), enabled=False, read_envelope=_read_envelope)


def test_unexpected_optional_failure_is_sanitized(tmp_path, capsys):
    image = tmp_path / "sample.jpg"
    Path(str(image) + ".desc.json").write_bytes(envelope([["A"]]))

    class Broken:
        def add_categories(self, paths):
            raise RuntimeError("private sentinel")

    accumulate_categories(
        PipelineResult(image, (StageResult("json", "completed"),)),
        Broken(),
        enabled=True,
        read_envelope=_read_envelope,
    )
    assert "private sentinel" not in capsys.readouterr().err
