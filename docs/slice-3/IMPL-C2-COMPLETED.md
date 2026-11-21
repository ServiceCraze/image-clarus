# Step C2 - Run regression packaging and quality checks [TEST] (COMPLETED)

**Status:** Complete. The Product Owner authorized the targeted correction of the newly identified prompt-expansion import cycle; C3 has not started.

**Subsequent progress:** [C3](IMPL-C3-COMPLETED.md) completed Slice 3 closeout and records later schema-cycle corrections and delivery versions. The C2 results below retain their original versions.

**Scope deviations:** None. Two publishable planning documents were sanitized during the scoped privacy audit; their historical technical meaning is unchanged. The privacy corrections were delivered in `0.2.17`, and the authorized dependency-cycle correction in `0.2.18`. The version was subsequently changed to `0.3.0` at the Product Owner's request; the verification results below retain the versions actually tested.

## Files created, updated, removed

- Created: this evidence record, `src/image_clarus/config_errors.py`, `tests/unit/test_config_error_imports.py`.
- Updated: `src/image_clarus/config.py`, `src/image_clarus/prompt_expansion.py` (authorized cycle correction); `docs/slice-2/IMPL-PLAN-slice-2.md`, `docs/slice-3/IMPL-PLAN-slice-3.md` (privacy and progress); `pyproject.toml`, `uv.lock`, `tests/unit/test_cli.py`, `tests/unit/test_resources.py` (version synchronization); `IMPL-C1-COMPLETED.md` (subsequent progress).
- Removed: None. The class was moved, not duplicated; its prior import path remains available.

## Observed evidence

1. On Linux, full suites with ExifTool 13.55 passed at `0.2.17`: Python 3.13.15 **1,206 passed**, Python 3.12.14 **1,206 passed**, no skips. The 3.12 run used an isolated locked environment; 3.13 used the locked development environment. An earlier 3.12 foreground attempt timed out, and one background launch failed to locate `uv`; both preceded successful runs and are not passes.
2. Ruff check and format check passed, with **150 files** formatted; `uv lock --locked` resolved **21 packages** and the CLI reported **0.2.17**. A source distribution and wheel were built from a scratch copy. With normal dependencies installed into an isolated Python 3.13 environment outside the checkout and `PYTHONPATH` unset, version/help and search-stub checks passed, all four packaged prompt/schema resources matched source bytes, initialization succeeded, and repeated synthetic existing-JSON skips preserved image/JSON bytes while accumulating expected state. The installed-wheel processing smoke did not exercise a live model, generated JSON, or XMP publication.
3. A disposable copy with both editable prompts replaced by fictional macro-free text passed the complete unit suite: **1,028 passed**, no skips. The copy used the preceding `0.2.16` snapshot; the only subsequent edits were two planning-document privacy corrections and synchronized version metadata/assertions. One built-in expansion test derives its expected result from the current resource, so its macro-specific assertion can be vacuous when the user removes the macro; separate explicit prompt-fixture tests cover that behavior. Source prompt bytes remained unchanged.
4. The full suites exercise inherited stage selection, handoff, skip/regeneration, safe-write, source integrity, XMP and signal tests. No claim is made of a new live-provider or manual digiKam test.
5. The cleanup audit found no remaining separate provider category argument or obsolete fixed request labels. Preferred-category validation remains used; structure's envelope helpers still have production consumers. State imports succeeded with stage imports blocked. The initial audit identified a new deferred static cycle: `stages.structure → prompt_expansion → config → schema_worker → stages.structure`; its correction is recorded below. Fresh imports and worker preflight/validation passed, but these do not establish the absence of all cycles. Other static cycles exist; without a historical source snapshot, the audit cannot classify every one as newly introduced or historical. No orphan-retention exception is asserted.
6. Completion records report per-delivery versions from `0.2.4` through `0.2.16`, including `0.2.9` and `0.2.14` corrections; these are recorded historical claims rather than independent release-history proof. The privacy correction was `0.2.17`. A targeted 50-file scan of current Slice 3 documents, state/macro code and tests, selected integration tests, README, sample configuration and the amended historical plan found zero matches for known internal identifiers and local home paths after removing two findings. This is not an exhaustive secret scan.

## Authorized cycle correction and final verification

- The Product Owner authorized extracting `ConfigurationError` into a dependency-free module, re-exporting the same class from `config.py`, and importing it directly in prompt expansion. This removes the newly introduced `prompt_expansion → config` edge; it does not claim to eliminate other, historically unclassified static cycles.
- The new fresh-process tests initially produced **2 failures and 4 passes**: the forbidden config import and missing new module. After correction all **6 passed**, including shared class identity and unchanged message/category behavior. The focused suite passed **225 tests**.
- On `0.2.18`, full Linux suites with ExifTool 13.55 passed **1,212 tests each** on Python 3.13.15 and isolated Python 3.12.14, no skips. Ruff and format passed with **153 files** formatted; `uv lock --locked` resolved **21 packages**. The 3.12 `uv --no-sync` run warned about the project-requested interpreter; the isolated environment was independently confirmed as Python 3.12.14.
- A fresh sdist and wheel were built and the wheel installed with normal dependencies into an isolated Python 3.13 environment outside the checkout. Version/help, error-class identity, expansion, resource-byte identity, synthetic initialization and enabled/disabled skipped-JSON accumulation passed. The installed-wheel smoke did not execute live inference or XMP.
- The prompt-edit unit run above remains evidence from `0.2.16`; the later correction changed only the shared error location/import, privacy documents and synchronized version fields, not prompt files. Actual historical and current runs remain distinguished.

## C2 acceptance

- [x] Required Linux Python 3.13 and 3.12 suites, lint/format, lock consistency, and build checks pass, with actual outcomes and any skips recorded. Failed or blocked required checks remain unchecked unless an explicitly approved exception is recorded.
- [x] Installed CLI/resource/state checks pass outside the checkout. A blocker is recorded and leaves the affected criterion unchecked unless an explicitly approved exception is recorded.
- [x] Prompt wording changes do not break previously passing unit behavior that should use independent fixtures.
- [x] Inherited stage/XMP/source/safe-write/signal behavior is protected by relevant regression evidence.
- [x] The bounded cleanup/import audit identifies removed or retained paths and introduces no unrecorded exception.
- [x] Version references, document links, step labels, scope, and privacy-scan findings are reconciled.
