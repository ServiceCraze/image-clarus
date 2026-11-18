# Step B3 — Implement the ExifTool XMP backend and mapping (COMPLETED)

**Status:** Complete for the B3 backend boundary. Actual digiKam interoperability is a separate C3 obligation. B4 selection and policy and B5 stage integration/publication have not been implemented by B3.

## Changes

- Created `src/image_clarus/xmp_backend.py` and `tests/unit/test_xmp_backend.py`.
- Updated `pyproject.toml`, `uv.lock`, `tests/unit/test_cli.py` and `tests/unit/test_resources.py` for application version `0.1.24`, plus the plan and this record for B3 closeout. No files removed.
- The backend reads a byte snapshot, creates an exclusive private working `.xmp` in the supplied directory, and returns validated candidate bytes. It does not select paths, apply update policies, invoke a model, publish to a destination, or use a source image as an ExifTool target. The shared artifact validator accepts valid candidate bytes.
- The only write targets are `XMP-digiKam:TagsList`, `XMP-dc:Title-x-default`, `XMP-dc:Description-x-default`, and `XMP-digiKam:CaptionsAuthorNames-x-default`. Other values are compared by expanded namespace and semantic values. Unrecognized or unsupported RDF structures fail closed rather than being discarded; this is a deliberate current compatibility limitation, not a claim that all valid XMP can be processed.
- Subprocess calls use argument lists, disabled user configuration and an end-of-options boundary; execution time and captured output are bounded, processes are killed and reaped on timeout, and failures are categorized without exposing paths, arguments, metadata or tool output. Synthetic timeout and output-limit tests use disposable processes.
- Source-image versus destination/backup alias checks, persisted-sidecar recovery, and final publication are owned by the later stage integration; they have not been implemented or claimed here. B3 provides an artifact-service-compatible structural validator, while candidate-specific preservation is verified during transformation.

## Evidence

- `PATH=<synthetic-test-exiftool-directory>:$PATH uv run --locked --extra dev --python 3.13 pytest -q tests/unit/test_xmp_backend.py`: **14 passed**, including the real ExifTool 13.64 synthetic round trip. An independent ExifTool read confirmed the four mapped values and French alternatives; the test also checks unchanged flat keywords, Lightroom hierarchy, the original sidecar snapshot and separate synthetic image bytes. This is not digiKam interoperability evidence.
- The remaining focused cases exercise missing tool, nonzero exit, bounded actual subprocess timeout and output, sanitized errors, private temporary files, invalid arguments, malformed and unsupported structures, malformed tool output, foreign mutation and removal of a French language alternative. A valid XMP packet was published through the existing `ArtifactService` with the backend validator.
- The backend-absent initial run failed during collection, which demonstrates missing implementation, not individual behavior RED. A real-tool test exposed incorrect list replacement before correction. The artifact-validator compatibility test failed with `invalid_artifact` before the validator fix and passed afterward; the description-attribute test failed as unsupported before the parser fix and passed afterward. Other cases are supplemental passing scenario coverage; no unobserved per-test RED is asserted.
- Full suite with ExifTool on PATH: **623 passed** on Python 3.13. `uv lock --locked`, Ruff check and format check across `src/image_clarus` and `tests` passed; the CLI reported `image-clarus 0.1.24`.
- No real photo, provider request, digiKam operation, or Git command was used. The local ExifTool test uses synthetic metadata only.

## Acceptance

- [x] Backend operates on XMP sidecars and never writes image bytes; actual read/write targets match the preliminary A3 mapping. Actual digiKam interoperability remains a separate C3 obligation.
- [x] Subprocess failures, tool absence, malformed XMP and unexpected field mutation fail with actionable, nonsecret outcomes.
- [x] Required real-ExifTool mapping checks and hermetic backend tests have recorded results; unmet required mapping remains unchecked.
- [x] Observed RED/GREEN, changed-file inventory and completion record are linked.
