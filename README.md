# image-clarus

Image Clarus is an open-source CLI for describing one image, generating structured metadata and publishing selected metadata to an XMP sidecar. Description and JSON generation use configurable OpenAI-compatible models; XMP publication consumes persisted JSON without a model. Search and batch processing are not implemented. The Product Owner has reported successful manual digiKam interoperability checks, subject to the documented limits below.

## Install

Use Python 3.12 or newer and [uv](https://docs.astral.sh/uv/getting-started/installation/); Python 3.13 is the development baseline. To use `xmp`, separately install [ExifTool](https://exiftool.org/install.html) and make a working `exiftool` executable available on `PATH`. ExifTool is not required for `desc` or `json` alone.

### Install as a CLI tool

From the project checkout directory, install the CLI into an isolated uv tool environment:

```sh
uv tool install --python 3.13 .
```

Once uv's tool executable directory is on your `PATH`, run from any directory without `uv run` or activating a project environment:

```sh
image-clarus --version
image-clarus --help
image-clarus process --help
image-clarus init --help
image-clarus search --help
```

If the shell cannot find `image-clarus`, use `uv tool dir --bin` to locate its executable directory and add it to `PATH`; alternatively `uv tool update-shell` can configure your shell, after which open a new shell. Installing from `.` is not editable. After changing the checkout, reinstall from the checkout:

```sh
uv tool install --python 3.13 --force --reinstall .
```

Tool installation resolves its own dependencies and does not use the project's locked development environment.

### Run from the project environment

Alternatively, from the project checkout directory:

```sh
uv sync --locked
uv run --locked image-clarus --version
uv run --locked image-clarus --help
uv run --locked image-clarus process --help
uv run --locked image-clarus init --help
uv run --locked image-clarus search --help
```

`uv sync` creates the project environment and installs the CLI without administrator privileges. The bare command is available when that environment is activated. Without activation, prefix processing examples with `uv run --locked` and run them from the checkout.

## Configure

Start with [examples/config.yaml](examples/config.yaml). Its endpoint and model IDs are fictional placeholders, not a running service. For `desc`/`json`, replace them with values supported by your provider: `desc` needs an image-capable model, and `json` needs structured requests. The example stores only an environment variable name, not a credential. Supply its value through your environment or remove `api_key_env` from your private configuration if no authentication is required. A configured but unset or empty credential fails selected-stage authentication preflight, even when an existing output would be skipped.

Use the API base URL, not the full `/chat/completions` path; the adapter appends that path. The provider must support OpenAI-compatible Chat Completions, image data URLs for `desc`, and JSON-object response mode for `json`. HTTP and HTTPS URLs may use DNS/FQDN hostnames or IPv4/IPv6 addresses, without application-level hostname resolution or destination restrictions; DNS and connection failures occur at request time. HTTP does not encrypt credentials or request data; prefer HTTPS. Provider requests can transmit image bytes, descriptions, prompts, schemas, category guidance and generated metadata. Authorize the endpoint, model, data transfer and potential costs before making any request. Do not send private data or credentials without authorization.

Precedence, lowest to highest: built-in defaults, one selected YAML file, repeated `--set PATH=VALUE` overrides (the last assignment to the same path wins), then applicable dedicated flags such as `--desc-prompt`, `--json-prompt`, `--json-schema`, `--regenerate` and `--missing-prerequisite`. `--stages` selects the invocation. `--config FILE` uses only that file and disables discovery; otherwise the first existing user config is selected before the system config, with no merge or fallback after an invalid file. On Linux these are `~/.config/image-clarus/config.yaml` and `/etc/image-clarus/config.yaml`; macOS and Windows locations are in the [A2 contract](docs/slice-1/IMPL-A2-COMPLETED.md#discovery-precedence-and-path-bases).

Paths in YAML are relative to that file; explicit config and prompt/schema paths supplied on the command line or through `--set` are relative to the current working directory. `--set` values are YAML: preserve the inner quotes for an empty string, as in `--set 'stages.xmp.tag_root=""'`. Likewise quote the YAML string `off` in `--set 'stages.desc.reasoning_effort="off"'`, or YAML may parse it as a boolean. Do not put API keys in arguments or `--set`. JSON validation retries default to zero; `stages.json.validation_retries` permits 0–2 additional validation attempts, not network retries.

Configuration syntax, unknown keys and global structure are checked for the whole file; stage-specific settings and dependencies are validated for selected stages. All selected stages are preflighted before any stage runs. Thus `xmp` alone needs a usable ExifTool but no model, provider credential, prompt, schema file or description; unrelated `desc`/`json` invocations do not require ExifTool or valid unused XMP values. Unknown keys remain errors even in an unselected stage.

## Prompts and macros

Both `--desc-prompt FILE` and `--json-prompt FILE` replace their stage's instructions completely. The built-in description prompt is `Fully describe and explain everything about this image.` The built-in JSON prompt includes advisory preferred categories; replacement prompts may remove that guidance. Required image data, description and schema are still supplied as inputs, but no separate category instruction is injected. Prompt files can contain optional macros in either stage, for example:

```text
Use these preferred paths as optional guidance: {{config.stages.json.preferred_categories}}
Previously observed paths: {{state.categories.known}}
```

Macro names have `config` or `state` followed by dot-separated segments beginning with a letter or underscore and containing letters, digits, underscores or hyphens. Whitespace, expressions and indexing are not supported. Strings expand as raw text; other values use compact JSON with sorted object keys. Expansion is single-pass; `\{{` emits literal `{{`. Unknown, malformed, forbidden or unclosed references cause a sanitized stage error; prompts of outputs already skipped are not read or expanded. `config` exposes a filtered resolved configuration, not credentials: `api_key` and `api_key_env` are omitted even from containing objects, and configured credential values are filtered from the snapshot. This does not sanitize arbitrary text you write in a prompt. The currently available state domain is `state.categories.known`; unavailable state produces a visible state error and an empty list instead of blocking the stage. State values may contain sensitive metadata; referencing them sends them to the chosen provider.

Under `prompt_expansion.macros`, options apply independently to the exact full macro name. `delimiter` defaults to `/` and must be a nonempty string; `max_depth` defaults to `null` (unlimited), accepts a nonnegative integer, and `0` produces `[]`. For configured macros the value must be an array of strings. Positive depth truncates each path at that many delimiter-separated segments and deduplicates identical results in first-occurrence order. For example, at depth 2 both `food/desserts/cookies` and `food/desserts/cakes` become `food/desserts`. This changes only prompt output, not the prompt file, configuration or complete stored paths. Unconfigured arrays are serialized normally.

Use bracketed JSON-string keys for dotted macro names in CLI overrides; ordinary dotted syntax would split the macro name. Values are YAML and overrides are applied left to right; a later parent replaces its subtree and a later child changes that result. For example (a manual provider call, subject to the authorization above):

```sh
image-clarus process ./photo.jpg --config ./examples/config.yaml --stages json \
  --set 'stages.json.preferred_categories=[food, food/desserts/cookies]' \
  --set 'prompt_expansion.macros["config.stages.json.preferred_categories"].max_depth=2' \
  --set 'prompt_expansion.macros["state.categories.known"].delimiter="/"' \
  --set 'prompt_expansion.macros["state.categories.known"].max_depth=0' \
  --set stages.json.include_prompt_sha256=true
```

`stages.json.include_prompt_sha256` is a strict boolean, default `false`. When enabled, new JSON includes the SHA-256 of the exact original prompt-file bytes, not the expanded prompt or complete request. Existing artifacts with a valid hash remain accepted; when present the hash must be valid. `prompt_id`, model/provider identifiers, `description_sha256` and custom-schema identity remain supported. Changing this option or prompt does not invalidate an existing output or bypass the normal skip; use `--regenerate` to replace selected JSON explicitly.

## Optional application state

Run `image-clarus init` in the desired collection directory to initialize `.image-clarus/state.sqlite3`; repeat initialization of a valid repository is a no-op. An existing incomplete or invalid directory is not replaced: initialization fails, preserving its contents. Normal processing never creates a persistent repository. State supplements rather than replaces sidecars, and absent persistent state is temporary memory for that invocation only.

Selection is, in order: dedicated `--state-dir DIR`, `--set state.directory=...`, YAML `state.directory`, nearest initialized CWD ancestor, nearest initialized image-directory ancestor, then memory. The explicit directory is `.image-clarus` itself, not its parent. `state.directory` defaults to `null`; `--set state.directory=null` clears a YAML selection and permits discovery. YAML relative paths use the config file directory; CLI paths use CWD; `~` is expanded. The dedicated flag wins over `--set` regardless of argument order.

For example, with initialized `collection/.image-clarus` and `collection/nested/.image-clarus`, processing from `collection/nested` selects the nested repository. From `collection`, it selects the collection repository even when the image is in an unrelated initialized `other` collection: CWD ancestry wins. To share one repository across unrelated collections, select it explicitly:

```sh
# From a directory containing shared and collection; manual provider call.
image-clarus process ./collection/photo.jpg --config ./examples/config.yaml --stages json --state-dir ./shared/.image-clarus
```

Discovery skips an accessible uninitialized `.image-clarus` directory with no database, but a selected corrupt, inaccessible or incompatible repository is an error, not permission to search for another persistent store. Processing reports state errors visibly on stderr even if stages succeed, falls back to invocation-local memory, and does not claim the failed state operation persisted. An `init` failure itself is an error. SQLite shares state across processes with short transactions; it does not lock sidecars or make state and sidecar updates atomic. Protect the state directory as it can contain sensitive category metadata.

`state.accumulate_categories` is a strict boolean and defaults to `true`. After all selected stages finish, completed JSON or JSON skipped because an existing valid envelope was found contributes recognized complete paths, including leaf and single-segment paths; a later selected-stage failure does not undo eligible accumulation. An eligible skipped JSON artifact contributes categories without regeneration, modifying the artifact, or making another model request. Set `--set state.accumulate_categories=false` to disable updates from both new and skipped JSON. Other JSON skips, failures, unselected JSON and interruptions do not contribute. Built-in 2.0.0 and recognized custom identities use the conventional `metadata.tag_candidates` array of segment arrays, independent of XMP mappings; built-in 1.0.0 contributes none. Missing or empty candidates contribute none; malformed candidates or unknown identities reject the optional contribution without changing the primary stage result. Extraction uses the envelope and category shape, not the current payload schema; an envelope-valid skipped JSON can therefore contribute even if unrelated payload fields are missing. State updates preserve full paths regardless of prompt depth, XMP root or tag limit; there is no historical import or automatic taxonomy reconciliation.

## Process one image

Relative paths below assume the checkout directory; otherwise adjust them, including the configuration path. Use a synthetic or otherwise authorized image and JSON. The `desc` and `json` examples below are **manual provider calls**: run only after authorizing the endpoint, model, data transfer and potential costs. Do not commit personal images or device metadata.

```sh
# Manual provider calls: choose only after configuring an authorized endpoint.
image-clarus process ./photo.jpg --config ./examples/config.yaml --stages desc
image-clarus process ./photo.jpg --config ./examples/config.yaml --stages json
image-clarus process ./photo.jpg --config ./examples/config.yaml --stages desc,json
image-clarus process ./photo.jpg --config ./examples/config.yaml --stages json,xmp
image-clarus process ./photo.jpg --config ./examples/config.yaml --stages desc,json,xmp

# Manual provider call: replace prompts and schema independently.
image-clarus process ./photo.jpg --config ./examples/config.yaml --stages desc,json --desc-prompt ./description.txt --json-prompt ./structure.txt --json-schema ./schema.json

# Manual provider call: regenerate the selected description and JSON outputs.
image-clarus process ./photo.jpg --config ./examples/config.yaml --stages desc,json --regenerate
```

For a **provider-free XMP invocation**, install ExifTool first and supply an existing synthetic or authorized `photo.jpg.desc.json` with a supported envelope and payload, beside a readable `photo.jpg`. This example does not generate JSON or contact a provider:

```sh
image-clarus process ./photo.jpg --config ./examples/config.yaml --stages xmp
```

Without `--stages`, all three run in fixed `desc,json,xmp` order; selected subsets run in that order regardless of argument order and never implicitly add prerequisites. The image is not modified. Sidecars use the full image filename: `photo.jpg.desc.txt`, `photo.jpg.desc.json`, and `photo.jpg.xmp`. JSON reads the persisted description; XMP reads persisted JSON and may update an existing XMP sidecar. Missing prerequisites fail by default; `--missing-prerequisite skip` skips the affected stage instead. Invalid or unreadable artifacts are not treated as missing.

Description and JSON outputs are create-only by default. Existing valid outputs are skipped; `--regenerate` permits full replacement of selected `desc` and `json` outputs, not a JSON field merge. It does not override XMP policies. Changes to inputs, model, prompt, schema or category guidance do not automatically trigger regeneration. An existing JSON with a valid fixed envelope can be skipped even if its description is missing or the current payload schema changed; skip does not validate the payload against that schema. Selected-stage configuration and credentials are checked before a skip. Failed or invalid output is not published as complete.

Each stage prints a completed, skipped or failed summary on stdout; diagnostics go to stderr. Exit codes are `0` for success/skips, `1` for stage or authentication failure, `2` for usage/configuration errors, `3` for the search stub, and `130`/`143` for SIGINT/SIGTERM. A missing or unusable ExifTool during selected-stage preflight is a configuration error (exit `2`), before stage summaries.

## Structured JSON and recommendations

New built-in payloads retain `subjects`, `objects`, `actions`, `setting`, `visual_characteristics` and `keywords`, and add required `title`, `caption` and `tag_candidates`. The short caption does not replace the comprehensive description. `""` for title or caption and `[]` for candidates mean unavailable. Candidates are arrays of tag-segment arrays, in descending rank: `[["food", "pepper"], ["plate"]]` represents a categorized assignment and an uncategorized one. The configured XMP root is not part of these JSON paths, and an ancestor is not separately assigned merely because a descendant is selected.

`stages.json.preferred_categories` defaults to `[]`; an ordered list such as `[food, food/desserts/cookies]` is advisory, not evidence or a closed taxonomy. Unlisted categories and uncategorized tags are allowed. Entries must be unique complete paths, each made of nonempty slash-separated segments. Each segment must be valid UTF-8, with no leading/trailing whitespace, `/`, `|`, or C0/C1 controls (including DEL); spelling and case are preserved. The built-in JSON prompt includes the preferences through a macro; a replacement prompt can omit them entirely. Prompt and description hashes do not fingerprint the expanded guidance or complete request.

`stages.xmp.tag_limit` defaults to `10` and accepts any nonnegative integer. XMP validates every candidate before selecting the first N distinct complete paths, without semantic reranking. A concept in two hierarchies counts twice. Custom duplicate paths are deduplicated in first-occurrence order before truncation; duplicates in built-in 2.0.0 are invalid. Zero or an empty candidate list means no tag changes, including under `overwrite`.

The built-in payload schema is identified by `urn:image-clarus:metadata-schema:2.0.0` and version `2.0.0`; this is independent of the application version and the fixed envelope `format_version: 1`. The XMP reader also accepts the exact historical built-in `urn:image-clarus:metadata-schema:1.0.0` / `1.0.0` pair and validates it against its bundled schema. Valid 1.0.0 JSON has no new publication fields; XMP does not repurpose its `keywords`. New 2.0.0 required fields cannot be missing, though supported empty values are no-ops. Unknown/mismatched built-in identity, unsupported envelope, malformed JSON or schema-invalid built-in payload fails publication. Existing-output skip validates the envelope only; successful skip does not imply the XMP consumer will accept the payload.

A custom schema fully replaces the payload schema, not the application envelope; external references, nested `$id` and `$dynamicRef` are restricted. XMP recognizes `urn:image-clarus:custom-metadata-schema` with a `custom-sha256:` version followed by exactly 64 lowercase hexadecimal digits. That identity describes the original schema bytes, not proof of payload conformance. No publication fields are inferred: configure `stages.xmp.custom_title_property`, `custom_caption_property` and/or `custom_tags_property` as literal top-level `metadata` property names. These mappings do not alter built-in mappings. Missing mappings or missing mapped properties are no-ops; mapped title/caption must be strings and mapped tags must be arrays of nonempty valid segment arrays. Supported empty strings/lists are no-ops; present nulls, wrong types and malformed paths fail, including invalid paths beyond the limit. XMP does not read the original custom schema or call a model to repair input.

Schema evolution is independent: incompatible required-field or meaning changes require a major version, compatible optional additions/loosening a minor version, and annotation-only changes a patch. Readers explicitly support exact identities; there is no automatic migration. Regenerate JSON explicitly to replace it, or retain an older compatible artifact. See the [A2 contract](docs/slice-2/IMPL-A2-COMPLETED.md) and the [Slice 1 schema contract](docs/slice-1/IMPL-A3-COMPLETED.md).

## XMP policies and preservation

`stages.xmp.tag_root` defaults to `ai` when omitted; it is one hierarchy segment, not an XML namespace. Explicit `""` means no prefix and is **not** the same as omission. The following table applies only when selected candidates are nonempty:

| Root | `tag_policy` | Effective operation |
| --- | --- | --- |
| Nonempty, including omitted default `ai` | `add` (default) | Union selected exact paths with existing assignments. |
| Nonempty | `new` | Add only if no existing assignment belongs to that exact root segment. |
| Nonempty | `overwrite` | Replace assignments under that exact root only, including manual assignments within it; assignments outside it survive. |
| Nonempty | `disabled` | Leave tags unchanged. |
| Explicit `""` | `add`, `new`, `overwrite` | Effective `add`: union without duplicates; **never delete existing tags**. |
| Explicit `""` | `disabled` | Leave tags unchanged. |

Ownership is case-sensitive by complete root segment: `ai` is not `aisle`. There is no cross-root taxonomy reconciliation or synchronization. Flat keywords and Lightroom hierarchy are not write targets. XMP writes only `XMP-digiKam:TagsList`, `XMP-dc:Title-x-default`, `XMP-dc:Description-x-default`, and, when configured, `XMP-digiKam:CaptionsAuthorNames-x-default`. The Product Owner's manual digiKam checks exercised these mappings; they do not establish compatibility with every digiKam version or XMP structure.

Title, caption and caption author have independent `new`, `overwrite` and `disabled` policies, each defaulting to `new`. For a nonempty available source:

| Policy | Effect for that field |
| --- | --- |
| `new` | Write `x-default` only if all existing language alternatives are absent or empty. Whitespace-only values count as nonempty. |
| `overwrite` | Write only `x-default`, preserving other language alternatives. |
| `disabled` | Leave the field unchanged. |

A missing or supported empty source never clears that field, even under `overwrite`. `stages.xmp.caption_author` defaults to `null`; `null` or `""` leaves all author metadata untouched. A nonempty author is supplied by the user, never inferred from JSON or assumed to identify the photographer. Its policy is `stages.xmp.caption_author_policy`. An unchanged XMP operation is reported as skipped (`no_change`), although required recovery and configured backup cleanup may already have occurred.

The XMP backend checks that unrelated supported metadata and non-default languages are preserved semantically before publication; XML serialization may change. It does **not** support all valid RDF/XMP structures: unsupported structures fail closed rather than being silently discarded. Malformed XMP, invalid input, ExifTool failures or failed preservation checks do not produce a successful update. Recovery validates the XMP container separately and is not full RDF semantic validation.

Writes use the shared artifact service's staged validation, backup and recovery mechanisms; source and artifact alias checks protect the image. The default `pipeline.backup_retention` is `remove`; `retain` keeps backups. There are no application-level locks or conflict detection: concurrent XMP edits can be lost under last-replacement-wins behavior. Filesystem durability varies; this is not a universal crash-proof guarantee.

**Filesystem permissions:** Sidecars and backups can contain sensitive metadata. Some filesystems or mount options cannot enforce private POSIX permissions; check destination access controls, including ACLs, and use a suitably private location. The safe-write service attempts and verifies POSIX modes where supported; unsupported mode semantics produce a privacy warning rather than rejecting an otherwise valid artifact solely for a mode mismatch. Operator testing verified artifact publication on Linux-mounted NTFS/FUSE, including a synthetic create-only probe. This is not exhaustive filesystem or crash-durability verification; native Windows execution is not proven.

## Current limits

Only one image path is accepted; directories, globs, traversal and batches are not implemented. `search --help` works, but `search` reports not implemented and exits `3`. There is no internal scheduler; external schedulers may invoke the CLI. Linux is the required test platform; other operating systems are not claimed as fully tested.

ExifTool synthetic round trips are not digiKam interoperability tests. In manual digiKam 9.1.0 testing, the Product Owner reported successful import, hierarchy filtering, title/caption and author display, and tag edit/readback; **Reread Metadata** was used to refresh the edited sidecar. See the [C3 evidence](docs/slice-2/IMPL-C3-COMPLETED.md) for the observed XMP incompatibility, correction, retest and limitations. External sidecar changes may require a metadata reread or database refresh; do not assume an automatic refresh.

## Project documents

- [Requirements](docs/REQ-image-clarus.md)
- [High-Level Design](docs/HLD-image-clarus.md)
- [Slice 1 implementation plan](docs/slice-1/IMPL-PLAN-slice-1.md) — complete; see the [C5 closeout](docs/slice-1/IMPL-C5-COMPLETED.md)
- [Slice 2 requirements](docs/slice-2/REQ-slice-2.md), [discovery](docs/slice-2/DISCOVERY-slice-2.md), and [implementation plan](docs/slice-2/IMPL-PLAN-slice-2.md) — complete; see the [C5 closeout](docs/slice-2/IMPL-C5-COMPLETED.md) for the accepted prompt-control gap and evidence boundaries
- [Slice 3 requirements](docs/slice-3/REQ-slice-3.md) and [implementation plan](docs/slice-3/IMPL-PLAN-slice-3.md)
