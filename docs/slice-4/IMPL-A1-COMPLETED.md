# Step A1 - Freeze selection and configuration contracts [DESIGN]

**Status:** Design complete; Slice 4 implementation has not begun. The decisions below are A1's selected design for subsequent review and reconciliation, not implemented behavior. A2–A4 must reconcile their shared contracts before A5. Product-behavior choices identified in §8 require Product Owner approval before Phase A closes; assignment of A1 establishes requirements readiness and is not a separate REQ-acceptance gate.

**Scope deviations:** None.

## Files created, updated, removed

- Created: `docs/slice-4/IMPL-A1-COMPLETED.md`.
- Updated: `docs/slice-4/IMPL-PLAN-slice-4.md` for A1 status and contract; `pyproject.toml`, `uv.lock`, `tests/unit/test_cli.py`, and `tests/unit/test_resources.py` for the patch-version delivery.
- Removed: None. No selection, configuration, stage, or state implementation was changed.

## Baseline and authority

The governing parent REQ, HLD, Slice 4 REQ and plan define scope. Baseline package version is `0.3.3`; this design delivery is `0.3.4`. This filesystem inspection does not assert a Git revision or clean worktree. Current CLI accepts one readable, explicitly selected file, resolves it strictly, rejects literal wildcard syntax, and applies no discovery extension filter. Current configuration resolution merges defaults, the selected YAML file, ordered `--set` overlays, then dedicated options; YAML-origin paths are relative to the YAML directory and CLI-origin paths to CWD. `pipeline.missing_prerequisite` currently defaults to `fail`; configuration provenance is needed to implement a batch default without overriding explicitly configured `fail`. Selected-stage preflight currently combines static validation and execution probes, including selected XMP's ExifTool probe. These are observations, not Slice 4 implementation evidence.

## 1. Selection grammar and context

The selected process grammar is `image-clarus process [OPTIONS] SELECTION [SELECTION ...] [OPTIONS]`. Options may precede or follow the contiguous selection group; do not support inserting options between selections (`process a.jpg --verbose b.jpg` is invalid). After `--`, all remaining tokens are selections, including tokens beginning with `-`; `--` cannot split a selection group or resume option parsing. At least one nonempty selection is required. **Product Owner decision: literal paths take precedence.** After home expansion, first check the token as an exact path: an existing file or directory is a literal selection even if its name contains `*`, `?` or `[]`. Otherwise, a token containing glob metacharacters is a native pattern; a token without them is a literal path and follows the missing-path policy. A dangling symlink, inaccessible entry or other existing non-regular literal entry is a selection error rather than silently falling through to glob expansion; an existence/access check error is also an error. This classification uses metadata, not image or sidecar content.

Shell quote characters are removed before Image Clarus receives arguments; quoting alone never determines classification. An unquoted glob may be expanded by the shell first, and each resulting token is classified literally first. Its wildcard provenance cannot be recovered: one resulting literal file is explicit-single context, and shell-expanded links are explicit selections. Quote a glob to prevent shell expansion when native pattern matching and its symlink and batch-context rules are desired, but an exact existing path still wins. Unmatched unquoted globs are controlled by shell settings.

| Input | Selected behavior | Context and outcome |
| --- | --- | --- |
| One literal readable regular file | Resolve strictly, including an explicit image symlink; use resolved path for execution, sidecars and image-ancestor state. Preserve current explicit-file behavior even if its suffix is absent from the discovery allowlist; adapter errors remain execution outcomes. | Single-file context, including an explicit symlink. |
| One literal directory, including explicit directory symlink | Resolve the starting root, enumerate eligible image files recursively subject to depth; do not follow any symlink encountered below the root. | Batch context, even if zero or one file is found. |
| Native pattern after literal-first check | Expand internally from the longest literal directory prefix; match files, not implicit recursive processing of matched directories. Apply image eligibility, depth, ordering and no-discovered-symlink rules. | Batch context even if it yields one file. |
| Multiple tokens of any kind | Process tokens in supplied order; merge candidates and deduplicate before planning. | Batch context even if deduplication leaves one file. |
| Valid empty directory or valid pattern with no match | After the startup validation in §4 succeeds, produce an explicit empty selection and zero-count summary, with no stage work or state mutation. | Normal empty batch result, subject to A4's final output/exit design. |
| Missing, unreadable or non-regular explicit input; nonexistent/unreadable literal pattern anchor; discovery I/O failure | Report an actionable sanitized selection error and abort planning before any stage writes; do not execute a partial selection. | Error; retain current explicit-file failure semantics. |
| Missing positional input, malformed pattern or an empty token | Report invalid selection/usage; no execution. | Error; no implicit CWD selection. |

A direct file with an unsupported extension may pass selection but can fail in the selected adapter. Directories and native patterns use the configured allowlist. Preserve selected-stage ordering, explicit subsets and existing prerequisite behavior.

## 2. Pattern, order, depth and identity

Expand a leading `~` or `~user` using the existing `Path.expanduser()` behavior for literal and patterned tokens; an unresolvable home or NUL is an error. Absolute and relative paths are accepted; relative paths anchor at CWD. **Parse according to the host OS before recognizing wildcard components:** Windows accepts `\` and `/` separators, drive-qualified paths such as `C:\Photos\*.jpg`, and UNC roots such as `\\server\share\photos`; on POSIX, `/` separates components and `\` is a literal filename character. Do not reinterpret a Windows path as a POSIX path on Windows. Apply literal-first classification before expansion; exact existing filenames such as `photo[1].jpg` require no escaping. For tokens classified as patterns, normalize `.` components; resolve `..` only in the fully literal prefix before pattern traversal and reject `..` after the first wildcard. Native patterns use Bash-style glob concepts, not regex or a Bash process: component-local `*`, `?`, bracket classes and component-wide `**`. Bracket classes support literal characters, ascending ranges and leading `!` negation; `[[]`, `[]]`, `[*]` and `[?]` match literal metacharacters. Reject unclosed, empty, negation-only and descending-range classes and embedded `**` in a component. On POSIX backslash is a literal filename character, not an escape; on Windows it is a separator. Patterns match dot-prefixed names and are case-sensitive by default on both hosts; `-i` / `--ignore-case` makes native-pattern component matching case-insensitive. Use Python Unicode `re.IGNORECASE` semantics for literal characters and bracket ranges on both platforms, without Unicode normalization, locale collation or multi-character full case folding; retain the existing glob grammar and do not expose regex syntax. Treat the longest fully literal prefix as the host-resolved anchor, not an enumerated case-insensitive search; `-i` applies to matching components from the first wildcard onward. Exact literal selection continues to follow host filesystem lookup. `**` matches zero or more directories but does not bypass the depth limit. These rules are not a claim of complete Bash or locale equivalence. An explicit directory or entirely literal prefix may be a link root; discovered links never are.

The Product Owner approved these matching outcomes. Thus, with native pattern `'photos/*.jpg'`, `photo.JPG` does not match by default but does under `-i`, despite directory extension eligibility being independently case-insensitive. `-i` never changes exact resolved-path identity or merges distinct case-variant files. To prevent shell expansion before the option can apply, quote patterns; shell-expanded tokens cannot be retrospectively reinterpreted. The same invocation-only option applies to process and category rebuild patterns.

- Use portable native APIs such as `pathlib` and `os.scandir`; no Bash subprocess or POSIX-only path assumption. Process roots/patterns in CLI token order. At each directory emit eligible files first, then descend depth-first into real subdirectories. Sort names by filesystem-encoded bytes on POSIX and UTF-16 code units on Windows, preserving representable names without locale collation, case folding or Unicode normalization; preserve first occurrence. This guarantees repeatable ordering for an unchanged collection on the same host, not identical order across operating systems or filesystems. Pattern traversal applies the same order and filters matches; duplicate matches from repeated `**` paths are emitted once.
- Anchor depth 0 at each explicit directory root or the longest literal directory prefix of a native pattern. Depth N permits files in directories at most N levels beneath that anchor. A literal file has no traversal depth. Process and rebuild each have an independent limit; the existing macro depth truncates category paths and is unrelated.
- Deduplicate using the host-resolved absolute pathname as an exact string, without case folding or Unicode normalization; do not rely on `PureWindowsPath` equality, which folds case. An explicitly selected symlink and its resolved target with the same resulting spelling are one identity. Different hard-link names remain distinct because their sidecar paths and image ancestry differ. Case-variant aliases and other names that resolve to the same filesystem object but retain different resolved spellings are **not guaranteed to deduplicate**, including on case-insensitive Windows volumes; do not falsely promise filesystem-wide object identity or collapse distinct files on case-sensitive directories. The first retained spelling determines order and provenance. There is no deduplication guarantee across bind mounts or external filesystem changes. Deduplication does not change invocation context: a pattern remains batch context.
- Evaluate eligibility and explicit-versus-discovered symlink rules for each token before deduplication; skipped discovered symlinks cannot suppress a later explicit symlink. If a pattern first finds a real target and a later literal symlink resolves to that target, keep one identity at the first position; the invocation remains batch context because it contains multiple tokens. An unmatched pattern or empty valid directory contributes no candidates but does not discard other valid selections. Any missing/unreadable literal input or invalid pattern aborts the entire initial plan even when other tokens matched; no stage work starts.
- Use non-following metadata for each discovered component and never intentionally traverse discovered symlinks or Windows junctions, including matching pattern links or directories. Explicitly supplied directory symlinks or junctions can designate starting roots. If a platform cannot reliably classify a discovered link/reparse point, report the limitation/error rather than silently follow it. This is not a security sandbox against concurrent path replacement. A detected access/race error aborts initial planning with a visible diagnostic rather than silently executing a partial plan. An unchanged collection yields deterministic discovery; it is not a filesystem snapshot.

## 3. Frozen controls and layering

The names in this table are A1 design choices, not currently implemented flags. `selection` is a new process-selection section; `category_rebuild` is independent command configuration. A3 owns management command grammar/target semantics and must reconcile its chosen grammar with these controls before A5.

| Setting | YAML default and valid values | Dedicated CLI | Invalid / empty |
| --- | --- | --- | --- |
| Process depth | `selection.max_depth: null`; null means unlimited; integer N >= 0 | `--max-depth N`; `--max-depth-unlimited` overrides configured limit | Reject negatives, booleans, nonintegers, empty strings, repeated/conflicting dedicated depth options. |
| Image extensions | `selection.extensions: [jpg, jpeg, png, webp, tif, tiff]`; nonempty list of nonempty ASCII alphanumeric suffixes without dots | `--extensions jpg,png` replaces the list | Reject empty lists/elements, dots, separators or whitespace inside values; match ASCII case-insensitively. Duplicate values deduplicate after case folding. |
| Native pattern case | Invocation-only, default case-sensitive | `-i` / `--ignore-case` on process and rebuild | Repeated singleton occurrence is an argument error; literal paths and identity are unchanged. |
| Initial LLM allowance | `pipeline.max_work_files: null`; null means unlimited; integer N > 0 | `--max-work-files N`; `--no-max-work-files` clears configured limit | Reject zero, negative, booleans, nonintegers, empty input and repeated/conflicting dedicated forms. |
| Inter-stage concurrency | `pipeline.inter_stage_concurrency: true`; boolean only | `--inter-stage-concurrency` / `--no-inter-stage-concurrency` | Reject nonbooleans and repeated/conflicting dedicated forms; false invokes image-first mode. |
| Rebuild depth | `category_rebuild.max_depth: null`; null/unlimited or integer N >= 0, independent of process | Rebuild subcommand `--max-depth N` / `--max-depth-unlimited` | Same depth validation and conflict behavior; not an alias for `selection.max_depth`. |
| Dry-run | Invocation-only, default false | `--dry-run` on process | No persistent YAML setting; repeated singleton occurrence is an argument error. |
| Verbose | Invocation-only, default false | `--verbose` on process | No persistent YAML setting; repeated singleton occurrence is an argument error. |

The dedicated options override ordered generic `--set` overlays, which override selected YAML, which overrides built-in defaults. For any generic repeat, preserve existing last-assignment behavior including parent replacement semantics; validate keys in each layer and effective types after higher-priority repair, consistent with existing configuration. Dedicated paired switches are mutually exclusive and each singleton may be specified once. `--set selection.max_depth=null` and `--set pipeline.max_work_files=null` are valid unlimited overrides. Dedicated options are scoped to their process or rebuild command; do not let an unrelated command probe selected processing stages. Existing CLI/YAML paths retain their current origin-relative semantics and state selection does not initialize or open a store during resolution.

`--extensions ''`, `--extensions jpg,`, and `--extensions 'jpg, png'` are invalid; surrounding or embedded element whitespace is not trimmed. Repeating `--extensions` is an error. `--set 'selection.extensions=[jpg, png]'` supplies a list, not comma-separated CLI text. A structurally valid but invalid lower-layer value can be repaired by a higher-priority assignment before effective-value validation, e.g. YAML `extensions: []` followed by `--extensions jpg,png`; unknown keys remain invalid per layer.

**Missing-prerequisite provenance:** explicit dedicated CLI > surviving effective explicit `--set` leaf/parent assignment > surviving selected YAML leaf > contextual default. A `--set pipeline=...` assignment replaces the earlier pipeline subtree and its provenance, even if the replacement omits the policy; a later leaf override restores explicit provenance. If no surviving higher layer explicitly supplies the leaf, use `fail` for a single literal file and `skip` for every batch context, including a directory or quoted pattern with one result. Preserve explicit `fail` or `skip` from a surviving higher layer. Track presence through parent replacement and final fallback, not only the merged value. Invalid explicit policy is an error unless repaired by a valid higher layer. A2 owns `pipeline.on_stage_failure` expansion to include batch abort; do not change existing `stop`/`continue` meaning.

| Selected YAML / generic overrides, in order | Batch outcome without dedicated flag | Dedicated `--missing-prerequisite fail` |
| --- | --- | --- |
| YAML omits policy; no override | contextual `skip` | `fail` |
| YAML explicitly sets `fail`; no override | YAML `fail` | `fail` |
| YAML `fail`; `--set 'pipeline={}'` | contextual `skip`: replacement removed YAML policy, despite restoring built-in defaults for other leaves | `fail` |
| YAML `fail`; `--set 'pipeline={}'`; `--set pipeline.missing_prerequisite=fail` | generic `fail` | `fail` |
| YAML `skip`; `--set 'pipeline={missing_prerequisite: fail}'` | generic `fail` | `fail` |
| YAML `fail`; `--set pipeline.missing_prerequisite=skip` | generic `skip` | `fail` |

The same reset without a surviving override yields contextual `fail` for a single literal file. Invalid final explicit values fail validation; a dedicated valid flag repairs a lower invalid value under existing layering rules. Tests must cover parent replacement, leaf-after-parent, repeated parent/leaf ordering and dedicated repair.

Illustrative future configuration and commands use fictional, provider-free examples:

```yaml
selection:
  max_depth: 2
  extensions: [jpg, jpeg, png, webp, tif, tiff]
pipeline:
  max_work_files: 1000
  inter_stage_concurrency: true
category_rebuild:
  max_depth: 1
```

```text
image-clarus process 'photos/**/*.jpg' --max-depth 2 --max-work-files 1000 --dry-run
image-clarus process photos --no-inter-stage-concurrency --set pipeline.missing_prerequisite=fail
image-clarus state categories rebuild photos --max-depth 1
```

The management command spelling is illustrative pending A3; it is not implemented.

## 4. Startup and dry-run access contract

Split configuration into (1) selection, layering, structural/key/type validation and static validation of every selected stage; (2) execution-only dependency preflight for all selected stages, before any stage can write; (3) stage execution. Selected-stage static validation retains model/provider references, URL syntax, settings, prompt/schema availability and validation, and actionable sanitized errors. Configuration, selected prompt and schema resources may be read; a bounded local schema-validation subprocess is allowed only if it performs no prohibited content read or mutation. Static validation must not contact providers or resolve network destinations. Existing credential-source checks retain their security behavior without exposing values.

During dry-run, metadata-only discovery/planning may inspect directory entries, file types, selection eligibility, sidecar existence, and resolved configuration. It must not open image/sidecar contents or application state, recover sidecars, initialize/migrate/write state, invoke ExifTool or a model, or write artifacts on success **or error** paths. It must not invoke execution-only dependency probes. Report ExifTool/runtime dependency usability as **not checked**, not as passed. Planning completes before workers would start; memory estimate and reporting scope belong to A4. For real execution, perform all selected execution-only preflight checks before the first selected stage write, preserving ExifTool isolation to selected XMP and selected-stage validation. Never require XMP or provider preflight for unrelated category operations; A3 settles state access and management command failures.

Startup ordering is parse → layer/validate selected configuration → enumerate every selection → if a real selection is nonempty, preflight all selected runtime dependencies → plan and execute. A fatal parse, configuration or enumeration error prevents execution, including when another token is empty or valid. A valid empty batch still undergoes selected-stage static validation, including configured model and credential-source checks, but neither real execution nor dry-run invokes runtime-only provider or ExifTool preflight when there is no work. An unavailable runtime dependency therefore does not make an otherwise valid empty batch fail. Dry-run never performs runtime preflight, even with work, and reports runtime usability as not checked. After applicable checks succeed an empty batch returns the zero-count outcome; exact summary/exit format is A4's task.

## 5. Reusable discovery boundary

Select `src/image_clarus/discovery.py` as the proposed B2 module. Its public design interface takes ordered raw selections, an independent depth limit, and an injected eligibility policy; it yields ordered resolved candidate paths with selection provenance and structured diagnostics, or a fatal discovery failure. It does not import stages, providers, state storage or XMP policy, and performs no image/sidecar content reads. Planning owns plan completion, deduplication enforcement, admission and queue routing; the discovery boundary supplies enough identity/order information for deterministic deduplication before admission. Whether records are streamed or retained is reconciled with A2/A4, not a claim of constant memory.

Process injects image-extension eligibility. Rebuild injects `.desc.json` eligibility and its separate depth control, using the same traversal and symlink primitives. Subsequent A3 decisions accept explicit and orphan sidecars and choose one configured/CWD-selected destination with an explicit override; see [A3](IMPL-A3-COMPLETED.md). Proposed test locations: `tests/unit/test_discovery.py`, `tests/unit/test_slice4_config.py`, `tests/integration/test_slice4_selection_cli.py`, plus existing CLI/config tests. A5 confirms final interfaces and paths before implementation.

## 6. Acceptance scenarios and rationale

| Case | Expected designed outcome and rationale |
| --- | --- |
| `a.jpg`, `z.JPG`, `b/c.jpg`, `b/deep/d.png` | Unlimited order is root files then depth-first descendants in byte-name order; depth 0 excludes descendants, depth 1 includes `b/c.jpg`. Existing extension matching is case-insensitive; no decoder success is implied. |
| Reverse two roots with limit 1 | First qualifying distinct image of the first supplied root is admitted. Overlapping roots, repeated literal files and explicit aliases deduplicate before admission when their resolved spellings match; distinct resolved spellings and separate hard-link names remain distinct. |
| Explicit file link vs same link discovered during walk or pattern | Explicit link resolves as today; discovered link is skipped, including outside-root targets and cycles. Explicit target plus explicit alias is one resolved-path identity. |
| `root/*.jpg` vs `root/**/*.jpg` | When neither token names an existing literal path, the first matches only root-level eligible files; the second includes descendants within depth, without following discovered symlinks. A native pattern with one match remains batch context. |
| Native pattern case and identity | Quoted `'photos/*.jpg'` excludes `photo.JPG` by default and includes it with `-i`; directory eligibility includes both cases. Exercise `-i` with bracket ranges, Unicode and `**`, exact literal paths, shell-expanded arguments, and two distinct case-variant files without collapsing identities. Both process and rebuild use the option. |
| Existing literal `photo[1].jpg` and glob-matching `photo1.jpg` | The exact existing `photo[1].jpg` wins and is one explicit file even if quoted; it is not expanded to `photo1.jpg`. If the exact entry is absent, the same received token is a native glob, subject to normal matching and batch rules. A literal directory containing metacharacters likewise wins. |
| Literal metacharacter path is a dangling symlink or inaccessible | Report a selection error; do not silently reinterpret an existing invalid/inaccessible entry as a glob. Shell-expanded arguments are still classified by their received literal values. |
| Windows paths and portability | On Linux, pure-path tests parse `C:\Photos\*.jpg`, `C:/Photos/*.jpg`, and `\\server\share\photos\*.jpg` into correct Windows roots/components before glob handling; native Linux tests retain literal backslashes in filenames. These pure tests do not verify Windows filesystem access, junctions, permissions, case resolution, subprocesses, or runtime behavior. |
| Shell-expanded one-match pattern | CLI receives one literal token and uses explicit-single context; no impossible wildcard-provenance inference is claimed. Quoting prevents shell expansion but native-pattern behavior occurs only if the exact token is not an existing literal path. |
| Explicit unlisted suffix vs discovered unlisted suffix | Explicit readable file retains current selection compatibility; discovered file is excluded unless configured. Decoding, if needed, is an execution concern. |
| Directory selection and explicit YAML/`--set`/dedicated `fail` | Batch default is `skip` only when no higher layer explicitly supplies the value; explicit `fail` wins. Direct literal default is `fail`. |
| Depth/work controls | 0 depth is valid; negative, boolean or fractional depth and nonpositive/boolean work limit fail. Null clears a YAML limit; dedicated unlimited options override it. Process, rebuild and category-macro depths remain independent. |
| Dry-run with selected XMP and unavailable ExifTool | Static selected-stage checks run; no ExifTool probe or stage/state/image/sidecar access occurs. Report runtime prerequisite not checked. Nonempty real execution must probe selected XMP before any write. |
| Empty/no-match vs missing/unreadable root | Valid empty selection yields an explicit zero summary without work or state mutation; missing/unreadable input aborts before execution and is visibly reported. |
| Empty real batch and unavailable execution dependency | After successful static validation, a valid empty batch succeeds without provider/ExifTool runtime preflight; nonempty real execution still runs selected runtime preflight before writes. |

These are required future tests, not executed application results. Tests must include native patterns with discovered symlink intermediates, outside-root links, invalid syntax, duplicate arguments, quoted/shell-expanded distinction, all six extension candidates, independent process/rebuild depths, metadata-access spies and startup/error paths. A3 supplies rebuild-specific eligibility/target scenarios.

## 7. Verification and evidence

Design tables and acceptance scenarios do not assert that Slice 4 behavior already exists. No live provider call or real-image test was performed for this design step.

At package version `0.3.4`, executed from the project root:

- `uv lock --locked` — passed; 21 packages resolved.
- `uv run --locked --extra dev --python 3.13 image-clarus --version` — `image-clarus 0.3.4`.
- `uv run --locked --extra dev --python 3.13 pytest -q tests/unit/test_cli.py tests/unit/test_resources.py tests/unit/test_config.py tests/unit/test_cli_config_acceptance.py` — 124 passed.
- `uv run --locked --extra dev --python 3.13 ruff check .` — passed.
- `uv run --locked --extra dev --python 3.13 ruff format --check .` — passed; 162 files already formatted.

These are existing CLI/configuration regressions and delivery checks, not execution evidence for the planned A1 contracts. The package install emitted a hardlink-to-copy fallback warning; the command succeeded. Full-suite and Slice 4 implementation tests were not run.

**Subsequent literal-first design update:** Delivered as `0.3.5`, without implementing file selection. `uv lock --locked` passed; `uv run --locked --extra dev --python 3.13 image-clarus --version` reported `image-clarus 0.3.5`; `uv run --locked --extra dev --python 3.13 pytest -q tests/unit/test_cli.py tests/unit/test_resources.py` passed 60 tests; `uv run --locked --extra dev --python 3.13 ruff check .` passed and `uv run --locked --extra dev --python 3.13 ruff format --check .` passed for 162 files. The earlier 124-test result remains evidence at `0.3.4`, not a rerun at `0.3.5`. The installation again reported a successful hardlink-to-copy fallback.

**Subsequent Windows-by-design update:** Delivered as `0.3.6`, without implementing discovery. `uv lock --locked` passed; the Python 3.13 CLI reported `image-clarus 0.3.6`; `uv run --locked --extra dev --python 3.13 pytest -q tests/unit/test_cli.py tests/unit/test_resources.py` passed 60 tests; Ruff check and format check passed (162 files). A Python 3.13 `pathlib.PureWindowsPath` probe on Linux verified standard-library parsing of the drive-letter, mixed-separator and UNC examples in §6. It did not exercise Image Clarus discovery or Windows runtime/filesystem behavior. Installation again fell back successfully from hardlinking to copying. Earlier version-specific test results remain unchanged.

An independent read-only review identified ambiguity in generic parent overrides, pattern grammar, empty-selection preflight, mixed input handling, extension parsing and approval classification. The design tables were corrected before closeout. A local Python documentation check then confirmed the four plan/record acceptance rows match, all 19 summary and detailed headings match, the YAML example parses with the documented values, manifest/lock versions agree, and the plan and record pass a scoped whitespace and privacy scan for internal host/provider terms and local paths. These checks are not tests of an implemented discovery engine.

## 8. Product-behavior decisions and handoff

The Product Owner approved literal-first selection, Bash-style glob concepts, exact resolved-path identity, dotfile inclusion and case-sensitive native matching by default, with `-i` / `--ignore-case` as specified in §2. The Product Owner also approved valid-empty and mixed-invalid input outcomes, dotless ASCII-alphanumeric extension restrictions, and explicitly changed the earlier empty-run preflight proposal: a valid empty batch skips runtime-only preflight after static validation. Existing `--max-depth`, `--max-work-files`, `--dry-run`, `--verbose`, explicit-file compatibility and explicit-symlink behavior are not reopened. The parser and repeated/conflicting singleton handling are A1 design mechanics, not separately claimed Product Owner decisions. None of these Slice 4 choices is implemented here.

**Subsequent Product Owner platform decision:** Windows is an expected deployment platform, and Slice 4 discovery must be designed and implemented for both Windows and Linux now using portable filesystem operations; a Windows test machine is not required. The host-specific path, matching, ordering, symlink/junction and identity rules in §2 supersede A1's original POSIX-only path interpretation. The Product Owner subsequently approved exact-string resolved-path identity with the stated limitation: case-variant or other aliases that retain different resolved spellings may be processed and budgeted separately, including on Windows; this does not assert all Windows filesystems are case-insensitive. Pure-path tests do not prove Windows filesystem behavior. Review other touched subprocess and filesystem seams for portability within their owning steps; no historical behavior is claimed Windows-verified.

## A1 acceptance

- [x] Every supported selection/control has a documented valid, invalid, and empty-case outcome, including duplicate identities and explicit/discovered symlink boundaries.
- [x] Defaults and overrides retain existing precedence; process/rebuild/category-macro depth are distinct.
- [x] Dry-run startup and failure paths have a demonstrable metadata-only boundary, while real execution retains selected-stage preflight.
- [x] New product-behavior decisions have an outcome, rationale, acceptance scenario, and required approval before A5.
