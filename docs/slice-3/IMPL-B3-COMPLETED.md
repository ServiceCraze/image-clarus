# Step B3 - Implement initialization and state resolution [CODE] (COMPLETED)

**Status:** Complete for initialization, selection and optional per-invocation state. Prompt macro integration and JSON-derived accumulation remain assigned to B4–B6.

**Scope deviations:** None.

## Files created, updated, removed

- Created: `src/image_clarus/state/resolution.py`, `state/service.py`; `tests/unit/test_state_resolution.py`, `test_state_service.py`, `test_b3_precedence_matrix.py`; `tests/integration/test_state_cli.py`, `test_state_b3_primary.py`; and this record.
- Updated: `src/image_clarus/config.py`, `src/image_clarus/cli.py`, `tests/unit/test_slice3_config.py`, `tests/unit/test_cli.py`; the Slice 3 plan and A3/B1/B2 subsequent-progress notes; `pyproject.toml`, `uv.lock`, and `tests/unit/test_resources.py` for version synchronization.
- Removed: None. No prompt-expansion or JSON accumulation consumer was implemented.

## Behavior and evidence

1. `image-clarus init` targets CWD independently of image, model and stage configuration; `init --help` works without them. It delegates to the B2 non-destructive initializer, which recognizes existing valid state and refuses incomplete or invalid state. Ordinary processing does not initialize a persistent repository.
2. Explicit CLI state selection precedes YAML, then CWD ancestors, image ancestors and memory. The matrix tests dedicated flag, override, YAML and null clearing, relative origins, nested repositories, CWD priority and an explicit shared repository serving unrelated collections. An accessible nearer uninitialized directory is skipped; a selected broken or inaccessible candidate is an error rather than a reason to select a different persistent repository.
3. An independent audit identified premature non-strict state-path resolution: a dangling symlink followed by a parent component could normalize to a different persistent repository, and injected path-access failures could become fatal config errors. State paths now preserve filesystem components while anchoring to their correct configuration origin; strict selection happens in the state layer. Focused cases exercise the real CLI and injected permission failures. The five cases failed before the fix and passed afterward.
4. The invocation-local service uses a selected SQLite repository or memory. Open/read/update failures produce sanitized stderr independent of logging level; read failure returns an empty snapshot, and update failure is not retried in memory. Subsequent memory-only operations work without claiming persistence. The service closes after pipeline processing and on an injected stage-setup failure. Stop-token errors propagate rather than becoming state fallback.
5. A synthetic loopback-provider CLI test generates new description and JSON sidecars with missing, corrupt and incompatible explicitly selected repositories at all four supported logging levels. It verifies successful primary output, visible sanitized state errors, source-image integrity, no missing-repository creation and byte-for-byte preservation of a different discoverable repository. A separate CLI case publishes XMP through real ExifTool with unavailable state and no provider request. Tests use no live model or private images.

**Subsequent B4 progress:** [B4](IMPL-B4-COMPLETED.md) implemented the independent macro engine; model-stage integration remains B5. The B3 evidence above is historical.

## Verification and limitations

- The first resolution/service test attempts failed collection because the new modules did not exist; these establish missing modules, not behavioral RED for every initial B3 behavior. The initial implementation's focused configuration, resolution, service and CLI tests passed after implementation. The audit-driven path regressions provided observed behavioral RED (**5 failures**) and GREEN (**5 passes**); other matrix and publication tests were supplemental after implementation. The initial test-order limitation is retained as historical evidence.
- A final independent audit did not reproduce a further concrete defect. It identified a possible setup-exception cleanup gap; the service cleanup scope was extended to cover stage setup, and a supplemental injected-failure test verifies close. That test was added after the change and is not claimed as historical RED evidence.
- With temporary ExifTool 13.55 on `PATH`, `uv run --locked --extra dev --python 3.13 pytest -q` passed **1,032 tests** without skips, including the supplemental XMP fallback case. A focused state/CLI run passed **98 tests**; the subsequent publication test file passed **13 tests**.
- `uv run --locked --extra dev --python 3.13 ruff check .` and `ruff format --check .` passed; **130 files** were formatted. An initial format check found one line needing formatting; it was corrected and the check rerun. `uv lock --locked` resolved **21 packages**; the CLI reported **0.2.10**.
- Permission denial was tested by controlled injection, not by an actual OS-permission-denied CLI run. B2 supplies separate-process initialization contention/crash tests; B3 does not claim an actual OS-signal race at SQLite commit or end-to-end accumulation, which remain later integration concerns. No Git command, live provider, or consumer GUI test was run.

## B3 acceptance

- [x] `init` initializes in CWD, and ordinary processing in an uninitialized tree leaves no persistent repository.
- [x] Table-driven tests cover the entire precedence order, nearest nested matches, unrelated-collection sharing, and CWD winning over a different image repository.
- [x] An invalid explicit selection emits a state error and does not update another persistent repository; otherwise valid primary work retains its outcome.
- [x] Diagnostics remain visible under supported logging-level settings and exclude synthetic secret values.
- [x] Existing CLI and selected-stage behavior remain supported; `init --help` is available without an image or configured model.
