# Step A1 — Confirm package layout, runtime, and development tools (COMPLETED)

**Status:** ✅ Complete
**Scope deviations:** None
**Files Created/Updated/Removed:**
- Created: `docs/slice-1/IMPL-A1-COMPLETED.md`
- Updated: `docs/slice-1/IMPL-PLAN-slice-1.md`
- Removed: None

---

## Summary

Completed Phase A1 as a design-only step. The Slice 1 package layout, module ownership, build backend, runtime/development dependencies, application-version source, bundled-asset strategy, fixture policy, and verification commands are now fixed in the plan. No production code, tests, package metadata, lockfile, or examples were created. Step A2 has not started.

## Decision record

### Package and application version

- Distribution name: `image-clarus`; import package: `image_clarus`.
- Use a `src/image_clarus/` package layout and `tests/unit/`, `tests/integration/`, and `tests/fixtures/` directories.
- `pyproject.toml` is the sole authoritative application-version source: static `[project].version = "0.1.0"`. Use SemVer; Slice 1 releases remain on `0.1.x`.
- The console script target is `image-clarus = "image_clarus.cli:main"`.
- Read the installed distribution version with stdlib `importlib.metadata.version("image-clarus")`; do not keep a duplicate version constant in package source.
- A2 still owns the exact user-visible `--version` behavior and output. No A2 decision or implementation was performed here.

### Build and dependencies

- Build backend: Hatchling, configured in `pyproject.toml`. The wheel force-includes canonical root assets as package resources, avoiding a second maintained copy. See [Hatchling build configuration](https://hatch.pypa.io/1.9/config/build/).
- Supported Python: `requires-python = ">=3.12"`; pin the development baseline to `3.13` in `.python-version`.
- Generate `uv.lock` in B1 and commit it; A1 does not create a lockfile because no `pyproject.toml` exists yet.
- Runtime: stdlib `argparse` (no added CLI dependency), `PyYAML` (YAML), `jsonschema` (schema validation), and synchronous `httpx` (HTTP).
- Development extra: `pytest` and `ruff` for tests, lint, and formatting. No type checker, coverage gate, image-processing dependency, provider framework, or ExifTool dependency is added for Slice 1.
- Declare Apache-2.0 project metadata and reference the existing `LICENSE`. The repository has no separate `NOTICE` file; no new notice file is added by A1.

### Module ownership and bundled assets

- `__main__.py` delegates to `cli.main`; `cli.py` owns `argparse` construction and dispatch, while A2 owns the exact command contract.
- `config.py` resolves and validates configuration; `results.py` defines shared outcomes; `pipeline.py` owns the ordered built-in stage registry and coordinator; `artifacts.py` owns safe sidecar access/recovery.
- `resources.py` locates built-in prompts/schemas from the source tree or through stdlib `importlib.resources`; it does not resolve user overrides.
- `providers/openai_compatible.py` owns synchronous HTTP transport; `stages/description.py` and `stages/structure.py` own the `desc` and `json` stages.
- Keep `prompts/image-description.txt` as the canonical description source. Hatchling maps it to `image_clarus/resources/prompts/image-description.txt` in the wheel. A3 owns the JSON prompt/schema source filenames; B7 maps the A3-selected root paths into the matching `image_clarus/resources/prompts/` and `image_clarus/resources/schemas/` subdirectories. `resources.py` resolves package resources after installation and the root asset during source development; B1 tests both paths.
- Defer `examples/config.yaml` until B9, after A2 freezes configuration keys.
- Test data is synthetic: YAML/schema/description/provider-response fixtures only. Create image input files under pytest `tmp_path`; do not commit real photos or identifying metadata.

### Selected commands

After B1 creates the project metadata and lockfile:

```text
uv lock
uv sync --locked --extra dev --python 3.13
uv run --locked --extra dev pytest <target>
uv run --locked --extra dev pytest
uv run --locked --extra dev ruff check .
uv run --locked --extra dev ruff format --check .
uv run --locked --extra dev ruff format .
uv build --python 3.13
```

Python compatibility checks use:

```text
uv sync --locked --extra dev --python 3.12
uv run --locked --extra dev --python 3.12 pytest
uv sync --locked --extra dev --python 3.13
uv run --locked --extra dev --python 3.13 pytest
```

The formatter write command is run only when formatting changes are needed. C3 records actual interpreter availability and leaves any unrun compatibility row unchecked.

## Acceptance

- [x] Runtime, development, and test dependencies are explicitly selected with rationale; no choice is presented as already installed.
- [x] Package layout, module ownership, built-in resource lookup, and console-script name are exact and consistent with `image-clarus`.
- [x] Initial Slice 1 application version is `0.1.0`, the Slice 1 version line is `0.1.x`, and the sole authoritative package-version source is recorded.
- [x] Python 3.12+ support, Python 3.13 baseline, Linux validation, `uv`, and committed lockfile are preserved as plan decisions; lockfile generation remains a B1 deliverable.
- [x] No extra architecture or dependency is introduced without a Slice 1 requirement.
- [x] This completion record exists, records created/updated/removed files, and is linked from Step A1.

## Verification and environment notes

- Confirmed the repository is still greenfield: no `pyproject.toml`, `uv.lock`, package source, or tests exist yet. Existing `LICENSE` is Apache License 2.0; the canonical prompt remains `prompts/image-description.txt`.
- `uv --version` returned `uv 0.12.6`.
- The available interpreters are Python 3.14.9, 3.11.16, and 3.9.25; Python 3.12 and 3.13 are not currently installed. No interpreter was installed during A1. This does not block the design decision; obtain/provision the required interpreters before the C3 runtime matrix or record the precise blocker there.
- No application tests or build were run because implementation has not started. Repository/toolchain discovery was read-only; documentation updates were design artifacts only.

## Follow-ups

- Step A2 remains the next Phase A step and was not started, per the user’s boundary.
- B1 must create `.python-version` containing `3.13`, `pyproject.toml`, `uv.lock`, the package scaffold and resource lookup, tests, and `.gitignore` entries for `.venv/`, `dist/`, `build/`, `*.egg-info/`, `__pycache__/`, `.pytest_cache/`, and `.ruff_cache/` while preserving existing ignore patterns. The repository owner commits `uv.lock` with the implementation work.
