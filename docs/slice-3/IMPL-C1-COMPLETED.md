# Step C1 - Verify requests persistence and state failure behavior [TEST] (COMPLETED)

**Status:** Complete for C1 runtime evidence. C2 regression/package and C3 slice closeout remain open.

**Subsequent C2 progress:** [C2](IMPL-C2-COMPLETED.md) completed regression and package checks and corrected the identified new dependency cycle. C3 remains open; C1 evidence is historical.

**Scope deviations:** None. Fault-injection limits are stated below; no live model or new manual interoperability test was required.

## Files created, updated, removed

- Created: `tests/integration/test_c1_macro_requests.py`, `test_c1_state_faults.py`, `test_c1_state_inference.py`, `test_c1_xmp_isolation.py`, and this record.
- Updated: `pyproject.toml`, `uv.lock`, `tests/unit/test_cli.py`, `tests/unit/test_resources.py` for patch-version delivery; the Slice 3 plan and `IMPL-B7-COMPLETED.md` progress note.
- Removed: None. No production behavior was changed.

## Acceptance-to-evidence crosswalk

- **E01–E02:** `test_c1_macro_requests.py::test_authored_namespace_requests_and_hash` captures all four stage/namespace combinations in separate CLI subprocesses, asserting exact request roles/messages, image or description/schema data and absence of hidden framing. `test_omitted_advice_and_parent_snapshot_secrets` covers replacement omission and filtered containing objects. Fixtures do not freeze editable production wording.
- **E03:** `test_prompt_expansion.py::test_depth_and_delimiter`, `test_sources_and_state_unchanged_for_zero`, `test_prompt_expansion_boundaries.py::test_mixed_arrays_rejected_for_every_configured_depth` and `test_slice3_config.py::test_macro_override_order_and_distinct_keys` exercise hierarchy transforms, generic arrays, independent overrides and source immutability at component/config boundaries. C1 request tests add built-in default/positive/zero depth and both namespace negative-depth CLI rejection. These combined boundaries, not a claim that every permutation was captured over HTTP, support E03.
- **E04:** `test_c1_macro_requests.py::test_omitted_advice_and_parent_snapshot_secrets` and `test_direct_secret_reference_fails_without_request` exercise synthetic inline/environment secrets, parent-object filtering, no unsafe request or diagnostics, and normal authentication to a loopback stub. B4 security tests cover deeper recursive boundaries.
- **E06–E08:** The authored JSON CLI fixture verifies the stored hash of raw prompt bytes after expansion. `test_slice3_b1.py` covers hash default and YAML/CLI precedence; `test_c1_compatibility.py::test_xmp_cli_accepts_optional_hash_and_rejects_invalid` covers absent/present/invalid hash using actual XMP; structure tests cover envelope fields and custom schema identity. `test_builtin_json_guidance_depth` captures default, positive and zero depth.
- **E09–E10:** `test_state_accumulation_cli.py` uses independent invocations and unrelated directories for generated and skipped JSON, enabled and disabled. `test_state_accumulation_timing.py::test_later_real_xmp_stage_finishes_before_category_accumulation` observes state while a real later XMP stage is held and after release. `test_c1_xmp_isolation.py` exercises real later-stage failure and unusable optional candidates without altering the skipped artifact.
- **E11:** `test_c1_state_faults.py::test_cli_state_precedence_and_no_creation`, `test_nested_discovery_real_cli_provider`, and `test_yaml_explicit_failure_does_not_use_discovered_store` verify explicit, nested, CWD/image and no-creation cases against competing repositories; `test_state_cli.py` covers initialization and idempotence. B3's detailed unit matrix covers additional path-origin and resolution boundaries.
- **E12:** `test_c1_state_faults.py::test_injected_state_failures_preserve_primary_and_do_not_substitute` injects open, permission, read, update and migration-boundary faults in actual CLI subprocesses; the real writer-contention case holds a SQLite lock in another process. Both model stages exercise state-macro read fallback. `test_state_b3_primary.py` covers missing/corrupt/incompatible explicit state and diagnostic logging levels; `test_c1_xmp_isolation.py::test_xmp_only_invalid_selected_state_never_expands_or_accesses_provider` uses actual ExifTool with unavailable state and guards macro/provider execution.
- **E13:** `test_c1_state_inference.py::test_other_process_reads_and_updates_state_during_held_inference` holds one CLI's synthetic provider response while a second independent CLI reads and writes the same repository before release; final state contains both contributions. Storage tests cover independent concurrent unions and migration preservation/rollback fixtures. This does not assert a sidecar-race winner or state/sidecar atomicity.
- **E05/E14** are C2-owned prompt-edit, packaging and inherited regression checks; the full suite below is a current regression run, not C2 completion.

## Verification and limits

- `PATH="$TMPDIR/exiftool-b1:$PATH" uv run --locked --extra dev --python 3.13 pytest -q` passed **1,206 tests**, no skips, with ExifTool 13.55. `ruff check .` passed; `ruff format --check .` passed with **149 files**; `uv lock --locked` resolved **21 packages**; CLI version **0.2.16**.
- Synthetic local providers and fictional images were used; no live provider or additional model-quality or digiKam acceptance was performed. ExifTool-based C1 scenarios were executed, not inferred from a skipped run.
- Permission and migration-boundary failures in CLI subprocesses are injected, not physical access denial or an actual failing migration callback; separate storage migration fixtures test transactional callback rollback. Contention uses a genuine separate SQLite lock. No-substitution assertions apply to the constructed alternate repositories. Signal boundary and prior storage/process evidence retain the limitations recorded in B6.
- An audit found initially incomplete full-request assertions and an unbounded test-holder readiness wait. Both tests were strengthened before the final suite; supplemental tests were not presented as historical RED evidence.

## C1 acceptance

- [x] The runtime outcomes assigned to C1 in §6 have passing observed evidence. C2-owned prompt-edit, regression, and package checks remain pending C2. Blocked or failed required C1 cases stay unchecked unless an explicitly approved exception is recorded.
- [x] Persistence/sharing evidence uses independent processes, not only object reuse or threads.
- [x] Failure scenarios demonstrate diagnostic visibility, primary-outcome independence, preserved sidecars, and no alternate persistent writes.
- [x] Concurrency/inference evidence proves the required state behavior without adding stronger sidecar-race guarantees.
- [x] Live provider calls, extra model-quality benchmarks, and new digiKam manual acceptance were not made prerequisites.
