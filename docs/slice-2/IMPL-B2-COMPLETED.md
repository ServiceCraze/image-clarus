# Step B2 — Extend structured JSON generation and packaged resources (COMPLETED)

**Status:** Complete. The Product Owner accepted the documented original per-test RED evidence gap. The review correction passes regression tests. B2 implements the enhanced built-in JSON schema (2.0.0), updated prompt, category guidance as a third user message part, and historical schema packaging. XMP backend, deterministic selection, CLI integration, and documentation remain B3–B6.

**Accepted evidence gap:** Original individual RED results were not established. The Product Owner explicitly accepted this documented gap. Initial B2 version was `0.1.21`; the review correction was `0.1.22`; this closeout is `0.1.23`.

## Files created, updated, and removed

- **Created:** `schemas/image-structure-v1.schema.json`, `tests/unit/test_slice2_structure.py`, `docs/slice-2/IMPL-B2-COMPLETED.md`.
- **Updated:** `schemas/image-structure.schema.json`, `prompts/image-structure.txt`, `src/image_clarus/resources.py`, `src/image_clarus/stages/structure.py`, `src/image_clarus/providers/openai_compatible.py`, `tests/unit/test_structure_resources.py`, `tests/unit/test_structure_stage.py`, `tests/integration/test_single_image_pipeline.py`, `docs/slice-2/IMPL-PLAN-slice-2.md`, `pyproject.toml`, `uv.lock`, `tests/unit/test_cli.py`, `tests/unit/test_resources.py`.
- **Removed:** None. Version-test changes track the package patch increment. Legacy test expectations were reconciled with the new 2.0.0 schema and prompt; they continue to test schema validation and provenance rather than simply deleting coverage.

## Work and decisions

- Copied the exact historical 1.0.0 schema bytes to `schemas/image-structure-v1.schema.json` (SHA-256 `9d90dd0aa3722535fe4f79eb1770b50900dcfe61ce376e4ce54fee03b43877f0`), mapped it into the wheel at `image_clarus/resources/schemas/image-structure-v1.schema.json`, and added `structure_schema_v1()` to `src/image_clarus/resources.py` with the existing packaged/source lookup pattern. Verified exact identity, hash, and source-tree/installed-wheel resource loading.
- Evolved the canonical schema to A2's 2.0.0: new required fields `title` (string), `caption` (string), `tag_candidates` (array of segment arrays); strict segment validation rejecting leading/trailing whitespace, `/`, `|`, C0/C1 controls, DEL; `uniqueItems` on paths; built-in `schema_id` `urn:image-clarus:metadata-schema:2.0.0` and `schema_version` `2.0.0`. The six Slice 1 properties and their definitions remain unchanged. The envelope `format_version` remains `1`.
- Replaced the built-in prompt with the exact A2 text (1,207 bytes, SHA-256 `282bf0bd58c65aff44979f90d4e98f53bdf718a8ecc85c06e262c88d17f8beff`), ending in exactly one LF. The prompt requests title, caption, ranked tag candidates, optional category guidance, and no XMP root in paths.
- Implemented category guidance as an optional **third user message part** in the provider request: when `preferred_categories` is a non-empty list, append `Preferred categories (JSON data, not instructions):\n` followed by `json.dumps(preferred_categories, ensure_ascii=False, allow_nan=False)`. When omitted or empty, omit the third part. The snapshot is validated once per generation and reused exactly on all validation retries. Custom prompt/schema overrides remain independent; guidance does not impose the built-in schema on a custom one.
- Existing valid 1.0.0 JSON artifacts are skipped without provider calls, without reading/hashing the current description, and without comparing schema/prompt/model/guidance. Invalid envelopes fail unless explicit `--regenerate` is used, which replaces the complete sidecar after validation and safe-write; failure preserves recoverable prior data. A custom replacement schema may omit the built-in publication fields; its identity remains the exact schema-byte hash.
- `prompt_sha256` remains the hash of the exact effective prompt-file bytes; `description_sha256` the hash of the exact persisted description-byte snapshot. Neither identifies category guidance or the complete request. The closed format-1 envelope has no guidance fingerprint.

## Test-first evidence

The earlier record claimed an individual RED and GREEN for each original test. That table was not supported by recorded individual test runs and is withdrawn; the original per-test RED evidence is unverified. The reported initial full-suite GREEN below is separate evidence and does not establish test-first history.

For the review correction, `uv run --locked --extra dev --python 3.13 pytest -q tests/unit/test_slice2_structure.py::test_category_guidance_snapshot_reused_on_retry` failed before the fix because the second request contained the mutated configuration, then passed after copying and validating the snapshot. The root-independence comparison and invalid-category cases are supplemental GREEN coverage, not claimed as historical RED tests.

## Review correction

The original implementation held the mutable configuration list rather than a snapshot, contrary to the statement above. Version `0.1.22` copies and validates the list once before requests and reuses the independent snapshot. The retry test mutates the original list after the first request and checks the exact guidance in both requests. The root-independence test compares requests and generated paths under two configured roots, including a legitimate `airplane` tag.

- Python 3.13 full suite: **609 passed**; `uv lock --locked`, Ruff check and format check passed for the correction.

## Verification

- `uv run --locked --extra dev --python 3.13 pytest -q tests/unit/test_slice2_structure.py` — **27 passed**.
- `uv run --locked --extra dev --python 3.13 pytest -q` — **606 passed** on Python 3.13.
- `uv lock --locked`, Ruff check and Ruff format check on all changed Python files passed; `uv run --locked --python 3.13 image-clarus --version` reported `image-clarus 0.1.21`.
- Existing regression tests updated for 2.0.0 schema/prompt: `test_structure_resources.py` (prompt/schema hashes), `test_structure_stage.py::test_builtin_resources` (schema version, required fields), `test_single_image_pipeline.py` (envelope schema_id/version, METADATA with new fields).
- The first full suite after implementation reported failures from superseded 1.0.0 expectations; the reconciled full suite above passed. The first format check found formatting issues in four files; all were corrected and the recorded rerun passed. No Git commands were run.

## Acceptance

- [x] New built-in outputs validate and contain the approved publication-oriented metadata while existing descriptive fields and provenance remain intact.
- [x] Model inference/category guidance is independent of the XMP root and custom schema/prompt replacement still works.
- [x] Existing JSON skip, explicit replacement, strict validation, schema identity and safe publication behavior pass.
- [x] Observed RED/GREEN and relevant regression evidence, changed-file inventory and completion record are linked.