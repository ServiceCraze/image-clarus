# Step B4 — Implement stage results, registry, and coordinator (COMPLETED)

**Status:** Complete.

**Scope deviations:** None. Stage implementations, artifact access and CLI integration remain with B5–B8.

**Files created:** `src/image_clarus/results.py`, `src/image_clarus/pipeline.py`, `tests/unit/test_results.py`, `tests/unit/test_pipeline.py`, and this record.

**Files updated:** `docs/slice-1/IMPL-PLAN-slice-1.md`, `docs/slice-1/IMPL-B3-COMPLETED.md` (subsequent progress note).

**Files removed:** None.

## Summary

Added immutable structured stage and single-image results and exit aggregation, a fixed `desc`, `json` registry, and a coordinator that invokes injected stage implementations in registry order. Selection never expands prerequisites; invalid selections and unavailable selected implementations fail before any stage runs. The coordinator passes the same image path, complete resolved configuration and shared services to each stage, without reading sidecars or deciding stage-specific input, overwrite or completion policy. The caller supplies the already-resolved image path and preflight-validated configuration; B8 owns CLI integration and preflight ordering.

Stop-on-failure produces `stage_not_run_after_failure` records; continue invokes the next stage, which owns its own persisted prerequisites. A cooperative stop token records SIGINT or SIGTERM and prevents starting further stages; the signal exit takes priority. The tests simulate cooperative signaling and preserve a stage's completed result; actual OS-signal handling, cancelling in-flight provider calls and reaching safe-write boundaries remain B5–B8/C2 integration work. No real stages or artifact service exist yet. The JSON-only missing-prerequisite fail/skip checks use stage test doubles, not actual JSON-stage execution; B7/B8/C1 own real-stage verification.

## Verification and TDD evidence

- Focused test-first cycles observed failures for missing result/pipeline modules, unsupported stage selection, incorrect selection order and invalid-selection handling, failure-stop behavior, missing cooperative stop token, and a missing implementation being discovered after an earlier stage ran. Corresponding implementations were added and targeted tests passed. The `continue` case and supplemental tests that passed on first execution are additional GREEN coverage, not claimed as observed RED. The expanded full-configuration identity and unchanged-value assertion is also supplemental GREEN coverage.
- `uv run --locked --extra dev pytest tests/unit/test_results.py tests/unit/test_pipeline.py -q` — **15 passed**. Tests use fake stage functions and service objects; they verify ordering/subsets, fail/skip prerequisite results delegated to a fake JSON stage, unchanged configuration/service identity, failure aggregation, and cooperative interruption.
- `uv run --locked --extra dev pytest -q` — **119 passed**. `ruff check .`, `ruff format --check .`, `uv lock --check`, and `uv build --python 3.13` passed. No live provider requests or real credentials were used. Python 3.12 runtime verification remains C3 work.

## Acceptance

- [x] Registry order is deterministic; explicit selection never expands prerequisites.
- [x] The complete resolved configuration reaches each stage unchanged.
- [x] Coordinator contains no stage-specific input, completion, overwrite, or output-parsing rules.
- [x] Result and exit behavior matches A2.
- [x] RED/GREEN and regression evidence is recorded; [IMPL-B4-COMPLETED.md](IMPL-B4-COMPLETED.md) is linked.

## Follow-up

At B4 closeout, B5 and later steps had not started. B5 has since implemented and tested the artifact service; B6 and later steps have not started. Actual stage and CLI integration and OS signals are not claimed by the B4 tests.
