# Step A4 - Freeze reporting and memory estimation contracts [DESIGN]

**Status:** A4 design complete. A5 subsequently reconciled A2's provider transport and the initial graph representation in §4; A3's backend/identity decisions and the remaining A5 gate are open. No Slice 4 reporting or planner feature is implemented by this record.

**Scope deviations:** None.

## 1. Ownership and facts

`src/image_clarus/results.py` currently defines immutable single-image `StageResult` (`completed`, `skipped`, `failed`) and `PipelineResult`; it maps stage failure to 1 and a handled signal to `128 + signal`. `cli.py` emits current stage summaries to stdout and state diagnostics to stderr. A4 does not claim its batch structures already exist. Proposed `src/image_clarus/batch_reporting.py` consumes immutable facts from the A2 coordinator; B6 owns rendering and estimator integration, M1–M3 own management-specific reports, and A5 confirms paths and interfaces. The coordinator serializes events and owns lifecycle/terminal truth; the reporter alone derives counters from those events. Stage actors and provider adapters emit facts, never mutate display counters. Records contain monotonic timestamp/sequence, internal invocation/image identity, selected stage and generation as applicable, event kind, sanitized status/reason and typed count data. Never record prompts, response content, credentials, raw exception text or resolved endpoint secrets.

Event keys are `(invocation,image,kind)` for discovery, plan and image finalization; `(invocation,image,stage,generation,kind)` for one-shot evaluation, transformation and terminal facts; and `(invocation,image,stage,generation,request_id,kind)` for provider starts/results. `request_id` includes the per-stage attempt number, so validation retries cannot collide. Deduplicate exact repeats by key, but reject conflicting payloads as internal accounting errors. Coordinator serializes start registration before dispatch; if result arrives before its start, retain it pending keyed by request ID until the start is processed; an orphan at drain is an accounting error, not an invented request. A result for an already closed/stale generation is recorded as a discarded diagnostic and cannot affect terminal counts or publish; already accepted request starts remain counted. Serialize stop and lifecycle transitions with coordinator sequence numbers. At drain, emit the summary only after actors stop, protected operations and finalization events settle, and pending event pairs resolve; verify all stage/image and admission equations. If reconciliation fails, print sanitized internal-accounting error to stderr, return failure (or first-signal exit), report known counters as incomplete, and never manufacture a successful 100% summary.

| Event | Emitting owner | Meaning |
| --- | --- | --- |
| `discovered` | planner | one deduplicated eligible resolved image, with ordered selection context |
| `planned` | planner | immutable admission class, selected-stage predictions, initial route and admission-boundary position; not a `StageResult` |
| `stage_evaluated`, `transform_started` | owning actor | first authoritative inspection/execution entry, and separately first transformation entry for the image-stage |
| `provider_request_started`, `provider_request_result` | provider boundary via actor | actual request attempt identity and sanitized outcome; retries have unique attempt numbers |
| `stage_terminal` | coordinator after actor outcome | exactly one completed, skipped, failed, interrupted or not-attempted accounting disposition per selected image-stage |
| `image_finalized`, `state_diagnostic` | coordinator/state service | once-only finalization and separate optional-state diagnostic; not a primary stage rewrite |
| `stop`, `abort`, `summary` | coordinator/reporter | first handled signal, failure-policy abort, and final reconciled summary |

Payload contracts: `discovered` carries `(image_id, origin_id)`; `planned` carries `(image_id, class, stage_prediction_map, route, admission_ordinal_or_none)`; `stage_evaluated` and `transform_started` carry `(image_id, stage, generation)`; provider events add `(request_id, attempt_number, is_validation_retry)` and result adds a sanitized category; `stage_terminal` adds `(disposition, reason_code_or_none, publication_confirmed)`; `image_finalized` adds `(state_outcome)`; `state_diagnostic` contains only an allowlisted operation/category and correlation ID; `stop` carries first signal; `abort` carries an allowlisted cause. The reporter's immutable `summary` contains the exact counters and reconciliation status specified below. Event-local IDs and counters are never derived from displayed redacted paths.

The public single-image result types remain compatible. Accounting-only `interrupted` and `not_attempted` are not silently added as public `StageResult` statuses; translate the existing public `skipped/interrupted` appropriately and preserve real completed publications. A budget-only bypass without inspection is an accounting skip reason, never `output_exists`.

## 2. Counter and progress definitions

| Metric | Exact boundary |
| --- | --- |
| Discovered | number of distinct eligible selected images after deduplication. |
| Initial admitted / no-work / known-excluded | mutually exclusive immutable planning image classes. Admission is the first N distinct initially LLM-needy images; no replenishment. When unlimited, all such images are admitted. |
| Planned bypass by stage | count of predicted stage bypasses and reason (`existing_output` or `budget_excluded`) at planning; explicitly provisional, not actual success. |
| Stage evaluation | first authoritative inspection or execution entry for a selected image-stage pair. A budget bypass without inspection is not evaluated. |
| Transformation execution | first entry into that stage's transformation for an image-stage pair. Count once even with validation retries; it can fail before a request. Non-LLM transformation is reported independently. |
| Provider requests / validation retries | each attempted request when entering the provider boundary, including failure; first request and JSON validation-feedback retry are separate counters. Existing validation retry history remains bounded by configuration; do not introduce automatic network retries. |
| Actual distinct LLM-work images | unique image identities for which at least one selected LLM provider boundary was entered. An admitted-but-skipped image is not actual work. A known-excluded image must never enter it. |
| Corrective images | distinct actual LLM-work images initially classified `NO_LLM_WORK`; count once even if multiple corrective stages/requests occur, regardless of the budget. It may exceed N or twice N; known exclusions never become corrections. |
| Stage outcome | exactly one of completed, skipped (with actual reason), failed, interrupted, not attempted per selected image-stage. For output-exists require A2 authoritative validation. |
| XMP evaluation/write | evaluation is stage entry, not a write. Count confirmed publication and `no_change` separately; missing prerequisite is its actual policy outcome. No write is inferred from evaluation or predicted metadata. |
| State diagnostics | independent visible events and count; do not change successful ordinary processing's primary result/exit. |

For S selected stages and D discovered distinct images, each stage's immutable denominator is D and the overall denominator is D×S **selected image-stage pairs**. A terminal disposition, including interruption and not-attempted, advances accounted progress once; queued/running work does not. Display actual outcome buckets beside progress, so 100% accounted never means 100% succeeded. `0/0 (no work)` has no percentage. Corrections do not add image-stage pairs and therefore do not inflate these denominators; display corrections and actual request attempts separately, and show runtime divergence from predicted bypass. An image can be terminal with unattempted selected stages due to stop/abort. Stages omitted by selection never enter a denominator. First-signal cancellation wins exit precedence; protected operations drain with their real outcomes and queued work is not attempted. Do not synthesize a global temporal ordering of concurrent work.

## 3. Output, precedence, and failures

- **Single-image nonverbose:** retain the current stdout line formats and exit behavior, including actual failed-stage lines on stdout and optional-state diagnostics on stderr. No new mandatory batch-style block changes this compatibility path.
- **Batch default:** concise final summary on stdout, containing discovered images, immutable admission classes, planned bypasses by stage/reason, actual stage outcome/evaluation/transformation counters, the count of actual distinct LLM-work images, the count of distinct corrective images, provider attempts/retries, XMP writes/no-change and elapsed monotonic time. Identity sets are internal; do not dump unbounded path lists. Include interruption/not-attempted, runtime plan deviations and final accounting even for failures.
- **Verbose single or batch:** add serialized start/end events, escaped image identification, stage, status/reason, monotonic elapsed and stage/overall progress, then the summary. Completion records are not required in deterministic image order when workers overlap. Required diagnostics go to stderr regardless of configured logging level; optional diagnostics never hide real stage failures.
- **Dry run:** stdout emits a provisional escaped per-file record in deterministic discovery order, showing immutable admission class, per-stage predicted work/bypasses, initial route and the exact admitted image that exhausts N; state `not reached` or `unlimited` where applicable. The final complete-plan summary provides aggregate counts and the labeled estimate. A later fatal enumeration error means earlier records were only provisional: print a sanitized stderr diagnostic, `plan incomplete`, and `estimate unavailable: incomplete plan`; never execute partial selections or call an incomplete-plan value a full estimate. No invented machine-readable output flag or permanent report file. Encode path fields unambiguously as JSON string literals to escape embedded newlines; redact configured secrets and sensitive raw provider/SQLite errors before rendering. Terminal output is not a claim of a new JSON output format.
- **Management:** A3's list prints the requested category snapshot on stdout; clear/rebuild print their truthful summaries, with errors on stderr. Report A3's `discovered`, `inspected`, `success`, `skip`, `input_failure`, `storage_failure`, `commit_unknown`, `interrupted`, `not_attempted`, category-bearing/eligible-path and transaction/confirmed-insert counts. If an unknown commit exists, confirmed inserted count is a lower observed subtotal marked incomplete, not an exact total. A confirmed commit followed by close error stays committed but emits a command failure diagnostic.

**Framing and privacy:** process file records intentionally expose selected paths and category list intentionally exposes requested category values on stdout; both may be sensitive. Management errors never include path text or category values. Before config/secrets are available, emit fixed categorized messages, not raw parser/configuration/OS exception text. Once known, redact configured secret values before JSON-string escaping, but do not rely on replacement alone: diagnostics use allowlisted categories and fixed messages, never arbitrary provider or database text. JSON escaping must represent control characters, newlines and lone surrogates without encoding errors; filenames and categories are one quoted value per line. Internally distinct image identities remain distinct even if rendered strings redact to the same text. Output text is human-readable, line-delimited UTF-8 with JSON-quoted variable strings, fixed ASCII field names and fixed ordering below; no machine-readable format mode or stable cross-version API is introduced. Tests use synthetic secret sentinels and unusual filesystem names, including pre-configuration errors.

Fixed summary line groups, in order: `summary images=... admitted=... no_work=... excluded=...`; one `planned stage=... existing_output=... budget_excluded=...` and one `actual stage=... evaluated=... transformed=... completed=... skipped=... failed=... interrupted=... not_attempted=...` per selected stage in registry order; `work llm_images=... corrective_images=... requests=... first_requests=... retries=...`; `xmp evaluated=... writes=... no_change=...` only when selected; `progress accounted=.../... elapsed_seconds=...`; management rebuild uses A3's exact counter names and explicit `confirmed_inserted_complete=true|false`. Actual skip reason breakdown follows each stage line as `skip stage=... reason=... count=...` in stable reason order, including `output_exists`, `budget_excluded`, `missing_prerequisite` and `no_change` where applicable; unknown legitimate stage reasons are retained rather than coerced into another reason. Event and summary records are one line each; stdout is not a lossless secret-bearing identity channel.

Exit table: normal complete processing with ordinary skips/budget exclusions is 0; any actual primary stage failure, infrastructure failure, or configured batch abort is 1; selection/configuration/preflight error retains existing categorized CLI behavior (authentication 1, malformed selection/configuration 2); optional processing-state diagnostics alone do not change primary exit. Dedicated management complete success, including valid empty/no-category rebuild, is 0; input/state/partial/unknown-commit failure is 1; syntax/configuration/fatal pre-execution discovery is 2. First handled signal is `128 + signal`, taking precedence; report confirmed operations and unknown outcomes truthfully. The Product Owner approved this aggregate batch/management exit policy; retain existing explicit-single-image and categorized startup behavior.

Illustrative future human-readable output (synthetic names and counts; not application execution evidence). The ordered fixed summary groups specified above are normative; `…` below denotes omitted groups, not literal output:

```text
plan provisional image="photos/example.jpg" class=ADMITTED desc=work route=desc admission=1/1 budget=reached
plan complete images=1 admitted=1 no_work=0 excluded=0 runtime_dependencies=not_checked
estimated initial plan/queue memory: 1234 bytes (estimate, not peak or bound)
stage start image="photos/example.jpg" stage=desc elapsed=0.1s
stage end image="photos/example.jpg" stage=desc status=completed progress=1/1 accounted
summary images=1 admitted=1 no_work=0 excluded=0
planned stage=desc existing_output=0 budget_excluded=0
actual stage=desc evaluated=1 transformed=1 completed=1 skipped=0 failed=0 interrupted=0 not_attempted=0
work llm_images=1 corrective_images=0 requests=1 first_requests=1 retries=0
progress accounted=1/1 elapsed_seconds=1.0
```

The first three lines belong to a dry run and the later lines to a separate real verbose invocation. `1234` is an example placeholder, not a measured or computed estimate. Other boundaries, in addition to their ordered summary fields above:

```text
# stdout: successful empty dry run
plan complete images=0 admitted=0 no_work=0 excluded=0 runtime_dependencies=not_checked
estimated initial plan/queue memory: 432 bytes (estimate, not peak or bound)
# stdout: ordinary nonverbose batch (following stage/accounting lines omitted here)
summary images=2 admitted=1 no_work=1 excluded=0
# stdout: requested list; exactly one JSON-quoted category per line
"Nature/Birds"
# stdout: rebuild partial or interrupted; include all A3 fields in actual output
rebuild discovered=2 inspected=2 success=1 input_failure=1 commit_unknown=0 confirmed_inserted=2 confirmed_inserted_complete=true
# stderr: late fatal enumeration; any earlier dry-run records were provisional
image-clarus: selection error: input unavailable
plan incomplete
estimate unavailable: incomplete plan
# stderr: interrupted management; first signal determines exit
image-clarus: interrupted; committed updates retained
```

These examples do not define a new machine-readable mode; they show line boundaries and channel ownership. Exit status is determined by the preceding table. A user running any of these commands should expect paths or requested category content on stdout; do not redirect it to a public log without authorization.

### Dry-run access and logging

Apply A1 parse → selected static configuration validation → selection/enumeration → metadata-only plan. Config, selected prompt/schema resources and a bounded local schema validation helper may be read as A1 permits. Do not resolve network destinations or invoke runtime-only provider/ExifTool preflight; report runtime dependencies **not checked**, never passed. Never open image/sidecar contents or application state, run recovery, initialize/migrate state, execute stages, invoke ExifTool/model calls, accumulate categories, or mutate artifacts/state on success or failure. Current CLI initializes stderr logging (`cli.py`); dry-run must not open/create/truncate/append a file log even on early parse/configuration errors. If future file logging is configured, suppress its file handler for dry-run and emit required sanitized diagnostics on stderr; ordinary real-execution logging is not changed by this rule. No background writer or scratch spool is used for displayed per-file rows. Actual empty success still performs A1 static validation and reports the zero-plan estimate below.

## 4. Reproducible memory estimate

The number is labeled `estimated initial plan/queue memory`, expressed in bytes, for the current Python interpreter/platform. Its frozen boundary is after the complete plan and initial predicted queues are seeded but before actors start. It estimates that proposed execution representation—not the dry-run process's RSS, a measurement, a peak, a hard bound, or a guarantee. It excludes state and execution services, actual workers/transport, images, prompts, response buffers, allocator fragmentation and native allocations, later result/growth objects, runtime correction expansion, and temporary estimator/discovery sorting allocations. It does not predict provider work from later artifact changes.

Common classification row is immutable `(path_string, origin, predicted_work_mask, predicted_bypass_mask, admission_class, initial_generation)`; a dedup set and the ordered execution row list share the same path-string objects. `origin` is a shared interned tuple `(raw_selection_string, resolved_anchor_string, selection_kind)` holding A1 selection provenance and state-resolution context; each distinct origin tuple and its unique string objects is included once. Explicit value interning shares equal origin/path strings, without relying on incidental Python string identity. Fixed `selection_kind`, masks, class and initial generation use pooled immutable objects. The stage route and earlier confirmation obligations are derived from masks and selection order; no uncounted per-image route object exists. Each stage's initial FIFO deque contains `(row, confirmation_mask)` once for each image routed there; the coordinator derives later confirmation jobs dynamically. A lifecycle list and a stage-tracking list per selected stage hold pooled initial sentinels; list index is the image ordinal, with no separate initial per-pair dict, event or token object. The initial generation and stage identity are represented by row and tracking-list position. One outer tuple holds all stage queues and another holds all stage tracking lists; the rows, lifecycle and per-stage lists start empty and grow by `append`, queues start empty and grow by `append`, and outer tuples are constructed once from the resulting stage-order objects. Fixed descriptor/mask/class/sentinel bodies are excluded, while reference slots are included in their containers. Classifier/admission rules and path identity are exactly A1/A2's for both modes; real execution builds the full plan before seeding workers. Runtime service contexts, state resolutions, dynamic confirmation jobs/results and worker bookkeeping are excluded and not yet allocated in this initial graph.

Dry-run retains the actual dedup set and the summed `sys.getsizeof(path_string)` once per distinct path, but streams display rows and does not retain per-file plan tuples or queue entries. It keeps counts for rows, initial stage queues and tracking slots. At completion build calibration lists/deques with shared placeholder references in the **same append sequence** as the execution containers. Compute using current-runtime `sys.getsizeof` shallow sizes:

```text
estimate_bytes = sizeof(actual_dedup_set) + sum(sizeof(each distinct path string))
  + sizeof(origin_table) + sum(sizeof(each distinct origin tuple))
  + sum(sizeof(each distinct origin string not already counted as a path string))
  + sizeof(calibration_rows_list) + rows * sizeof((placeholder, placeholder, 0, 0, 0, 0))
  + sizeof(queue_outer_container) + sum(sizeof(each calibration_stage_deque))
  + queued_entries * sizeof((placeholder, 0))
  + sizeof(tracking_outer_container) + sizeof(calibration_lifecycle_list)
  + sum(sizeof(each calibration_stage_tracking_list))
```

`origin_table` is an append-built list of interned origin tuples, sharing string objects with the dedup set whenever their values coincide; count each underlying string by identity once across both. The estimator retains this table; the temporary interning lookup dictionary is discarded before the execution graph's measured boundary and excluded from the estimate. Count each container once, and each row/path object body once; tuple/list/deque reference slots are already included in their shallow size, so do not recurse and charge references again. `0` is a placeholder for a pooled excluded immutable object, not a second charged object. Outer containers use the same concrete type/construction sequence as execution; queue lists, tracking lists and set allocation growth must not be approximated with hardcoded constants. Calibration is temporarily O(D) in references, as are deduplication and some directory sorting; streaming avoids retained display rows, not all O(D) memory. Empty selection yields the nonzero empty-container estimate for the selected stage count, not a fabricated zero. The Product Owner resolved the early-failure ambiguity: every completed dry-run plan reports the numeric labeled estimate, while a parse/configuration/enumeration failure before a complete plan reports `estimate unavailable: incomplete plan` instead of a fabricated number. A5 selected this concrete representation; if it changes, update estimator, documentation and graph-comparison tests together.

## 5. Worked accounting examples

**10,000 selected images, all three stages, initial N=1,000.** Assumptions: 6,000 already have valid description and JSON; 1,000 have only valid descriptions; 3,000 have neither. All missing JSON inputs have no recoverable backup; admitted generated outputs are valid, usable XMP input. Discovery order admits 1,000 of the latter and excludes the remaining 2,000 plus the 1,000 description-only images. No external changes, failures, signals or abort; missing prerequisite policy is skip. Of 7,000 images with usable JSON, the fixture further stipulates exactly 5,000 writes and 2,000 `no_change` outcomes. Those XMP outcomes are hypothetical fixture conditions, not deductions from sidecar metadata. Initial routes are desc 1,000, JSON 0, XMP 9,000. The XMP route is evaluation eligibility, not proof of valid prerequisites.

| Stage | Evaluated | Completed | `output_exists` | `budget_excluded` | Other skip |
| --- | ---: | ---: | ---: | ---: | ---: |
| desc | 8,000 | 1,000 | 7,000 | 2,000 | 0 |
| json | 7,000 | 1,000 | 6,000 | 3,000 | 0 |
| xmp | 10,000 | 5,000 writes | 0 | 0 | 2,000 `no_change`, 3,000 missing prerequisite |

Each row accounts for 10,000 pairs; overall progress is 30,000/30,000 accounted, including skips, not 30,000 successes. Actual distinct LLM-work images=1,000, corrections=0, LLM transformations=2,000, provider requests=2,000 assuming one request each and no retry. XMP write/no-change counts are illustrative actual outcomes, not metadata predictions. For a separate N=1 case with one admitted image and three initially no-work images whose missing descriptions are correctable, distinct actual LLM-work images=4 and corrections=3; no initially excluded image may request inference.

**Rebuild:** 997 category-bearing inputs commit and three inputs fail validation: discovered=inspected=1,000; success=997, input_failure=3, skip=storage_failure=commit_unknown=interrupted=not_attempted=0, transactions_attempted=confirmed_committed=997, exit 1. Eligible-path and confirmed-insert counts depend on the actual paths and existing store and cannot be inferred from file totals. With a later uncertain commit, show confirmed inserted subtotal and `incomplete` per A3, not invented final inserts.

The three 10,000-pair sums, 30,000 total, corrective example, and 997+3 input total were checked using a local Python assertion. This is arithmetic verification of the illustrative numbers only, not a planner or execution test.

## 6. Future verification boundaries

These are prospective tests, not results of A4:

1. Feed a fake fact stream with duplicate and reordered actor messages, at least two distinct validation retries including result-before-start, conflicting duplicates and orphan messages, provider failures, correction beyond N and beyond 2N, budget exclusions, selected stage subsets, active cancellation and late completion. Assert exactly-once terminal image-stage accounting, immutable classes, distinct provider attempt identities and absence of phantom successes.
2. Use deterministic barriers and 10,000 synthetic image plans to exercise the example's routing and 30,000 stage dispositions with separate XMP evaluation/write outcomes; assert non-default continuation and actual counts, not fabricated provider calls.
3. Independently construct the execution object graph with shared paths/rows and compare an identity-deduplicated shallow-size sum with the estimator for zero, one, many, all admission classes, different stage counts, queue allocations and growth thresholds. Verify the exact append construction; change the formula when representation changes. This is an estimate-contract test, not a peak-memory benchmark.
4. Run the installed CLI against safe synthetic selections for complete/empty, file detail/budget exhaustion, duplicate selection, Unicode/newline paths, malformed config and late discovery failure. Assert provisional/final labels, no partial plan execution, runtime prerequisite `not checked`, dry-run state/content/write/log-handler spies on both success and failure, and redaction across stdout/stderr at all configured logging levels.
5. Cover all three failure policies and signal precedence, continued active safe writes, zero denominators and 100%-accounted failures/not-attempted. Rebuild fixtures cover 997/3, duplicate paths, unknown commit and post-commit close failure with exact A3 equations. A5 reconciles A3's unfinished access/backend without replacing its approved management behavior.

## 7. Actual verification and completion

At version `0.3.11`, from the project root, `uv lock --locked` passed (21 packages), `uv run --locked --extra dev --python 3.13 image-clarus --version` reported `image-clarus 0.3.11`, and `uv run --locked --extra dev --python 3.13 pytest -q tests/unit/test_cli.py tests/unit/test_resources.py tests/unit/test_pipeline.py tests/unit/test_config.py` passed **123 tests**. `uv run --locked --extra dev --python 3.13 ruff check .` and `uv run --locked --extra dev --python 3.13 ruff format --check .` passed (164 files). The hardlink-to-copy fallback succeeded. A standalone synthetic CPython shallow-size comparison of the documented initial graph and formula passed for 0, 1, 7, 40 and 1,000 rows (2,976; 3,570; 5,724; 15,698; and 305,958 bytes respectively on this runtime). This checks formula arithmetic for those synthetic shapes, not the unimplemented production graph, execution peak, platform portability or the accuracy of future estimates. The 123 tests are existing-baseline checks, not execution of the designed reporting or worked examples; no full suite, live provider or Windows runtime was tested.

Created this record; updated `docs/slice-4/IMPL-PLAN-slice-4.md` and `docs/slice-4/REQ-slice-4.md`, and synchronized `pyproject.toml`, `uv.lock`, `tests/unit/test_cli.py` and `tests/unit/test_resources.py` for the patch version. No feature implementation or behavior test was changed. Independent review findings on accounting, event retry identity, output/privacy and graph scope were reconciled. The Product Owner explicitly approved a numeric estimate for completed plans and an unavailable marker on early failure; A4 and B6 criteria were synchronized without fabricating an incomplete estimate.

### A4 acceptance

- [x] Initial admission, corrective images, actual distinct LLM-work images, stage evaluations/executions, retries, and writes cannot be confused in the documented output.
- [x] Progress and final summaries account for partial, failed, aborted, interrupted, and empty runs with defined channels and exits.
- [x] Every completed dry-run plan has a labeled estimate with a reproducible method, stated scope/assumptions, and no unsupported bound claim; an incomplete plan reports that the estimate is unavailable.
- [x] All output/access decisions needed by B6 and Phase M are resolved and cross-referenced before A5.
