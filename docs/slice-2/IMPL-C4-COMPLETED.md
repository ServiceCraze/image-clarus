# Step C4 — Linux package, compatibility, and quality gates (COMPLETED)

**Status: Complete.** The Product Owner chose to retain the current lowercase guidance and clarified that prompt wording changes must not break tests. The contract and tests are reconciled, and the applicable gates pass. C5 remains open. The separate prompt-configurability concern remains unresolved.

## Gate results

Tests used synthetic inputs and local tooling; no real provider or personal image was used. Separate isolated Python environments were used. The application version tested was **0.2.2**; Linux, `uv 0.12.6`, Python **3.13.15** and **3.12.14**, Ruff **0.17.5**, and local ExifTool **13.64** were used.

| Check | Observed result |
| --- | --- |
| `uv lock --locked` | Passed; 21 packages resolved. |
| Python 3.13: `uv run --locked --extra dev --python 3.13 ruff check .` | Passed. |
| Python 3.13: `uv run --locked --extra dev --python 3.13 ruff format --check .` | Passed; 104 files formatted. |
| `uv build --python 3.13` | Passed; source distribution and wheel built in scratch. |
| Python 3.13: `uv run --locked --extra dev --python 3.13 pytest -q` with ExifTool 13.64 | **864 passed**, no skips. |
| Python 3.12: `uv run --locked --extra dev --python 3.12 pytest -q` with ExifTool 13.64 | **864 passed**, no skips. |
| Isolated normal wheel installation and CLI checks | Installed the built wheel with dependencies into a separate Python 3.13 environment. From outside the checkout with `PYTHONPATH` unset, version printed `image-clarus 0.2.2`, top-level/process/search help succeeded, and the search stub returned exit 3 with its documented diagnostic. Four prompt/schema resource lookups returned files. Version matched project metadata; wheel resource bytes matched source in the resource tests. |
| Installed `desc`, `json`, and missing-ExifTool preflight | With an empty `PATH` and a controlled local synthetic HTTP service, independently selected `desc` and `json` completed, produced the expected synthetic metadata, and left the source bytes unchanged. Selecting `xmp` without ExifTool returned exit 2 and an ExifTool diagnostic. The local service shut down after the test. This proves only the exercised installed-wheel paths. |
| Reachability, unused artifacts and dependency expansion | Reviewed statically; see the audit and limitations below. |

Before correction, both full suites returned **861 passed, 3 failed** because the current prompt added lowercase-tag guidance while three tests required the historical A2 prompt bytes. The Product Owner chose to keep the guidance and directed that tests not break when prompt wording changes. The A2 record retains its historical text and records the subsequent decision. Tests now verify nonempty UTF-8 prompt availability, actual source-to-wheel byte identity, and exact bytes sent and fingerprinted using a fictional prompt fixture; schema identity checks remain unchanged. In a disposable source copy with a completely different fictional built-in prompt, the affected resource, wheel, provenance and built-in invocation checks returned **7 passed**. The full-suite results above were run after this reconciliation.

An earlier Python 3.13 run found **854 passed, 5 failed, 5 skipped**: in addition to the three prompt failures, the previously scratch-installed ExifTool disappeared during execution. ExifTool 13.64 was recovered into scratch from the upstream source release; the subsequent runs had no ExifTool failures or skips. An initial Python 3.12 run also had the three prompt failures. An attempted download from an outdated archive URL failed before the upstream source was used. No system install was made.

## Reachability and dependency audit

- `pyproject.toml` registers the CLI; `src/image_clarus/cli.py` wires the selected description, structure and XMP stages. `src/image_clarus/__main__.py` supports `python -m`. The historical v1 schema is used by `src/image_clarus/stages/xmp.py` for compatible older payloads and is not an orphan.
- PyYAML, jsonschema, httpx and referencing have production imports and are declared directly. The Product Owner-approved direct `referencing` dependency is documented in Slice 1 B2. ExifTool remains an XMP-only external executable. This review found no unapproved dependency expansion.
- Static inspection found import-graph cycles involving `config.py`, `schema_worker.py` and `stages/structure.py`, including deferred reverse imports and a worker invoked as a separate process. The review does **not** claim an acyclic graph, a baseline comparison, or absence of all dynamic dependencies. Full suites and the installed-wheel synthetic path passed; no import-time failure was demonstrated. These existing graph relationships are documented rather than silently characterized as resolved.
- No confirmed orphaned production functions were identified by the bounded static audit; dynamically invoked framework callbacks remain in use. No production code or fixture was removed. Static discovery is not proof that every possible dynamic consumer or artifact was exhaustively identified.

## Acceptance

- [x] Full tests, Ruff, locked dependency check and build pass on Python 3.13 Linux, with actual commands/outcomes recorded.
- [x] Python 3.12 compatibility is executed and passes or remains explicitly blocked/unchecked.
- [x] Built/installed package exposes required commands and resources; ExifTool is optional outside XMP, version/lock are coherent.
- [x] Production reachability, unused artifacts and no-unapproved-dependency expansion are reviewed; record and checkoffs agree.

**Files:** Updated `tests/unit/test_slice2_structure.py`, `tests/unit/test_structure_resources.py`, application version/lock/version assertions, `docs/slice-2/IMPL-A2-COMPLETED.md`, `docs/slice-2/IMPL-C3-COMPLETED.md` (subsequent progress), this record and the plan. The current built-in prompt itself was retained, not rewritten by C4. Application version advanced to `0.2.2`. C5 and the separate prompt-configurability concern remain open.
