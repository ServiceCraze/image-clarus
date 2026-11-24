# Step B1 - Extend configuration and command boundaries [CODE] (COMPLETED)

**Status:** Complete for the B1 parser, configuration, and startup boundaries. B2 discovery, B6 integrated batch/dry-run execution, and M1/M2 category operations remain unimplemented; unfinished invocation paths report a nonzero not-implemented result rather than success.

**Scope deviations:** None.

## Files created, updated, removed

- Created: `tests/unit/test_slice4_config.py`, this record.
- Updated: `src/image_clarus/config.py`, `src/image_clarus/cli.py`, `tests/unit/test_config.py`, `tests/unit/test_cli.py`, `tests/unit/test_slice2_config.py`, `tests/unit/test_resources.py`, `pyproject.toml`, `uv.lock`, and the Slice 4 plan.
- Removed: None.

## Implementation and boundaries

- Added layered selection/depth/extension, work allowance, concurrency and failure-policy controls, the dedicated parser options and independent rebuild-depth configuration. Contextual missing-prerequisite defaults preserve explicit surviving configuration and overrides.
- Added a management configuration boundary that does not perform unrelated processing preflight; management operations themselves remain stubs. Process dry-run and other unfinished batch paths likewise remain non-success stubs, not a completed planner or real empty-batch implementation.
- Split static configuration validation from runtime ExifTool preflight. Dry-run stub tests guard content/state/artifact/pipeline and ExifTool access. Replaced selector-based ExifTool pipe reading with a bounded reader thread; direct child timeout and oversized-output cleanup are tested. No Windows runtime test was performed. An inherited stdout handle held by a descendant can keep the daemon reader alive until that handle closes; the preflight deadline does not wait for it.
- Parser tests cover singleton/conflict rules and contiguous selection grammar. Existing single-file paths remain supported; actual batch selection and execution are owned by later steps. Real empty-batch startup and runtime-preflight behavior require B2/B6 evidence.

## Verification

At package version `0.3.25`, from the project root:

- `uv lock --locked`: passed; CLI `--version`: `image-clarus 0.3.25`.
- `uv run --locked --extra dev --python 3.13 pytest -q`: **1,190 passed, 66 skipped**. Skips are not passes.
- `uv run --locked --extra dev --python 3.13 ruff check .`: passed; `ruff format --check .`: 167 files already formatted.
- Earlier focused tests included a selector-unavailable regression and real child timeout/oversized-output cleanup. The selector regression was observed failing before the portable reader change and passing afterward. An earlier concurrently edited audit run encountered a transient syntax error; its rerun passed. An earlier focused run had two fixture errors that were corrected.
- No live provider, Windows runtime or Slice 4 integrated batch/category acceptance test was run. These test results do not establish later-step behavior.

## B1 acceptance

- [x] Every approved setting is resolved through its designed YAML/CLI parser and configuration boundaries with tested precedence and diagnostics; unfinished command execution does not report success. B6 and M1/M2 own integrated process and management behavior.
- [x] Process/rebuild/macro depth settings are independent; nonpositive work limits and other invalid controls fail as designed.
- [x] Batch-default skip does not override explicit missing-prerequisite policy.
- [x] Dry-run and management startup avoid execution-only side effects; real selected-stage preflight and existing CLI behavior remain covered.
