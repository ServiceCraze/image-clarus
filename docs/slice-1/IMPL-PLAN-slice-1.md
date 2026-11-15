# Slice 1 Implementation Plan

> **For Hermes / implementers:** Execute this plan by phase. Phase A is a design and contract-freeze gate; do not begin production-code work until its acceptance checks pass. For every completed step, create the linked `IMPL-<StepId>-COMPLETED.md` record beside this plan, list files created/updated/removed, record `Scope deviations: None` or an approved deviation with its carry-forward link, and make the same acceptance checkoffs in this plan and the step record. Reviewers should read the step record first. Every code step uses test-first RED → GREEN → REFACTOR; capture the expected failing test before implementation.

**Status:** Candidate — Phase A in progress; Steps A1–A3 design artifacts complete; A3 Product Owner decision pending; implementation not started
**Goal:** Deliver a buildable single-image `desc` + `json` CLI pipeline, with independently selectable stages, configurable model/configuration inputs, schema-validated structured metadata with provenance, and recoverable sidecar writes.
**Architecture:** A small Python CLI resolves configuration once and passes the complete resolved configuration to an ordered stage coordinator. `desc` writes the authoritative `.desc.txt` handoff; `json` reads that persisted artifact and writes `.desc.json`. Shared provider and artifact services handle HTTP communication and safe writes; stages retain ownership of their own input, completion, and policy decisions.
**Tech stack:** Python 3.12+ (Python 3.13 development baseline, pinned in `.python-version`); Hatchling with static project metadata in `pyproject.toml` and committed `uv.lock`; stdlib `argparse`; PyYAML; `jsonschema`; synchronous `httpx`; pytest and Ruff as development tools; `uv` for environment and lock management. A1 records selection separately from actual tool availability.
**Versioning:** Application releases use Semantic Versioning. Slice 1 starts at `0.1.0` and remains on the `0.1.x` line. The generated metadata schema is versioned independently from the application.

---

## Purpose and scope

Slice 1 is the first buildable delivery slice for Image Clarus. It must process one image at a time and provide useful description and structured metadata outputs. The two stages are independently invocable and composable through persisted sidecars; `json` must not depend on an in-memory description produced earlier in the same process.

This plan follows the project's slice/phase hierarchy: **Slice 1** is the delivery unit; Phase A, Phase B, Phase C, and their step IDs belong only to this plan. The planning checklist is adapted to this standalone Python project: retain ordered phases, exact summary/detail step matching, categorized outputs, objective acceptance, per-step completion records, and explicit TDD; do not import Service Craze, COMMS, frontend/backend, tenant, UI, or JavaScript workspace gates.

## Scope authority and locked constraints

The source of truth is the [REQ](../REQ-image-clarus.md), [HLD](../HLD-image-clarus.md), and the existing [description prompt](../../prompts/image-description.txt). Preserve these decisions throughout planning and implementation:

- Slice 1 contains single-image `desc` and `json` processing; both stages can be selected independently or together. The `json` stage consumes the persisted `.desc.txt` file. Selecting only `json` does not automatically run `desc`.
- Sidecars are adjacent to the source and use the complete image filename before the suffix: `<image>.desc.txt` and `<image>.desc.json`. Do not modify the source image.
- With no stage selection, run all stages registered in this slice, in registry order (`desc`, then `json`). Create missing outputs by default; replace an existing owned output only after explicit regeneration is selected.
- The complete resolved application configuration is passed to each stage. The coordinator must not construct stage-specific configuration objects or own stage-specific prerequisite/overwrite rules.
- Initial model transport is OpenAI-compatible Chat Completions over HTTP. Named providers/models and independent model selection for `desc` and `json` are required. Do not hard-code a specific model. Credentials may be direct or environment-variable-backed and must never appear in logs, errors, test evidence, or committed examples.
- The built-in description prompt remains exactly `Fully describe and explain everything about this image.` No extra instruction may be appended to that default prompt.
- Application releases use Semantic Versioning; Slice 1 starts at `0.1.0`, and Slice 1 releases stay on the `0.1.x` line. Static `[project].version` in `pyproject.toml` is the sole authoritative source; the CLI reads installed distribution metadata with stdlib `importlib.metadata` and must not maintain a duplicate version constant. A2 freezes `--version` output behavior.
- Phase A must define the initial JSON schema, JSON-generation prompt, and provenance contract, including custom-schema behavior, before JSON implementation begins.
- JSON metadata schema versioning is independent of application versioning; A3 defines its marker, initial value, and evolution/replacement rules.
- Built-in retry count is zero. Optional schema-validation retry is opt-in and must be bounded. Invalid or incomplete outputs are not marked complete.
- Use a shared safe-write/recovery service. If the destination is absent and `.bak` exists, restore the backup; if both exist, the destination is authoritative. Temporary files are disposable, not recovery sources. Do not add application-level locks; last successful replacement wins and lost concurrent updates remain an accepted limitation.
- Description and JSON generation require no external executable beyond Python. ExifTool, XMP work, and digiKam validation are outside Slice 1.
- Required test platform is Linux. Do not promise an exhaustive filesystem or operating-system matrix. Public fixtures/examples must not contain identifying photo, location, camera, lens, serial-number, owner, or device metadata.

## In scope

- Installable Python package and `image-clarus` console entry point.
- One-image `process` invocation, the accepted top-level, `process`, and `search` help surfaces, and top-level `image-clarus --version`. Search execution returns an explicit not-implemented result in Slice 1; search matching is not implemented.
- YAML configuration discovery and explicit configuration selection; built-in defaults; CLI override precedence; independent prompt/schema path overrides; selected-stage validation.
- Named providers/models and the OpenAI-compatible adapter needed by both model-driven stages.
- Ordered `desc` and `json` stage registry/coordinator, per-stage result reporting, and no automatic prerequisite expansion.
- Description output, JSON-generation prompt, replaceable built-in JSON schema, schema validation, provenance, and optional configured validation retry.
- Shared safe writing, backup/recovery behavior, permission handling where feasible, and clear single-image failure reporting.
- Automated unit/integration tests, Linux validation, a sanitized example configuration, and updated user-facing installation/usage documentation.

## Out of scope and carry-forward ledger

No scope deviations are approved. These capabilities are outside Slice 1 by the REQ/HLD roadmap, not silently dropped from the end-state product:

| Capability | Slice 1 disposition | Carry-forward |
| --- | --- | --- |
| XMP generation, ExifTool integration, digiKam mappings, title/description/tag policies | Out of scope | XMP slice plan; preserve REQ/HLD field-ownership and fixture-sanitization rules |
| Directory, glob, recursive discovery, multi-image batches, batch summaries and run bounds | Out of scope | Selection/operations slice plan |
| Search matching or machine-readable search results | Out of scope | Deterministic-search slice plan |
| Search command/help surface | In scope: register `search`, provide `image-clarus search --help`, and report not implemented when executed | Search matching remains in the deterministic-search slice |
| Built-in scheduler, database, persistent job queue, embeddings/semantic search | Out of scope / future goal | Remain explicit non-goals unless a later approved slice changes them |
| Additional provider protocols, additional XMP backends, non-digiKam metadata writes | Out of scope | Later extension plans only |
| General retry/backoff policy, batch continuation/aggregation, configurable file logging, external run-window controls | Out of scope except zero-retry behavior and single-image error/result reporting needed here | Carry to the operational/batch slice; do not let this block Slice 1 |

## Requirements-to-slice traceability

This matrix allocates the REQ's end-state requirements without expanding Slice 1. Only behavior explicitly assigned to Slice 1 becomes acceptance scope here; later-slice and future-goal entries remain carry-forward work for their own plans. REQ references use exact heading names, not file line numbers, so they remain stable as the document changes.

| REQ area | Slice 1 allocation | Candidate Release 1 delivery (later slices; not committed) | Later goal | Prerequisite and verification evidence |
| --- | --- | --- | --- | --- |
| Product purpose, platform, runtime, packaging and license (Purpose; Guiding requirements; Runtime and external dependencies; Delivery approach and scope; Known non-goals of the initial implementation) | Python 3.12+, Python 3.13 dev baseline, `uv`, locked package, initial app version `0.1.0` on the SemVer `0.1.x` line, top-level `--version`; confirm Apache-2.0 metadata/notices | Package/publish only after the selected release scope is implemented and verified | Non-Linux portability is desirable; exhaustive cross-platform CI is not required | A1/A2/B1 freeze and exercise version source/behavior; C3 verifies installed CLI and runtime support |
| Stage outputs, source integrity, create-only defaults, and explicit regeneration (Guiding requirements; Processing stages and artifacts) | `desc`/`json` sidecars for one image; source unchanged; skip existing outputs unless explicitly regenerated | XMP field-specific updates only if the XMP slice is included in Release 1 | — | A2 contract; B6–B8; C1–C2 test exact paths, skip/regenerate, and image integrity |
| Input selection and traversal (Input selection and traversal) | One image path only | Directory, pattern and recursive selection are later-slice candidates; Release 1 inclusion is uncommitted | Exclusion patterns and expanded format support are later goals | Later selection plan defines traversal, allowlist, corrupt/unsupported-image and eligibility tests; C1 covers one image |
| Stage prerequisites and composition (Stage dependencies) | `json` requires valid persisted `.desc.txt`; explicit `json` never auto-runs `desc`; single-image missing-input policy is frozen in Phase A | Directory/pattern skip-and-continue behavior only with the selection/batch slice | — | A2; B4/B7/B8; C1 prerequisite and independent-stage matrix |
| Providers, prompts, model selection, reasoning and schema retry (Model providers and prompts) | OpenAI-compatible HTTP adapter; named per-stage models; exact description prompt; JSON prompt/schema overrides; reasoning and bounded opt-in validation retry | Additional adapters only if selected for Release 1 | Expanded provider protocols are a later goal | A3–A4; B3/B6/B7; C1/C4 local-stub and authorized-provider evidence |
| Structured metadata and provenance (Structured metadata expectations) | Default schema covers required discovery fields; full custom-schema replacement, required provenance, and schema-version identification independent of app version are defined | Schema evolution follows the independent version/compatibility policy frozen in A3 | — | A3 gate before JSON code; B7; C1 schema-positive/negative/version-marker tests |
| XMP/digiKam integration and metadata preservation (XMP metadata integration) | Not implemented | ExifTool backend, digiKam mappings, `ai` tag hierarchy/policies, title/description defaults, unrelated-data preservation and round-trip tests are a later slice; Release 1 inclusion is uncommitted | Optional non-digiKam representations remain separately configurable | XMP plan defines mappings and sanitized fixtures; do not infer them in Slice 1 |
| Search (Search) | Register `search`; top-level and `search --help`; execution reports not implemented | Deterministic case-insensitive text/JSON matching, human- and machine-readable results, and shared traversal are a later slice; Release 1 inclusion is uncommitted | Embeddings are an explicit future goal and not a Release 1 requirement | B1/B8/C3 verify stub; search plan defines matching, traversal and result tests |
| Configuration and precedence (Configuration and precedence) | One selected YAML file, built-in defaults, CLI precedence, prompt/schema overrides, Linux discovery, and OS-aware path resolution without creating system directories | Add optional-stage configuration only when the owning stage is introduced | — | A2; B2/B8; C1 config matrix with temporary roots and platform-path unit tests |
| Failures, retries, logging and summaries (Failure policies, retries and logging) | Clear single-image results/errors and nonzero failures; zero request retries; bounded opt-in schema retry; credentials excluded from logs | Batch category actions, per-file continuation, summaries and configurable destinations belong to later operational work; Release 1 inclusion is uncommitted | General retry/backoff policy remains optional beyond the schema-retry requirement | A2/A4; B2–B8; C1/C2/C4; later batch plan owns aggregate exit behavior |
| External scheduling, stop, resume and concurrency (External scheduling, stop and resume) | No internal scheduler or queue; independent CLI processes and lock-free last-write-wins semantics are exercised for `desc`/`json` | Multi-image rescan/resume, graceful batch stop and run bounds are later operational-slice candidates; Release 1 inclusion is uncommitted | A built-in scheduler remains a non-goal | C1/C2 subprocess tests; later operational plan tests signal/run-bound behavior |
| Safe writes and recovery (Safe-write requirements) | Shared service for `.desc.txt` and `.desc.json`, backup/recovery and failure handling; test representative available Linux filesystems | Reuse the service for XMP if that stage is added | Expand filesystem/OS coverage only when evidence warrants it; no exhaustive matrix | A5; B5; C2 fault injection and separate-process writer test; C3 records actual filesystem/interpreter |
| Requirements-to-design handoff (Requirements-to-design handoff) | Phase A resolves Slice 1 CLI/config/provider/schema/provenance/safe-write decisions before implementation | XMP mappings, selection/search syntax and batch controls belong to their own plans before implementation | — | A1–A6 readiness gate; every later plan maps assigned REQ obligations to tests |

## Confirmed project layout

Step A1 confirms the package/module/test layout. A3 freezes the JSON prompt/schema paths shown below. `pyproject.toml` owns static package metadata, the version, dependency declarations, Hatchling configuration, and the console entry point. Hatchling maps the existing root-level prompt and later schema assets into package resources without maintaining duplicate source files. `uv.lock` is generated in B1 and must be committed by the repository owner. `examples/config.yaml` is created only in B9, after A2 freezes the config keys.

```text
.python-version                     # 3.13 development baseline
pyproject.toml
uv.lock
src/image_clarus/
  __init__.py
  __main__.py
  cli.py
  config.py
  results.py
  pipeline.py
  artifacts.py
  resources.py
  providers/
    __init__.py
    openai_compatible.py
  stages/
    __init__.py
    description.py
    structure.py
prompts/
  image-description.txt              # existing; preserve exact text
  image-structure.txt                # A3-frozen default JSON-generation prompt
schemas/
  image-structure.schema.json        # A3-frozen built-in metadata-payload schema
examples/
  config.yaml                        # created in B9 after A2; sanitized env-var reference only
tests/
  unit/
  integration/
  fixtures/                          # synthetic config/schema/text/provider data only
```

Module ownership is fixed as follows: `__main__.py` delegates to `cli.main`; `cli.py` owns `argparse` construction and dispatch (A2 owns the exact command contract); `config.py` resolves and validates configuration; `results.py` defines shared outcomes; `pipeline.py` owns the ordered built-in stage registry and coordinator; `artifacts.py` owns safe sidecar access/recovery; `resources.py` locates built-in prompts/schemas from source-tree paths or with stdlib `importlib.resources`; `providers/openai_compatible.py` owns synchronous HTTP transport; and `stages/description.py` / `stages/structure.py` own `desc` / `json`. `__init__.py` contains no separately maintained version constant.

Keep the existing `prompts/image-description.txt` as the canonical source asset. Hatchling maps it to `image_clarus/resources/prompts/image-description.txt` in B1. A3 freezes `prompts/image-structure.txt` and `schemas/image-structure.schema.json`; B7 adds mappings from those root paths into the corresponding `image_clarus/resources/prompts/` and `image_clarus/resources/schemas/` subdirectories. `resources.py` prefers package resources when installed and supports the repository-root file during source development. User override resolution remains part of A2, not `resources.py`. Use synthetic YAML/schema/description/provider-response fixtures; create image inputs under pytest `tmp_path` without real photos or identifying metadata. The sanitized config example is deferred to B9.

Test modules are `tests/unit/test_cli.py`, `test_resources.py`, `test_config.py`, `test_results.py`, `test_pipeline.py`, `test_artifacts.py`, `test_openai_compatible.py`, `test_description_stage.py`, `test_structure_stage.py`, and `tests/integration/test_single_image_pipeline.py`. Do not add a plugin framework, database, scheduler, type checker, coverage gate, image-processing dependency, or other unrequested architecture.

## Implementer and reviewer protocol

1. Complete Phase A before changing production code. Record each design decision, alternatives considered, rationale, contract examples, and acceptance in its step completion record.
2. Every CODE/TEST step follows RED → GREEN → REFACTOR: add a focused behavior test, run it and observe the intended failure, implement the minimum behavior, rerun the focused test, then run the relevant regression suite. Never write production code first and add tests afterward.
3. Use synthetic/non-identifying image fixtures. Use a local HTTP stub or test transport for automated provider tests; tests must not require a live API key or send private images to a remote endpoint.
4. Keep API keys and credential values out of configuration examples, logs, stack traces, completion records, and screenshots. For manual provider checks, use an operator-controlled environment variable and a synthetic image; do not make an external request without explicit operator authorization of endpoint, model, and any cost/data transfer.
5. Each completed step creates `docs/slice-1/IMPL-<StepId>-COMPLETED.md`. Required fields: step title/status, scope-deviation line, exact files created/updated/removed, summary, and tests/evidence. Link that record in the step's Outputs. Do not pre-create completion records for unexecuted steps.
6. Mirror every acceptance checkoff in the detailed step and this plan's summary checklist. Keep the overall status, phase summary, detailed acceptance rows, and completion records consistent. A completion record is evidence, not automatic proof that every acceptance item passed.
7. If implementation evidence requires a scope or architecture change, stop at the boundary and raise it for Product Owner decision before changing this plan or proceeding. Do not silently narrow Slice 1 or pull later-slice features forward.

## Phase summary checklist

### Phase A — Discovery and contract freeze

- [x] Step A1 — Confirm package layout, runtime, and development tools [DESIGN]
- [x] Step A2 — Freeze the single-image CLI, configuration, and result contracts [DESIGN]
- [x] Step A3 — Freeze the JSON schema, prompt, and provenance contract [DESIGN]
- [ ] Step A4 — Freeze the provider request and security contract [DESIGN]
- [ ] Step A5 — Freeze safe-write, recovery, and concurrency details [DESIGN]
- [ ] Step A6 — Pass the Phase A readiness gate [DESIGN]

### Phase B — Build the single-image pipeline

- [ ] Step B1 — Bootstrap the installable Python package and test harness [CODE/TEST]
- [ ] Step B2 — Implement configuration resolution and precedence [CODE/TEST]
- [ ] Step B3 — Implement the OpenAI-compatible provider adapter [CODE/TEST]
- [ ] Step B4 — Implement stage results, registry, and coordinator [CODE/TEST]
- [ ] Step B5 — Implement the recoverable sidecar artifact service [CODE/TEST]
- [ ] Step B6 — Implement the description stage [CODE/TEST]
- [ ] Step B7 — Implement the structured JSON stage [CODE/TEST]
- [ ] Step B8 — Wire the single-image `process` command [CODE/TEST]
- [ ] Step B9 — Document Slice 1 installation, configuration, and use [DOCS/TEST]

### Phase C — Verify and close Slice 1

- [ ] Step C1 — Verify independent stage execution and persisted handoff [TEST]
- [ ] Step C2 — Verify failure recovery, source integrity, and credential hygiene [TEST]
- [ ] Step C3 — Run Linux package and quality gates [TEST]
- [ ] Step C4 — Perform an authorized real-provider quality smoke test [MANUAL/TEST]
- [ ] Step C5 — Reconcile acceptance evidence and close Slice 1 [DOCS/TEST]

---

# Detailed steps

## Phase A — Discovery and contract freeze

**Phase A exit rule:** All Phase A decisions below are recorded and accepted in completion artifacts, all planned paths/commands are exact, the accepted top-level/`process`/`search` help surfaces, top-level `--version` output, application SemVer/version-source contract, independent schema-version contract, and the not-implemented `search` result are specified, and this plan is updated before Phase B starts. Phase A produces design evidence only; no production code is changed.

### Step A1 — Confirm package layout, runtime, and development tools [DESIGN]

**Goal:** Lock the greenfield Python package structure, application version source, dependency set, and reproducible Linux development/verification commands.

**Inputs:**
- `docs/REQ-image-clarus.md` — runtime/dependency requirements and Slice 1 boundary
- `docs/HLD-image-clarus.md` — component boundaries and open implementation decisions
- `README.md`
- `prompts/image-description.txt`
- Current repository tree and available Python/`uv` toolchain

**Actions:**
1. Confirm the `src/image_clarus/` and `tests/` layout and module ownership. Keep `prompts/image-description.txt` canonical and package it with Hatchling force-include; defer `examples/config.yaml` to B9 after A2 freezes configuration keys.
2. Select stdlib `argparse` for CLI parsing (no added dependency), PyYAML for YAML, `jsonschema` for schema validation, and synchronous `httpx` for HTTP. Do not add a generic provider/plugin framework.
3. Select pytest and Ruff. Use `uv run --locked --extra dev pytest <target>` for targeted tests, `uv run --locked --extra dev pytest` for the suite, `uv run --locked --extra dev ruff check .`, and `uv run --locked --extra dev ruff format --check .`; format only when required with `uv run --locked --extra dev ruff format .`. Do not add a type checker or coverage gate.
4. Select Hatchling as the build backend; declare `requires-python = ">=3.12"`, pin development to Python 3.13 in `.python-version`, require Linux validation, use `uv` with a committed `uv.lock`, and set Apache-2.0 metadata/license-file references consistent with `LICENSE`.
5. Establish application versioning: Semantic Versioning, initial Slice 1 package version `0.1.0`, and the `0.1.x` line for Slice 1 releases. Make static `[project].version` in `pyproject.toml` authoritative; obtain installed version through stdlib `importlib.metadata` and maintain no duplicate version constant.
6. Record exact dependency names, supported Python constraints, package/entry-point names, built-in asset packaging, synthetic fixture strategy, and all setup, test, quality, and build commands used by later steps.

**Outputs:**
- Decision record and final package/tooling contract in [IMPL-A1-COMPLETED.md](IMPL-A1-COMPLETED.md)
- This plan updated with the initial version, authoritative version source, final paths/module ownership, resource packaging, dependencies, fixture strategy, and commands

**Acceptance:**
- [x] Runtime, development, and test dependencies are explicitly selected with rationale; no choice is presented as already installed.
- [x] Package layout, module ownership, built-in resource lookup, and console-script name are exact and consistent with `image-clarus`.
- [x] Initial Slice 1 application version is `0.1.0`, the Slice 1 version line is `0.1.x`, and the sole authoritative package-version source is recorded.
- [x] Python 3.12+ support, Python 3.13 baseline, Linux validation, `uv`, and committed lockfile are preserved.
- [x] No extra architecture or dependency is introduced without a Slice 1 requirement.
- [x] `IMPL-A1-COMPLETED.md` exists, lists files created/updated/removed, and is linked above.

### Step A2 — Freeze the single-image CLI, configuration, and result contracts [DESIGN]

**Goal:** Make the Slice 1 command surface, version display, resolution rules, stage semantics, single-image outcomes, and process exit behavior unambiguous before implementation.

**Inputs:**
- `docs/REQ-image-clarus.md` — stages, config precedence, failures/retries, single-image prerequisite policy
- `docs/HLD-image-clarus.md` §§3–5, 8, 10 — stage independence, accepted CLI conventions, and Slice 1 boundary
- Step A1's package/tooling decision

**Actions:**
1. Specify the exact one-image `process` syntax, positional/option grammar, repeatability, conflicts, help text contract, and how the image path is validated. Preserve the accepted option names `--config`, `--stages`, and `--set`; decide any dedicated overrides only where needed.
2. Specify `--stages` parsing and defaults: absent means the registered Slice 1 stages in registry order; explicit `desc` or `json` selection runs only the named stages; selection never expands prerequisites.
3. Preserve the accepted command surface: register the top-level `search` subcommand and provide `image-clarus search --help`. A non-help `search` invocation reports `search is not implemented in Slice 1` and exits nonzero using the not-implemented status selected in this step. Do not implement search matching, sidecar traversal, or model calls.
4. Define configuration discovery and precedence exactly: built-in defaults; explicit config loads only that file and disables discovery; otherwise choose at most one user-level file before system-level on Linux; no implicit merge; CLI overrides highest. Define relative-path resolution for config, prompt, and schema files and which values can be overridden by `--set` versus dedicated flags.
5. Define the configuration key schema for providers, named models, stage model selection, prompts/schema paths, reasoning effort, regeneration, validation retry, missing-prerequisite policy, logging needed for single-image results, and credentials/environment variables. Validate global settings before stage settings; unused stage credentials/models must not block an unrelated selected stage.
6. Define stage outcomes (`completed`, `skipped`, `failed` or an explicitly justified equivalent), user-visible single-image result format, failure categories, default zero retries, single-image missing-`.desc.txt` behavior, continuation behavior after a stage failure, exit-code mapping, and graceful-stop status/behavior for SIGINT and SIGTERM. Ensure a failed/invalid output is never reported as complete.
7. Record CLI examples for `desc` only, `json` only with an existing description, combined `desc,json`, explicit config, prompt/schema overrides, and regeneration. Label any examples as illustrative until the grammar is frozen.
8. Freeze top-level `image-clarus --version`: print exactly one line, `image-clarus 0.1.0`, to stdout with success status; it must work without loading configuration, credentials, provider access, or an image. For later `0.1.x` releases, the displayed version must come from A1's authoritative package-version source.

**Outputs:**
- CLI/config/result contract, examples, and any decisions/deferred items in [IMPL-A2-COMPLETED.md](IMPL-A2-COMPLETED.md)
- This plan updated with final command/version examples and the fixed `search` stub response/status

**Frozen command and result summary:**

```text
image-clarus --help
image-clarus --version
image-clarus process --help
image-clarus process IMAGE [--config FILE] [--stages STAGE[,STAGE...]] [--set PATH=VALUE]... [--desc-prompt FILE] [--json-prompt FILE] [--json-schema FILE] [--regenerate] [--missing-prerequisite {fail,skip}]
image-clarus search --help
image-clarus search
```

- No `--stages` selects `desc,json` in registry order. Explicit selection runs only those stages; `json` never expands to `desc`.
- `image-clarus --version` prints exactly `image-clarus 0.1.0` on stdout, exits `0`, and reads the A1 authoritative version without loading runtime configuration.
- `image-clarus search` prints exactly `search is not implemented in Slice 1` to stderr and exits `3`; `search --help` is available, with no matching, traversal, or model calls.
- Single-image stage results are `completed`, `skipped`, or `failed`; skipped work does not fail the process. Exit statuses are `0` success/skips, `1` stage failure, `2` usage/config/input error, `3` not-implemented search, `130` SIGINT, and `143` SIGTERM. The completion record specifies streams, config keys/precedence, paths, and signal/write boundaries.

**Acceptance:**
- [x] A user can tell exactly how to process one image, select stages, override config, regenerate, and interpret each result/exit status, including graceful-stop signals.
- [x] `image-clarus --version` returns exactly `image-clarus 0.1.0` for the initial package, uses the authoritative source, and requires no runtime configuration or provider access.
- [x] `json`-only execution never silently runs `desc`; absent description follows the approved single-file policy.
- [x] Configuration search/selection, no-merge behavior, precedence, stage validation, and path resolution are testable without relying on the host user's real config.
- [x] Top-level help, `process --help`, and `search --help` are part of Slice 1; executing `search` reports not implemented with exit status `3`. Do not implement search matching, sidecar traversal, or model calls.
- [x] [IMPL-A2-COMPLETED.md](IMPL-A2-COMPLETED.md) is complete and linked.

### Step A3 — Freeze the JSON schema, prompt, and provenance contract [DESIGN]

**Goal:** Define the initial structured artifact and independent schema-version contract completely enough to implement and test JSON generation without inventing field semantics.

**Inputs:**
- `docs/REQ-image-clarus.md` §§7–8 — schema and semantic coverage requirements
- `docs/HLD-image-clarus.md` §4.4 and §10.3 — Phase A prerequisite and replacement-schema boundary
- Step A2's config/result contract

**Actions:**
1. Specify exact default JSON prompt text and file path; ensure it consumes the persisted description and asks for valid output matching the selected schema.
2. Specify the built-in metadata payload's exact field names/types/requiredness for subjects/objects, actions, setting/context, useful visual characteristics, and searchable keywords/tags. Specify provenance in the application-owned envelope. Keep the contract useful for discovery and later XMP mapping without designing XMP behavior now.
3. Decide whether provenance is represented inside the replaceable user schema, in an application-owned envelope, or through another explicit mechanism. Define how full schema replacement works without silently losing the required model/prompt provenance.
4. Define the provenance fields and stable values captured (selected provider alias, model alias and model ID, prompt identity and exact-content SHA-256); exclude credentials, authorization headers, local paths, and secret-bearing URLs.
5. Use the A2 key `stages.json.validation_retries` with default zero and a finite upper bound of two additional attempts; define normalized parse/schema feedback, strict JSON parsing, Unicode/serialization, envelope and payload validation, extra-property behavior, and fenced/prose-wrapped output handling.
6. Establish a schema-versioning convention independent of application SemVer: freeze the initial schema version, how each generated `.desc.json` identifies that contract, compatibility/evolution rules, and how full custom-schema replacement identifies its version. Never infer schema version from the application version.
7. Provide a small synthetic description, example structured JSON, and positive/negative schema-validation cases, including schema-version identification. Do not include a real photograph or personal metadata.

**A3 frozen contract:** The canonical prompt and schema sources are `prompts/image-structure.txt` and `schemas/image-structure.schema.json`; B7 packages these without duplicate source copies. The Draft 2020-12 built-in payload is a closed object requiring `subjects` (unique non-empty-string array), `objects` (same), `actions` (same), `setting` (`type` and `context` strings), `visual_characteristics` (`colors` array plus `composition`, `lighting`, and `visual_style` strings), and `keywords` (same array rules). All fields are required; their strings/arrays may be empty where unsupported, and built-in objects reject extra properties. The app owns a fixed `format_version: 1` envelope with `schema_id`, `schema_version`, `provenance` (`provider_alias`, `model_alias`, `model_id`, `prompt_id`, `prompt_sha256`), and validated `metadata`; the exact closed envelope schema is in the A3 record and is an application constant, not a user asset. `format_version` is a separate major-only envelope contract; any envelope schema change increments it, independently of payload-schema SemVer. Custom schemas wholly replace the payload schema only, require an object root, allow same-document references only, and use the SHA-256 of exact schema bytes as their independent identity/version. The built-in schema starts at `1.0.0`. Strict parsing rejects fences/prose, duplicate keys, invalid Unicode, and non-finite values. `stages.json.validation_retries` accepts only non-boolean integers 0–2 and returns normalized, sorted feedback without raw output or validator prose. B7 must test valid/invalid payloads, fixed-envelope validation/versioning, full custom replacement with retained envelope/provenance, schema preflight without a provider call, strict parsing and retries, exact prompt hash, Unicode, deterministic serialization, and packaged-resource lookup; the completion record contains the synthetic examples and exact feedback/compatibility rules.

**Product Owner gate:** Erik's review of this A3 design remains pending. The A3 design artifact is complete, but A6 remains unchecked until the Phase A decisions are accepted or revised; this does not authorize Phase B implementation.

**Outputs:**
- Reviewed JSON/schema-version contract and examples in [IMPL-A3-COMPLETED.md](IMPL-A3-COMPLETED.md)
- This plan updated with final schema/prompt paths, fields, and test assertions

**Acceptance:**
- [x] Schema, prompt, and provenance are defined before any JSON production-code step begins.
- [x] Every required semantic category from the REQ is represented and testable.
- [x] Full custom-schema replacement and provenance interaction have an explicit, non-contradictory rule.
- [x] The generated metadata schema has an independent, identified version and explicit compatibility/evolution rules, including custom-schema behavior.
- [x] No secrets or identifying photo/device data can enter the public example contract.
- [x] [IMPL-A3-COMPLETED.md](IMPL-A3-COMPLETED.md) is complete and linked.

### Step A4 — Freeze the provider request and security contract [DESIGN]

**Goal:** Define the OpenAI-compatible HTTP boundary, per-stage model behavior, and provider capability/error semantics for both stages.

**Inputs:**
- `docs/REQ-image-clarus.md` §§7, 14–15
- `docs/HLD-image-clarus.md` §§2.1, 4.2–4.3
- Steps A1–A3 decisions

**Actions:**
1. Use A2's `providers.<name>.base_url`, `timeout_seconds`, `api_key`/`api_key_env`, and `models.<name>.provider`/`model_id` keys. Freeze their OpenAI-compatible request semantics and, if required, add explicitly named generation-setting leaves under the existing provider/model/stage maps; do not add another config root, rename A2 fields, or duplicate key sources. Keep credentials out of provider result objects and logs.
2. Define the supported OpenAI-compatible Chat Completions request shape for description image input and structured JSON generation. Use a local test server/transport to assert request and response handling.
3. Use the A2 `stages.<stage>.model` references for independent or shared model selection. Define provider-independent behavior for a shared versus distinct provider/model and model-default versus stage-specific generation settings.
4. Use A2's generic reasoning-effort values and stage-over-model precedence; record the provider mapping source and error behavior for unsupported options. Do not silently send unsupported capabilities or silently fall back.
5. Specify authentication, HTTP status/error mapping, timeouts, response parsing, malformed/empty response handling, and redaction requirements. Built-in request retry count stays zero; do not include broad retry/backoff behavior.
6. Specify automated tests using a local HTTP stub, including image payload, prompt, model ID, structured output request, auth header presence without disclosure, timeout, auth failure, provider error, and capability mismatch.

**Outputs:**
- Provider contract, request/response examples, error table, and security notes in [IMPL-A4-COMPLETED.md](IMPL-A4-COMPLETED.md)
- This plan updated with exact request/response test fixtures and dependency/API choices

**Acceptance:**
- [ ] Both stages can use independent named models and can share a provider/model without coordinator-specific configuration objects.
- [ ] Unsupported provider capabilities fail clearly; there is no silent reasoning/model fallback.
- [ ] Automated tests do not require external network access or real credentials.
- [ ] A dummy credential is proven absent from captured logs and error messages.
- [ ] [IMPL-A4-COMPLETED.md](IMPL-A4-COMPLETED.md) is complete and linked.

### Step A5 — Freeze safe-write, recovery, and concurrency details [DESIGN]

**Goal:** Translate the HLD's shared artifact and recovery invariants into precise, fault-testable behavior for `.desc.txt` and `.desc.json`.

**Inputs:**
- `docs/REQ-image-clarus.md` §§16–17
- `docs/HLD-image-clarus.md` §§7.1–7.2
- Steps A1–A4 decisions

**Actions:**
1. Specify temporary-file naming/location, flush/close/validation order, destination replacement, backup creation/refresh, permission handling, success verification, cleanup, and error reporting.
2. Specify recovery order exactly: missing destination + `.bak` restores backup; destination + `.bak` keeps destination authoritative; temporary files are never recovery sources; remove only temporary files proven stale.
3. Define observable behavior for failed generation, failed validation, backup failure, replacement failure, interrupted write, and cleanup failure. Preserve the original or recoverable backup; never mark partial output complete.
4. Define testable last-write-wins behavior for overlapping writers without locks. Do not claim serialized updates, conflict detection, or crash-proof semantics on unsupported filesystems.
5. Record representative Linux filesystem/test-environment coverage and how fault injection will exercise failures without destructive host operations.

**Outputs:**
- Safe-write state table and fault-injection matrix in [IMPL-A5-COMPLETED.md](IMPL-A5-COMPLETED.md)
- This plan updated with exact failure/recovery assertions

**Acceptance:**
- [ ] Every HLD backup/recovery invariant is represented in a deterministic test case.
- [ ] Failure paths never delete the only recoverable original or publish an incomplete sidecar.
- [ ] The lock-free, last-successful-replacement-wins limitation remains explicit; no lock mechanism is added.
- [ ] [IMPL-A5-COMPLETED.md](IMPL-A5-COMPLETED.md) is complete and linked.

### Step A6 — Pass the Phase A readiness gate [DESIGN]

**Goal:** Ensure all implementation choices required by Slice 1 are decided, internally consistent, and reflected in the executable steps before coding starts.

**Inputs:** Steps A1–A5 records and the current plan.

**Actions:**
1. Reconcile the decisions against the REQ/HLD; mark each open item resolved, explicitly deferred, or blocked for Product Owner decision.
2. Update proposed paths, dependencies, command examples, and validation commands in this plan to the selected contract. Keep source documents unchanged unless separately authorized.
3. Verify the scope still includes both `desc` and `json`, independent stage selection, full resolved configuration, the required provenance contract, safe writes, and basic failure reporting.
4. Record any remaining blocker without proceeding to Phase B. A scope change requires explicit approval and a plan revision.

**Outputs:**
- Phase A readiness and unresolved-item disposition in [IMPL-A6-COMPLETED.md](IMPL-A6-COMPLETED.md)
- This plan with all Phase B paths/commands finalized

**Acceptance:**
- [ ] Steps A1–A5 are complete and their summary and detailed acceptance rows agree.
- [ ] No schema/prompt/provenance, CLI, provider, dependency, or safe-write decision is left for an implementer to guess during Phase B.
- [ ] The detailed steps use the final selected file paths and commands.
- [ ] No Phase B code work has started before this gate passes.
- [ ] [IMPL-A6-COMPLETED.md](IMPL-A6-COMPLETED.md) is complete and linked.

## Phase B — Build the single-image pipeline

**Phase B entry rule:** Step A6 passed. Use final decisions recorded in Phase A; if a decision changes, stop and update the plan before coding.

### Step B1 — Bootstrap the installable Python package and test harness [CODE/TEST]

**Goal:** Establish the declared Python package, authoritative version metadata, CLI entry point including `--version`, dependency lock, and automated test harness without implementing pipeline behavior.

**Inputs:** Step A1 and A6 records; finalized toolchain commands in this plan.

**Files:**
- Create: `.python-version`, `pyproject.toml`, `uv.lock`
- Modify: `.gitignore`, preserving current patterns and adding `.venv/`, `dist/`, `build/`, `*.egg-info/`, `__pycache__/`, `.pytest_cache/`, and `.ruff_cache/`
- Create: `src/image_clarus/__init__.py`, `src/image_clarus/__main__.py`, `src/image_clarus/cli.py`, `src/image_clarus/resources.py`
- Create: `tests/unit/test_cli.py`, `tests/unit/test_resources.py`

**Actions:**
1. Write failing tests for top-level help, `process --help`, `search --help`, top-level `image-clarus --version`, the exact search stub line/status `3`, and resolution of the canonical description prompt from both a source checkout and the built wheel.
2. Run the targeted test and record the expected failure before adding package code.
3. Define package metadata, initial version `0.1.0` from A1's static `[project].version`, `requires-python = ">=3.12"`, the `image-clarus` console entry point, Hatchling build configuration, the A1-selected runtime/dev dependencies and Apache-2.0 license metadata, and the lockfile using `uv`.
4. Configure Hatchling to map `prompts/image-description.txt` to `image_clarus/resources/prompts/image-description.txt`; implement the minimal `resources.py` lookup using A1's package-resource/source-tree paths. Implement importable package startup, both subcommand help surfaces, and top-level `--version` from installed distribution metadata without a duplicated version constant; make bare `search` return the exact A2 stderr line and exit status `3`. Do not add search behavior or process-stage behavior in this step.
5. Run the targeted test, then all current tests and selected lint/format checks.

**Outputs:**
- Package scaffold and test evidence; [IMPL-B1-COMPLETED.md](IMPL-B1-COMPLETED.md)

**Acceptance:**
- [ ] The package installs in an isolated Linux environment and exposes `image-clarus`.
- [ ] `uv.lock` is present and consistent with `pyproject.toml`.
- [ ] The canonical description prompt is available through `resources.py` from the source tree and installed wheel without a duplicated maintained copy.
- [ ] Python 3.12+ is declared and Python 3.13 is used for the development baseline.
- [ ] Installed `image-clarus --version` prints the A2-defined version, initially `image-clarus 0.1.0`, from the authoritative package version source.
- [ ] Top-level help lists `process` and `search`; both subcommand help surfaces work, and executing `search` reports not implemented as specified in A2.
- [ ] No external executable is required.
- [ ] RED and GREEN evidence is recorded and all current tests/quality checks pass.
- [ ] [IMPL-B1-COMPLETED.md](IMPL-B1-COMPLETED.md) is complete and linked.

### Step B2 — Implement configuration resolution and precedence [CODE/TEST]

**Goal:** Load built-in defaults and at most one selected YAML file, then apply CLI overrides according to the frozen precedence contract.

**Files:**
- Create: `src/image_clarus/config.py`
- Create: `tests/unit/test_config.py`
- Modify: `src/image_clarus/cli.py` only for config argument integration if required by A2

**Actions:**
1. Add failing tests for built-in defaults, explicit config suppressing discovery, user-level-before-system-level selection, no user/system merge, CLI-over-file precedence, independent prompt/schema overrides, relative paths, and invalid global configuration.
2. Verify RED; implement configuration parsing/resolution with the selected YAML library and only the exact keys/precedence from A2.
3. Validate global settings independently from selected-stage settings; do not require an unused provider credential/model for a different selected stage.
4. Add tests showing CLI generic overrides parse into the types specified in A2 and invalid overrides report a clear path/value error without revealing secrets.
5. Verify GREEN and run the full current suite.

**Outputs:** Configuration resolver and tests; [IMPL-B2-COMPLETED.md](IMPL-B2-COMPLETED.md)

**Acceptance:**
- [ ] All precedence and file-selection rules in A2 have passing tests using temporary config roots, not the host's real config files.
- [ ] Explicit config never discovers or merges another file.
- [ ] Selected-stage validation is isolated and deterministic.
- [ ] No credentials are emitted in diagnostics.
- [ ] RED/GREEN and regression evidence is recorded; [IMPL-B2-COMPLETED.md](IMPL-B2-COMPLETED.md) is linked.

### Step B3 — Implement the OpenAI-compatible provider adapter [CODE/TEST]

**Goal:** Provide a testable HTTP boundary shared by `desc` and `json`, translating generic model requests to the selected OpenAI-compatible Chat Completions API.

**Files:**
- Create: `src/image_clarus/providers/__init__.py`, `src/image_clarus/providers/openai_compatible.py`
- Create: `tests/unit/test_openai_compatible.py`

**Actions:**
1. Add failing local-transport tests for description image/prompt requests, structured JSON requests, model IDs, stage-specific selection, response parsing, reasoning default/off/mapping, and unsupported capabilities.
2. Verify RED; implement a minimal synchronous provider adapter using the A1-selected HTTP client and A4 request contract.
3. Add tests for timeout, authentication failure, non-success HTTP responses, malformed/empty responses, and zero automatic retry behavior.
4. Use a dummy credential to prove headers are sent when configured but never appear in logs, exceptions, or returned results. Do not make live API calls.
5. Verify GREEN and run current tests/quality checks.

**Outputs:** Provider adapter and local HTTP-boundary tests; [IMPL-B3-COMPLETED.md](IMPL-B3-COMPLETED.md)

**Acceptance:**
- [ ] Both model-driven stages can call the adapter through the contract fixed in A4.
- [ ] Test coverage proves request construction, success parsing, error handling, capability handling, and secret redaction.
- [ ] Automated tests use no external service or real credentials.
- [ ] RED/GREEN and regression evidence is recorded; [IMPL-B3-COMPLETED.md](IMPL-B3-COMPLETED.md) is linked.

### Step B4 — Implement stage results, registry, and coordinator [CODE/TEST]

**Goal:** Implement minimal ordered single-image orchestration while keeping stage-specific policies inside each stage.

**Files:**
- Create: `src/image_clarus/results.py`, `src/image_clarus/pipeline.py`
- Create: `tests/unit/test_results.py`, `tests/unit/test_pipeline.py`

**Actions:**
1. Write failing tests for stable `completed`/`skipped`/`failed` results (or the A2-approved equivalents), structured reason/category, registry order, explicit stage subsets, default registered-stage selection, and single-image exit aggregation.
2. Verify RED; implement the smallest typed result contract and fixed registry containing only `desc` and `json` in Slice 1.
3. Implement a coordinator that passes the full resolved configuration and shared service interfaces to stages. It must not parse sidecars, infer prerequisites, or decide create/overwrite policy.
4. Verify that `--stages=json` schedules only `json`; the stage reports its missing prerequisite according to the approved single-file policy. Verify a combined run schedules `desc` before `json`.
5. Verify GREEN and run all current tests.

**Outputs:** Result, registry, coordinator, and tests; [IMPL-B4-COMPLETED.md](IMPL-B4-COMPLETED.md)

**Acceptance:**
- [ ] Registry order is deterministic; explicit selection never expands prerequisites.
- [ ] The complete resolved configuration reaches each stage unchanged.
- [ ] Coordinator contains no stage-specific input, completion, overwrite, or output-parsing rules.
- [ ] Result and exit behavior matches A2.
- [ ] RED/GREEN and regression evidence is recorded; [IMPL-B4-COMPLETED.md](IMPL-B4-COMPLETED.md) is linked.

### Step B5 — Implement the recoverable sidecar artifact service [CODE/TEST]

**Goal:** Implement shared create/replace/recovery behavior for the two Slice 1 sidecars without adding file locks.

**Files:**
- Create: `src/image_clarus/artifacts.py`
- Create: `tests/unit/test_artifacts.py`

**Actions:**
1. Add failing tests for create, replacement, current-original backup refresh, restore when destination is missing, destination-authoritative behavior when both destination and backup exist, and removal/retention after verified success.
2. Add fault-injection tests for write/flush/validation/backup/replacement failure; assert the previous destination or recoverable backup is preserved and incomplete output is never published.
3. Test temporary files are created in the destination directory, are never recovery sources, and only proven-stale temporary files are removed.
4. Test permission behavior where supported and overlapping writers on a temporary directory; assert final content is complete and comes from a successful writer, without asserting lock/serialization behavior.
5. Verify RED; implement the minimal artifact API needed by `desc` and `json`, then verify GREEN and current regression suite.

**Outputs:** Shared artifact service and fault tests; [IMPL-B5-COMPLETED.md](IMPL-B5-COMPLETED.md)

**Acceptance:**
- [ ] HLD §7.1 recovery rules are all covered.
- [ ] Failed writes preserve recoverable originals and cannot produce a success result.
- [ ] No application-level lock or false crash-proof promise is introduced.
- [ ] Source image paths are never passed as write destinations.
- [ ] RED/GREEN and fault-test evidence is recorded; [IMPL-B5-COMPLETED.md](IMPL-B5-COMPLETED.md) is linked.

### Step B6 — Implement the description stage [CODE/TEST]

**Goal:** Generate the exact configured description prompt against one image and safely create or explicitly regenerate `<image>.desc.txt`.

**Files:**
- Create: `src/image_clarus/stages/__init__.py`, `src/image_clarus/stages/description.py`
- Create: `tests/unit/test_description_stage.py`
- Read: `prompts/image-description.txt`, `src/image_clarus/resources.py`

**Actions:**
1. Write failing tests for one valid synthetic image, exact default prompt text, prompt override, selected description model, new-only skip behavior, explicit regeneration, provider failure, and safe-write failure.
2. Verify RED; implement stage-owned input checks, provider request, complete output validation, result construction, and artifact write through the shared service.
3. Ensure the default request contains exactly `Fully describe and explain everything about this image.` as its prompt, without appended instructions.
4. Verify existing `.desc.txt` is preserved unless regeneration is explicitly selected; a failed model call never creates a completion sidecar.
5. Verify GREEN and run all current tests.

**Outputs:** Description stage and tests; [IMPL-B6-COMPLETED.md](IMPL-B6-COMPLETED.md)

**Acceptance:**
- [ ] `desc` works alone and writes exactly `<image>.desc.txt` beside the input.
- [ ] The default prompt is byte-for-byte consistent with the existing resource; prompt override works independently.
- [ ] Existing output is skipped by default and replaced only on explicit regeneration.
- [ ] Failures are reported and leave no falsely completed output.
- [ ] RED/GREEN and regression evidence is recorded; [IMPL-B6-COMPLETED.md](IMPL-B6-COMPLETED.md) is linked.

### Step B7 — Implement the structured JSON stage [CODE/TEST]

**Goal:** Convert the persisted description into schema-valid structured metadata with required provenance and safe create/regenerate behavior.

**Files:**
- Create/update: `src/image_clarus/stages/structure.py`
- Create: `prompts/image-structure.txt`, `schemas/image-structure.schema.json`
- Create: `tests/unit/test_structure_stage.py`
- Modify: `pyproject.toml` to map the A3-selected root JSON-prompt and schema paths into the matching `image_clarus/resources/prompts/` and `image_clarus/resources/schemas/` subdirectories
- Read: `src/image_clarus/resources.py`
- Read: `src/image_clarus/artifacts.py`, `src/image_clarus/providers/openai_compatible.py`

**Actions:**
1. Add failing tests for valid and invalid model JSON, all A3-required semantic/provenance fields, schema-version identification for default and custom schema contracts, custom prompt/schema file overrides, malformed/fenced responses, zero validation retries by default, configured bounded validation retry, missing `.desc.txt`, existing JSON skip, and explicit regeneration.
2. Verify RED; implement a stage that reads `.desc.txt` from disk, calls the selected JSON model, parses and validates against the resolved schema, adds/validates provenance and schema-version identification exactly as A3 specifies, and writes only validated content through the artifact service.
3. Keep model-generated values distinct from application-owned provenance according to the A3-frozen contract. Do not allow custom schema replacement to silently remove required provenance.
4. Ensure a missing description for explicit one-image `json` selection follows A2 and does not trigger `desc` implicitly.
5. Verify GREEN and run the complete current test suite.

**Outputs:** Default JSON prompt/schema, JSON stage, and tests; [IMPL-B7-COMPLETED.md](IMPL-B7-COMPLETED.md)

**Acceptance:**
- [ ] `json` consumes the persisted `.desc.txt` and writes exactly `<image>.desc.json`.
- [ ] The output is fully schema-validated, includes the required provenance contract, and covers all required metadata categories.
- [ ] The output identifies its metadata-schema version independently of the application version, following A3's default/custom-schema rules.
- [ ] Custom schema and prompt replacement work without source changes and follow A3 semantics.
- [ ] Invalid/missing prerequisites follow the approved result policy; invalid output is never published as complete.
- [ ] RED/GREEN and regression evidence is recorded; [IMPL-B7-COMPLETED.md](IMPL-B7-COMPLETED.md) is linked.

### Step B8 — Wire the single-image `process` command [CODE/TEST]

**Goal:** Connect CLI parsing, config resolution, stage selection, coordinator, results, and exits for the frozen one-image contract.

**Files:**
- Modify: `src/image_clarus/cli.py`, `src/image_clarus/__main__.py`
- Create/update: `tests/unit/test_cli.py`
- Read: `src/image_clarus/config.py`, `src/image_clarus/pipeline.py`, `src/image_clarus/results.py`

**Actions:**
1. Add failing CLI tests for exact A2 command grammar, help, one image, `--config`, `--stages`, generic/dedicated overrides, invalid options, skip/completed/failure output, and exit codes.
2. Verify RED; wire CLI parsing to config resolution and coordinator without re-implementing stage logic.
3. Verify `desc` only, `json` only, and combined selection. Verify combined execution reads the description back from the sidecar written to disk.
4. Verify `image-clarus search --help`; verify bare `search` returns the exact A2 not-implemented message and exit status `3`. Do not add search matching or sidecar traversal.
5. Verify GREEN and full suite.

**Outputs:** CLI integration and tests; [IMPL-B8-COMPLETED.md](IMPL-B8-COMPLETED.md)

**Acceptance:**
- [ ] Every accepted CLI option and behavior from A2 has a black-box test.
- [ ] Stage selection, config precedence, result display, and exit behavior match their contracts.
- [ ] The CLI does not modify the source image and does not silently invoke unselected stages.
- [ ] Top-level, `process`, and `search` help work; executing `search` reports not implemented, with no Slice 1 search matching.
- [ ] RED/GREEN and regression evidence is recorded; [IMPL-B8-COMPLETED.md](IMPL-B8-COMPLETED.md) is linked.

### Step B9 — Document Slice 1 installation, configuration, and use [DOCS/TEST]

**Goal:** Give users reproducible installation and one-image examples without implying later-slice features are implemented.

**Files:**
- Modify: `README.md`
- Create: `examples/config.yaml`
- Read: `docs/REQ-image-clarus.md`, `docs/HLD-image-clarus.md`, final CLI help

**Actions:**
1. Document Python/`uv` installation, the `image-clarus` entry point and `--version` command, required provider configuration, environment-variable credential setup, and the exact config precedence.
2. Provide sanitized examples for `desc`, `json`, combined execution, custom prompt/schema, and explicit regeneration using the frozen CLI grammar.
3. State current Slice 1 limitations: single-image only; the `search` command exists for help but reports not implemented; no search matching, traversal/batch, XMP, ExifTool, or scheduler.
4. Ensure the sample config contains only an environment variable name, never a credential value, and example images/data contain no private metadata.
5. Run every documented command that does not require a live provider, including `image-clarus --version`; label the manual provider smoke command and authorization boundary clearly.
6. Preserve the README's project-document links while adding Slice 1 installation and usage guidance.

**Outputs:** Updated README, sanitized sample config, command verification; [IMPL-B9-COMPLETED.md](IMPL-B9-COMPLETED.md)

**Acceptance:**
- [ ] Examples match actual help and CLI behavior.
- [ ] Configuration precedence, secret handling, and current scope are clear.
- [ ] No unimplemented batch/search/XMP behavior is presented as available.
- [ ] Documentation links and commands are validated; [IMPL-B9-COMPLETED.md](IMPL-B9-COMPLETED.md) is linked.

## Phase C — Verify and close Slice 1

### Step C1 — Verify independent stage execution and persisted handoff [TEST]

**Goal:** Prove the required one-image behavior end-to-end through the public CLI and stage contracts.

**Files:**
- Create/update: `tests/integration/test_single_image_pipeline.py`
- Read: all Slice 1 stage, config, provider, and CLI modules

**Actions:**
1. Run the CLI against a generated synthetic image with a local HTTP stub; assert `desc` creates `.desc.txt` and `json` reads that exact file to produce `.desc.json` with the schema-version identifier frozen in A3.
2. Test `desc` only, `json` only with an existing description, `json` only with a missing description, combined stages, default stage selection, existing-output skip, and explicit regeneration.
3. Assert stage order and persisted-file handoff; make the JSON fake model inspect the description content it receives, not an in-memory stage return.
4. Seed `.desc.txt` with a complete sentinel description `v1`. Launch a real `desc`-only CLI process with its own temporary config and selected description model; use a threaded local HTTP stub to hold its regeneration response before the stage writes `v2`. While it is held, launch a separate `json`-only CLI process with a different temporary config and JSON model. Observe and hold the JSON request, release the description response so the first process writes complete `v2`, then release the JSON response. This forces the JSON request to consume the persisted `v1` while the two OS processes overlap.
5. Assert the requests use their distinct configured model IDs, the JSON request contains exactly the on-disk `v1` description, both processes return the expected results, final `.desc.txt` equals the complete `v2` response, and `.desc.json` parses and validates against the selected schema. The JSON test response must be deterministic for the `v1` request; assert no output is truncated or interleaved.
6. Assert original image bytes/hash are unchanged and no XMP or unrelated files are written.
7. Run targeted integration tests, then all current tests.

**Outputs:** End-to-end acceptance matrix and results; [IMPL-C1-COMPLETED.md](IMPL-C1-COMPLETED.md)

**Acceptance:**
- [ ] All required Slice 1 stage combinations and prerequisite behaviors pass.
- [ ] `json` reads the persisted handoff and never triggers `desc` when explicitly omitted.
- [ ] Generated `.desc.json` identifies the schema version according to A3, independently of the application version.
- [ ] Two separate CLI processes execute `desc` and `json` concurrently with their independently selected models; JSON consumes a complete persisted description and neither completed sidecar is corrupted.
- [ ] Source image remains unchanged; outputs use the exact sidecar names.
- [ ] [IMPL-C1-COMPLETED.md](IMPL-C1-COMPLETED.md) is complete and linked.

### Step C2 — Verify failure recovery, source integrity, and credential hygiene [TEST]

**Goal:** Verify safety invariants under failures and overlapping writes without claiming stronger guarantees than the HLD.

**Files:**
- Create/update: `tests/unit/test_artifacts.py`, `tests/unit/test_openai_compatible.py`, `tests/integration/test_single_image_pipeline.py`

**Actions:**
1. Run safe-write fault-injection cases for backup, replacement, invalid model output, and cleanup failures; inspect destination/backup/temp state after each case.
2. Run recovery cases for destination absent + backup present and destination + backup present; confirm temporary files are never used as recovery sources.
3. Spawn two separate OS processes through the safe-write test harness, synchronize them to write different complete payloads to the same temporary sidecar, and assert the destination is exactly one complete valid payload, not truncated/interleaved. Do not assert which writer wins or imply serialized updates; document the last-write-wins limitation.
4. Use local provider/write barriers to send SIGINT and SIGTERM before a response and during a safe-write operation; assert statuses `130`/`143`, no later selected stage starts, in-flight requests are cancelled when safe, and an already-started write reaches its safe boundary. Do not call SIGKILL graceful; verify its filesystem aftermath through A5 recovery cases.
5. Capture logs/errors using a dummy API key and assert the secret is absent. Verify no real credential or real personal image is used.
6. Record the filesystem used and any unsupported durability limitations; do not claim crash-proof or cross-filesystem coverage.

**Outputs:** Safety/fault evidence; [IMPL-C2-COMPLETED.md](IMPL-C2-COMPLETED.md)

**Acceptance:**
- [ ] Recoverable originals are preserved across injected failures.
- [ ] No incomplete/invalid artifact is reported as complete.
- [ ] Separate-process overlapping writes leave a complete valid sidecar; the test does not claim conflict detection or a deterministic winner.
- [ ] SIGINT/SIGTERM return `130`/`143`, stop before the next stage, cancel requests when safe, and finish any write already in progress before exit.
- [ ] Secret redaction and lock-free limitations are verified.
- [ ] Evidence states actual tested filesystem and does not overclaim.
- [ ] [IMPL-C2-COMPLETED.md](IMPL-C2-COMPLETED.md) is complete and linked.

### Step C3 — Run Linux package and quality gates [TEST]

**Goal:** Verify reproducible installation, installed CLI version display, supported Python baseline, test suite, and selected quality gates on Linux.

**Files:** No production changes expected; if a fix is required, add a test-first corrective step and record it before proceeding.

**Actions:**
1. In a clean isolated environment, run `uv sync --locked --extra dev --python 3.13` and confirm the committed lockfile is current.
2. Run the full suite with `uv run --locked --extra dev --python 3.13 pytest`.
3. Run `uv run --locked --extra dev --python 3.13 ruff check .` and `uv run --locked --extra dev --python 3.13 ruff format --check .`.
4. Run `uv sync --locked --extra dev --python 3.12`, then `uv run --locked --extra dev --python 3.12 pytest` on Linux to verify the declared minimum. If a required interpreter/dependency cannot be obtained, report the precise blocker and leave the affected acceptance row unchecked.
5. Verify the console entry point, `image-clarus --version` against the authoritative package metadata, top-level help, `process --help`, `search --help`, and the exact `search` stderr line/status `3` in the isolated environment; confirm `desc`/`json` use no external executable. Do not run an exhaustive OS/filesystem matrix.

**Outputs:** Command transcript, interpreter versions, and result summary; [IMPL-C3-COMPLETED.md](IMPL-C3-COMPLETED.md)

**Acceptance:**
- [ ] Clean locked install succeeds on Linux.
- [ ] All tests and selected quality gates pass on Python 3.13.
- [ ] Python 3.12 compatibility is actually exercised, or remains explicitly unchecked with its blocker.
- [ ] Installed `image-clarus --version` matches the authoritative package metadata and prints the initial `image-clarus 0.1.0` value.
- [ ] `image-clarus` entry point and top-level, process, and search help work from the installed package; executing `search` reports not implemented.
- [ ] No external executable is required for Slice 1.
- [ ] [IMPL-C3-COMPLETED.md](IMPL-C3-COMPLETED.md) is complete and linked.

### Step C4 — Perform an authorized real-provider quality smoke test [MANUAL/TEST]

**Goal:** Confirm the selected compatible provider can produce useful description and schema-valid structured metadata with the actual adapter, without exposing private images or credentials.

**Owner:** Operator/user controls endpoint, model, credentials, and any cost/data transfer. Hermes must not request or type a secret.

**Inputs:** A synthetic, non-identifying image; approved endpoint/model; credential already available through the operator's chosen environment variable; A3 schema/prompt contract.

**Actions:**
1. Do not make a remote request until the operator explicitly authorizes the endpoint, model, synthetic input, and any expected charge/data transfer.
2. Run the documented one-image `desc` and `json` commands using the approved environment variable; never put the credential in command arguments or evidence.
3. Check description usefulness, schema validity, required metadata categories, provenance, and absence of credentials/private metadata in outputs and logs.
4. If no authorized endpoint is available, record `NOT SAFELY AVAILABLE` and the exact boundary; do not retry with another endpoint or real photo.

**Outputs:** Sanitized manual result/disposition and operator authorization provenance; [IMPL-C4-COMPLETED.md](IMPL-C4-COMPLETED.md)

**Acceptance:**
- [ ] The approved provider completes both stages with the agreed contract, or the row remains unchecked with `NOT SAFELY AVAILABLE` and a precise blocker.
- [ ] Only synthetic, non-identifying input is used; no secret is copied into the record.
- [ ] Manual result is not represented as automated test evidence.
- [ ] [IMPL-C4-COMPLETED.md](IMPL-C4-COMPLETED.md) is complete and linked.

### Step C5 — Reconcile acceptance evidence and close Slice 1 [DOCS/TEST]

**Goal:** Close only the Slice 1 criteria demonstrated by implementation and test evidence, with plan status and phase state synchronized.

**Inputs:** All step completion records, REQ/HLD acceptance mapping, current test/quality results, and this plan.

**Actions:**
1. Reconcile each acceptance row below against its linked step records and real test/manual evidence. Do not infer runtime success from a plan or completion record alone.
2. Update each detailed acceptance row and matching phase/step summary checkbox together; leave any blocked or unverified row unchecked.
3. Record remaining issues and approved carry-forward for XMP, traversal/batch, search, and later operational capabilities.
4. Set overall plan status to Complete only if every required Slice 1 acceptance row is verified. Otherwise set status to Partial/Blocked with exact remaining work; do not close the slice.

**Outputs:** Final acceptance reconciliation and status; [IMPL-C5-COMPLETED.md](IMPL-C5-COMPLETED.md)

**Acceptance:**
- [ ] Every required Slice 1 behavior maps to an executed automated or authorized manual check.
- [ ] Overall status, phase summaries, detailed acceptance rows, and completion evidence agree.
- [ ] No XMP, batch, or search implementation has been pulled into Slice 1 without approval.
- [ ] Remaining work has explicit ownership/carry-forward and is not presented as complete.
- [ ] [IMPL-C5-COMPLETED.md](IMPL-C5-COMPLETED.md) is complete and linked.

## Slice 1 acceptance checklist

These are the plan-level completion criteria. Detailed test evidence is owned by the mapped steps; keep each row unchecked until executed and verified.

| ID | Acceptance criterion | Evidence steps |
| --- | --- | --- |
| S1-AC1 | Installable Python 3.12+ package and `image-clarus` entry point; Python 3.13 Linux development baseline; `uv.lock` committed | B1, C3 |
| S1-AC2 | Single-image `desc` writes `<image>.desc.txt`; exact built-in prompt and independent prompt/model override work | B6, B8, C1, C4 |
| S1-AC3 | Single-image `json` reads the persisted `.desc.txt`, validates structured output, and writes `<image>.desc.json` | A3, B7, B8, C1, C4 |
| S1-AC4 | Default schema covers required metadata and provenance; full custom-schema replacement has defined provenance behavior | A3, B7, C1 |
| S1-AC5 | `desc` and `json` are independently selectable; combined invocation follows registry order; no prerequisite auto-expansion; top-level/process/search help is available and search execution reports not implemented | A2, B1, B4, B8, C1, C3 |
| S1-AC6 | Config discovery, no-merge behavior, precedence, selected-stage validation, and CLI overrides match the frozen contract | A2, B2, B8, C1 |
| S1-AC7 | OpenAI-compatible provider boundary supports named per-stage models and reports unsupported capabilities/errors clearly without logging secrets | A4, B3, C2, C4 |
| S1-AC8 | Existing outputs are skipped unless explicitly regenerated; failures/invalid JSON do not publish false completion artifacts | A2, B5–B8, C1–C2 |
| S1-AC9 | Shared safe-write service implements backup/recovery invariants and preserves source images; lock-free last-write-wins limitations are explicit | A5, B5, C1–C2 |
| S1-AC10 | Linux tests/quality gates pass; Python 3.12 compatibility is verified; no external executable is required for desc/json | B1–B9, C3 |
| S1-AC11 | User docs and examples accurately describe the implemented Slice 1 scope and contain no credentials/private metadata | B9, C4–C5 |
| S1-AC12 | Separate CLI processes can execute `desc` and `json` concurrently with independent model selections; JSON consumes persisted description and completed sidecars remain uncorrupted | C1–C2 |
| S1-AC13 | Application uses SemVer, starts at `0.1.0` on the Slice 1 `0.1.x` line, has one authoritative version source, and `image-clarus --version` reports it | A1–A2, B1, C3 |
| S1-AC14 | Generated JSON identifies its metadata-schema version independently of application version and follows A3 default/custom-schema rules | A3, B7, C1 |

## Open items and resolution paths

All of the following are Phase A work, not permission to invent details during coding:

| Open item | Resolve in | Required result |
| --- | --- | --- |
| Provider request shape, image encoding, reasoning/capability mapping, timeouts and errors | A4 | Local-testable HTTP contract with secret-redaction rules |
| Artifact API details, temp/backup naming, permissions, failure and recovery assertions | A5 | Fault-testable state table preserving HLD invariants |

## Source documents and planning basis

- [Requirements](../REQ-image-clarus.md)
- [High-Level Design](../HLD-image-clarus.md)
- [Exact built-in description prompt](../../prompts/image-description.txt)
- Adapted implementation-plan checklist mechanics: ordered phases, matching summary/detail headings, categorized work, explicit TBD resolution, per-step completion evidence, and mirrored acceptance state. Service Craze-specific product, frontend/backend, COMMS, tenant, and workspace constraints are intentionally excluded.
