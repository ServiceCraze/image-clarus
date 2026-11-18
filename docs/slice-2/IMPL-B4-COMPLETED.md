# Step B4 — Implement deterministic XMP selection and field policies (COMPLETED)

**Status:** Complete for the deterministic policy-planning boundary. B5 stage/CLI integration and C3 actual digiKam interoperability remain open.

**Subsequent progress:** B5 stage/CLI integration has been implemented but B5 remains open on an unexplained interruption-test timeout observed once; see [IMPL-B5-COMPLETED.md](IMPL-B5-COMPLETED.md). Actual digiKam interoperability remains C3.

## Changes

- Created `src/image_clarus/stages/xmp.py` and `tests/unit/test_xmp_stage.py`. The planner takes a persisted JSON byte snapshot, XMP snapshot and resolved settings; it returns exact backend updates and the effective tag policy, or a sanitized missing/invalid/no-change result. It does not invoke a model, generate JSON, write files or publish a sidecar.
- Validates the fixed envelope and exact built-in v1/v2 schema pairs against the bundled resources. It accepts the exact custom identity only with a lowercase SHA-256-shaped version, and extracts custom data only via explicit literal property mappings. It validates all present mapped values and candidate paths before selecting, keeps ranked order and deduplicates exact custom paths before the limit. A historical v1 payload does not repurpose keywords.
- Implements the nonempty-root policy table and the explicit empty-root non-deletion override, with exact-segment ownership. Independent localized title/caption/author `new` checks inspect all language alternatives; an unavailable source never clears metadata. Only the backend's explicitly mapped fields are planned. `no_change` indicates no new publication is needed, not that B5 recovery or retention cleanup can be skipped.
- Updated `pyproject.toml`, `uv.lock`, `tests/unit/test_cli.py` and `tests/unit/test_resources.py` to application version `0.1.26`; updated the plan and B3's subsequent-progress note. No files removed.

## Verification and evidence

- Observed behavior RED using `uv run --locked --extra dev --python 3.13 pytest -q tests/unit/test_xmp_stage.py::test_ranked_paths_are_selected_in_order_under_default_root`: after introducing the empty planner, it failed because the update was `{}` instead of the two ranked root-prefixed paths. The same test passes in the focused GREEN run below. An earlier absent-module failure was only an availability check.
- Observed further RED with `uv run --locked --extra dev --python 3.13 pytest -q tests/unit/test_xmp_stage.py::test_custom_literal_mapping_deduplicates_before_limit_without_normalization tests/unit/test_xmp_stage.py::test_missing_input_differs_from_invalid tests/unit/test_xmp_stage.py::test_empty_root_is_nondestructive_and_idempotent`: seven parameterized cases failed against the empty planner on missing results, wrong effective policy or absent planned changes. All pass in the final focused run. Other scenarios were added alongside implementation or as supplemental GREEN coverage; no separate earlier RED is asserted for them.
- `PATH=<exiftool-directory>:$PATH uv run --locked --extra dev --python 3.13 pytest -q tests/unit/test_xmp_stage.py tests/unit/test_xmp_backend.py`: **126 passed**. The tests cover the root/policy tables and repeat invocations; ordering, exact-path deduplication and invalid paths beyond the cutoff; localized-field policies and absent values; built-in/historical/custom identity, strict JSON, mappings and malformed inputs; and missing versus invalid versus no-change outcomes. The isolated unit harness forbids JSON generation and network socket creation. A synthetic test takes planned updates through the real ExifTool backend, checks unaffected localized values and repeats to a no-change plan. This is not a digiKam test or published-stage integration.
- Full suite with ExifTool 13.64 on PATH: **735 passed** on Python 3.13 and **735 passed** on Python 3.12.14 in an isolated project environment. `uv lock --locked`, `ruff check src/image_clarus tests`, and `ruff format --check src/image_clarus tests` passed; the CLI reported `image-clarus 0.1.26`.
- B5 owns actual filesystem prerequisite reading and errors, source/destination alias guards, recovery and configured backup cleanup, transformation and publication, result conversion, registry/CLI wiring, and tests at those boundaries. The planner's missing-input sentinel does not prove filesystem recovery. C3 owns real digiKam read/edit verification. No provider, real photograph or digiKam operation was used and no Git command was run.

## Acceptance

- [x] Top-N selection is reproducible and follows persisted order without semantic reranking.
- [x] Empty-root and nonempty-root policy truth tables pass, with verified no-deletion guarantees.
- [x] Title, caption and author fields follow independent policies; unavailable source data never deletes XMP values.
- [x] Older/custom JSON behavior, malformed input and no-op results match A4; XMP logic makes no model call.
- [x] Observed RED/GREEN, regression and completion record evidence are linked.
