# Step A1 — Confirm package layout, runtime, and development tools (COMPLETED)

**Status:** ✅ Complete
**Scope deviations:** None
**Files Created/Updated/Removed:**
- Created: `docs/slice-1/IMPL-A1-COMPLETED.md`
- Updated: `docs/slice-1/IMPL-PLAN-slice-1.md`
- Removed: None

---

## Summary

Completed Phase A1 as a design-only step. The Slice 1 package layout, module ownership, build backend, runtime/development dependencies, application-version source, bundled-asset strategy, fixture policy, and verification commands are now fixed in the plan. No production code, tests, package metadata, lockfile, or examples were created. At A1 closeout, Step A2 had not started.

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

### Decision rationale and provenance

The project/user requirements established the YAML preference, HTTP provider boundary, shared resolved-configuration architecture, minimal-dependency posture, and SemVer versioning with Slice 1 starting at `0.1.0` on `0.1.x`. The specific Python libraries and Hatchling were selected by Hermes during A1; the rationales below explain those selections, not prior discussion or user approval of each package.

| Decision | Provenance | Rationale |
| --- | --- | --- |
| Python 3.12+; Python 3.13 development baseline | Project requirement | Keeps 3.12 installations supported while standardizing development on 3.13 and testing compatibility separately. |
| YAML; PyYAML parser | YAML is the established user preference; PyYAML is the A1 implementation choice | Uses the requested familiar configuration format with a small, established parser. |
| `argparse` | A1 choice by Hermes | Standard library support is sufficient for the agreed subcommands/help surface without adding a CLI dependency; no need for Click/Typer at this scope. |
| Synchronous `httpx` | Provider architecture is established; library choice by Hermes | Supports local/remote HTTP endpoints, timeouts, and test transports while matching the synchronous single-image pipeline; avoids coupling to a provider SDK. |
| `jsonschema` | A1 choice by Hermes | Validates generated metadata against the built-in contract and full user-supplied schema replacements instead of adding bespoke validation logic. |
| `uv` and committed `uv.lock` | Project requirement | Provides repeatable dependency resolution and isolated development/test environments. |
| pytest and Ruff | A1 choices by Hermes | Cover automated tests, lint, and formatting with one focused test tool and one focused quality tool; no separate type-check or coverage infrastructure is justified for Slice 1. |
| Static version in `pyproject.toml`; `importlib.metadata` retrieval | User established SemVer, `0.1.0`/`0.1.x`, and one authoritative source; A1 selected the mechanism | A single static metadata value avoids duplicated constants and reads the version from the installed distribution. |
| Hatchling | A1 choice by Hermes | Its wheel `force-include` mapping packages the canonical root prompt as an application resource without a second maintained copy or custom packaging script. |

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

- At A1 closeout, Step A2 had not started; it was completed subsequently in [IMPL-A2-COMPLETED.md](IMPL-A2-COMPLETED.md).
- B1 was tasked with creating `.python-version` containing `3.13`, `pyproject.toml`, `uv.lock`, the package scaffold and resource lookup, tests, and `.gitignore` entries for `.venv/`, `dist/`, `build/`, `*.egg-info/`, `__pycache__/`, `.pytest_cache/`, and `.ruff_cache/` while preserving existing ignore patterns. The repository owner commits `uv.lock` with implementation work.

**Subsequent progress:** Steps A2–A6, B1–B9, and C1–C5 are complete; the final acceptance crosswalk and current lock/version verification are in [C5](IMPL-C5-COMPLETED.md). Commit state remains repository-owner-controlled and was not inspected.
