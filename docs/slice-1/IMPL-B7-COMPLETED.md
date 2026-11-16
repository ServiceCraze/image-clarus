# Slice 1 — Step B7 execution record

**Status: Complete.**

**Scope deviations:** Product Owner approved isolated, bounded schema validation and a documented exception for incomplete historical B7 behavioral RED evidence. Real OS-signal and full-pipeline interruption validation carries forward to [Step C2](IMPL-PLAN-slice-1.md#step-c2--verify-failure-recovery-source-integrity-and-credential-hygiene-test). The original TDD limitation remains described below.

**Files created:** `src/image_clarus/stages/structure.py`, `src/image_clarus/schema_worker.py`, `prompts/image-structure.txt`, `schemas/image-structure.schema.json`, `tests/unit/test_structure_stage.py`, `tests/unit/test_structure_resources.py`, `tests/unit/test_structure_edge_cases.py`, `tests/unit/test_schema_worker.py`, `tests/unit/test_schema_preflight_boundary.py`, `tests/unit/test_schema_offline.py`, `tests/unit/test_boolean_context.py`, and this record.

**Files updated:** `src/image_clarus/config.py`, `src/image_clarus/resources.py`, `pyproject.toml`, and [IMPL-PLAN-slice-1.md](IMPL-PLAN-slice-1.md).

**Files removed:** None. Temporary debugging files created during the step were removed and are not deliverables.

## Implemented and verified so far

The structured stage, A3 prompt/schema source assets and wheel resource mappings are present. Tests exercise generated output, provenance snapshots, custom inputs, retries, existing-output handling, safe-write recovery and local schema references using synthetic data and an HTTPX mock transport; no live provider was contacted.

Final verification: `uv run --locked --extra dev pytest -q` reported **297 passed**; Ruff, formatting, `uv lock --locked`, and `uv build` passed. A freshly built wheel installed with normal dependencies in a new Python 3.13 environment; outside the checkout with `PYTHONPATH` cleared, its worker passed valid-schema preflight, invalid referenced-schema rejection, and boolean-feedback checks. Tests use synthetic inputs; no live provider was contacted.

## Observed test-first corrections

- Existing description double-read: the focused read-count test failed before correction and passed after it. Description recovery retention and non-progressing property-reference recursion each had an observed failing regression test followed by a passing test.
- Large integer JSON parsing and direct recursive-reference validation had observed failing tests before correction. A 401-digit integer with `multipleOf: 0.1` raised `OverflowError`; its focused test failed before adding a sanitized failure boundary and passed afterward.
- Focused reference-feedback regressions were observed failing before their corrective implementation, including anchored/escaped targets, nested targets, sibling keywords and boolean references. Further review nevertheless found the boolean feedback defect below.

## Review findings and decisions

1. Boolean subschema feedback initially reported incorrect instance/schema pointers. Validation-time location capture now covers direct false schemas, nested references, arrays, anchors, percent encoding and branches in synthetic tests.
2. Custom-schema regular expressions initially allowed unbounded validation. Bounded subprocess preflight and validation now return a sanitized configuration failure on timeout; this is a wall-clock boundary, not a memory sandbox.
3. Original B7 behavioral RED evidence is incomplete: the initial missing-module failure and tests added after implementation do not establish a behavioral RED for every B7 acceptance case. Record supplemental passing tests as such, not as historical RED. The Product Owner explicitly accepted this documented TDD exception and directed completion and verification; the missing historical evidence remains a limitation, not a claimed pass.

The Product Owner also approved designing and implementing bounded, isolated validation for custom-schema regexes rather than silently restricting the schema language.

**Subsequent progress:** Schema preflight and payload validation are routed through a disposable worker with a 10-second wall-clock deadline. A timeout returns a sanitized configuration failure without a model-validation retry or output publication. The focused timeout boundary was observed failing before integration and passing afterward. Worker timeout and exception tests exercise child cleanup; real OS signal and full pipeline interruption validation remains assigned to C2. Four boolean-schema behavior cases initially failed and later passed.

**Further progress:** Boolean-schema feedback and `minContains`/`maxContains` pointer regressions pass. An audit found that nested Draft 7 `dependencies` could bypass the fragment-only reference check and trigger a network fetch. Regression tests using a local HTTP server observed the bug before correction and zero requests afterward; runtime validation uses an offline registry. The first correction overrestricted inactive annotation data; dialect/scope-aware traversal corrected the observed cases. Subsequent audit found invalid schemas activated through local references were not preflight-validated; two new regressions failed before the correction and pass after it. Tested library versions are `jsonschema 4.26.0` and `referencing 0.37.0`; boolean-location instrumentation uses private `jsonschema` internals and must be revalidated on dependency upgrades. These tests are not a proof for every schema/dialect combination.

**Known dependency risk:** `pyproject.toml` does not constrain `jsonschema` to the tested version or a tested compatibility range. A future installation may select an incompatible release, including one that changes the private internals used by boolean-feedback instrumentation. No incompatibility was observed in B7; a tested version bound or a supported public-API replacement remains a maintenance follow-up. The lockfile's tested resolution does not constrain independent package installations.

## Acceptance

- [x] `json` consumes the persisted `.desc.txt` and writes exactly `<image>.desc.json`.
- [x] Every newly generated output is fully schema-validated, includes the required provenance contract, and covers all required metadata categories.
- [x] The output identifies its metadata-schema version independently of the application version, following A3's default/custom-schema rules.
- [x] Newly generated output fingerprints the exact persisted description bytes consumed; a structurally valid existing output skips unchanged across selected schema/version changes.
- [x] Invalid existing JSON/envelope is not overwritten without explicit regeneration; regenerated output uses current selected inputs/schema and is published only after validation.
- [x] Custom schema and prompt replacement work without source changes and follow A3 semantics.
- [x] Invalid/missing prerequisites follow the approved result policy; invalid output is never published as complete.
- [x] RED/GREEN and regression evidence is recorded; [IMPL-B7-COMPLETED.md](IMPL-B7-COMPLETED.md) is linked.

B8 has not been started as part of B7. The B7 test-order exception above remains documented and explicitly accepted; it does not convert missing historical RED into observed evidence.

**Subsequent progress:** B8 is complete; see [IMPL-B8-COMPLETED.md](IMPL-B8-COMPLETED.md). B9 and Phase C remain open.
