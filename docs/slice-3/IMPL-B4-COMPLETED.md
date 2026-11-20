# Step B4 - Implement safe namespaced macro expansion [CODE] (COMPLETED)

**Status:** Complete for the reusable macro engine and safe configuration snapshot. Applying the engine to model stages and provider requests remains B5; JSON-derived accumulation remains B6.

**Scope deviations:** None.

## Files created, updated, removed

- Created: `src/image_clarus/prompt_expansion.py`, `tests/unit/test_prompt_expansion.py`, `test_prompt_expansion_boundaries.py`, `test_prompt_expansion_security.py`, and this record.
- Updated: the Slice 3 plan and A3/B3 subsequent-progress notes; `pyproject.toml`, `uv.lock`, `tests/unit/test_cli.py`, `tests/unit/test_resources.py` for version delivery.
- Removed: None. No stage, provider request, production prompt, or accumulation implementation was changed.

## Behavior and evidence

1. The engine scans authored prompt text once, resolves permitted `config` and `state` names, handles literal escaped openings and rejects malformed, unknown or forbidden references through sanitized configuration errors. Expansion output is not scanned recursively. It serializes JSON-compatible containers deterministically with Unicode preserved and uses raw text for strings. No stage-specific instruction is inserted.
2. A separate configuration snapshot recursively omits secret-bearing schema fields and configured inline/environment credential substrings from keys and values, including nested containers. An independent audit found a tuple-container bypass at the synthetic engine boundary; tuples are now recursively filtered, unsupported values are rejected safely, and unexpected errors are sanitized while stop signals propagate. The original provider configuration is unchanged.
3. Per-macro literal delimiters and depth options work for both namespaces and non-category arrays. Tests cover defaults, null, positive and zero depths, invalid negative/boolean depths, deduplication, independent options, mixed arrays and unchanged prompt/config/state inputs.
4. The engine reads known category paths via the existing invocation-local state service. An injected storage-read failure through the real service produces visible sanitized diagnostics and an empty known-category snapshot; later memory additions work. Intentional memory use and stop propagation are covered. This is unit-level evidence, not a captured stage request.
5. E02–E06 and related cross-step evidence remain open until B5/C1/C2 exercise the integration and request boundaries. No claim is made that real model requests already use macros or that unavailable state was tested through a model stage.

## Verification and limitations

- The initial new-module test run failed **collection** because the macro module did not exist; it was not a behavioral RED. Initial behavior tests and broader scenarios were then developed and passed. This test-order limitation is recorded, not reconstructed as historical failures.
- Audit-driven security/error tests produced **7 failures and 3 passes** before correction; the same test file passed **10 tests** afterward. The combined macro suites passed **56 tests**. Other boundary tests were supplemental and added after implementation.
- An independent final security audit reported no further applicable reproduced defect; its probes and tests used fictional values. The tuple leak reproduction was at the engine boundary, not a demonstrated ordinary validated YAML input.
- With temporary ExifTool 13.55 on `PATH`, `uv run --locked --extra dev --python 3.13 pytest -q` passed **1,088 tests**, no skips. `uv run --locked --extra dev --python 3.13 ruff check .` and `ruff format --check .` passed with **134 files** formatted. `uv lock --locked` resolved **21 packages**; the CLI reported **0.2.11**.
- No real provider, private credentials, live model request, stage integration or Git command was used. Captured-request security and the four stage/namespace combinations belong to B5/C1.

## B4 acceptance

- [x] Tests cover both namespaces and a non-category hierarchical-string array, demonstrating a generic mechanism.
- [x] Default, `null`, positive, zero, negative, delimiter, deduplication, and per-macro independence behave as specified.
- [x] Snapshot comparisons show no prompt/config/state mutation after expansion, including depth zero.
- [x] Direct, environment-resolved, and containing-object credential cases cannot expose secret values in expansions or diagnostics.
- [x] Unavailable state values use the frozen nonblocking behavior; no stage-specific prompt instruction is embedded in the engine.
