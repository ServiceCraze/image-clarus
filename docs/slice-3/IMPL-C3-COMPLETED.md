# Step C3 - Reconcile evidence and close Slice 3 [DOCS] (COMPLETED)

**Status:** Complete. The Product Owner directed closeout based on functional acceptance and verification evidence and rejected mandatory RED-before-implementation sequencing.

**Scope deviations:** None. **In-scope deferrals:** None.

## Requirement and acceptance crosswalk

The following summarizes recorded automated evidence; linked step records provide actual commands, assertions and limitations. S3-12 comprises E01–E14. No live model, new digiKam interoperability exercise, or additional model-quality benchmark was required or performed for this closeout.

| Outcome | Requirement | Evidence and boundary |
| --- | --- | --- |
| E01 | S3-01 | [B5](IMPL-B5-COMPLETED.md) and [C1](IMPL-C1-COMPLETED.md): authored request captures, replacement instructions and built-in prompt inspection. |
| E02 | S3-02 | B5 and C1: four stage/namespace combinations in CLI subprocesses and replacement omission. |
| E03 | S3-02 | [B1](IMPL-B1-COMPLETED.md), [B4](IMPL-B4-COMPLETED.md), C1: configuration and component transformation cases plus CLI requests; not every permutation was captured over HTTP. |
| E04 | S3-03 | B4, B5 and C1: fictional inline/environment secrets, containing-object filtering, diagnostics and synthetic provider authentication. |
| E05 | S3-04 | [C2](IMPL-C2-COMPLETED.md): both production prompts replaced in a disposable copy; unit suite passed at 0.2.16. One default-macro assertion can become vacuous when its macro is removed; separate authored fixtures cover expansion. |
| E06 | S3-04 | B1, B5 and C1: default/overridden hash, raw source bytes, old/new/invalid-present envelopes and actual ExifTool XMP cases. |
| E07 | S3-04 | B1, C1 and C2: approved identifier, description hash and custom-schema identity regression evidence. |
| E08 | S3-05 | B5 and C1: built-in full hierarchy at default depth, configured truncation and zero; replacement guidance omission. |
| E09 | S3-06, S3-07 | [B6](IMPL-B6-COMPLETED.md) and C1: generated metadata, real later-stage barrier and independent-invocation reuse; architectural separation is also evidenced by [A2](IMPL-A2-COMPLETED.md) and [B2](IMPL-B2-COMPLETED.md), not a second production domain. |
| E10 | S3-07 | B6 and C1: existing valid JSON skip contributes without request or changed bytes, and disabled accumulation prevents updates. |
| E11 | S3-08 | [B3](IMPL-B3-COMPLETED.md) and C1: explicit initialization, no automatic creation, discovery/selection precedence and conflicting repositories; some path-origin cases are unit-level. |
| E12 | S3-09 | B3, B6 and C1: primary-outcome preservation, visible state failures and no persistent substitution. Permission and migration-boundary faults were injected; XMP unavailable-state coverage is separate from the model-stage fault matrix. |
| E13 | S3-06, S3-10 | B2 and C1: independent processes, held inference, SQLite locking and test-only migration/rollback fixtures; no state/sidecar atomicity or physical power-loss claim. |
| E14 | S3-11 | C2 full regressions, package checks and C1 real ExifTool coverage; no new digiKam acceptance. |

## Version and verification

- C2's full Linux suites at **0.2.18** passed **1,212 tests each** on Python 3.12.14 and 3.13.15 with ExifTool 13.55 and no skips; its isolated installed-wheel checks and prompt-edit run retain their actual versions and limits in C2.
- After the authorized schema dependency separations, the Linux development full suite at **0.3.1** passed **1,217 tests** with ExifTool on PATH. Ruff and format checks passed. A static scan of 27 source modules, including ordinary deferred and relative imports, found no static cycle; dynamic imports are outside that scan. See [dependency assessment](cycle-dependencies-C2.md). The 0.2.18 minimum-runtime and wheel runs were not rerun at 0.3.1.
- At **0.3.2**, `uv lock --locked` resolved 21 packages; `uv run --locked pytest -q tests/unit/test_cli.py tests/unit/test_resources.py tests/unit/test_schema_dependency_boundaries.py tests/unit/test_schema_extracted_units.py` passed **65 tests** on rerun; CLI version, Ruff and format checks passed. The first focused run reported **1 failed, 64 passed**: the signal preflight test observed an empty worker PID marker after the file appeared. The rerun passed; this does not establish a product defect or fix the test synchronization race. No full-suite or installed-wheel run is claimed at 0.3.2.
- Closeout and the Product Owner's test-order decision are delivered as **0.3.3**. `uv lock --locked` resolved 21 packages; the same four-file focused command passed **65 tests**, CLI reported `image-clarus 0.3.3`, and Ruff check and format check passed (159 files). No full suite or installed-wheel run is claimed at 0.3.3.
- The independently reviewed dependency metadata leaves `jsonschema` and `referencing` unbounded while the worker uses a private `jsonschema` API. The locked tests establish the tested dependency resolution, not compatibility with every permitted future or older version; dependency bounds and broader verification are separate follow-up.

## History, scope and limitations

Slice 2 remains accepted, including its historically recorded prompt-control exception and Product Owner-reported digiKam observations. Slice 3 request evidence supports remedying the identified hardcoded prompt-framing gap without rewriting that history. Native batch, search, scheduling, historical taxonomy import and additional state domains remain outside Slice 3; no new future slice, release date or feature commitment is assigned. State concurrency does not change lock-free sidecar last-replacement-wins limitations. Permission and migration injections, synthetic providers and test-only migrations are not claims of physical failures, live provider use or power-loss durability.

B2, B3, B4 and B6 initially recorded missing-module collection failures rather than observed behavioral RED for every initial behavior. Later direct, audit-driven and integration tests are recorded in their respective records; absent historical failures are not invented. The Product Owner rejected mandatory RED-before-implementation sequencing: unit tests are the development harness and an initial pass or fail is not a violation. C3 closes on functional acceptance and verification evidence, not a test-order gate.

## Files and closeout

- Created: this reconciliation record.
- Updated: Slice 3 implementation plan, parent HLD roadmap, `pyproject.toml`, `uv.lock`, and the two exact-version assertions for the delivery boundary.
- Removed: none. No production behavior was changed in C3.

## C3 acceptance

- [x] Every in-scope requirement and acceptance outcome is supported by recorded evidence or an explicitly approved exception; nothing is silently deferred.
- [x] Phase and overall status match actual evidence and the orchestrator's closeout decision.
- [x] Historical acceptance remains intact, and remaining parent requirements are accurately allocated without new commitments.
- [x] The deviations/deferrals ledger and evidence limitations are explicit and consistent.
