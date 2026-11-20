# Step A2 - Freeze state and accumulation contracts [DESIGN] (COMPLETED)

**Status:** Complete as design; A3 subsequently completed the readiness assessment. No Slice 3 state implementation or acceptance test is represented as executed here. Assignment of A2 was the orchestration authorization for this step, not a new requirements-acceptance gate.

**Scope deviations:** None.

**Subsequent A3 progress:** [A3](IMPL-A3-COMPLETED.md) reconciled discovery, initialization coordination, transactions, signals, SQLite URI handling, extraction identities and fallback snapshots in the design below. The A2 verification and completion evidence remain historical; no implementation or behavioral test is implied.

## Files created, updated, removed

- Created: `docs/slice-3/IMPL-A2-COMPLETED.md`.
- Updated: `docs/slice-3/IMPL-PLAN-slice-3.md` and `docs/slice-3/IMPL-A1-COMPLETED.md` for A2 status and subsequent reconciliation; `pyproject.toml`, `uv.lock`, `tests/unit/test_cli.py`, and `tests/unit/test_resources.py` for the step's version delivery.
- Removed: None. No application implementation, prompt, schema, or behavior test was implemented in A2; the two test edits only synchronize version assertions.

## 1. Evidence and ownership boundaries

The current pipeline (`pipeline.py::run_pipeline`) returns `PipelineResult` after its selected stages, with `StageResult` values and interruption held separately; CLI constructs services and reports the result. It does not currently open state. `structure.py` checks the application envelope and can skip before reading the prompt or description; the v2 built-in schema defines `tag_candidates` as arrays of segment arrays, whereas built-in v1 has no such field. XMP interprets selected persisted metadata independently. These are inspected current behaviors, not proof that state exists.

Freeze the following proposed implementation paths for the later steps; these modules do not yet exist:

- `src/image_clarus/state/__init__.py`: package marker without runtime initialization or automatic repository creation.
- `src/image_clarus/state/resolution.py`: path selection and initialization entry point; no category or prompt policy.
- `src/image_clarus/state/storage.py`: repository recognition/open, transaction/version/migration dispatch, SQLite and memory backends; no stage, CLI or prompt imports.
- `src/image_clarus/state/categories.py`: category-domain snapshot and union; no sidecar writing, XMP policy or provider imports.
- `src/image_clarus/state/accumulation.py`: read one eligible persisted JSON artifact, validate/extract recognized paths and invoke the category domain; no stage-result mutation.
- `tests/unit/test_state_storage.py`, `test_state_resolution.py`, `test_state_categories.py`, and `tests/integration/test_state_cli.py`: planned focused tests. Existing `tests/integration/test_single_image_pipeline.py` supplies process/stub patterns. The B2/B3/B6 owners may add narrower fixtures without inventing another production domain.

The CLI owns a per-invocation state service and calls accumulation **after** `run_pipeline` returns; the coordinator remains format/domain neutral. Stages and A1's `prompt_expansion.py` receive only a read-only domain snapshot, not a SQLite connection. The service owns `snapshot_categories() -> list[str]`, `add_categories(paths) -> None`, and `close() -> None`; storage supports a transactional read and atomic category-union operation behind those methods. Storage operations return a result or a typed sanitized state failure, never a `StageResult`. Memory and SQLite expose the same domain contract; memory lasts for one process invocation. A1's `state.directory`, `state.accumulate_categories`, macro syntax, fallback and `state.categories.known` contract remain unchanged. No transaction or open cursor may span a provider call or sidecar operation.

## 2. Explicit initialization, recognition and schema

`image-clarus init` targets CWD's `.image-clarus/`; an explicit CLI/YAML state directory is that directory itself, not its parent. The only database file is `.image-clarus/state.sqlite3`. An initialized repository is a directory containing this existing regular SQLite file whose application identifier, format version, required tables and domain versions are valid. Validate using SQLite and schema queries; the mere presence of a directory or an empty file is not success. Resolve symlinks before checking; an inaccessible or dangling target is an error, not a request to create it. Do not print resolved paths or raw exception text in diagnostics.

For a newly absent destination, `init` alone creates the directory with an exclusive `mkdir` and exclusively creates `state.sqlite3`; it initializes the database inside one SQLite transaction and marks it complete only at commit. No code deletes or replaces an existing directory or database. An existing valid initialized repository is an idempotent no-op. An existing directory without a valid initialized database, non-directory path, corrupt/unrecognized database, or incomplete initialization is an explicit `init` error; preserve all contents for operator inspection. Do not assume an empty existing directory is disposable. A concurrent second initializer observes the existing directory and repeatedly rechecks recognition until one monotonic 250 ms deadline, without trying to create, delete or repair anything. It succeeds only after it sees and validates the committed repository; otherwise it reports incomplete state. This same bounded observation handles the windows before file creation and before transaction start without guessing whether a creator is alive. A later invocation after a crash follows the same rule and reports incomplete state rather than rebuilding it. No automatic cleanup of an initialization artifact whose ownership is uncertain.

Use `sqlite3` and default rollback-journal mode rather than enabling WAL as a hidden filesystem requirement. State has a format identifier `PRAGMA application_id = 0x49434C52` and `PRAGMA user_version = 1`, initialized in the same transaction as the tables:

```sql
CREATE TABLE domain_versions (
    domain TEXT PRIMARY KEY NOT NULL,
    version INTEGER NOT NULL CHECK (version > 0)
);
CREATE TABLE known_categories (
    path TEXT PRIMARY KEY NOT NULL
);
INSERT INTO domain_versions(domain, version) VALUES ('categories', 1);
```

The SQLite format version and per-domain version are independent of package and JSON schema versions. No second domain is created in this slice. A future registered domain can add its own table and version entry without replacing the facility. Only documented application-owned tables may be migrated; unrelated files in the repository directory are never touched. New database initialization is separate from opening an existing database. Ordinary processing uses a SQLite URI with `mode=rw` after regular-file checks, never `mode=rwc` or `CREATE` on its open path; the in-memory backend is explicit and never creates filesystem state. A file deleted between check and open must fail rather than be recreated. SQLite may create its normal transient journal next to an already initialized database when committing; this is not repository initialization.

On open, check the identifier, version, required schema and category domain version before exposing data. Newer/unknown identifiers or versions, missing schema, corruption, permissions, or unregistered migrations produce a state failure. An explicitly registered migration from a recognized older version executes under `BEGIN IMMEDIATE`, rechecks versions under the lock, applies transactional SQL and version updates, then commits as one unit; on failure roll back, close and preserve the original repository. Use explicit transaction control and individual `execute()` statements for initialization and migration; do not call Python `sqlite3.executescript()` inside the transaction because it may commit the pending transaction. Failure injection after each DDL, identifier and version operation must show rollback from a separate connection. No destructive replacement, reinitialization or fallback to another store. Reopen after another process has migrated and validate its version. A test-only older-version fixture and migration test the dispatcher; no speculative production migration or domain is created. A2's schema is design, not a claim migration tests have passed.

## 3. Resolution and failure decision table

Apply A1's origin and precedence rules: dedicated CLI `--state-dir` over CLI `--set state.directory` over selected YAML; explicit paths name `.image-clarus/` itself. An explicit null clears a lower YAML selection and permits discovery. Expand `~`; resolve relative CLI paths against CWD and YAML paths against the selected file directory. Resolve symlinks and search the resolved CWD directory and successive parents to the filesystem root, then, only if no CWD repository was selected, the resolved image-parent directory and its successive parents to root. Search nearest first, including starting directories. An accessible `.image-clarus` directory without a `state.sqlite3` entry is uninitialized and is skipped during discovery; it is not silently initialized. If the database entry exists, select that candidate and validate it: corrupt, incompatible, incomplete, or inaccessible state is reported and never silently replaced by a different persistent repository. Broken or inaccessible candidate entries are errors, not proof of absence. Explicit paths are never skipped, even when uninitialized. No loops: resolve each start, walk parents until `parent == current`, and do not revisit paths.

| Case | Resolution and primary operation |
| --- | --- |
| Explicit CLI or YAML selection exists and is valid | Open that repository; no ancestor search. |
| Explicit selection missing, invalid, inaccessible, dangling, corrupt or incompatible | Report state error and use invocation-local memory; never search another persistent repository. |
| No explicit selection; nearest CWD ancestor has a database entry | Select and validate it. On failure report and use memory; do not skip to a more distant repository or image ancestry. |
| No CWD repository selected; nearest image ancestor has a database entry | Select and validate it. On failure report and use memory; do not search beyond it. |
| All ancestor entries are absent or accessible but uninitialized, with no database entry | Use invocation-local memory without error or persistent creation. |
| An ancestry cannot be inspected or resolved | Report state error and use memory; do not search a lower-priority persistent store. |
| `init` cannot initialize, sees partial/corrupt state, or reaches its bounded contention limit | `init` fails visibly; it does not perform primary image processing or overwrite contents. |

An existing valid CWD repository wins even if the image is in another initialized tree; the nearest initialized repository in the chosen search wins. Explicit selection can serve unrelated image collections. A nearer accessible uninitialized directory does not hide a valid ancestor. A3 reconciles this discovery distinction with A2's earlier candidate wording; `init` still refuses to overwrite any existing directory. Normal processing never calls `init`, `mkdir`, exclusive file creation, `mode=rwc`, or schema-creation SQL. This separation is a design invariant to prove by B3 instrumented tests, not a claim of implemented behavior.

## 4. Transactions, concurrency and state error behavior

Each SQLite snapshot performs a short read transaction, materializes a sorted list of complete stored paths, closes its cursor and transaction, then hands the list to prompt expansion. Each union opens a short `BEGIN IMMEDIATE` transaction, inserts unique full paths with `INSERT OR IGNORE`, commits and closes the cursor. `PRIMARY KEY` uniqueness and transaction serialization prevent lost disjoint successful additions; completion order is not a promise about sidecar writes. Snapshots are sorted by SQLite binary text order; the memory backend returns the same stable order and deduplicates exact case-sensitive full paths. No truncation is applied to stored paths. A1's expansion transforms only its copied snapshot.

Use one monotonic 250 ms contention deadline per initialization, migration, snapshot or union operation; set SQLite's busy timeout to the remaining budget before lock-taking statements and do not restart that budget on each statement. The initialization recognition rechecks above use the same deadline. This bounds deliberate lock waiting, not arbitrary operating-system or filesystem I/O latency. No unbounded application retry loop. Construct the resolved database path as a properly percent-encoded `file:` URI with `mode=rw` and `uri=True`; test filenames containing `?`, `#`, spaces and non-ASCII. SQLite's transient rollback journal is permitted beside an existing repository, but processing must never recreate a missing database or repository. Test journal/lock cleanup and capability-dependent permissions without asserting no filesystem entries appear during a valid write.

Connection/setup failures, lock timeout, read/write/commit failure or migration failure are reported through a dedicated sanitized state diagnostic to stderr even if the logging level is OFF-equivalent or ERROR. Example: `image-clarus: state error: repository unavailable; using temporary state` or `image-clarus: state error: category update failed`; include operation/category but never raw paths, exception text, user data, credentials or connection URI. Each failed operation is not logged as successful. If open/read fails, close the failed handle and use fresh invocation-local memory; the failing read returns the A1 `[]` snapshot and emits the diagnostic. If a union fails, rollback, report failure and switch to fresh invocation-local memory without retrying the failed union there. Subsequent successful memory additions are visible in later snapshots but are not represented as persisted. Do not discard previously published sidecars or alter primary stage results.

Check the shared stop token before starting optional work, before `BEGIN` and immediately before `COMMIT`; if set, roll back any active transaction and close its cursor/connection in `finally`. A signal racing the actual SQLite commit cannot be promised to roll back: record the real commit outcome and signal exit without retrying or claiming atomic coupling to sidecars. The current signal handler sets the token outside interruptible calls; post-pipeline handling must consult that live token before optional writes and before final reporting, and preserve `main()`'s signal exit even though the earlier `PipelineResult` was already constructed. Test signals with barriers before begin, before commit and racing commit. Avoid unbounded optional work, while acknowledging the filesystem-latency limit above.

A1's safe prompt configuration view continues to remove configured secrets; state exposes only `categories.known` through a copied list and contains no provider credentials. Category values come from user metadata and can contain personal information: do not echo them in diagnostics or public fixtures. Persistent-state privacy and SQLite filesystem permissions remain deployment concerns; do not claim crash-proof durability or sidecar locking.

## 5. Category extraction and post-stage lifecycle

The registry stores complete paths, including single-segment paths and entire leaf paths; no unapproved leaf-versus-node distinction, XMP root, XMP tag limit or prompt depth changes the registry. Recognize only the exact built-in pairs `('urn:image-clarus:metadata-schema:2.0.0', '2.0.0')` and `('urn:image-clarus:metadata-schema:1.0.0', '1.0.0')`, or custom ID `urn:image-clarus:custom-metadata-schema` paired with `custom-sha256:` followed by exactly 64 lowercase hexadecimal digits, as in the existing XMP identity rules. For v2 and recognized custom artifacts, validate the existing envelope, then parse `metadata.tag_candidates` as an array of nonempty arrays of valid existing tag segments and join each path with `/`; preserve full strings and exact case, deduplicate exact complete paths. Missing or empty candidates contribute none; if any candidate is malformed, reject the entire optional contribution, not just one path. Do not require unrelated v2 payload fields to validate against the current schema: existing-output skip validity is envelope-based, and an otherwise valid skipped artifact with valid recognizable category paths must contribute them. Built-in v1 has no canonical `tag_candidates`, so valid v1 produces an empty contribution without an error or model call. For custom schema artifacts, the custom schema is user-replaceable and not necessarily available on a later skip; do not validate against the currently selected schema or infer taxonomy from arbitrary fields. This extraction is independent of any XMP mapping or selected XMP stage. Unknown or mismatched schema identity or incompatible/malformed optional category content contributes nothing and does not retroactively invalidate a valid-envelope JSON skip. Optional extraction may report a sanitized diagnostic but is not a state write success.

| Selected JSON outcome after pipeline | Accumulation when enabled | Disabled |
| --- | --- | --- |
| `completed` | Read the newly published `.desc.json`, validate eligible envelope/content and union paths after all selected stages finish. | No JSON-derived read/update. |
| `skipped` with `reason_code=output_exists` | Read existing artifact; valid recognizable paths contribute without model call, regeneration, or changing bytes. | No JSON-derived read/update. |
| `skipped` due to missing prerequisite, interruption or earlier-stage failure | No contribution even if a filename happens to exist. | None. |
| `failed`, not selected, or no `StageResult` | No contribution; never treat an unrelated old artifact as newly produced. | None. |
| JSON completed/skipped and a later selected stage failed | After `run_pipeline` returns, use the eligible JSON; preserve the later stage's failure and overall result. | None. |
| Stop signal observed before post-stage work | Skip optional accumulation and close; preserve interruption result and published sidecars. | None. |
| Eligible file missing, invalid, unreadable, or replaced between stage completion and optional read | Do not regenerate or call provider; contribute nothing, do not change JSON result or sidecars; emit a sanitized optional-read diagnostic. | None. |
| State update fails | Report state error, preserve pipeline result and sidecars; no claim of persisted update. | None. |

An eligible artifact is read once for this optional operation, then envelope and extraction use those same bytes. The accepted lock-free sidecar semantics still apply: an external writer may replace the artifact between stage and read; accumulation uses the complete valid snapshot actually read, with no deterministic winner or claim that state and sidecars commit atomically. A1's macro receives its own read snapshot before an inference request. After selected stages, the service union completes or fails independently; it cannot rewrite a completed result or roll back a sidecar.

## 6. Planned executable evidence

These are **future tests**, not results of A2:

1. `test_state_resolution.py` covers CLI/YAML/CWD/image/memory and null boundaries, nested/conflicting repositories, an uninitialized nearer directory with valid parent, unrelated collections, relative origins, symlink/dangling/inaccessible paths, nearest broken selected candidate, and a spy proving normal processing cannot create a repository. Include concurrent and repeated `init`, barriers before database creation and transaction start, timeout and creator crash, existing unrelated contents, partial creation, rollback and no destructive recovery.
2. `test_state_storage.py` covers memory equivalence, valid/invalid application identity, recognized and newer versions, atomic migration, injected failed commit/migration, missing/deleted file without recreation, and actual separate-process simultaneous disjoint unions. A barrier ensures overlap; assert both successful disjoint updates persist, and leave failed/timeout results observable rather than asserting a winner.
3. `test_state_categories.py` covers exact v1/v2/custom identities, mismatched/unknown identities, mixed valid/invalid candidate lists, empty and duplicate paths, including an envelope-valid v2 skip with recognizable valid paths but absent unrelated payload fields; custom conventional/missing/malformed category shapes; full leaf and single-segment paths, exact deduplication, ordering and snapshots unaffected by depth. Use synthetic artifacts and no live provider. Cover every eligibility row above, including later XMP failure and interruptions.
4. `test_state_cli.py` and controlled existing subprocess helpers use one initialized repository across independent invocations, different image directories and explicit state macros. Hold a synthetic provider request while another OS process reads and writes state; the second process must finish before release. Observe state before and after a selected later stage with barriers. Use bounded waits and always terminate/reap children, release barriers and close resources.
5. Exercise state failures at selection/open/read/update/migration and bounded contention while otherwise-valid `desc`, `json` and `xmp` cases run; assert visible sanitized stderr at every supported logging level, unchanged primary results/sidecars, no alternate persistent writes, no additional provider call for valid selected JSON skip, and no automatic repository creation. No real service or private image is needed.

## 7. Verification and acceptance

The above is design and repository inspection, not a state implementation or executed Slice 3 behavior. A2's version delivery advanced the application from `0.2.4` to `0.2.5`; the following checks actually ran:

- `uv lock --locked`: passed, resolved 21 packages.
- `uv run --locked --extra dev --python 3.13 pytest -q tests/unit/test_cli.py tests/unit/test_resources.py`: **60 passed**.
- `uv run --locked --python 3.13 image-clarus --version`: `image-clarus 0.2.5`.
- `uv run --locked --extra dev --python 3.13 ruff check .`: passed.
- `uv run --locked --extra dev --python 3.13 ruff format --check .`: passed, 108 files already formatted.
- Package installation reported a hardlink-to-copy fallback warning; checks passed. No external provider, new state test, full application suite, or Git command was run.

### A2 acceptance

- [x] A2 enumerates every state-precedence boundary and failure route, including explicit failures, and proves normal processing has no initialization path by design.
- [x] A2 specifies versioned SQLite/in-memory interfaces, non-destructive evolution, independent-process sharing, and transaction lifetimes.
- [x] A2 gives an extraction/eligibility table and a lifecycle sequence showing accumulation after selected stages, with both default-on and disabled behavior.
- [x] A2 defines observable state diagnostics that cannot change otherwise valid primary results or silently select another persistent repository.
- [x] A1/A2 agree on settings, safe macro values, service lifetime, and the tests required before implementation.
