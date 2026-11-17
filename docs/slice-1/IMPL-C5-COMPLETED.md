# Step C5 — Reconcile acceptance evidence and close Slice 1 (COMPLETED)

**Status:** Complete as a working-tree acceptance closeout on 2026-11-16, including remediation of the contract gaps found during final read-only audits and the final printable-ASCII credential correction. Git status and commit state were not inspected; repository commits remain Product Owner-owned. The current lockfile is present and passed `uv lock --locked` and locked-install verification.

**Scope deviations:** The Product Owner explicitly superseded C4's synthetic-only input criterion with operator-authorized test images and accepted the C4 results without another inference run. The Product Owner also accepted the documented safe-write test-order exception; its missing historical RED is not represented as observed evidence. The final audit found three in-scope contract gaps; their minimal corrections and regression tests are included below without adding Slice 1 feature scope.

**Files created:** `docs/slice-1/IMPL-C5-COMPLETED.md` (this record).

**Files updated:** `README.md`, `docs/REQ-image-clarus.md`, `docs/HLD-image-clarus.md`, `pyproject.toml`, `uv.lock`, `tests/unit/test_cli.py`, `tests/unit/test_resources.py`, `docs/slice-1/IMPL-PLAN-slice-1.md`, `docs/slice-1/IMPL-A1-COMPLETED.md`, `docs/slice-1/IMPL-A2-COMPLETED.md`, `docs/slice-1/IMPL-A3-COMPLETED.md`, `docs/slice-1/IMPL-A4-COMPLETED.md`, `docs/slice-1/IMPL-A5-COMPLETED.md`, `docs/slice-1/IMPL-A6-COMPLETED.md`, `docs/slice-1/IMPL-B1-COMPLETED.md`, `docs/slice-1/IMPL-B3-COMPLETED.md`, `docs/slice-1/IMPL-B4-COMPLETED.md`, `docs/slice-1/IMPL-B5-COMPLETED.md`, `docs/slice-1/IMPL-B6-COMPLETED.md`, `docs/slice-1/IMPL-B7-COMPLETED.md`, `docs/slice-1/IMPL-B8-COMPLETED.md`, `docs/slice-1/IMPL-B9-COMPLETED.md`, `docs/slice-1/IMPL-C1-COMPLETED.md`, `docs/slice-1/IMPL-C2-COMPLETED.md`, `docs/slice-1/IMPL-C3-COMPLETED.md`, `docs/slice-1/IMPL-C4-COMPLETED.md`, `docs/slice-1/IMPL-CONFIG-NETWORK-CORRECTION-COMPLETED.md`, `docs/slice-1/IMPL-SAFE-WRITE-FILESYSTEM-CORRECTION.md`, `src/image_clarus/endpoint.py`, `src/image_clarus/config.py`, `src/image_clarus/providers/openai_compatible.py`, `src/image_clarus/artifacts.py`, `tests/unit/test_endpoint_networking.py`, `tests/unit/test_config_diagnostics.py`, `tests/unit/test_openai_compatible.py`, `tests/integration/test_config_diagnostics_cli.py`, and `tests/unit/test_artifacts.py`.

**Files removed:** None. The application patch version is `0.1.7`; `0.1.6` captured the initial audit corrections, and this final correction bumped it from `0.1.6`. Production changes tighten shared URL syntax/canonicalization, require printable-ASCII credentials and valid UTF-8 model IDs at configuration and provider boundaries, and validate recovery backups with the stage validator during failed-write fallback.

## Final verification on version 0.1.7

| Check | Executed result |
| --- | --- |
| Linux CPython 3.13.15 full test suite | `uv run --locked --extra dev --python 3.13 pytest -q` — **539 passed** in 130.95s. |
| Linux CPython 3.12.14 full test suite | Separate scratch environment, `uv run --locked --extra dev --python 3.12 pytest -q` — **539 passed** in 110.69s. |
| Focused audit regressions | Five printable-ASCII regression cases failed before the correction; all 10 targeted cases passed afterward. The five relevant modules passed **184 tests**. |
| Ruff and formatting | `ruff check .` passed; `ruff format --check .` reported 72 files already formatted. |
| Lock and build | `uv lock --locked` passed; `uv build --python 3.13` built sdist and wheel for `0.1.7`. |
| Project-environment CLI commands | `image-clarus --version` reported `0.1.7`; top-level/process/search help passed; bare search returned exit `3`, empty stdout, and exact documented stderr. |
| Normal installed CLI | Isolated `uv tool install --python 3.13 --force --reinstall .`, invoked from outside the checkout, reported `0.1.7`; help passed and bare search returned exit `3`, empty stdout, and exact stderr. |
| Privacy/document consistency | Added tests use synthetic keys, hosts and payloads. Targeted scans found no user-identified private infrastructure strings in Markdown docs or unit-test Python files; five primary documents had no broken local links, trailing whitespace, or missing C5 file-path entries (38 checked). |

No live provider request was made as part of C5. C4's manual provider evidence below is operator-reported and is not reclassified as an automated test.

## Final audit corrections

- **Endpoint contract:** The shared validator accepted malformed raw URI characters, malformed percent escapes, and a percent-encoded-unreserved alias of the prohibited `/chat/completions` path. It now rejects malformed escapes and invalid raw ASCII authority/path characters, and canonicalizes dot segments plus unreserved path octets before the endpoint-suffix check. The config preflight and provider adapter continue to use the same validator without DNS resolution or destination filtering.
- **Configuration diagnostics:** Control-character and non-ASCII API keys and an unpaired-surrogate model ID could pass preflight or fail later as `provider_unavailable`. Credentials now require printable ASCII (`0x20`–`0x7E`) at both preflight and provider boundaries; model IDs must be valid UTF-8. Failures are sanitized and actionable. Tests cover direct and environment-backed credentials, CLI diagnostics, and zero transport calls.
- **Failed-write recovery:** If replacement removed the destination and then failed, fallback recovery could restore an original backup that failed the stage validator. Fallback recovery now uses the same stage validator; invalid backup bytes remain preserved in `.bak` but are not published as the destination. A deterministic replacement-failure regression covers this path.

## Slice 1 acceptance crosswalk

| ID | Result | Evidence |
| --- | --- | --- |
| S1-AC1 | Verified: installable package, CLI, supported Python versions and lock consistency. The lockfile is present and validated; Git commit state was not inspected. | B1 and C3 records; current locked installs, full suites and CLI version verification above. |
| S1-AC2 | Verified. | B6/B8 and C1 description-only, prompt/model override and exact sidecar tests; C4 operator-reported provider run. |
| S1-AC3 | Verified. | B7/B8 and C1 persisted-description handoff, schema validation and exact sidecar tests; C4 operator-reported structured generation. |
| S1-AC4 | Verified. | A3 design contract, B7 implementation and C1 validation/provenance evidence. |
| S1-AC5 | Verified. | A2/B1/B4/B8 and C1 stage-selection/order tests; C3 and current CLI help/stub checks. |
| S1-AC6 | Verified. | A2/B2/B8 and C1 configuration precedence and selected-stage integration coverage. |
| S1-AC7 | Verified within the documented evidence boundary. | A4/B3 provider tests, C2 credential-redaction tests, and C5 shared endpoint/configuration diagnostics at both preflight and provider boundaries; C4 operator-reported real-provider results. The inspected C4 artifacts contained no API credentials per the operator; C4 logs were not independently checked. |
| S1-AC8 | Verified. | B5–B8 and C1/C2 skip, regeneration, invalid-artifact, failure and recovery coverage. |
| S1-AC9 | Verified with documented limits. | A5/B5/C1/C2 transaction, recovery, source-integrity, concurrency and fault evidence; safe-write correction and C5 failed-write fallback validator regression tests; operator-reported NTFS/FUSE publication and create-only probe. Lock-free races and broad filesystem/power-loss durability are not claimed. |
| S1-AC10 | Verified. | C3 and current Linux CPython 3.12/3.13 full suites, quality gates, wheel build and installed-wheel no-external-executable smoke evidence. |
| S1-AC11 | Verified for the current documentation. | B9 record; current README commands and privacy boundary rechecked; C4 record omits private source details and records the contact-information finding without reproducing it. |
| S1-AC12 | Verified. | C1 barrier-controlled independent-process `desc`/`json` handoff and C2 overlapping-writer integrity tests. |
| S1-AC13 | Verified. | A1/A2/B1/C3 version-source contract and current `0.1.7` package/installed CLI checks. Historical `0.1.0` starting version remains unchanged. |
| S1-AC14 | Verified. | A3/B7 contract and C1 tests for independent schema identity/version and exact description fingerprint. |

The original C4 requirement for only synthetic, non-identifying images was superseded by the Product Owner for that completed manual test. The approved replacement is operator-authorized test images. The operator reported useful descriptions, successful structured generation/schema validation/provenance, and no API credentials in inspected outputs. Contact information visible in source screenshot metadata appeared in output metadata. Logs were not independently verified; no such claim is made.

## Scope and carry-forward

No XMP writer, multi-image traversal/batch processor, or functional search implementation was added. Search remains a help-visible stub returning exit 3. C1 also verifies that its tested processing scenarios create no XMP or unrelated outputs.

| Deferred item | Owner and next boundary |
| --- | --- |
| XMP/digiKam mappings, policies, ExifTool integration and round-trip checks | Product Owner to authorize/scope a later XMP slice; its implementation plan must freeze mappings and sanitized fixtures before implementation. |
| Directory/pattern selection, traversal and batch/operational controls | Product Owner to set scope and ordering in a later selection/operations plan; no Slice 1 batch support is implied. |
| Functional deterministic search | Product Owner to authorize a search slice; the current `search` command is only a stub. |
| Ranked tag candidates | Separate schema-design consideration; Product Owner decision before any schema change. It is not a C4/C5 blocker and is not implemented here. |
| Native Windows and exhaustive filesystem/crash-durability matrix | Not established or required for this Linux closeout. Consider only under a future portability/validation scope; no crash-proof or universal-filesystem claim is made. |

The original NTFS/FUSE failure's precise cause remains unknown. The correction's capability-dependent behavior and successful user-reported artifact publication close the Slice 1 compatibility objective without claiming that the initial failure was independently reproduced or diagnosed. The accepted TDD exception is retained as a process deviation: the corrected mode-capability regression passes, but no historical pre-fix RED is claimed.

## C5 acceptance

- [x] Every required Slice 1 behavior maps to executed automated evidence or authorized operator-reported manual evidence.
- [x] Overall status, phase summaries, detailed acceptance rows and completion records agree.
- [x] No XMP, batch or functional search implementation was pulled into Slice 1.
- [x] Remaining work has explicit ownership/carry-forward and is not presented as complete.
- [x] [IMPL-C5-COMPLETED.md](IMPL-C5-COMPLETED.md) is complete and linked.
