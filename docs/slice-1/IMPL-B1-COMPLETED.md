# Step B1 — Bootstrap the installable Python package and test harness (PARTIAL)

**Status:** Functional review corrections complete; B1 remains partial pending Product Owner disposition of the test-first process deviation.
**Scope deviations:** None. No pipeline, provider, configuration resolution, or search behavior was implemented. **Process deviation:** the installed-wheel resource/entrypoint test was added after packaging implementation, without observed RED evidence; no exception approval has been recorded.
**Files Created/Updated/Removed:**
- Created: `.python-version`, `pyproject.toml`, `uv.lock`, `src/image_clarus/__init__.py`, `src/image_clarus/__main__.py`, `src/image_clarus/cli.py`, `src/image_clarus/resources.py`, `tests/unit/test_cli.py`, `tests/unit/test_resources.py`, and this record.
- Updated: `.gitignore`, `README.md`, and `docs/slice-1/IMPL-PLAN-slice-1.md`.
- Removed: None.
- Generated locally: ignored `.venv/`, `dist/`, and tool caches; these are not source artifacts.

## Summary

Established the Hatchling package, `0.1.0` authoritative static metadata and installed console script, Python 3.13 development pin, 3.12+ support declaration, selected dependencies, and lockfile. The CLI provides help, the metadata-backed version, and the specified search stub. `process` reports not implemented until B8. The resource accessor prefers installed package data and falls back to the canonical checkout prompt. Hatchling packages that same prompt without another maintained copy.

## Test and build evidence

- Provisioned CPython 3.13.15 with `uv python install 3.13`; `uv 0.12.6` generated the lockfile. `uv lock --check` passed.
- RED: after dependency-only `uv sync --locked --extra dev --python 3.13 --no-install-project`, `uv run --no-sync --locked --extra dev pytest tests/unit/test_cli.py::test_top_level_help_lists_subcommands -q` failed because `image_clarus` did not yet exist. Minimal package/help implementation then passed that test.
- RED: CLI tests exposed missing process help, search stub, and version (3 failed, 2 passed); after implementation and locked project installation, all 5 CLI tests passed. The source-resource test failed before `resources.py` existed, then passed after implementation. The installed-wheel resource/entrypoint test was added as verification after packaging was implemented; it was not independently observed failing first.
- Patch 014 version-error regression: running `uv run --locked --extra dev pytest tests/unit/test_cli.py::test_version_missing_metadata_is_configuration_error -q` against the original implementation failed because missing distribution metadata produced exit 1 and a traceback. After the correction, the same test passed and asserts exit 2, empty stdout, and a fixed sanitized stderr diagnostic; no version fallback is used.
- `uv build --python 3.13` built an sdist and a wheel. The tests build and install a wheel in a separate virtual environment, run outside the checkout without `PYTHONPATH`, compare the prompt bytes with the canonical source, and invoke the installed console entry point. That isolated installation uses `--no-deps` because the exercised B1 CLI and resource paths use only the standard library; normal dependency installation was verified by the locked project sync.
- Python 3.13 full pytest suite after Patch 014: **8 passed**. `ruff check .`, `ruff format --check .`, `uv lock --check`, and `uv build --python 3.13` passed. The installed-wheel test verifies `image-clarus --version` prints `image-clarus 0.1.0`. Python 3.12 compatibility testing remains C3 work, not a claim of this step.
- The bootstrap runtime uses Python standard-library CLI/resource/version facilities; the build and test workflow uses `uv` and the selected development tools. No external image/provider executable is invoked.

## Acceptance

- [x] The package installs in an isolated Linux environment and exposes `image-clarus`.
- [x] `uv.lock` is present and consistent with `pyproject.toml`.
- [x] The canonical description prompt is available through `resources.py` from the source tree and installed wheel without a duplicated maintained copy.
- [x] Python 3.12+ is declared and Python 3.13 is used for the development baseline.
- [x] Installed `image-clarus --version` prints the A2-defined version, initially `image-clarus 0.1.0`, from the authoritative package version source.
- [x] Top-level help lists `process` and `search`; both subcommand help surfaces work, and executing `search` reports not implemented as specified in A2.
- [x] No external executable is required.
- [ ] RED and GREEN evidence is recorded and all current tests/quality checks pass.
- [ ] [IMPL-B1-COMPLETED.md](IMPL-B1-COMPLETED.md) is complete and linked.

## Follow-up

The wheel integration test's missing original RED evidence cannot be reconstructed. A Product Owner decision is needed on accepting that process deviation before B1 is marked complete. B2–B9 and Phase C remain unstarted. B8 owns real `process` behavior; C3 owns the Python 3.12 compatibility matrix.
