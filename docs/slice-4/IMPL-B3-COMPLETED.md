# Step B3 — Implement stage capabilities and metadata planning (COMPLETED)

**Status:** ✅ Complete

**Scope deviations:** None

## Files Created/Updated/Removed

- Created: `src/image_clarus/batch_plan.py`, `src/image_clarus/stage_protocol.py`, `src/image_clarus/stage_registry.py`, `tests/unit/test_batch_plan.py`, `tests/unit/test_description_stage.py`, `tests/unit/test_stage_registry.py`, `tests/unit/test_structure_stage.py`, and this record.
- Updated: `src/image_clarus/discovery.py`, `src/image_clarus/stages/description.py`, `src/image_clarus/stages/structure.py`, `src/image_clarus/stages/xmp.py`, `tests/unit/test_xmp_integration.py`, `pyproject.toml`, `uv.lock`, `tests/unit/test_cli.py`, `tests/unit/test_resources.py`, `README.md`, `docs/slice-4/IMPL-PLAN-slice-4.md`, and `docs/slice-4/IMPL-B2-COMPLETED.md`.
- Removed: None.

## Summary

Added a lazy generic stage registry, the complete metadata-only initial planner, and a shared continuation protocol. Description and JSON stage entry points now drive the same stage-owned continuations through their synchronous adapters. The XMP descriptor remains `uses_llm=false` and `skip_if_valid_output_exists=false`; its `inspect` only schedules `WorkRequired`, even when inference is disallowed, while `start_or_resume` runs the existing synchronous non-LLM path and returns its authoritative result. XMP is not bypassed from mere sidecar existence; its existing `no_change`, recovery, validation, and failure outcomes remain authoritative during execution. Discovery-time selection provenance is retained through planning, and all-bypassed routes still reach an owning selected stage for authoritative outcomes.

Planning records predictions, admission classes, routing, initial queues, and the A4 memory estimate; it does not execute a stage or treat a prediction as a successful result. `build_plan` returns only after classifying its full input; streamed rows are provisional and do not dispatch stages. B4 owns the integrated coordinator guarantee that execution starts after planning returns, which is not claimed or tested here. The regression matrix covers every supported selected-stage subset across sidecar-existence, regeneration, and planner admission cases (`None`, a planner-only zero-slot boundary, and one slot); the CLI/configuration contract remains a positive-integer limit. The 10,000-image synthetic case asserts initial queues of 1,000 description, zero JSON, and 9,000 XMP entries. Boundary tests prohibit content/file opens, SQLite opening, artifact recovery/writes, subprocess/ExifTool work, and provider transport on successful planning and on predicate, input-iteration, and invalid-selection failures.

Description and JSON continuations classify interrupted provider results and interrupted publication outcomes as `skipped/interrupted`. Existing pipeline/CLI stop ownership and signal exit precedence remain in place. B3 does not implement the batch coordinator, stage actors, provider child, or stop/result/publication races; those belong to later execution/verification steps. The XMP seam is synchronous because XMP is non-LLM work, not an asynchronous provider-request continuation.

## Reference / Orphan Audit

- Audit scope: `src/image_clarus/cli.py` stage wiring; the existing description, JSON, and XMP synchronous entry points; the registry's lazy references; and the planner/protocol imports.
- Confirmed orphaned or superseded code removed: None. Existing synchronous entry points remain reachable and drive the same stage-owned paths; no duplicate completion policy was retained.
- Approved orphan-retention exceptions: None.
- A static import-graph scan covered direct and relative imports across all 31 package modules and explicitly included the registry's three lazy stage targets. A scoped search found no other dynamic-import sites, and the graph had no cycles.

## B3 acceptance

- [x] Planning is complete before execution and respects the metadata-only boundary on success and failure paths.
  - Evidence: `src/image_clarus/batch_plan.py::build_plan`; `tests/unit/test_batch_plan.py::test_planning_has_no_execution_or_mutation_side_effects`; `tests/unit/test_stage_registry.py::test_planning_import_does_not_load_stages`.
- [x] Initial admission counts distinct images, honors deterministic order/regeneration, and does not suppress selected non-LLM eligibility after N.
  - Evidence: `tests/unit/test_batch_plan.py::test_admission_routes_and_dedup`, `tests/unit/test_batch_plan.py::test_metadata_matrix`, and `tests/unit/test_batch_plan.py::test_ten_thousand_routes`.
- [x] Stage subsets never expand implicitly; XMP-only planning consumes no LLM slots.
  - Evidence: `tests/unit/test_batch_plan.py::test_metadata_matrix`, `tests/unit/test_batch_plan.py::test_regeneration_selection_and_generic_capability`; `tests/unit/test_stage_registry.py::test_stage_references_and_order`.
- [x] Existing authoritative stage skip/recovery behavior remains correct after shared-logic extraction.
  - Evidence: `src/image_clarus/stages/description.py::run_description`, `src/image_clarus/stages/structure.py::run_structure`, and `src/image_clarus/stages/xmp.py::run_xmp`; description, structure, XMP stage/integration, and pipeline regression suites in the focused command below and full suite.
- [x] Required queue-count examples and generic-capability tests pass without using predictions as stage-success evidence.
  - Evidence: `tests/unit/test_batch_plan.py::test_ten_thousand_routes` and `tests/unit/test_stage_registry.py::test_generic_descriptor_needs_no_execution_or_name_special_case`.

## Tests and verification

At version `0.3.29`, from the project root:

- `uv run --no-sync --locked --extra dev pytest tests/unit/test_batch_plan.py tests/unit/test_stage_registry.py tests/unit/test_description_stage.py tests/unit/test_structure_stage.py tests/unit/test_xmp_stage.py tests/unit/test_xmp_integration.py tests/unit/test_pipeline.py -q` — **648 passed, 5 skipped**.
- `uv run --no-sync --locked --extra dev pytest -q` — **1,633 passed, 66 skipped**.
- `uv lock --locked` — passed; 21 packages resolved.
- `uv run --no-sync --locked --extra dev image-clarus --version` — `image-clarus 0.3.29`.
- `uv run --no-sync --locked --extra dev ruff check .` — passed.
- `uv run --no-sync --locked --extra dev ruff format --check .` — passed; 177 files already formatted.

No live provider call or Windows runtime test was performed. Batch coordinator/actor integration and real stop-race verification remain outside B3.