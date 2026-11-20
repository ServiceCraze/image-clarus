# Step C2 - Run regression packaging and quality checks [TEST] (IN PROGRESS)

**Status:** Partial. C2 remains open: the cleanup/import audit found a new deferred static dependency cycle involving the Slice 3 prompt-expansion module. The plan requires no unrecorded exception. No exception is approved and this TEST step does not itself authorize a production refactor. C3 has not started.

**Scope deviations:** None. Two publishable planning documents were sanitized during the scoped privacy audit; their historical technical meaning is unchanged. This correction was delivered as version `0.2.17` rather than a bump solely for closeout.

## Files created, updated, removed

- Created: this in-progress evidence record.
- Updated: `docs/slice-2/IMPL-PLAN-slice-2.md`, `docs/slice-3/IMPL-PLAN-slice-3.md` (privacy and progress); `pyproject.toml`, `uv.lock`, `tests/unit/test_cli.py`, `tests/unit/test_resources.py` (version synchronization); `IMPL-C1-COMPLETED.md` (subsequent progress).
- Removed: None. No application code was changed.

## Observed evidence

1. On Linux, full suites with ExifTool 13.55 passed at `0.2.17`: Python 3.13.15 **1,206 passed**, Python 3.12.14 **1,206 passed**, no skips. The 3.12 run used an isolated locked environment; 3.13 used the locked development environment. An earlier 3.12 foreground attempt timed out, and one background launch failed to locate `uv`; both preceded successful runs and are not passes.
2. Ruff check and format check passed, with **150 files** formatted; `uv lock --locked` resolved **21 packages** and the CLI reported **0.2.17**. A source distribution and wheel were built from a scratch copy. With normal dependencies installed into an isolated Python 3.13 environment outside the checkout and `PYTHONPATH` unset, version/help and search-stub checks passed, all four packaged prompt/schema resources matched source bytes, initialization succeeded, and repeated synthetic existing-JSON skips preserved image/JSON bytes while accumulating expected state. The installed-wheel processing smoke did not exercise a live model, generated JSON, or XMP publication.
3. A disposable copy with both editable prompts replaced by fictional macro-free text passed the complete unit suite: **1,028 passed**, no skips. The copy used the preceding `0.2.16` snapshot; the only subsequent edits were two planning-document privacy corrections and synchronized version metadata/assertions. One built-in expansion test derives its expected result from the current resource, so its macro-specific assertion can be vacuous when the user removes the macro; separate explicit prompt-fixture tests cover that behavior. Source prompt bytes remained unchanged.
4. The full suites exercise inherited stage selection, handoff, skip/regeneration, safe-write, source integrity, XMP and signal tests. No claim is made of a new live-provider or manual digiKam test.
5. The cleanup audit found no remaining separate provider category argument or obsolete fixed request labels. Preferred-category validation remains used; structure's envelope helpers still have production consumers. State imports succeeded with stage imports blocked. A new deferred static cycle remains: `stages.structure → prompt_expansion → config → schema_worker → stages.structure`. Fresh imports and worker preflight/validation passed, but these do not establish the absence of cycles. Other static cycles exist; without a historical source snapshot, the audit cannot classify every one as newly introduced or historical. No orphan-retention exception is asserted.
6. Completion records report per-delivery versions from `0.2.4` through `0.2.16`, including `0.2.9` and `0.2.14` corrections; these are recorded historical claims rather than independent release-history proof. The current privacy correction is `0.2.17`. A targeted 50-file scan of current Slice 3 documents, state/macro code and tests, selected integration tests, README, sample configuration and the amended historical plan found zero matches for known internal identifiers and local home paths after removing two findings. This is not an exhaustive secret scan.

## C2 acceptance

- [x] Required Linux Python 3.13 and 3.12 suites, lint/format, lock consistency, and build checks pass, with actual outcomes and any skips recorded. Failed or blocked required checks remain unchecked unless an explicitly approved exception is recorded.
- [x] Installed CLI/resource/state checks pass outside the checkout. A blocker is recorded and leaves the affected criterion unchecked unless an explicitly approved exception is recorded.
- [x] Prompt wording changes do not break previously passing unit behavior that should use independent fixtures.
- [x] Inherited stage/XMP/source/safe-write/signal behavior is protected by relevant regression evidence.
- [ ] The bounded cleanup/import audit identifies removed or retained paths and introduces no unrecorded exception.
- [x] Version references, document links, step labels, scope, and privacy-scan findings are reconciled.
