# Step A4 — Freeze configuration, update policies, compatibility, and stage outcomes (COMPLETED)

**Status:** Design complete; no Slice 2 functionality is implemented by this record. A5 and Phases B/C remain pending.

**Scope deviations:** None.

## Files created, updated, and removed

- **Created:** `docs/slice-2/IMPL-A4-COMPLETED.md` (this record).
- **Updated:** `docs/slice-2/IMPL-PLAN-slice-2.md`, `docs/slice-2/IMPL-A2-COMPLETED.md`, `docs/slice-2/IMPL-A3-COMPLETED.md`, `docs/HLD-image-clarus.md`, `pyproject.toml`, `uv.lock`, `tests/unit/test_cli.py`, `tests/unit/test_resources.py`.
- **Removed:** None. No production functionality, schema, prompt or public fixture was changed.

## Configuration and CLI contract

The existing built-ins, single selected YAML file, typed YAML `--set` syntax and precedence remain: built-ins < selected YAML < repeatable `--set` in order (last assignment wins) < existing applicable dedicated flags. Add these leaves under the existing `stages` mapping; they are **design**, not current executable behavior.

| Key | Default | Exact validation and meaning |
| --- | --- | --- |
| `stages.json.preferred_categories` | `[]` | YAML list of unique exact A2 tag segments, order retained. Empty list is no preference. |
| `stages.xmp.tag_root` | `"ai"` | A2-valid single tag segment or explicitly `""`; null and other types invalid. |
| `stages.xmp.tag_limit` | `10` | Nonnegative integer; booleans and floats invalid. Zero means no tag changes. |
| `stages.xmp.tag_policy` | `add` | One of `add`, `new`, `overwrite`, `disabled`. |
| `stages.xmp.title_policy` | `new` | One of `new`, `overwrite`, `disabled`. |
| `stages.xmp.caption_policy` | `new` | One of `new`, `overwrite`, `disabled`. |
| `stages.xmp.caption_author` | `null` | Optional UTF-8 string; null or `""` is unavailable/no-op. Nonempty strings are preserved as supplied, not trimmed; backend representability is validated before writing. |
| `stages.xmp.caption_author_policy` | `new` | One of `new`, `overwrite`, `disabled`. |
| `stages.xmp.custom_title_property` | `null` | Null disables mapping; otherwise a nonempty valid UTF-8 literal top-level `metadata` property name. |
| `stages.xmp.custom_caption_property` | `null` | Same, independently selecting the caption property. |
| `stages.xmp.custom_tags_property` | `null` | Same, independently selecting the ranked path-list property. |

An A2 segment is a nonempty valid UTF-8 string without leading/trailing Unicode whitespace, `/`, `|`, C0/C1 controls or DEL; do not trim, case-fold, normalize or silently split. Category duplicates are exact-string duplicates; case variants remain distinct. Custom property names are literal keys, not dotted paths, JSON Pointers, array indices or expressions. Duplicate role mappings are allowed, but each mapped value must satisfy each role's own type. Do not log user-supplied keys, categories or metadata values in diagnostics.

Example shell arguments, using fictional values and preserving inner YAML quotes:

```sh
--set 'stages.xmp.tag_root=""'
--set 'stages.json.preferred_categories=["architecture", "wildlife"]'
--set 'stages.xmp.custom_title_property="headline"'
```

The existing parser rejects `--set stages.xmp.tag_root=` because the value is missing; the first example passes the two YAML quote characters as the value, yielding an actual empty string. Quoted `"ai"`, `[]`, nonnegative numbers and policy literals use the same YAML parsing as file values. No new dedicated flags are required. The complete proposed YAML overlay below is illustrative, not an edited sample config:

```yaml
stages:
  json:
    preferred_categories: [architecture, wildlife]
  xmp:
    tag_root: ""
    tag_limit: 10
    tag_policy: add
    title_policy: new
    caption_policy: new
    caption_author: null
    caption_author_policy: new
    custom_title_property: headline
    custom_caption_property: null
    custom_tags_property: null
```

Globally parse YAML, reject duplicate or unknown keys and invalid override syntax, and validate global `pipeline`/`logging` and global structural boundaries. Stage-specific **values and stage mapping shape** are validated only for selected stages after overrides: an invalid unused `stages.xmp` value cannot block `desc` or `json`, and an invalid unused JSON category list cannot block `xmp`. Known invalid stage values may be superseded by a higher-precedence override. Unknown keys in any layer remain errors even for an unselected stage; this inherited structural check does not inspect or require ExifTool. B1 must adapt the current global `_validate_shape` implementation rather than pretending it already has these semantics. Selected `json` validates its categories and model/provider; selected `xmp` validates only its XMP values, discovers ExifTool on PATH with the A3 timeout/boundary, and requires no model, provider, credential, description, prompt or schema file. Preflight all selected stages before running any stage. Missing/unusable ExifTool during selected-stage preflight is a sanitized `configuration` error and process exit 2, with no stage summaries; a subsequent runtime tool disappearance/failure is a stage failure.

## Fixed policy behavior

The XMP root is a single tag segment, not an XML namespace. Omission gives `ai`; the literal empty string gives no prefix. The resolved configuration retains the literal value, not an `or`-defaulted value. For all rows below, an empty recommendation list or top-N zero is a no-op and never clears tags.

| Root | Configured policy | Effective operation |
| --- | --- | --- |
| Omitted (`ai`) or explicit nonempty | `disabled` | No tag update. |
| Omitted (`ai`) or explicit nonempty | `add` | Union selected exact paths with existing assignments. |
| Omitted (`ai`) or explicit nonempty | `new` | Union selected paths only if no existing assignment belongs to that exact root segment. |
| Omitted (`ai`) or explicit nonempty | `overwrite` | Replace assignments only within that exact root with selected paths. |
| Explicit `""` | `disabled` | No tag update. |
| Explicit `""` | `add`, `new`, `overwrite` | Additive union only; never delete existing assignments. |

Tag ownership and preservation follow A3; do not compare other roots' taxonomies or delete ambiguous flat keywords. Title, caption and configured author policies operate independently. For each, a source absent, null only where explicitly permitted by configuration, or supported empty string is unavailable and never clears metadata. For a present, nonempty source: `disabled` does nothing; `new` writes `x-default` only when all existing language alternatives for that property are absent or empty; `overwrite` writes only `x-default`. Whitespace-only existing values are nonempty, since silently trimming changes user metadata. Non-default language alternatives always survive. An unconfigured author leaves all author metadata untouched; it is never inferred from JSON.

## JSON input, compatibility, selection and stage results

The XMP stage independently reads `<image>.desc.json` after the existing recovery rules. Strictly parse UTF-8 JSON with the inherited duplicate-key, nonfinite-number and invalid-Unicode rejection; validate the fixed format-1 envelope and provenance as in Slice 1 A3/A2. Recognize exact built-in pairs `urn:image-clarus:metadata-schema:1.0.0` / `1.0.0` and `urn:image-clarus:metadata-schema:2.0.0` / `2.0.0`; validate against their respective bundled immutable validators. A valid 1.0.0 payload has no publication fields and does not repurpose `keywords`; a valid 2.0.0 payload maps the fixed A2 `title`, `caption`, `tag_candidates` fields. Built-in 2.0.0 fields are required: a missing one fails its schema, not an optional-field no-op. Supported empty string/list is a no-op. Unknown or mismatched built-in identities, unknown envelope versions, malformed envelopes and invalid built-in payloads fail as `invalid_artifact` with a sanitized actionable message.

Recognize the existing custom ID `urn:image-clarus:custom-metadata-schema` only when `schema_version` is `custom-sha256:` followed by exactly 64 lowercase hexadecimal digits. This identifies the original schema bytes, not proof of payload conformance. Do not access a current user schema to publish historical JSON. Only explicitly configured custom-property names select values from the `metadata` object; mapping settings never change built-in mapping. Omitted mapping or missing mapped property is unavailable/no-op; present mapped title/caption must be UTF-8 strings (`""` means unavailable), and present mapped tags must be an array of nonempty A2-valid segment arrays (`[]` means none). Null, wrong types, malformed or unrepresentable present data fail as `invalid_artifact`, including invalid tag paths beyond top-N. Exact duplicate custom paths are deduplicated before truncation, keeping the first; built-in duplicates fail its schema. Validate all present candidate paths before dedupe and selection; select first N in stored rank order. Do not infer arbitrary names, semantically repair input or call a model.

Missing JSON invokes `pipeline.missing_prerequisite`: `fail` produces `failed` / `missing_prerequisite`; `skip` produces `skipped` / `missing_prerequisite`. A present but unreadable file uses `file_io`; invalid or incompatible input fails rather than being skipped. An unchanged valid operation is `skipped` / `no_change`, with no new sidecar or backup churn. A safely published change is `completed` with the XMP output path. ExifTool runtime failures, malformed XMP, unexpected mutation or preservation failure produce a sanitized `invalid_artifact`; timeout produces `network_timeout` only for actual network operations, so an ExifTool timeout instead uses `file_io` with a sanitized timeout message. Filesystem failures use `file_io`. Diagnostics do not include raw tool output, user metadata, schema property values or secrets. Selected XMP does not auto-run `json` or `desc`.

CLI selected stages become the fixed `desc,json,xmp` registry in that order regardless of argument ordering; no `--stages` selects all three. Explicit subsets run independently, without expanding prerequisites. `--regenerate` sets regeneration for selected `desc` and `json` only; it does not add a `stages.xmp.regenerate` key or alter any XMP policy. Existing JSON skip checks the fixed envelope only before prerequisites; regeneration replaces the whole artifact, with no field merge. The current CLI output line shape and path redaction remain. A failed stage gives exit 1, all completed/skipped gives 0, invalid usage/configuration gives 2, existing authentication preflight gives 1, `search` stub gives 3, and signal exit 130/143 takes precedence. `pipeline.on_stage_failure` retains stop/continue and downstream results; no additional exit type is introduced.

## Implementation test matrix

B1–B5 must add observed RED/GREEN tests for: omitted root, explicit YAML empty root and quoted `--set` empty root; higher-precedence override and repeated overrides; category list ordering/duplicates/invalid segments; policy and integer type validation including boolean; malformed selected and unused stage values, unknown global and unselected keys; no ExifTool/model requirement for unrelated stages. Test all root/policy rows and repeated invocation; default/empty/localized-only title/caption/author under each policy; null and empty author; non-default language preservation; and no deletion when candidates absent or limit zero.

Test exact old/new schema pairs, mismatched or unknown built-in identity, invalid 2.0.0 payload, strict JSON failures, valid custom ID/hash, no custom mapping, mapped-but-missing and malformed values, literal property names, duplicates and invalid candidate beyond cutoff. Cover missing artifact fail/skip, runtime tool failure and timeout, preflight missing tool, invalid XMP and publication failure; `no_change` versus `completed` and no backup churn. Cover every stage subset, default selection, JSON skip with missing description, `--regenerate` with XMP `new`/`disabled`, stop/continue and signals. Use only synthetic values and keep fake-tool, real ExifTool and C3 digiKam evidence separate.

## Acceptance

- [x] Config defaults, override parsing, key-level validation and policy truth tables are exact and match the Slice 2 REQ without reopening product choices.
- [x] Missing artifact, absent/empty optional fields and malformed/incompatible JSON have distinct specified outcomes; old/custom JSON mapping is safe and explicit.
- [x] Stage `xmp` has no model dependency; unused XMP configuration/ExifTool cannot block unrelated selected stages.
- [x] Title/caption/author updates and `--regenerate` interactions are defined without accidental deletion or inferred identity.
- [x] A4 completion record and plan checkoffs are synchronized.

## Verification and limits

The YAML example and shell-preserved empty-root override are checked as design data, not as implemented Slice 2 behavior. `config.py`, `cli.py`, `pipeline.py`, `results.py` and `stages/structure.py` were inspected; A4 explicitly identifies where the current implementation must change. Application version advances to `0.1.18`; targeted version/resource regression checks are separate from the design assertions. No provider, ExifTool, digiKam or full application suite was run for A4, and no Git commands were run.
