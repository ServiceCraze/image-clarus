# Step B1 — Extend configuration and selected-stage validation (COMPLETED)

**Status:** Complete. B1 implements configuration resolution and isolated XMP preflight only. JSON generation enhancements, XMP policy execution, publication and CLI stage integration remain B2–B5 work.

**Scope deviations:** None. The application's patch version is `0.1.20`.

## Files created, updated, and removed

- **Created:** `tests/unit/test_slice2_config.py` and `docs/slice-2/IMPL-B1-COMPLETED.md`.
- **Updated:** `src/image_clarus/config.py`, `tests/unit/test_config.py`, `tests/unit/test_cli_config_acceptance.py`, `tests/unit/test_config_diagnostics.py`, `tests/unit/test_reasoning_effort_diagnostics.py`, `tests/unit/test_cli.py`, `tests/unit/test_resources.py`, `docs/slice-2/IMPL-PLAN-slice-2.md`, `docs/slice-2/IMPL-A5-COMPLETED.md`, `pyproject.toml`, and `uv.lock`.
- **Removed:** None. Version-test changes track the package patch increment. Legacy test expectations were reconciled with A4's explicit selected-stage isolation; they continue to test invalid selected-stage values and global unknown keys rather than simply deleting coverage.

## Work and decisions

- Added all A4 XMP defaults, JSON preferred categories, strict segment/UTF-8 checks, valid policy and integer types, optional author and literal custom-property mappings. YAML, defaults and ordered typed `--set` overrides preserve explicit empty root independently of omitted root. Unknown schema keys and nested unknown override paths are rejected without disclosing untrusted names.
- Stage-specific value and shape validation applies to selected stages; global structure and unknown-key validation continue. XMP selection uses an isolated ExifTool preflight without a model, credential, description or schema file. Other stages do not require ExifTool. The subprocess probe is shell-free, suppresses implicit tool configuration, bounds time and output, checks a version response, and sanitizes errors. The tested Linux timeout uses a shortened test deadline with an actual disposable process, not a 30-second wait.
- `regenerate=True` affects selected `desc`/`json`, not XMP settings. B4/B5 own actual XMP policy and CLI behavior. Existing higher-precedence dedicated `missing_prerequisite` behavior repairs a lower-priority malformed pipeline mapping; an audit suggestion to reject this was not adopted because an existing regression test explicitly establishes that precedence behavior.
- The existing CLI still registers only `desc,json`: the XMP preflight was exercised directly via `resolve_config`, not through a nonexistent XMP CLI. ExifTool sidecar writes and digiKam interoperability were not tested in B1.

## Test-first evidence

All commands below use `uv run --locked --extra dev --python 3.13 pytest -q` followed by the named selector in `tests/unit/test_slice2_config.py`:

| Behavior | Observed RED | Observed GREEN |
| --- | --- | --- |
| `::test_slice2_defaults_and_typed_root_precedence` | 1 failed | 1 passed |
| `::test_xmp_preflight_ignores_unused_stage_shapes_and_needs_no_model` | 1 failed | 1 passed |
| `::test_xmp_invalid_values_fail_before_tool_discovery` | 10 failed, 4 passed after correcting false-positive assertions | 14 passed |
| `::test_selected_json_rejects_invalid_categories` | 5 failed | 5 passed |

Additional cases were added as supplemental coverage; they are not represented as individually observed RED. An independent audit then found unknown nested override paths and a zero-output executable falsely accepted as ExifTool. Running the three parameterized `::test_unknown_nested_override_is_rejected_in_each_layer` cases plus `::test_exiftool_probe_rejects_executable_with_no_version` produced **4 failures** before their fixes; the same cases passed afterward. A fifth proposed audit test failed, but was revised to preserve the established dedicated-flag precedence instead of treating that expected behavior as a defect. Oversized tool output is supplemental coverage. Five old tests initially failed because they expected invalid unselected stage values to block a selected stage; those expectations were updated to the A4 contract while retaining selected-stage diagnostics.

## Verification

- `uv run --locked --extra dev --python 3.13 pytest -q tests/unit/test_slice2_config.py` — **40 passed**.
- `uv run --locked --extra dev --python 3.13 pytest -q` — **579 passed** on Python 3.13.
- `uv lock --locked`, Ruff check and Ruff format check on all changed Python files passed; `uv run --locked --python 3.13 image-clarus --version` reported `image-clarus 0.1.20`.
- A selected `xmp` `resolve_config` preflight using a temporary real ExifTool 13.64 executable passed and returned default root `ai`. This is dependency detection, not an XMP backend, digiKam interoperability or real image test.
- The first full suite after the worker's implementation reported five failures from superseded unselected-stage expectations; the reconciled full suite above passed. The first format check found two formatting issues; both were corrected and the recorded rerun passed. No Git commands were run.

## Acceptance

- [x] Configuration precedence and omitted/explicit-empty root values and policy settings pass resolution/validation examples.
- [x] `desc`/`json` do not depend on XMP-specific preflight or ExifTool; isolated XMP preflight does not require model/provider selection.
- [x] Optional author and policy settings resolve without inventing destructive overrides; B4/B5 verify actual XMP behavior.
- [x] Observed RED/GREEN, regression and completion record evidence are linked.
