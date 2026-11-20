# Step A3 - Verify implementation readiness [DESIGN] (COMPLETED)

**Status:** Complete. Phase A technical readiness is established for orchestration; no Phase B step is started or assigned by this record. The Slice 3 REQ is already accepted and no separate requirements-acceptance gate is introduced.

**Scope deviations:** None. **In-scope deferrals:** None.

## Files created, updated, removed

- Created: `docs/slice-3/IMPL-A3-COMPLETED.md`.
- Updated: `docs/slice-3/IMPL-PLAN-slice-3.md`, `docs/slice-3/IMPL-A1-COMPLETED.md`, and `docs/slice-3/IMPL-A2-COMPLETED.md` for readiness and bounded design clarifications; `pyproject.toml`, `uv.lock`, `tests/unit/test_cli.py`, and `tests/unit/test_resources.py` for this step's version delivery.
- Removed: None. No state, macro or provider implementation, production prompt, or behavior test was added. Version assertion edits only synchronize the delivery version.

## 1. Readiness crosswalk

The current plan maps all 12 S3 requirements to design, implementation and verification owners, and all 14 S3-12 observable outcomes E01–E14 to later evidence owners. The outcomes are planned evidence, not tests already passed.

| Outcome | Implementation owner | Evidence owner | Handoff |
| --- | --- | --- | --- |
| E01 Prompt replacement | B5 | B5, C1 | A1 request ownership and no injected instruction. |
| E02 Both namespaces in both prompts | B4, B5 | B4, B5, C1 | Four separately captured prompt/namespace combinations. |
| E03 Generic hierarchy transforms | B1, B4, B5 | B1, B4, C1 | Per-macro defaults, CLI precedence, depth, deduplication, immutable sources. |
| E04 Secrets | B4, B5 | B4, B5, C1 | Safe copied config and direct/parent/environment credential cases. |
| E05 Prompt edits and tests | B1, B5 | B1, B5, C2 | Independent fixed fixtures; disposable production-prompt wording change. |
| E06 Optional hash | B1, B5 | B1, B5, C1 | Old/new/invalid envelope and XMP; source-byte hash when enabled. |
| E07 Retained JSON fields | B1 | B1, C1, C2 | Model IDs, prompt ID, description and custom-schema hashes. |
| E08 Hierarchical guidance | B1, B5 | B1, B5, C1 | Actual built-in requests: full default, truncated and zero depth; replacement omission. |
| E09 Accumulated categories | B2, B6 | B6, C1 | Default-on post-stage union, independent later process and disabled mode. |
| E10 Existing JSON | B6 | B6, C1 | Envelope-valid selected skip contributes recognized paths without provider call or regeneration. |
| E11 Initialization/discovery | B1, B3 | B3, C1 | Explicit init, precedence, nested repositories, no auto-create. |
| E12 State failures | B3–B6 | B3–B6, C1 | Visible sanitized state errors; primary results, sidecars and persistent selection preserved. |
| E13 Concurrency/evolution | B2, B3, B6 | B2, C1 | Separate-process sharing, migration and held-inference boundaries. |
| E14 Regression | B1–B6 | B1–B6, C2 | Stage/sidecar/XMP/signal/resource behavior and package checks. |

## 2. A1/A2 interface and technical reconciliation

A1 owns names, override syntax, safe config snapshot, grammar, prompt request shape, shared envelope and hash behavior. A2 owns state location selection, initialization, state-domain snapshots, transactions, lifecycle and accumulation. The service snapshots full stored category paths before expansion; prompt depth never changes storage. The CLI owns optional state and post-pipeline work; the coordinator stays domain neutral. XMP is independent of provider calls, macro expansion and state. A1 and A2 remain the implementation contracts, with A2's A3 clarifications below incorporated directly and recorded as subsequent progress; their historical A1/A2 test evidence remains unchanged.

A3 found and resolved these technical blockers within the assigned readiness scope:

1. **Discovery:** An accessible nearer `.image-clarus/` with no database is uninitialized and does not mask an initialized ancestor. Once a database-bearing candidate is selected, corruption/inaccessibility is reported with nonpersistent fallback rather than silently choosing another repository. Explicit selections never get skipped. This reconciles the REQ's nearest-initialized rule with visible selected-state failures.
2. **Initialization race:** Concurrent `init` observes the existing directory through both pre-file and pre-transaction windows until one monotonic 250 ms deadline; it does not infer whether an initializer is alive or repair uncertain artifacts. On timeout or crash residue it fails safely. Barriers must cover both windows.
3. **Transaction mechanics:** Explicit transactions use individual `sqlite3.execute()` statements, not `executescript()` inside an open transaction, and failure injection verifies rollback. Busy-wait deadlines are operation-scoped and cannot bound arbitrary filesystem I/O.
4. **Signals:** The live stop token is checked before optional work, before `BEGIN` and immediately before `COMMIT`; an active uncommitted transaction is rolled back and closed. A signal racing the actual commit has a best-effort boundary and preserves the signal exit without falsely promising rollback.
5. **SQLite paths and artifacts:** A properly encoded file URI with `mode=rw` and `uri=True` handles special characters and cannot recreate a missing database. An ordinary transaction may create SQLite's transient journal; it must not initialize a repository.
6. **Extraction:** A2 now specifies exact supported built-in/custom identity predicates and whole-list rejection for malformed candidates, while preserving envelope-based skip validity and allowing recognized paths from a valid-envelope v2 artifact without unrelated fields. No XMP mapping, full current-schema validation or hidden regeneration is introduced.
7. **Fallback state:** A failed read returns `[]`; after switching to fresh invocation-local memory, later successful additions are visible only in that memory. A failed union is not retried or reported persisted.

These are implementation-mechanics clarifications, not added product capabilities or a scope exception. Required execution tests remain assigned to B2/B3/B6 and C1; a design probe does not prove their future implementation.

## 3. Code-ready step handoff

All paths for new modules are **planned**, not claims that they already exist. Existing paths and services must be rechecked when each step is assigned.

| Step | Frozen inputs and bounded output | Expected RED behavior before implementation |
| --- | --- | --- |
| B1 | A1 configuration/CLI, hash/validator contracts; existing `config.py`, `cli.py`, `stages/structure.py`, `stages/xmp.py`; config/JSON/XMP tests. | New default/overrides, literal dotted keys, hierarchy paths, old/new/invalid optional-hash envelopes fail against existing code. |
| B2 | A2 `state/storage.py`, `state/categories.py` and corresponding planned unit/process tests. | Domain snapshot/union, initialization/open separation, migration and concurrent persistence do not exist. |
| B3 | A1 settings and A2 `state/resolution.py`, `test_state_resolution.py`, CLI/state tests. | `init`, selected-directory precedence and nonblocking state diagnostics do not exist. |
| B4 | A1 `prompt_expansion.py`, `test_prompt_expansion.py`; A2 read-only domain snapshot interface. | Macro expansion, generic transforms and safe nested config view do not exist. |
| B5 | A1 request contract, two existing stages, provider, packaged JSON prompt and request tests. | The provider still supplies separate hardcoded framing and the stages do not expand macros. |
| B6 | A2 `state/accumulation.py`, `test_state_categories.py`, CLI/process tests. | Post-stage generated/skipped JSON accumulation and later process reuse do not exist. |

Observed RED/GREEN must be recorded during each CODE step; this table is expected behavior from inspection, not a claim a RED test was executed. A1 retains envelope helpers in `stages/structure.py`; B5 uses deferred/stage-local macro imports, and A2's state modules must not reverse dependency into stages. No unapproved dependency or new product domain is needed.

**Subsequent progress:** [B1](IMPL-B1-COMPLETED.md) implemented its configuration and envelope scope, [B2](IMPL-B2-COMPLETED.md) implemented state storage and category operations, [B3](IMPL-B3-COMPLETED.md) implemented initialization and state selection, [B4](IMPL-B4-COMPLETED.md) implemented the macro engine, [B5](IMPL-B5-COMPLETED.md) integrated it in model stages, [B6](IMPL-B6-COMPLETED.md) implemented accumulation, and [B7](IMPL-B7-COMPLETED.md) documented usage. Phase C remains open; this does not alter the historical A3 readiness evidence.

## 4. Verification and evidence limits

- Programmatic crosswalk inspection: 12/12 S3 requirement IDs mapped, 14/14 unique acceptance outcomes owned, and 13/13 summary/detail headings matched at review time. All E01–E14 remain `Not run` until their assigned later evidence exists.
- A disposable SQLite design probe using a temporary database verified that individually executed DDL and application-ID changes roll back, an encoded `file:` URI opens a name containing spaces, `?`, `#` and non-ASCII using `mode=rw`, and `mode=rw` does not recreate a deleted database. This is a SQLite mechanics probe, not a test of Image Clarus state behavior or concurrency.
- Delivery version advanced from `0.2.5` to `0.2.6`.
- `uv lock --locked`: passed, 21 packages resolved.
- `uv run --locked --extra dev --python 3.13 pytest -q tests/unit/test_cli.py tests/unit/test_resources.py`: **60 passed**.
- `uv run --locked --python 3.13 image-clarus --version`: `image-clarus 0.2.6`.
- `uv run --locked --extra dev --python 3.13 ruff check .`: passed.
- `uv run --locked --extra dev --python 3.13 ruff format --check .`: passed, 109 files already formatted.
- Installation reported a hardlink-to-copy fallback warning; the checks passed. No application implementation, Slice 3 behavioral acceptance suite, external provider, or Git command was run.

## 5. A3 acceptance

- [x] A1/A2 supply the exact contracts needed by B1–B6, and the crosswalk has no unowned acceptance outcome.
- [x] Shared services and dependencies are compatible; no unresolved design blocker is silently pushed into CODE work.
- [x] Summary/detail headings, output links, evidence IDs, and scope boundaries agree.
- [x] The readiness record supports orchestration advancing to Phase B without another REQ acceptance gate.
