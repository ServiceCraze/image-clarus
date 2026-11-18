# Step C1 — Verify the single-image persisted JSON-to-XMP pipeline (COMPLETED)

**Status at C1 closeout:** Complete for C1's synthetic black-box CLI and persisted-artifact verification. C2–C5 remained open at that closeout; ExifTool results are not digiKam interoperability evidence.

**Subsequent progress:** C2 metadata-preservation, recovery, failure-boundary and lock-free process-overlap verification is complete; see [IMPL-C2-COMPLETED.md](IMPL-C2-COMPLETED.md). C3–C5 remain open.

**Scope deviations:** None. This is a TEST step: new tests exercise the already-implemented production behavior and are supplemental GREEN scenario coverage, not a claim of observed test-first RED.

## Files created, updated, and removed

- **Created:** `tests/integration/test_c1_compatibility.py`, `tests/integration/test_c1_publication.py`, and this completion record.
- **Updated:** `tests/integration/test_xmp_cli_b5.py` (explicit ordered `desc,json,xmp` case), `docs/slice-2/IMPL-PLAN-slice-2.md`, `docs/slice-2/IMPL-B6-COMPLETED.md`, `pyproject.toml`, `uv.lock`, `tests/unit/test_cli.py`, and `tests/unit/test_resources.py`. Application patch version advanced to `0.1.30`.
- **Removed:** None. No production source changed and no Git command was run.

## CLI and persisted-artifact matrix

All cases use a synthetic image and fictional metadata in temporary directories. Provider-dependent cases use a controlled local HTTP provider double, not an external service. Real ExifTool **13.64** performed the XMP writes and independent field reads in applicable cases; version-only doubles are identified in the existing B5 tests and are not treated as real-tool publication evidence.

| Contract | Executed evidence |
| --- | --- |
| Stage selection and order | Existing `test_single_image_pipeline.py` and `test_xmp_cli_b5.py` exercise default selection; explicit `desc`, `json`, `xmp`, `json,xmp`, and `desc,json,xmp`; and a reversed selection with fixed execution order. They assert no implicit prerequisite expansion, no provider calls for XMP alone, and no ExifTool requirement when XMP is unselected. `test_xmp_only_ignores_invalid_unselected_json_settings_and_credentials` additionally removes the unused credential from the subprocess environment and sets invalid unused JSON settings. |
| Persisted handoff | Existing integration tests assert exact description request content and JSON output. `test_independent_xmp_consumes_swapped_persisted_json` generates JSON in one CLI invocation, deliberately changes the persisted valid artifact, then runs XMP independently and checks the actual ExifTool fields reflect the replacement with no additional provider call. `test_composed_pipeline_rereads_json_from_disk_at_stage_boundary` uses a test-only `sitecustomize` wrapper to replace JSON after the JSON stage and immediately before the real XMP stage; the completed composed CLI output reflects those disk bytes. This is an instrumented boundary test, not a claim of uninstrumented concurrent behavior. |
| Historical/custom compatibility and JSON regeneration | `test_c1_compatibility.py` checks recognized v1 and unmapped custom no-ops, explicit custom partial mappings and actual XMP output, missing/empty mapped fields, malformed present values, malformed/incompatible identities, and missing prerequisite fail/skip. It seeds an old-version JSON artifact, verifies create-only skip without description or provider request, then explicitly regenerates and checks the complete new 2.0.0 envelope/payload. JSON-only missing description `skip` is separately checked. |
| Rank, root, fields and integrity | Independent invocations check exact persisted order and top-N cutoff with a named root and explicit empty root, plus configured caption author, title and caption. Three independent policy combinations verify real sidecar title/caption/author values. Custom duplicate paths deduplicate before truncation, invalid paths after the cutoff fail, and supported empty sources under overwrite preserve the existing sidecar. Tests verify exact source bytes and, in the added publication scenarios, source SHA-256 before and after. |

## Verification

- `PATH=<exiftool-directory>:$PATH uv run --locked --extra dev --python 3.13 pytest -q tests/integration/test_c1_compatibility.py tests/integration/test_c1_publication.py tests/integration/test_xmp_cli_b5.py tests/integration/test_single_image_pipeline.py`: **58 passed**, no skips. One initial synthetic candidate fixture duplicated a built-in path and was corrected because built-in duplicates are invalid; no production defect was identified by that fixture correction.
- Isolated Python 3.13.15 project environment: `PATH=<exiftool-directory>:$PATH UV_PROJECT_ENVIRONMENT=<scratch-environment> uv run --locked --extra dev --python 3.13 pytest -q tests/integration`: **90 passed**, no skips. Running existing regression tests in this suite does not close the separate C2 step.
- Full suites with real ExifTool on PATH: **842 passed** on Python 3.13.15 and **842 passed** on Python 3.12.14. `uv lock --locked`, Ruff check and format check passed; CLI reported `image-clarus 0.1.30`.
- Scanned **44** public text artifacts across `README.md`, `examples/`, `tests/`, and `prompts/` for a targeted set of private-infrastructure and specific model-name sentinels: **0 matches**. This targeted scan is not a proof against every possible private identifier. No real image, external provider, or digiKam operation was used.
- Actual digiKam import/edit/read-back and qualitative metadata review remain C3. C2 owns the separate preservation and failure-boundary acceptance; no concurrency, power-loss durability, or universal compatibility claim is made here. The previously documented B5 one-time signal-test timeout and its unknown cause remain historical evidence.

## Acceptance

- [x] All selected-stage and default single-image flows follow persisted-file contracts and expected results.
- [x] Historical/custom JSON, missing artifact and optional-source versus invalid-input cases are distinguished correctly.
- [x] Published XMP field values, source-image integrity and policy/rank behavior match the design.
- [x] Executed test logs and completion record substantiate the verified cases.
