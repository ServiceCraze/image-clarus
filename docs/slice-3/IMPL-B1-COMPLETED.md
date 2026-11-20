# Step B1 - Extend configuration and JSON hash compatibility [CODE] (COMPLETED)

**Status:** Complete. B1 implements the configuration and envelope boundary only; state storage/discovery, macro expansion, and prompt integration remain assigned to later steps.

**Scope deviations:** None.

## Files created, updated, removed

- Created: `tests/unit/test_slice3_config.py`, `tests/integration/test_slice3_b1.py`, and this record.
- Updated: `src/image_clarus/config.py`, `src/image_clarus/cli.py`, `src/image_clarus/stages/structure.py`; `tests/unit/test_description_stage.py`, `tests/unit/test_structure_stage.py`, `tests/unit/test_slice2_structure.py`, `tests/unit/test_xmp_stage.py`, `tests/integration/test_c1_compatibility.py`; the Slice 3 plan and A3 subsequent-progress note; `pyproject.toml`, `uv.lock`, `tests/unit/test_cli.py`, and `tests/unit/test_resources.py` for version synchronization.
- Removed: None. XMP continues consuming the existing shared structure validator; no XMP production relocation was needed.

## Behavior and evidence

1. The resolver supports the new state and prompt settings, strict validation, YAML-relative and CLI-relative state paths, `--state-dir` precedence, and JSON-bracketed literal macro-name override segments. Tests cover ordered parent/child assignments, invalid depth, safe diagnostics, selection isolation, and rejection of unknown mapping keys in each layer. An independent audit exposed unknown nested keys under scalar leaves; focused failing cases drove the fix. A higher-priority state-directory flag may repair a malformed lower-priority state value under existing precedence.
2. Config and JSON accept full slash-separated preferred category paths using the existing segment rules; XMP root and segment validation remain unchanged. The existing provider receives complete configured paths at this step. Prompt-controlled category guidance and its captured expansion are B5 work.
3. Newly generated envelopes omit `prompt_sha256` by default. YAML or CLI opt-in includes the SHA-256 of exact independently authored prompt source bytes. The shared envelope validator and XMP accept valid artifacts with or without the field, and reject malformed present values. The CLI integration suite uses a controlled local provider stub to verify default, YAML and CLI precedence, exact fixture bytes, prompt-change skip, and explicit regeneration. The source-byte meaning after macro expansion remains B5 evidence, since expansion is not implemented in B1.
4. Existing provenance identifiers, description hash, custom-schema hash, create-only and regeneration behavior remain covered. A former description-stage assertion froze the production prompt text; it now compares the captured request with the actual resource while retaining an independent custom-prompt case. The production prompt itself was not changed.
5. Shared crosswalk outcomes E03, E05–E08 and E14 remain open as whole outcomes because they also belong to later steps; B1 evidence does not imply those later portions ran. State availability and initialization are not implemented by accepting the setting.

**Subsequent progress:** [B2](IMPL-B2-COMPLETED.md) implemented the state storage and category-domain foundation. CLI discovery and nonblocking integration remain assigned to B3; B1's recorded evidence is unchanged.

## Verification and limitations

- Initial focused configuration RED: `uv run --locked --extra dev --python 3.13 pytest -q tests/unit/test_slice3_config.py` showed **16 failures, 5 passes** before configuration implementation; the failures included absent defaults, override grammar and CLI support. The subsequently extended focused file passed **33 tests**.
- Initial structure/envelope focused run showed **6 failures, 6 passes** before implementation; the same selected scenarios passed **12 tests** afterward. Supplemental XMP and provenance tests were added after implementation and are not represented as historical RED evidence.
- The audit-driven unknown-child fix began with **six failing focused cases**, then `uv run --locked --extra dev pytest -q tests/unit/test_slice3_config.py -k 'unknown_mapping_child or state_dir_repairs_scalar_state'` passed **10 tests**; related configuration and CLI regression files passed **149 tests**. The CLI hash and prompt-change cases were supplemental tests written after implementation.
- A separate isolated copy with both built-in prompts substantially changed initially produced **1 failure, 816 passes**: the old description-stage test expected fixed production wording. After correcting that test, `uv run --locked --extra dev --python 3.13 pytest -q tests/unit` in the modified-prompt copy passed **817 tests**. The actual project prompts were not changed.
- With a temporary ExifTool 13.55 on `PATH`, `uv run --locked --extra dev --python 3.13 pytest -q` passed **927 tests**, with no skips. This includes actual ExifTool CLI old/new/invalid-hash compatibility; no consumer GUI or live model was exercised. A prior run without ExifTool passed **850** and skipped **61**; the temporary tool enabled the final run.
- `uv run --locked --extra dev --python 3.13 ruff check .` passed; `ruff format --check .` passed with **112 files** already formatted. `uv lock --locked` resolved **21 packages**; `uv run --locked --python 3.13 image-clarus --version` reported **0.2.7**.
- One independent audit's broad run had a boolean-schema feedback failure that passed in isolation; its cause was not established. The final complete suite passed, but that does not establish a root cause. During development an incorrect focused test node selected no tests; a corrected invocation passed. Neither is presented as a successful initial run.
- No live provider request, state implementation, Git command, or consumer-application interoperability test was performed. Controlled stub requests and temporary local files are test evidence only.

## B1 acceptance

- [x] Tests demonstrate CLI > YAML > defaults for the new controls, including literal dotted macro keys and negative-depth rejection.
- [x] Single and hierarchical preferred paths pass; XMP segment/root validation and unrelated stage configuration remain unchanged.
- [x] Default generation omits the hash; explicit YAML/CLI enablement includes the expected fixture-source hash.
- [x] Shared validation and XMP accept old valid artifacts with the field and new valid artifacts without it, and reject an invalid present hash.
- [x] Tests preserve `prompt_id`, raw-description hashing, model identifiers, custom-schema hashing, and create-only/regeneration behavior.
