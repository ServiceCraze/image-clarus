# Step M4 - Document Slice 4 usage and compatibility [DOCS]

**Status:** Documentation work complete and ready for review. Review acceptance and Slice 4 final verification/closeout are separate; Phase C has not been started.

**Version:** 0.3.53

**Scope deviations:** None.

## Changes

- Updated `README.md` with native file/directory/pattern selection, quoted case-insensitive patterns for processing and rebuild, recursion and extension rules, dry-run planning, budget classes, corrections, non-LLM stages, progress and memory estimate limitations. The 10,000-image example states its admission and outcome assumptions.
- Documented concurrent/sequential behavior, failure policy, interruption and resume, per-image processing state, strict category-management target selection, additive rebuild and explicit clear-then-rebuild, partial outcomes, exits and sidecar concurrency limitations.
- Updated `examples/config.yaml` with selection, independent rebuild depth, work allowance and concurrency defaults. The example intentionally omits `missing_prerequisite` so its contextual single-file/batch default remains active. Example provider and model values are fictional; no credential is stored.
- Reconciled current Slice 4 status in `docs/REQ-image-clarus.md` and `docs/HLD-image-clarus.md`, preserving historical records and distinguishing implementation progress from draft requirements and later verification.
- Updated `pyproject.toml`, `uv.lock`, this plan, and this completion record. No production source or historical Slice 1–3 completion record was changed.

## Verification

- In isolated tool and home directories, ran `uv tool install --python 3.13 .` and `uv tool install --python 3.13 --force --reinstall .`; from outside the checkout the installed CLI reported `image-clarus 0.3.53` and all documented help entries succeeded. `search` returned the documented stub message and exit 3.
- Executed all three documented batch dry-run examples with synthetic images, copied sample config and a synthetic environment credential: completed plans contained 2, 2 and 3 images respectively. Executed documented `init`, list, quoted-pattern rebuild, clear and directory rebuild on a disposable empty store; all returned 0. No provider or ExifTool was called.
- `uv sync --locked` and documented project-environment version and help commands succeeded; restored development dependencies with `uv sync --locked --extra dev` after the default sync removed them. Sample YAML parsing and selected-stage preflight passed with a synthetic environment value; its provider stores only the environment-variable name, and contextual missing-prerequisite defaults were checked for single and batch selections.
- `uv run --no-sync --locked pytest -q -p no:cacheprovider` — **1,814 passed, 67 skipped**. `uv lock --check`, Ruff check and formatting passed; 205 files formatted. These are regression checks, not proof of every documentation assertion.
- Targeted privacy and local-link/whitespace checks cover the changed public artifacts. Provider-dependent examples remain manual; no live provider or user image was used. Search/installation examples were exercised in isolated directories, not the user's shell configuration.

## Acceptance

- [x] Documented options and examples match implemented behavior and current defaults.
- [x] Admission, correction, non-LLM routing, memory-estimate and category-rebuild semantics are explicit and accurate.
- [x] Current parent docs distinguish implementation progress from acceptance; historical Slice 1–3 records remain intact.
- [x] Public examples contain fictitious data and no sensitive infrastructure identifiers or credentials.

## Evidence limits

The documented 10,000-image scenario is an explained fixture, not a new live-provider run. Windows runtime, remote provider behavior and broader external-consumer interoperability were not verified here. The CLI's top-level `process` help still says “Process one image” despite accepting batch selections; this documentation step does not change application code.
