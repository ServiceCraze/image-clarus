# Step A5 - Complete design and verify implementation readiness [DESIGN]

**Status:** In progress; Phase A remains open and neither Phase B nor Phase M is authorized to start. The Product Owner approved the three decisions listed below; a portable nonmutating SQLite read mechanism and A5 technical reconciliation remain unresolved. A3 remains open. This is an execution record, not proof of completion.

**Scope deviations:** None authorized. No Slice 4 feature was implemented.

## 1. Readiness and evidence boundaries

The governing inputs are the parent REQ/HLD, `REQ-slice-4.md`, `IMPL-PLAN-slice-4.md`, A1–A4 records and the existing CLI, stage, provider, state and artifact code. Assignment establishes requirements readiness; no separate REQ acceptance gate exists. A5 is the explicit Phase A design gate, and no significant decision may remain TBD when it closes. Prior Slice 1–3 records are historical and unchanged.

Four independent read-only assessments examined state-read feasibility, provider cancellation, design contradictions and requirement ownership. They did not implement or verify Slice 4 behavior. Independent SQLite research did not establish a portable enforcement mechanism as implementation-ready. Independent provider research exercised a sleeping child and a full-pipe child in a synthetic Linux subprocess; this is not an HTTP, Windows or product-protocol test and is not used to claim a shutdown deadline.

At delivery version `0.3.12`, from the project root, `uv lock --locked` passed (21 packages); `uv run --locked --extra dev --python 3.13 image-clarus --version` printed `image-clarus 0.3.12`; `uv run --locked --extra dev --python 3.13 pytest -q tests/unit/test_cli.py tests/unit/test_resources.py tests/unit/test_pipeline.py tests/unit/test_config.py tests/unit/test_state_storage.py tests/unit/test_state_accumulation.py` passed **173 tests**; `uv run --locked --extra dev --python 3.13 ruff check .` and `uv run --locked --extra dev --python 3.13 ruff format --check .` passed (165 files). The installation used a successful hardlink-to-copy fallback. These are existing baseline checks, not Slice 4 acceptance or proof of a design; no full suite, live provider or Windows runtime test was performed.

**Subsequent Product Owner decisions, version `0.3.13`:** the three decisions in §3 were approved and synchronized in the Slice 4 REQ, A1/A2/A4 records and plan. `uv lock --locked` passed (21 packages); the CLI reported `image-clarus 0.3.13`; `uv run --locked --extra dev --python 3.13 pytest -q tests/unit/test_cli.py tests/unit/test_resources.py tests/unit/test_pipeline.py` passed **78 tests**; Ruff check and format check passed (166 files). The hardlink-to-copy fallback succeeded. These are focused existing-baseline checks; the prior 173-test result remains specific to `0.3.12`.

**Subsequent scratch-probe record, version `0.3.14`:** `uv lock --locked` passed (21 packages); the CLI reported `image-clarus 0.3.14`; `uv run --locked --extra dev --python 3.13 pytest -q tests/unit/test_cli.py tests/unit/test_resources.py` passed **60 tests**; Ruff check and format check passed (166 files). These baseline checks do not validate the scratch candidates or Slice 4 behavior. The installation's hardlink-to-copy fallback succeeded.

Files created: this record. Updated: `docs/slice-4/REQ-slice-4.md`, `docs/slice-4/IMPL-PLAN-slice-4.md`, `docs/slice-4/IMPL-A1-COMPLETED.md` through `IMPL-A4-COMPLETED.md` as described above, `pyproject.toml`, `uv.lock`, `tests/unit/test_cli.py` and `tests/unit/test_resources.py`. No production feature or behavioral test was changed.

## 2. Requirement and evidence ownership

The current plan's §5 and §6 own the detailed mapping and future evidence. A structural check found 18 distinct `S4-01`–`S4-18` REQ headings, 18 matching plan rows and 20 distinct evidence rows E01–E20. These are planned owners, **not** executed results.

| Requirement | Implementation owners | Evidence owners |
| --- | --- | --- |
| S4-01 selection/traversal | B1, B2, B6 | E01, E02, E17; C1 |
| S4-02 symlink boundaries | B2, M2 | E01, E15, E17; C1, M3 |
| S4-03 independent depth controls | B1, B2, M2 | E01, E15; C1, M3 |
| S4-04 stage capabilities | B3 | E03–E05; C1 |
| S4-05 metadata-only planning | B3, B6 | E03, E11, E19; C1 |
| S4-06 early routing | B3–B5 | E04, E05, E07, E18; C1 |
| S4-07 authoritative rechecks | B3–B5 | E06, E08, E10, E18; C1, C2 |
| S4-08 initial allowance/corrections | B1, B3–B6 | E05, E06, E12, E18; C1, C2 |
| S4-09 optional inter-stage concurrency | B1, B4, B5 | E07; C1 |
| S4-10 per-image state and timing | B4, B5 | E08, E09; C1, M3 |
| S4-11 stop/failure/resume | B1, B4–B6 | E10, E13, E20; C1, C2 |
| S4-12 dry run | B3, B6 | E03, E11, E19; C1 |
| S4-13 verbose reporting | B6, B7 | E02, E12, E20; C1, C2 |
| S4-14 batch metrics | B3–B6 | E05, E06, E12, E20; C1, C2 |
| S4-15 category list | M1 | E14; M3 |
| S4-16 category clear | M1 | E14; M3 |
| S4-17 additive JSON rebuild | B2, M2 | E15; M3 |
| S4-18 prior-slice compatibility | all affected CODE steps | E02, E08–E10, E14–E16; C3 |

E01–E16 correspond to the REQ's 16 acceptance areas; E17–E20 add edge-case evidence. The 10,000-image case must count actual selected-XMP evaluation entries under its stated fixture assumptions; synthetic collaborators and representative real CLI/stage/XMP integration are distinct evidence boundaries. C3 owns full regression and packaging evidence; C4 reconciles it, without attributing earlier tests to a later version. The mapping is structurally checked; no row is marked as having passed behavior.

## 3. Decision and conflict ledger

| Decision | Current disposition and evidence | Remaining owner |
| --- | --- | --- |
| Selection and literal-first glob handling | Product Owner approved literal-first and Bash-style concepts; A1 specifies host-native syntax and no discovered-link following. | A5 must reconcile identity below. |
| Distinct-image admission | First N initially LLM-needy image identities admitted; no refill; known exclusions never infer; permitted corrections can exceed N or 2N. | Existing Product Owner decision, not reopened. |
| Invalid primary without regeneration | Existing invalid-artifact failure and configured continuation remain; do not overwrite with a valid backup or invent correction. | Existing behavior. |
| Invalid predicted-existing JSON for a known-excluded image | Product Owner approved reporting the real confirmation failure and applying configured continuation, without excluded inference or fabricated skip. | Approved; A2 and REQ synchronized. |
| Case-variant aliases | Product Owner approved exact host-resolved path spellings; distinct spellings may process and consume allowance separately, including case aliases on Windows, and hard-link paths remain distinct. | Approved; A1, REQ and E17 synchronized. Linux pure-path parsing does not verify Windows runtime. |
| Batch/management exits | Product Owner approved 0 for success/ordinary skips, 1 for primary/partial/storage/accounting failure, 2 for invalid selection/configuration, and first handled signal as `128 + signal`; existing authentication startup remains 1. Existing nonverbose single-image output/exits remain compatible. | Approved; A2/A4 and REQ synchronized. |
| Three continuation policies | Continue-next-stage, default stop-current-image and batch abort are required by HLD; request-local provider failures follow the selected policy, fatal actor/coordinator failure aborts. | Existing contract; do not request approval of the three policies again. |
| One actor per stage | A2 owns all authoritative inspection/transformation/publication in one actor with one outstanding provider request, permitting other confirmations during a pending request. No second actor performs stage decisions. | A5 must reconcile the actor/pending-I/O interpretation with the selected transport and fixed one-worker requirement; never infer PO approval from A2's checked row. |
| Provider transport | Candidate baseline is one disposable provider subprocess per request; compare against cancellable `httpx.AsyncClient`, including synchronous construction/parsing, privacy, retries, pipe handling, Windows packaging and stop/result races. | A5 must select and reconcile; no hard timeout/remote-cancellation promise. |
| State and category policy | Per-image ordinary state and nonblocking diagnostic behavior preserved. Product Owner approved CWD/configured management destination, explicit/orphan sidecars, registered migration for clear/nonempty rebuild, no migration for list or empty/no-category rebuild. | Existing decisions, not reopened. |
| Strict list/empty-safe recognition | `mode=ro`, `immutable=1` on a live database, raceable header checks and APSW's inherited WAL shared memory alone do not establish a no-write guarantee. Native VFS and OS-enforced sandbox are candidates, neither proven portable or selected. | A3/A5 blocker: choose a fail-closed implementation with a consistent snapshot, safe WAL/hot-journal/mode-change behavior and credible Linux/Windows deployment. |
| Management repository identity | Retain selected path; detect replacement where trustworthy identity is available; absence of optional identity alone is not failure. Report genuinely uncertain commit/replacement rather than asserting success; no guarantee against external path replacement races. | A5 confirms concrete portable contract without imposing optional identity on every platform. |
| Management migration transaction | Nonmutating recognition; for clear or first eligible rebuild contribution use a non-migrating open, `BEGIN IMMEDIATE`, revalidate, registered migration and mutation in one transaction, commit/rollback together; empty/no-category rebuild never enters it. | A3 §6 and future M1/M2 tests; dependent on safe recognition. |
| Dry-run access and estimate | No sidecar/image content, state, ExifTool, provider or writes, including error paths. Product Owner approved numeric estimate for complete plans and unavailable marker for incomplete plans. | A4; A5 reconciles representation below. |
| Initial execution graph | A4 defines shared path/origin objects, rows, FIFO stage queues and tracking containers with an explicit size formula; A2's pending confirmations are mask-derived and later dynamic work is excluded from the initial estimate. | A5 must cross-check actual ownership/allocation lifecycle against A2 and freeze interfaces; synthetic formula checks do not prove a production implementation. |
| Native search/content-aware planning | Outside Slice 4; no implicit deferral of required Slice 4 work. | Existing scope. |

### Portable read-only state: unresolved safety boundary

The existing `state/storage.py` constructor opens writable and may migrate. Strict `list` requires no changes to database, journal, WAL, shared memory or directory even when opening fails. SQLite `mode=ro` alone does not prove WAL sidecars cannot be modified; `immutable=1` against a live writable database disables needed locking/change detection; copying live DB/WAL files independently is not a coherent snapshot. SQLite's online backup still needs a source reader that honors the same no-mutation boundary. The native wrapper candidate needs proof that **every** mutation path is denied while real SQLite locks work, and credible Linux/Windows build/packaging and same-library registration; an OS sandbox needs proof that it denies all source writes while preserving SQLite lock identity and works on both platforms. A pre-open header/sidecar test alone races a writer. Any solution must fail visibly rather than fall back to an unsafe reader, report unavailable safe reads including hot-journal/WAL cases truthfully, and not impose optional filesystem-identity support as a blanket prerequisite.

The native VFS is **not** a chosen or approved dependency; no unverified Python APSW shared-memory interception is claimed. References: [SQLite WAL](https://sqlite.org/wal.html), [SQLite locking](https://sqlite.org/lockingv3.html), [SQLite URI](https://sqlite.org/uri.html), [SQLite backup](https://sqlite.org/backup.html), [SQLite VFS](https://sqlite.org/c3ref/vfs.html). M1/M3 must ultimately exercise real independent-process read/write, WAL, hot-journal, mode-change, open/close/failure races and nonmutation; this requirement cannot be handed to implementation as an unresolved design decision at the Phase A gate.

### Subsequent isolated feasibility probes

These probes used synthetic data on Linux only, not product code or live providers. They narrow the tradeoffs but do not close either design decision or demonstrate Slice 4 behavior.

- **Native SQLite VFS:** A scratch C wrapper using Python 3.14.9 and SQLite 3.53.1 rejected mutating VFS methods, omitted shared-memory methods, and forwarded native locking. A rollback-mode database was read with no observed inventory changes; a synthetic hot journal returned `SQLITE_READONLY_ROLLBACK`, and live WAL returned `SQLITE_CANTOPEN`, again with no observed inventory changes. Independent reader/writer contention produced `SQLITE_BUSY` until the opposing lock released. In one race, 500 writer commits coincided with 216 successful reader queries and 284 busy results; a reader-only trace found no identified target-mutating syscalls within its selected syscall/path filters. Non-race inventories compared names, sizes, mtime, ctime and content hashes, not access times. This is promising evidence for fail-closed rollback-mode access, **not** proof for all mutation paths, hostile paths, races, VFS variants, filesystems or Windows. It does not support live WAL listing. An initial prototype crashed because its registered extension was unloaded; keeping it permanently loaded fixed subsequent runs. Native build/distribution, extension-loading availability and registration with the reader's SQLite library remain unresolved; see [SQLite loadable extensions](https://www.sqlite.org/loadext.html) and [Python sqlite3 extension loading](https://docs.python.org/3/library/sqlite3.html#sqlite3.Connection.enable_load_extension).
- **Async transport:** A loopback server held responses while an `httpx.AsyncClient` task was cancelled. Across three runs before headers and three after partial body delivery, cancellation completed, the client closed, and the server observed EOF without releasing the response. This was Python 3.14.9, httpx 0.28.1, httpcore 1.0.9, `timeout=None`, `trust_env=False`, and the Linux asyncio selector loop. It demonstrates cooperative cancellation at these network-await points only: it does not establish interruption of synchronous request construction or response parsing, Windows behavior, remote computation/billing cancellation, application shutdown deadlines, or comparative subprocess performance. The actor/transport decision and preservation of existing transport semantics remain open.

## 4. Corrections made in this readiness pass

- The 10,000-image REQ and plan examples now explicitly require predicted existing outputs to validate and no earlier stage to stop the image before asserting all 10,000 reach XMP evaluation. An earlier validation failure follows normal continuation; no XMP writes are inferred from evaluations. C1 now requires 10,000 actual entries at the selected evaluation boundary and separately records representative real CLI/stage/XMP evidence.
- The E17 identity claim is scoped to the Product Owner-approved exact resolved-path spelling contract; A1's Windows case-alias limitation is explicit.
- A3 now states the exact nonmutating recognition → first eligible contribution → non-migrating open → `BEGIN IMMEDIATE` → revalidation → registered migration plus first union → commit/rollback sequence. Clear uses the analogous transaction; no-category rebuild cannot migrate. This is a design contract, not a claim the current constructor implements it.
- A5 remains permitted to reconcile A3 while A3 is open, but cannot close until A3's remaining acceptance rows and all required decisions are complete. A1, A2 and A4 retain their actual completed design evidence; no feature implementation was started.

## 5. Remaining acceptance and gate

The interactive form initially timed out, after which the Product Owner explicitly chose the first option for all three questions; the decisions are recorded as approved in §3. A5 still requires the SQLite mechanism and provider/actor/graph reconciliation, and any other genuinely new product-visible decisions must be dispositioned; routine architecture work is not an additional REQ acceptance gate. The existing product choices listed as approved are not reopened.

- [ ] A1–A4 agree, every significant design decision is resolved, and no significant TBD remains.
- [ ] Required product decisions are approved; already decided behavior has not been reopened unnecessarily.
- [ ] Every implementation/evidence step has concrete inputs, observable outcomes, dependencies, and future completion-record links.
- [ ] Requirements, accepted examples, failure boundaries, and end-state allocation are covered without silent scope deferral.
- [ ] The orchestrator can advance to B1 or the eligible Phase M work using the completed design evidence.
