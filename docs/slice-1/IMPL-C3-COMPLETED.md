# Step C3 — Run Linux package and quality gates (COMPLETED)

**Status:** Complete.

**Scope deviations:** None. The authorized real-provider quality smoke test remains [C4](IMPL-PLAN-slice-1.md#step-c4--perform-an-authorized-real-provider-quality-smoke-test-manualtest).

**Files created:** `docs/slice-1/IMPL-C3-COMPLETED.md` (this record).

**Files updated:** `docs/slice-1/IMPL-PLAN-slice-1.md`, `docs/slice-1/IMPL-C2-COMPLETED.md`.

**Files removed:** None.

## Environment and commands

Linux `5.14.0-687.46.1.el9_8.x86_64`, x86_64; `uv 0.12.6`. The development baseline was CPython **3.13.15** and the declared minimum was exercised with CPython **3.12.14**. Each `uv sync` below used a separate, newly created `UV_PROJECT_ENVIRONMENT` under the agent scratch directory; neither reused nor replaced the project `.venv`.

| Command | Result |
| --- | --- |
| `uv sync --locked --extra dev --python 3.13` | Passed in the clean Python 3.13 environment. |
| `uv lock --locked` | Passed; 21 packages resolved. |
| `uv run --locked --extra dev --python 3.13 pytest` | **410 passed**. |
| `uv run --locked --extra dev --python 3.13 ruff check .` | Passed. |
| `uv run --locked --extra dev --python 3.13 ruff format --check .` | Passed. |
| `uv build --python 3.13` | Source distribution and wheel built successfully. |
| `uv sync --locked --extra dev --python 3.12` | Passed in the clean Python 3.12 environment. |
| `uv run --locked --extra dev --python 3.12 pytest` | **410 passed**; an independent rerun in the same environment also passed **410 tests**. |

The test scratch filesystem was reported as XFS. The repository filesystem was reported as `fuseblk` in the parent environment; the separate Python 3.13 worker reported `virtiofs`. These are environment-specific observations, not evidence of a cross-filesystem or portability matrix. C2 records its explicit XFS/tmpfs fault evidence.

A separately built wheel was installed with normal dependencies in a fresh Python 3.13 virtual environment. From outside the checkout and with `PYTHONPATH` unset, `importlib.metadata.version("image-clarus")` matched `pyproject.toml` at **0.1.0**; the installed console entry printed exactly `image-clarus 0.1.0`, and top-level, process and search help passed. Bare `search` produced the exact stderr line `search is not implemented in Slice 1` and exit 3.

The installed wheel also ran both stages against a synthetic local HTTP provider with an empty `PATH`, producing both expected sidecars and valid synthetic metadata. Production source inspection found the schema worker invokes `sys.executable`; this is a Python subprocess, not an external application such as ExifTool. The probe verifies the exercised path, not every possible system environment. No live provider, real credential or personal image was used. C4 has not been executed.

## Acceptance

- [x] Clean locked install succeeds on Linux.
- [x] All tests and selected quality gates pass on Python 3.13.
- [x] Python 3.12 compatibility is actually exercised, or remains explicitly unchecked with its blocker.
- [x] Installed `image-clarus --version` matches the authoritative package metadata and prints the initial `image-clarus 0.1.0` value.
- [x] `image-clarus` entry point and top-level, process, and search help work from the installed package; executing `search` reports not implemented.
- [x] No external executable is required for Slice 1.
- [x] [IMPL-C3-COMPLETED.md](IMPL-C3-COMPLETED.md) is complete and linked.

C4 and later steps have not been started as part of C3.
