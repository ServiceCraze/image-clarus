# Step B2 - Implement reusable deterministic discovery [CODE] (COMPLETED)

**Status:** Complete. The review-identified Windows wildcard-classification defect was corrected and verified as described below. Integrated process/rebuild command wiring and empty-run preflight remain B6/M2 and B6/C1 obligations; B3 has not been started. Earlier versioned test evidence remains historical.

**Scope deviations:** None.

## Files created, updated, removed

- Created: `src/image_clarus/discovery.py`, `tests/unit/test_discovery.py`, and this record.
- Updated: `pyproject.toml`, `uv.lock`, `tests/unit/test_cli.py`, `tests/unit/test_resources.py`, and the Slice 4 plan.
- Removed: None.

## Implementation and evidence boundaries

Discovery supplies image and sidecar selection interfaces using resolved controls, literal-first classification, metadata-only deterministic traversal, native glob matching, depth, resolved-path identity and first-selection provenance. Explicit file, discovered link and directory-root rules differ as designed. Fatal selection errors identify the input index without exposing underlying exception details and do not return a partial result. The tests use synthetic files, and include guarded content/mutation calls on successful and error paths for both interfaces.

Independent audits identified an invalid rejection of `[**]` within a bracket class, gaps in sidecar/error and reparse-point tests, and Windows-invalid fixture names. The implementation and tests were corrected; simulated reparse attributes and host-independent Windows path parsing are not Windows filesystem/runtime tests. The six default suffixes establish discovery eligibility, not decoder support. CLI batch execution, category state, provider and XMP operations were not implemented by B2.

## Verification

At version `0.3.26`, from the project root:

- `uv lock --locked` passed; `image-clarus --version` reported `0.3.26`.
- `uv run --locked --extra dev --python 3.13 pytest -q`: **1,223 passed, 66 skipped**; skips are not passes.
- `uv run --locked --extra dev --python 3.13 ruff check .`: passed; `ruff format --check .`: 170 files already formatted.
- The focused discovery suite passed 33 tests after audit corrections. Real Linux traversal and pure Windows drive/UNC/separator parsing were exercised; Windows runtime, junction behavior and decoder support were not verified.

**Subsequent review correction, version `0.3.27`:** Windows `lstat` can report `ERROR_INVALID_NAME` (WinError 123) for paths containing `*` or `?`. Literal-first classification now proceeds to native pattern handling for that specific combination; other access errors and invalid names without those wildcard characters remain failures. Simulated error tests cover image and sidecar interfaces, both wildcard characters, existing bracket literals, non-wildcard invalid names and permission/other errors. Before the correction, the focused regression run reported four failures and ten passes; afterward the discovery unit file passed 47 tests. On the delivered version, `uv lock --locked` passed, CLI `--version` reported `0.3.27`, the full suite passed **1,237 tests with 66 skipped**, Ruff passed, and format check reported 171 files already formatted. These Windows errors were simulated on Linux; no Windows runtime execution is claimed.

## B2 acceptance

- [x] Repeated unchanged selections yield the documented order and deduplicated identities across files, roots, and patterns.
- [x] Depth and symlink behavior match A1/A3, including independent rebuild controls.
- [x] The default candidate set visibly covers `jpg`, `jpeg`, `png`, `webp`, `tif` and `tiff`, subject to documented adapter support; configuration/CLI overrides work without claiming eligible extensions are decodable.
- [x] Discovery handles empty/errors as designed and performs no stage, state, or content operations.
- [x] Portable design and host-independent Windows drive/UNC/separator parsing tests, plus real Linux traversal, cover the A1 platform contract without claiming unperformed Windows runtime verification.
