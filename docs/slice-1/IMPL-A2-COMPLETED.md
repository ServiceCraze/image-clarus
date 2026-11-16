# Step A2 — Freeze the single-image CLI, configuration, and result contracts (COMPLETED)

**Status:** ✅ Complete

**Scope deviations:** None

**Files Created/Updated/Removed at A2 closeout:**
- Created: `docs/slice-1/IMPL-A2-COMPLETED.md`
- Updated: `docs/slice-1/IMPL-PLAN-slice-1.md`, `docs/slice-1/IMPL-A1-COMPLETED.md`
- Removed: None

---

## Summary

Completed Phase A Step A2 as a design-only step. This record freezes the one-image `process` grammar, stage selection and regeneration behavior, CLI override names and precedence, Linux and portable config discovery, the A2 configuration-key schema, selected-stage validation, user-visible results, failure/exit behavior, interruption statuses, the exact `--version` line, and the help-only `search` stub. The plan records the public command examples and maps interruption verification to C2. No production code, tests, package metadata, or configuration examples were created. At A2 closeout, Steps A3–A6 were pending; Steps A3–A5 have since completed, Erik accepted A3 as documented during A6, and the A6 readiness gate has passed. Phase B/C implementation remains unstarted.

## Frozen CLI contract

### Command grammar

```text
image-clarus --help
image-clarus --version
image-clarus process --help
image-clarus process IMAGE [--config FILE] [--stages STAGE[,STAGE...]] [--set PATH=VALUE]... [--desc-prompt FILE] [--json-prompt FILE] [--json-schema FILE] [--regenerate] [--missing-prerequisite {fail,skip}]
image-clarus search --help
image-clarus search
```

- `-h` and `--help` are accepted at the top level and for each subcommand. Help exits `0` without reading configuration, credentials, or an image. Top-level `--version` is supported only before a subcommand. Options use `--option VALUE`; argparse's equivalent `--option=VALUE` spelling is accepted.
- `process` requires exactly one `IMAGE`. Expand `~`, resolve relative paths against the current working directory, and resolve symlinks to their target. The target must exist, be a readable regular file, and not be a directory or glob. Directories and multi-file selection are not supported in Slice 1. A corrupt or model-unsupported image is a stage failure, not a CLI path-syntax error.
- `--config`, `--stages`, each dedicated path override, and `--missing-prerequisite` may appear at most once. `--regenerate` is a single boolean flag. `--set` is repeatable. Empty, unknown, or duplicate stage identifiers are rejected. Stage identifiers are case-sensitive and restricted to the Slice 1 registry: `desc`, `json`.
- `--stages` accepts one comma-separated list. Trim surrounding whitespace from each item; empty, unknown, or duplicate items are errors. Without it, select the registered Slice 1 stages in registry order: `desc`, then `json`. An explicit list selects only those stages and still runs them in registry order; `--stages json` never invokes `desc`. It does not accept `xmp` in Slice 1.
- `--desc-prompt FILE`, `--json-prompt FILE`, and `--json-schema FILE` independently override the corresponding file path. They apply only if their stage is selected. `--regenerate` applies to each selected stage's owned output and does not add prerequisite stages. Credentials are not accepted as CLI options or `--set` values.
- The process help synopsis must show the required image path, every accepted option, the `desc,json` default, the `fail` missing-prerequisite default, the create-only output default, and that `search` is a help-only Slice 1 stub. Tests assert semantic help contents and option names, not argparse's whitespace wrapping.

### Version and search

- `image-clarus --version` writes exactly `image-clarus 0.1.0\n` to stdout and exits `0`. It bypasses config discovery, config parsing, credentials, provider access, and image-path validation. The initial value comes from A1's authoritative static `[project].version` through `importlib.metadata`; no duplicate version constant or fallback version is permitted. Missing installed metadata is an installation/configuration error, not a reason to print a guessed version.
- `image-clarus search --help` is registered and exits `0` without loading runtime configuration. The no-argument non-help command writes exactly `search is not implemented in Slice 1\n` to stderr and exits `3`. Search accepts no positional arguments or options in this slice; extra/unknown arguments are ordinary usage errors (exit `2`). It performs no matching, sidecar traversal, config/provider loading, or model calls.

## Configuration contract

### Discovery, precedence, and path bases

- Built-in defaults are always the base layer. An explicit `--config FILE` loads only that file and disables discovery; a missing, unreadable, or malformed explicit file is an error and never falls back.
- Without `--config`, select at most one existing file, checking the user location before the system location. Linux: `~/.config/image-clarus/config.yaml`, then `/etc/image-clarus/config.yaml`. macOS: `~/Library/Application Support/image-clarus/config.yaml`, then `/Library/Application Support/image-clarus/config.yaml`. Windows: `%APPDATA%\image-clarus\config.yaml`, then `%PROGRAMDATA%\image-clarus\config.yaml`. The first existing file is authoritative; if it is unreadable or invalid, fail rather than trying the lower-priority path. Do not merge user and system files. If no file exists, use built-in defaults.
- Effective value precedence is built-in defaults < selected YAML file < repeated `--set` entries (last occurrence wins for the same path) < dedicated CLI flags. Dedicated flags win over a `--set` targeting the same setting regardless of argument order. `--stages` is invocation selection, not a persistent config value.
- The explicit config path and all dedicated CLI paths resolve from the current working directory. File paths stored in the selected YAML file resolve from that YAML file's parent directory. Paths supplied as file-path values through `--set` resolve from the current working directory. Built-in prompt/schema paths resolve through packaged resources. Expand `~` consistently.
- `--set PATH=VALUE` splits at the first `=`, uses a dot-separated mapping path, and parses VALUE with PyYAML `safe_load` (scalar, sequence, or mapping); unsafe YAML tags are rejected. A missing/empty VALUE is invalid; use `null` for an explicit null. Provider/model aliases use letters, digits, `_`, and `-` so dotted paths are unambiguous. Array-index path segments are not supported. Unknown configuration keys and paths are rejected. `--set` may create named entries under `providers` and `models`, but may not add schema fields. `providers.<name>.api_key` is forbidden in `--set` to avoid putting secrets in shell history/process arguments; use an environment-backed credential instead. Quote the `off` reasoning-effort string in YAML and inside `--set` values (for example, `--set 'stages.desc.reasoning_effort="off"'`), because PyYAML `safe_load` may interpret bare `off` as boolean `false`.
- A selected YAML file overlays built-in defaults as a mapping. Duplicate YAML mapping keys are invalid. Lists supplied by the file replace default lists; they are not concatenated.

### A2 configuration keys and defaults

A4 added explicitly named reasoning-mapping leaves under the existing provider/model maps. A5 subsequently adds only `pipeline.backup_retention` under the existing `pipeline` map; neither step adds another config root, duplicates a key source, or changes precedence. The provider request contract remains A4's responsibility, and the backup/recovery semantics are frozen in [IMPL-A5-COMPLETED.md](IMPL-A5-COMPLETED.md).

| Key | Type / default | Contract |
| --- | --- | --- |
| `providers.<name>.base_url` | URL; required for a selected model's provider | Absolute `http` or `https` URL, including DNS/FQDN names and all IPv4/IPv6 destinations; A4 specifies the shared validation policy and Chat Completions transport. The Product Owner superseded B2’s earlier HTTP restriction; see [B2](IMPL-B2-COMPLETED.md). |
| `providers.<name>.api_key` | Optional non-empty string | Inline credential in a private operator-controlled YAML file; never log or include in results/errors. A configured empty value fails preflight as `authentication`. Mutually exclusive with `api_key_env`. |
| `providers.<name>.api_key_env` | Optional environment-variable name | Read the value at runtime; if configured, the variable must be set and non-empty or preflight fails as `authentication`. The variable name is non-secret configuration; the resolved value is never logged or returned. Mutually exclusive with `api_key`; if neither key source is configured, omit Authorization. |
| `providers.<name>.timeout_seconds` | Positive finite number; `60` | Per-request timeout in seconds; A4 may define request-specific application semantics, but not a different key or precedence. |
| `models.<name>.provider` | Provider alias; required when selected | Must reference a configured provider. |
| `models.<name>.model_id` | Non-empty string; required when selected | Provider's model identifier; no model is hard-coded as a built-in default. |
| `models.<name>.reasoning_effort` | Enum; default `default` | One of `default`, `off`, `minimal`, `low`, `medium`, `high`, `extra_high`, `max`, `ultra`. |
| `stages.desc.model` | Model alias; default `null` | Required only when `desc` is selected. |
| `stages.desc.prompt_file` | Path or `null`; default `null` | `null` selects the canonical packaged prompt. |
| `stages.desc.reasoning_effort` | Enum or `null`; default `null` | Stage value overrides model value; absent/null inherits the model value, then `default`. |
| `stages.desc.regenerate` | Boolean; default `false` | Explicitly replaces the owned description output when true. |
| `stages.json.model` | Model alias; default `null` | Required only when `json` is selected. |
| `stages.json.prompt_file` | Path or `null`; default `null` | `null` selects the A3-defined packaged prompt. |
| `stages.json.schema_file` | Path or `null`; default `null` | `null` selects the A3-defined packaged schema. |
| `stages.json.reasoning_effort` | Enum or `null`; default `null` | Stage value overrides model value; absent/null inherits the model value, then `default`. |
| `stages.json.regenerate` | Boolean; default `false` | Explicitly replaces the owned JSON output when true. |
| `stages.json.validation_retries` | Non-negative integer; default `0` | Opt-in schema-validation retries; A3 sets and enforces the finite upper bound and exact error-feedback contents. |
| `pipeline.missing_prerequisite` | `fail` or `skip`; default `fail` | For this single-image contract, applies when `json` needs a missing persisted `.desc.txt`. |
| `pipeline.on_stage_failure` | `stop` or `continue`; default `stop` | `stop` does not invoke later selected stages; `continue` invokes them and lets each stage independently evaluate its persisted inputs/outputs. |
| `pipeline.backup_retention` | `remove` or `retain`; default `remove` | A5-defined `.bak` policy after successful artifact verification. Failed writes preserve any backup regardless of this value. |
| `logging.level` | `DEBUG`, `INFO`, `WARNING`, or `ERROR`; default `WARNING` | Console diagnostics go to stderr. Single-image stage summaries always go to stdout. File/both destinations and batch summaries remain deferred to the operations slice. |

The CLI `--regenerate` sets regeneration true for every selected `desc`/`json` stage and wins over file or `--set` values. `--missing-prerequisite fail|skip` overrides `pipeline.missing_prerequisite`. Dedicated prompt/schema options override their respective `stages.*.*_file` values. Stage-specific model selection, reasoning, and the A5 backup-retention leaf can be overridden through `--set`, for example `--set stages.desc.model=local-vision` or `--set pipeline.backup_retention=retain`.

Illustrative config shape (not a B9 user-facing example):

```yaml
providers:
  local:
    base_url: http://127.0.0.1:1234/v1
    api_key_env: IMAGE_CLARUS_API_KEY
    timeout_seconds: 60
models:
  local-vision:
    provider: local
    model_id: local-vision-model
stages:
  desc:
    model: local-vision
  json:
    model: local-vision
    validation_retries: 0
pipeline:
  missing_prerequisite: fail
  on_stage_failure: stop
logging:
  level: WARNING
```

Only the environment-variable name is shown; no credential value is present. Omitted stage fields take the defaults in the table.

### Validation and selected-stage isolation

1. Parse CLI syntax and validate the single image path.
2. Resolve built-ins and at most one YAML source, then apply `--set` and dedicated overrides.
3. Validate global config shape, known fields, field types, YAML syntax/duplicate keys, and override paths before any stage executes.
4. Validate requirements for selected stages only, including the selected stage's model reference, selected model/provider relationship, required endpoint/model ID, credential source, prompt/schema path, and stage-specific reasoning value. Validate all selected-stage configuration before the first stage starts so a malformed later-stage config cannot cause an avoidable earlier-stage write. Configuration, models, providers, credentials, and prompt/schema files belonging only to unselected stages do not block execution of an unrelated selected stage.
5. Missing/invalid selected-stage configuration is reported before execution with exit `2`; a selected provider's absent required environment-backed credential is an authentication failure (exit `1`). No provider request occurs on a failed preflight.

### Stage completion and missing prerequisites

- After the HLD-required recovery check, a selected stage evaluates its own output and policy. An existing valid owned output with regeneration disabled yields `skipped` / `output_exists` before prerequisite validation; thus an existing valid JSON artifact may be skipped even if `.desc.txt` is now absent. Mere file existence is not enough to call an invalid artifact complete. Stage-specific validity rules are finalized by A3 and the implementing stage. An invalid existing artifact is not silently overwritten; report a failure unless explicit regeneration was requested.
- When generation is needed, `json` reads the persisted `.desc.txt`. It never invokes `desc` implicitly. If that prerequisite is absent, the default `fail` policy yields a `failed` stage with category `missing_prerequisite` and process exit `1`; `skip` yields a `skipped` stage and does not make a missing output look complete. The same policy is used for other genuinely missing stage prerequisites, not for an invalid CLI image path.
- Stage outputs are created when missing by default. `--regenerate` (or a true stage-specific `regenerate` key) explicitly permits replacing the corresponding complete owned artifact. Failed generation/validation is never reported as `completed`.
- With `pipeline.on_stage_failure: stop`, later selected stages receive `skipped` / `stage_not_run_after_failure`; with `continue`, the next selected stage runs only if its own persisted prerequisites and policies allow it. Any failed stage makes the overall process exit `1`, even when a later stage succeeds.

## Result, stream, and exit contract

The internal single-image result contains the resolved image path and ordered per-stage records with these fields: `stage`, `status` (`completed`, `skipped`, `failed`), `output_path` (nullable), `reason_code` (nullable), `error_category` (nullable), and a sanitized human-readable `message`. Stable skip reasons include `output_exists`, `missing_prerequisite`, `stage_not_run_after_failure`, and `interrupted`. Stable error-category IDs are `configuration`, `authentication`, `unknown_model`, `provider_unavailable`, `network_timeout`, `schema_validation`, `unsupported_image`, `corrupt_image`, `invalid_artifact`, `missing_prerequisite`, `file_io`, and `interrupted`. The result contract is internal; Slice 1 does not add a machine-readable `process --json` output mode.

- After execution, stdout contains one stable summary line for every selected stage, in registry order. Completed: `<stage>: completed — output=<JSON string for path, including quotes>`; skipped: `<stage>: skipped — reason=<reason_code>`; failed: `<stage>: failed — category=<error_category>; message=<single-line-sanitized-message>`. The path is encoded as a JSON string so unusual path characters cannot create extra lines. Use no ANSI color. Runtime diagnostics and logging go to stderr. Preflight errors produce a diagnostic on stderr and no stage-summary rows. Configuration errors identify the affected key and an actionable reason without sensitive values, full endpoint URLs, credentials, or raw exception text. Messages and paths must not reveal credentials.
- `0`: all attempted stages completed or skipped without any failure.
- `1`: one or more stage failures, including missing prerequisite under `fail`, authentication/provider/image/schema/file errors.
- `2`: CLI usage error, invalid image path, invalid/global/selected-stage configuration, or unavailable installed-version metadata.
- `3`: the `search` not-implemented result.
- `130`: graceful stop after `SIGINT`; `143`: graceful stop after `SIGTERM`. Do not start another selected stage after the signal is observed. Cancel an in-flight provider request when safe; if a safe-write operation has started, let it reach its defined safe boundary before exiting. A stage with no completed artifact at interruption is reported `skipped` / `interrupted`; a write that safely completes before exit remains `completed`. Remaining selected stages are `skipped` / `interrupted`. The signal exit code takes precedence over ordinary stage-failure aggregation. `SIGKILL` cannot be handled and remains covered by A5 recovery guarantees.

## Examples

```text
image-clarus process ./photos/peppers.jpg
image-clarus process ./photos/peppers.jpg --stages desc
image-clarus process ./photos/peppers.jpg --stages json
image-clarus process ./photos/peppers.jpg --stages desc,json
image-clarus process ./photos/peppers.jpg --config ./config.yaml
image-clarus process ./photos/peppers.jpg --desc-prompt ./prompts/description.txt --json-prompt ./prompts/structure.txt --json-schema ./schemas/structure.json
image-clarus process ./photos/peppers.jpg --regenerate
image-clarus process ./photos/peppers.jpg --set stages.desc.model=local-vision --missing-prerequisite skip
```

The `json`-only example assumes `./photos/peppers.jpg.desc.txt` already exists. The path overrides are relative to the current working directory. Examples document the contract; they were not executed because implementation has not started.

## Decisions and alternatives

- Selected one-image positional input with comma-separated stage IDs and an ordered fixed registry; rejected implicit prerequisite expansion and filesystem traversal because they conflict with the accepted stage contract and Slice 1 boundary.
- Selected one discovered YAML file (user before system) plus built-ins and layered CLI overrides; rejected user/system merging to preserve deterministic configuration and the REQ's no-merge rule.
- Selected typed YAML values for `--set` because YAML is the established config format; rejected untyped string-only overrides, which would make booleans, counts, and lists ambiguous.
- Selected dedicated prompt/schema path flags and one explicit regeneration flag; model selection and other supported values use `--set`. Rejected CLI credential values to avoid shell-history/process-list disclosure; retain inline YAML or named environment-variable sources.
- Selected `stop` as the single-image failure default and `continue` as the configurable alternative; an `abort_run` action would duplicate `stop` when the command handles one image only.
- Kept `search` help-only with a deterministic stub status, and kept human-readable stage summaries separate from diagnostics; rejected search implementation and a new result-output mode as out of Slice 1.
- Selected conventional `130`/`143` signal statuses while preserving the REQ's safe-cancel and safe-write boundary; `SIGKILL` remains unrecoverable during execution and is not misrepresented as graceful shutdown.

## Acceptance

- [x] A user can tell exactly how to process one image, select stages, override config, regenerate, and interpret each result/exit status, including graceful-stop signals.
- [x] `image-clarus --version` returns exactly `image-clarus 0.1.0` for the initial package, uses the authoritative source, and requires no runtime configuration or provider access.
- [x] `json`-only execution never silently runs `desc`; absent description follows the approved single-file policy.
- [x] Configuration search/selection, no-merge behavior, precedence, stage validation, and path resolution are testable without relying on the host user's real config.
- [x] Top-level help, `process --help`, and `search --help` are part of Slice 1; executing `search` reports not implemented with exit `3`, and no search matching leaks into Slice 1.
- [x] [IMPL-A2-COMPLETED.md](IMPL-A2-COMPLETED.md) is complete and linked.

## Verification and environment notes

- This is a `[DESIGN]` step. No production/test files were created or modified, and no application tests, typechecks, or builds were run.
- The plan's exact A2 acceptance decisions and its previously pending command/result/config details are recorded in this completion artifact and cross-linked from the plan.
- C2 owns later runtime verification of signal stop behavior. B2/B8/C1 own automated configuration, CLI, result, and exit-code tests using temporary config roots and local stubs; A2 does not claim those tests have run.
- Step A3 subsequently froze the exact JSON prompt/schema content, JSON artifact validity, schema versioning, the exact persisted-description input fingerprint, create-only skip behavior across selected schema changes, and finite upper bound/error-feedback semantics for `validation_retries`; see [IMPL-A3-COMPLETED.md](IMPL-A3-COMPLETED.md). Step A4 subsequently froze Chat Completions request/response details and provider-specific capability/error mapping; see [IMPL-A4-COMPLETED.md](IMPL-A4-COMPLETED.md). Step A5 has since frozen safe-write boundaries, backup retention, recovery, and interruption/fault cases; see [IMPL-A5-COMPLETED.md](IMPL-A5-COMPLETED.md). These are defined by their named Phase A steps, not left for Phase B implementers to guess.

## Follow-ups

- At A2 closeout, Step A3 was next and A3–A6 were unchecked. Steps A3–A5 have since completed; Erik accepted A3 as documented during A6, and the Phase A readiness gate has passed. A5's later `pipeline.backup_retention` addition is documented above and in [IMPL-A5-COMPLETED.md](IMPL-A5-COMPLETED.md). Phase B/C implementation remains unstarted.
