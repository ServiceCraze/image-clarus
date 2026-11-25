# Step B4 - Implement per-image execution and state lifecycle [CODE] (COMPLETED)

**Status:** Complete

**Scope deviations:** None

## Files Created/Updated/Removed

- Created: `src/image_clarus/batch_execution.py`, `tests/unit/test_batch_execution.py`, and this record.
- Updated: `src/image_clarus/stage_protocol.py`, `src/image_clarus/stages/description.py`, `src/image_clarus/stages/structure.py`, `src/image_clarus/stages/xmp.py`, `src/image_clarus/state/storage.py`, `src/image_clarus/state/service.py`, `src/image_clarus/state/accumulation.py`, `pyproject.toml`, `uv.lock`, `tests/unit/test_cli.py`, `tests/unit/test_resources.py`, `README.md`, and `docs/slice-4/IMPL-PLAN-slice-4.md`.

Distribution-check hardening (same step): `tests/unit/test_resources.py` now skips its two distribution-channel checks when the tests are not run from the project checkout (no `pyproject.toml`/`prompts/image-description.txt`) or when `uv` is unavailable, instead of failing in an environment that cannot build a wheel. Both distribution checks and the CLI version check now compare against the installed metadata version rather than a hard-coded string, so a patch bump no longer breaks them.
- Removed: None.

## Summary

Implemented a sequential image-first executor over the frozen B3 plan. It runs each selected stage through its registered inspection and continuation, keeping planner predictions provisional and taking stage outcomes from authoritative execution. Known budget exclusions do not enter LLM inference; initially no-work images can be routed to permitted corrective inference without replenishing the admission allowance. Provider attempts, including failed attempts, receive correlated start/result facts. Transformation facts are emitted only after continuation inspection confirms work is required.

Each image gets its own state service resolved from the effective state selection and existing CWD/image ancestry rules. Invocation-local memory is shared only among images that select no persistent repository; failed selected-store fallback remains image-local. Services close after finalization, and the invocation memory backing closes after sequential processing. State errors produce sanitized, image-correlated diagnostics, do not change an otherwise valid primary result, and never redirect writes to another persistent repository.

Eligible JSON accumulation occurs once after that image's selected stages terminate, including a later-stage failure. Generated JSON and valid JSON skipped as `output_exists` contribute when enabled. Disabled accumulation and a handled stop before optional accumulation do not read JSON for that optional operation or update categories. The next image starts after finalization. Initial plan facts remain unchanged; terminal, state, interruption, and failure-policy outcomes are recorded separately.

The executor is not yet wired into the user-facing batch CLI. Concurrent stage coordination and shutdown ownership remain B5 work; reporting and CLI integration remain later plan steps. This completion does not claim actual OS-signal, in-flight publication-race, Windows-runtime, or live-provider validation.

## B4 acceptance

- [x] Sequential mode completes one image's selected stages and eligible accumulation before the next starts.
  - Evidence: `tests/unit/test_batch_execution.py::test_sequential_plan_is_complete_before_first_stage_and_not_mutated`; `test_previous_valid_json_updates_shared_memory_before_next_prompt` verifies that eligible category state is visible to later images.
- [x] Rechecks/corrections/exclusions preserve the Phase A tables and existing stage policies; actual results override predictions only in actual reporting.
  - Evidence: `test_output_appearing_before_continuation_recheck_does_not_start_transform`, `test_prediction_is_rechecked_and_valid_backup_is_recovered`, `test_initial_no_work_can_correct_missing_output_after_plan`, `test_known_exclusion_confirms_predicted_bypass_without_inference`, and `test_invalid_predicted_description_fails_without_regeneration_or_replenishment`.
- [x] State identity remains correct across collections and all precedence/fallback cases; no optional state error changes otherwise valid primary success.
  - Evidence: `test_explicit_state_precedes_cwd_and_image_collections`, `test_each_image_selects_its_own_collection_state`, `test_invalid_explicit_state_does_not_fall_back_to_cwd_store`, `test_corrupt_selected_state_is_visible_and_fallback_is_image_local`, and `test_invocation_memory_pool_closes_after_each_image_service`.
- [x] Generated and valid-skipped JSON contribute as designed; planning, unrelated skips and disabled accumulation do not.
  - Evidence: `test_previous_valid_json_updates_shared_memory_before_next_prompt`, `test_valid_skipped_json_finalizes_after_later_selected_failure` (accumulation enabled and disabled), `test_stop_after_json_terminal_skips_optional_accumulation`, and `test_budget_excluded_json_created_after_planning_does_not_accumulate`.
- [x] Existing single-image outcomes and persisted handoffs remain covered by relevant regressions.
  - Evidence: description, structure, XMP stage/integration, pipeline and CLI regression tests in the focused and full-suite commands below.
- [x] `transform_started` facts represent actual transformation work, not stage attempts.
  - Evidence: description, JSON and XMP announce only after their own inspection/validation establishes that a write will occur; `test_missing_description_is_not_a_transformation` (JSON, both `skip` and `fail` prerequisite policies), `test_transformation_is_announced_only_when_json_is_published`, `test_missing_prerequisite_is_not_a_transformation`, `test_no_change_plan_is_not_a_transformation`, `test_successful_publication_reports_a_transformation`, and the batch-level `test_known_excluded_image_still_runs_selected_non_llm_stage`, which now asserts no transformation fact for a prerequisite-skipped XMP stage.

## Tests and verification

At package version `0.3.32`, using Python `3.13.15`, from the project root (the editable reinstall was refreshed with `uv sync --extra dev` so `--version` reflects `0.3.32`):

- `uv run --no-sync --locked --extra dev pytest tests/unit/test_batch_execution.py tests/unit/test_stage_registry.py tests/unit/test_batch_plan.py tests/unit/test_description_stage.py tests/unit/test_structure_stage.py tests/unit/test_xmp_stage.py tests/unit/test_xmp_integration.py tests/unit/test_state_resolution.py tests/unit/test_state_service.py tests/unit/test_state_accumulation.py tests/unit/test_state_storage.py tests/unit/test_pipeline.py tests/unit/test_cli.py tests/unit/test_resources.py -q` — **798 passed, 6 skipped**.
- `uv run --no-sync --locked --extra dev pytest -q` — **1,661 passed, 67 skipped**.
- `uv run --no-sync --locked --extra dev ruff check .` — passed.
- `uv run --no-sync --locked --extra dev ruff format --check .` — passed; **180 files already formatted**.
- `uv lock --locked` — passed; **21 packages resolved**.
- `uv run --no-sync --locked --extra dev image-clarus --version` — `image-clarus 0.3.32`.
- `uv run --no-sync --locked --extra dev python --version` — `Python 3.13.15`.

After the final budget-exclusion regression, `uv run --no-sync --locked --extra dev pytest tests/unit/test_batch_execution.py::test_budget_excluded_json_created_after_planning_does_not_accumulate -q` — **1 passed**; Ruff check and format check for that test file passed. The focused and full-suite results above include this regression.

Wheel contents were inspected directly rather than inferred: `uv build --wheel` produces `image_clarus-0.3.31-py3-none-any.whl` containing `image_clarus/resources.py`, `resources/prompts/image-description.txt`, `resources/prompts/image-structure.txt`, `resources/schemas/image-structure-v1.schema.json`, and `resources/schemas/image-structure.schema.json`. That wheel was installed into a throwaway virtual environment, where `description_prompt()` resolved from the installed package. The earlier installed-wheel failures were an environment artifact of running the tests from outside the checkout, which cannot build a wheel; the skip guard now records that condition explicitly instead of failing. No packaging defect was found.

No live provider call, Windows runtime test, CLI batch execution, actual OS signal, or stop/publication race test was performed. Stop behavior here is exercised with a cooperative test token and injected stage failures. No historical RED result is claimed; tests and implementation evolved together under the approved development policy.
