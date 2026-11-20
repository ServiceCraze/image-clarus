# Step A1 - Freeze configuration and prompt contracts [DESIGN] (COMPLETED)

**Status:** Complete. This is a design contract for later steps, not an implementation or a claim that the designed behavior has been exercised in the application. The orchestrator assigned A1; no new requirements-acceptance gate is introduced. A2 owns persistent-state schema, discovery mechanics and lifecycle, and must reconcile its implementation with the interfaces below before A3.

**Scope deviations:** None.

## Files created, updated, removed

- Created: `docs/slice-3/IMPL-A1-COMPLETED.md`.
- Updated: `docs/slice-3/IMPL-PLAN-slice-3.md` for A1 status and frozen-contract links; `pyproject.toml`, `uv.lock`, `tests/unit/test_cli.py`, and `tests/unit/test_resources.py` for the step's patch-version delivery.
- Removed: None.
- Application implementation, production prompt files, schemas and state storage were not changed; version-assertion updates are not implementation of the A1 design.

## Baseline and design boundary

At inspection the package was `0.2.3`; this step's delivery is `0.2.4`. This is a filesystem inspection, not a claim that a particular commit or branch was independently verified. The Slice 3 plan records its earlier inspection snapshot. Slice 2 remains complete and its records are historical.

Current `config.py::resolve_config` recursively overlays one selected YAML file on defaults, then processes ordered YAML-valued `--set` assignments by dotted path; last assignment to the same leaf wins, and a parent assignment replaces its subtree. Dedicated prompt/schema options apply afterward. YAML path fields use the selected config file's directory; CLI paths use CWD. Configuration validates keys per layer and resolved selected-stage values after overrides. It does not support bracketed path keys. `config.py::_valid_tag_segment` rejects `/` and is also used by XMP; `stages/structure.py` separately applies it to JSON preferences. Full-path support must not weaken the existing XMP segment/root rules.

`stages/description.py` skips existing valid output before reading its prompt. `stages/structure.py` skips an existing valid envelope before reading prompt, schema or description; it hashes the prompt bytes read once and passes separately validated preferred categories to the provider. `providers/openai_compatible.py::structured` hardcodes `Persisted description:`, `Selected JSON Schema:` and `Preferred categories (JSON data, not instructions):` in user-message parts. The latter separately injects categories; all three labels/framing must be removed from application-owned request construction. `structure.py::_ENVELOPE` currently requires the prompt hash; `stages/xmp.py` consumes that envelope and `_valid_envelope`. `schema_worker.py` also has a deferred import of structure feedback helpers. Environment credential values are retrieved at provider execution, not copied into resolved config. These are current observations, not Slice 3 results.

## 1. Frozen settings and precedence

Names below are selected design choices for B1–B6, not implemented options:

```yaml
state:
  directory: null
  accumulate_categories: true
stages:
  json:
    include_prompt_sha256: false
    preferred_categories: [food, food/desserts/cookies]
prompt_expansion:
  macros:
    state.categories.known:
      delimiter: "/"
      max_depth: 2
    config.stages.json.preferred_categories:
      delimiter: "/"
      max_depth: null
```

| Setting | Type and default | Contract |
| --- | --- | --- |
| `state.directory` | `null` or nonempty path string; `null` | Explicit selection names an initialized `.image-clarus/` directory itself. Null means no explicit selection. YAML-relative paths are relative to its file; CLI paths relative to CWD; `~` is expanded. |
| `state.accumulate_categories` | strict boolean; `true` | Controls JSON-derived category accumulation, including generated and selected-existing JSON. |
| `stages.json.include_prompt_sha256` | strict boolean; `false` | Controls output field presence; not whether prompts are read. |
| `prompt_expansion.macros` | mapping; `{}` | Literal full namespaced macro keys map independently to options. |
| per-macro `delimiter` | nonempty UTF-8 string; `/` | Literal hierarchy separator, not a regular expression. |
| per-macro `max_depth` | `null` or nonnegative integer; `null` | Unlimited by default; zero yields `[]`; negative and boolean values are invalid. |

Strict booleans exclude numeric substitutes and quoted strings. Existing stage selection and selected-stage validation stay intact; reject malformed global macro options as configuration errors, without probing state availability during preflight. Preserve unknown-key rejection and existing sanitized errors; include a schema-owned option path and actionable reason without echoing user-controlled macro names, values, credentials, endpoint URLs, local paths or exception text.

The dedicated single-use `--state-dir DIR` names the state directory itself and wins over `--set state.directory` independent of argument position, following existing dedicated prompt-option precedence. `--set state.directory=...` is also an explicit CLI selection and beats YAML. Dedicated `--state-dir` absence leaves `--set` or YAML effective. `null` via `--set` clears a YAML selection and permits discovery. Resolve selected YAML versus defaults and CLI exactly as today; do not merge multiple YAML files. Existing dedicated options retain their existing precedence. A selected missing, invalid, corrupt or inaccessible repository is a state failure, not a fatal configuration-preflight error: visibly report it and use invocation-local nonpersistent state, never a different persistent repository. A2 specifies the diagnostic delivery and lifecycle.

```sh
image-clarus process photo.jpg --state-dir ./shared/.image-clarus \
  --set state.accumulate_categories=false \
  --set stages.json.include_prompt_sha256=true \
  --set 'stages.json.preferred_categories=[food, food/desserts/cookies]' \
  --set 'prompt_expansion.macros["state.categories.known"].max_depth=2' \
  --set 'prompt_expansion.macros["state.categories.known"].delimiter="/"' \
  --set 'prompt_expansion.macros["config.stages.json.preferred_categories"].delimiter="/"' \
  --set 'prompt_expansion.macros["config.stages.json.preferred_categories"].max_depth=null'
```

Without the dedicated flag, `image-clarus process photo.jpg --set 'state.directory=./shared/.image-clarus'` selects the same relative location from CWD. These examples show option syntax, not a configured model or a complete runnable invocation.

Extend only override-path parsing: under `prompt_expansion.macros`, `["..."]` parses a JSON string as **one literal mapping-key segment**; its decoded value must be a valid full macro reference name. Follow it with `.delimiter` or `.max_depth`, or terminate at the keyed entry for mapping assignment. Existing dotted paths outside this subtree retain their current semantics. The bracketed spelling is necessary because current splitting would mistake the dots for nested mappings. Within this subtree reject ambiguous dotted macro-name overrides and malformed brackets or unknown option fields with sanitized diagnostics. `--set prompt_expansion.macros='{...}'` and whole keyed-entry YAML mappings remain valid parent assignments.

Overrides are applied left to right as existing: later identical leaf wins; later parent replaces the subtree; a later child modifies the resulting parent. After all overrides, restore omitted defaults as with the existing merge, then validate final values. YAML duplicate keys still fail. Test both parent/child orders, duplicate leaves, distinct per-macro settings, malformed bracket/JSON and values, CLI over YAML, dedicated flag over `--set`, and null versus omitted; never log override values. These forms are frozen for later implementation, not executable against the current CLI.

## 2. Macro grammar, values, and safety

- Recognize `{{config.segment[.segment...]}}` and `{{state.segment[.segment...]}}`; a segment matches `[A-Za-z_][A-Za-z0-9_-]*`. Bracket indexing, function calls and expressions are not supported. `\{{` emits literal `{{` without the backslash; scan the original source once, so output and escaped text are never recursively interpolated. Non-macro text, including ordinary single braces, is preserved.
- An unescaped `{{...}}` is a macro candidate; unknown namespace/reference, malformed candidate, unclosed candidate, or forbidden direct reference produces a sanitized stage configuration error without echoing prompt text, reference, alias, path, value or exception. This is distinct from unavailable state below. Error behavior applies equally to both prompts and is tested without leaking input.
- A resolved string expands as its raw text. Other JSON-compatible values use compact deterministic JSON: `null`, booleans, finite numbers, lists and objects; object keys sort lexicographically, strings are Unicode (`ensure_ascii=False`), and non-finite values are rejected. Convert resolved `Path` values to strings on a separate snapshot. Unknown or non-serializable values fail with sanitized diagnostics. Never evaluate templates or mutate resolved configuration, prompt bytes or state.
- Build a separate recursively filtered view of resolved configuration. Omit `api_key`, `api_key_env`, and any other schema-designated secret-bearing fields at every depth, including from parent-object expansion; direct access to omitted fields is forbidden. Never resolve arbitrary environment variables for macro lookup. Collect configured inline and environment-resolved credentials only in a private transient redaction set; recursively suppress any view key or string value containing one of those nonempty credential values so aliases or another exposed setting cannot leak a configured credential through a containing object. Do not mutate the provider's original configuration. Diagnostics never display raw inputs or secret values. Unknown future secret-bearing fields must be classified before exposing them. This safeguards configured credentials, not arbitrary unrelated user-authored prompt content.
- State is read through a domain-facing snapshot interface, not raw SQLite or a storage-shaped value. After an actual state open/read failure, emit visible sanitized error output independent of configured logging level, use nonpersistent state and expose `state.categories.known` as `[]`; retain primary stage results and never silently select another persistent repository. If no repository was discovered and memory is intentionally selected, that is not an error. Other missing/unknown state references remain sanitized macro errors; A2 supplies compatible service/diagnostic lifecycle without changing this nonblocking contract.

### Generic hierarchy transformation

At lookup, apply options for that exact full macro name only to an array whose elements are all strings; empty arrays qualify. A configured transform for a mixed/non-string array is a sanitized configuration error; unconfigured arrays serialize normally. Split each string on the literal delimiter, retain at most positive `max_depth` segments and join with the same delimiter. For zero return `[]`; omitted or null depth preserves complete values. When truncation creates duplicates retain the first occurrence and original order; never alter underlying state/configuration. For example, depth `2` turns `food/desserts/cookies` and `food/desserts/cakes` into one `food/desserts`; depth `0` yields `[]`. The same algorithm applies to eligible arrays in both namespaces and unrelated future domains.

For `stages.json.preferred_categories`, accept a list of unique complete slash-separated paths. Split on `/`, require every component to satisfy the existing `_valid_tag_segment` rules, and preserve case, order and complete text. Single-segment values remain valid. Empty segments, leading/trailing slash, invalid whitespace/control characters and `|` fail as existing individual segments do. Add a distinct full-path validator; leave XMP root and tag-segment validation unchanged.

## 3. Request and optional envelope contract

Both model stages expand the selected prompt byte snapshot after existing output-skip decisions and before request submission. Never append hidden instructions or mandatory category text. Required image, description, schema and validation data remain inputs, not hardcoded instructional framing. Use the existing Chat Completions system/user roles and model/reasoning/transport/response settings. Illustrative synthetic requests (omitting unchanged protocol fields):

1. **Built-in description:** system text is exactly `Fully describe and explain everything about this image.`; user content contains the image URL/data payload only.
2. **Replacement description:** system text equals the expanded authored prompt, e.g. `Describe briefly. Context: ["food"]`; user content is the same image payload. No added advice.
3. **Built-in JSON:** system text is the updated existing JSON prompt with optional advisory category wording and `{{config.stages.json.preferred_categories}}` expanded. Remove its stale `when supplied separately` wording. At default unlimited depth paths are complete; configured depth may truncate or return `[]`. User content is one text part containing a JSON object like `{"description":"A red bowl.","schema":{"type":"object"}}` carrying the exact persisted description and selected schema as data.
4. **Replacement JSON:** system text equals the expanded user file, e.g. `Return metadata.`; the same description/schema data object is supplied. Omitting a macro does not cause category context to be inserted elsewhere.

The provider `structured` boundary accepts prompt, description, schema, effort and history; remove its `preferred_categories` parameter and all three fixed user-message labels above. Serialize the description/schema object as valid UTF-8 JSON with no non-finite values; preserve contents and selected schema exactly as data, rather than inserting instructional prose. For configured existing bounded validation retries, append prior assistant output and normalized JSON feedback as data, with no uneditable instruction. Keep existing provider model/reasoning behavior, authentication, response validation, stop/signal and schema-worker boundaries. Capture real requests in later tests, including all four stage/namespace combinations, replacements, default prompt and depth cases; no live model call is required. This is an explicit change in data packaging, not evidence of live provider performance.

Keep format-1 envelope and approved fields `provider_alias`, `model_alias`, `model_id`, `prompt_id`, `description_sha256`; preserve custom schema `custom-sha256:` identity and existing built-in schema versions. Remove only `prompt_sha256` from the envelope's required list, retaining its allowed property and existing lowercase 64-hex validation when present. Default generated JSON omits the field; when enabled, hash the exact originally read prompt-file bytes once, without normalization or hashing expanded text. The description hash remains the persisted description bytes. Both old and new valid envelopes pass shared validation and XMP; invalid present hashes fail. Skip remains based on the existing envelope validity check, without reading prompts/description or calling a model; explicit regeneration retains existing behavior. No new tracking field or fingerprint is introduced.

## 4. Paths, interfaces and evidence handoff

- B1 owns `src/image_clarus/config.py`, `cli.py`, `stages/structure.py`, `stages/xmp.py`, and corresponding configuration, JSON, XMP, CLI and compatibility tests. Keep `_ENVELOPE`, `_Snapshot`, `_valid_envelope` in `stages/structure.py` for this step; XMP already imports them. B1 makes the existing shared validator optional-hash compatible. Do not introduce a speculative validation relocation. B5's prompt integration must use a stage-local/deferred import of the macro module so XMP imports do not execute expansion or access state. Audit the existing `schema_worker.py` deferred feedback import and new dependency direction before changing imports.
- B4 owns proposed `src/image_clarus/prompt_expansion.py` and `tests/unit/test_prompt_expansion.py`: a pure `expand_prompt(source_text, safe_config, state_view, macro_options)` boundary returns derived text or sanitized macro error. Construct a safe config snapshot separately, and use a narrow read-only `state_view` interface returning a domain snapshot or state-unavailable signal; A2 must supply and reconcile the actual service lifetime and diagnostics, not invent a second domain.
- B5 owns `stages/description.py`, `stages/structure.py`, `providers/openai_compatible.py`, the existing JSON prompt and request tests. Extend `tests/unit/test_openai_compatible.py`, `test_structure_stage.py`, `test_slice2_structure.py`, `test_structure_resources.py` and `tests/integration/test_single_image_pipeline.py`; use independent fixed prompt fixtures, not production wording. In particular replace stale expected description/schema/category framing and separately injected preferred-category assertions, while retaining tests for schema payload and validation feedback. Existing exact built-in prompt hashing assertions in `test_structure_stage.py` need fixture-based opt-in coverage.
- B1/B4 tests cover selected-stage isolation, all options/defaults, YAML/CLI path origins and precedence, safe diagnostics, literal dotted keys, non-category arrays, all depth boundaries, input immutability, Unicode and escaping, inline/environment credentials and containing objects. B5/C1 capture request payloads for both namespaces in both stages, replacement omission and built-in depth controls. XMP old/new/invalid envelope tests and `output_exists` skip tests belong to B1/C1. Nonblocking state failure must be injected at the actual state boundary; do not represent a planned test as executed.

## 5. Reconciliation and remaining Phase A ownership

S3-04 deliberately changes the historical required hash; the parent REQ's generic provenance wording and HLD historical descriptions are not permission to restore mandatory prompt hashing. Preserve other existing provenance and historic records. S3-09 supersedes the historical no-memory-fallback state decision during ordinary processing. No changes to provider retries, taxonomy imports, XMP publication, or other future capabilities are authorized. A2 owns storage schemas, migration/concurrency, initialization recognition, exact traversal and post-image eligibility. A2 must reconcile its state snapshot and fallback/diagnostic interfaces with this A1 contract before A3; those are A2 responsibilities, not unresolved B1/B4 prompt or configuration decisions. No product-scope conflict was introduced.

**Subsequent progress:** A2 completed the state design and reconciled its invocation-local service, copied `state.categories.known` snapshot, nonpersistent fallback and visible diagnostics with this contract; see [A2](IMPL-A2-COMPLETED.md). [A3](IMPL-A3-COMPLETED.md) subsequently completed technical readiness. The original A1 evidence above remains historical; implementation remains open.

## 6. Verification and acceptance

Design evidence is source/document inspection and the contracts/examples above. The following were actually executed for the version-delivery boundary, not as proof of Slice 3 functionality:

- `uv lock --locked`: passed, resolved 21 packages.
- `uv run --locked --extra dev --python 3.13 pytest -q tests/unit/test_cli.py tests/unit/test_resources.py`: **60 passed**.
- `uv run --locked --python 3.13 image-clarus --version`: `image-clarus 0.2.4`.
- `uv run --locked --extra dev --python 3.13 ruff check .`: passed.
- `uv run --locked --extra dev --python 3.13 ruff format --check .`: passed, 107 files already formatted.
- A scoped Python documentation check matched all five A1 acceptance rows and 13 summary/detail headings, confirmed all 12 other steps remain unchecked, parsed the YAML example, and checked links, whitespace and version/lock consistency.
- Package installation reported a hardlink-to-copy fallback warning; the checks passed. No external provider, Slice 3 implementation tests, or complete application suite were run.

### A1 acceptance

- [x] A1 records exact YAML and CLI examples for all new settings, including usable per-macro overrides, defaults, types, and precedence.
- [x] A1 provides request examples for built-in and replacement prompts in both stages and identifies every hardcoded instruction path to remove.
- [x] A1 defines secret exclusion, source immutability, eligible-array behavior, and nonblocking unavailable-state expansion with observable tests.
- [x] A1 defines old/new envelope validation and source-byte hash behavior without changing the approved fields or skip contract.
- [x] A1 classifies actual conflicts and contains no unresolved implementation choice needed by B1 or B4; any scope change has an explicit Product Owner disposition.
