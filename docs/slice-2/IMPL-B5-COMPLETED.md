# Step B5 — Integrate the XMP stage, registry, and single-image CLI

**Status:** In progress — implementation and most verification are complete, but the interruption acceptance row remains open because one real-signal regression test timed out once. The failure has not been reproduced or diagnosed; later passing runs do not establish its cause or prove it cannot recur. B5 is not marked complete.

## Changes

- Integrated `run_xmp` in `src/image_clarus/stages/xmp.py`: source/sidecar/backup alias guards, persisted JSON and XMP recovery, policy planning, ExifTool transformation and recoverable publication. No-change still performs required recovery and backup cleanup. Selected XMP does not invoke a model; errors and timeout are categorized without raw metadata or tool output.
- Added XMP to the fixed `desc,json,xmp` registry and CLI default in `src/image_clarus/pipeline.py` and `src/image_clarus/cli.py`; explicit subsets do not expand prerequisites. Signal state reaches the stage, and the existing result and exit formatting is retained. Help distinguishes create-only description/JSON from policy-driven XMP.
- Added `tests/unit/test_xmp_integration.py`, `tests/integration/test_xmp_cli_b5.py` and `tests/integration/test_xmp_signal_b5.py`; reconciled existing unit CLI/pipeline and integration tests with the new registry without dropping the previous description/JSON scenarios. The retained real-signal description test uses an explicitly labeled version-only ExifTool double for selected-stage preflight.
- Updated `pyproject.toml`, `uv.lock`, `tests/unit/test_cli.py` and `tests/unit/test_resources.py` to application version `0.1.27`; updated the plan and B4 subsequent-progress note. No files removed.

## Evidence

- Observed RED: new registry ordering/subset tests failed five cases before implementation; a new `--stages xmp` black-box test rejected the stage as invalid. A stage test initially failed because `run_xmp` did not exist, which shows missing availability rather than an individual behavior failure. A later cooperative cancellation scenario reported `no_change` instead of `interrupted` before correction. These cases pass in subsequent focused/full runs; other scenarios are supplemental coverage, not claimed historical RED.
- `PATH=<exiftool-directory>:$PATH uv run --locked --extra dev --python 3.13 pytest -q tests/integration/test_xmp_signal_b5.py tests/integration/test_xmp_cli_b5.py tests/unit/test_xmp_integration.py tests/unit/test_xmp_stage.py tests/unit/test_xmp_backend.py`: **184 passed** before the additional signal and regenerate scenarios. The real-ExifTool synthetic CLI tests cover standalone and composed runs, persisted JSON, source bytes, no-change, errors and preservation; other tests use explicitly identified tool/provider doubles. Real SIGINT/SIGTERM tests at the end of XMP transformation and during output write, backup replace and destination replace subsequently passed **8/8**, preserving the appropriate original or complete replacement and backup. The tests do not claim digiKam interoperability or power-loss durability.
- Final full suite with ExifTool 13.64 on PATH: **816 passed** on Python 3.13 and **816 passed** on Python 3.12.14 in an isolated environment. A separate Python 3.13 run without ExifTool passed **795** with **17 skipped** before the last four real-tool-only signal cases were added. `uv lock --locked`, Ruff check and format across source and tests passed; CLI reported `image-clarus 0.1.27`.
- The first parent full run found ten integration expectations still tied to the old two-stage default; these were reconciled and the corresponding tests pass in the final suites. A later run exposed a help-string capitalization mismatch; it was corrected and the final suites pass.
- **Unresolved signal observation:** one subsequent focused integration run timed out after four seconds waiting for the CLI to exit on SIGTERM during a held description-provider request. The process was killed by test cleanup. The same uninstrumented case passed a direct rerun and **130 further repetitions**, and both final full suites passed. A further **100 instrumented repetitions** passed without producing a diagnostic trace. There is no established root cause or evidence that the failure predates B5. These passes do not erase the failure; the interruption criterion remains unchecked pending diagnosis or explicit Product Owner disposition.
- Reviewed stage and registry reachability: CLI wires selected XMP through `run_xmp`, and the stage uses the B4 planner, B3 backend and shared artifact service. Existing two-stage tests were updated or scoped explicitly to `desc,json`; no obsolete production implementation or fixture was removed. No Git command was run.

## Acceptance

- [x] Default and explicit stage combinations follow `desc,json,xmp` order and require no automatic prerequisite expansion.
- [x] XMP stage works alone with persisted JSON and requires ExifTool only when selected; source image bytes remain unchanged.
- [ ] Recoverable sidecar publishing, stage outcomes, exit codes, interruption and config precedence match the frozen contracts.
- [x] Existing `desc`/`json`, search stub and artifact behavior regressions pass; obsolete code/fixtures are reviewed.
- [x] Observed RED/GREEN, regression and completion record evidence are linked.
