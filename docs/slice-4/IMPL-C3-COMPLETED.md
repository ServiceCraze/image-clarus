# Step C3 - Run regression packaging and quality checks [TEST]

**Status:** Complete and ready for review; review acceptance is separate. C4 was not started by this step.

**Version:** 0.3.57. Full-suite environment: Linux, Python 3.13.15 and 3.12.14, ExifTool 13.10. The Python 3.12 suite used a separate locked virtual environment. Provider fixtures were synthetic loopback services; no live provider was contacted.

**Changes:** Synchronized `pyproject.toml` and `uv.lock`; corrected prompt-fixture dependence in `tests/integration/test_c1_macro_requests.py`; created this record and updated the plan status. No production files or assets were changed or deleted. **Scope deviations:** None.

## Regression and quality evidence

- With ExifTool on PATH, `uv run --no-sync --locked --extra dev pytest -q -p no:cacheprovider` on Python 3.13.15: **2,001 passed in 1006.45s**.
- With ExifTool on PATH, a separate `UV_PROJECT_ENVIRONMENT` synced using `uv sync --locked --extra dev --python <python3.12>`, then `uv run --python <python3.12> --no-sync --locked --extra dev pytest -q -p no:cacheprovider`: Python 3.12.14, **2,001 passed in 886.19s**. Both full runs began after the final test change.
- `uv lock --check`, `uv run --no-sync --locked ruff check .`, `uv run --no-sync --locked ruff format --check .`, and `uv run --no-sync --locked image-clarus --version` passed; CLI reported `image-clarus 0.3.57`. `uv build --out-dir <scratch-dist>` produced both an sdist and a wheel built from that sdist.
- Focused `tests/integration/test_c1_macro_requests.py`: **12 passed**. In a disposable source copy, replacing both editable built-in prompts with fictional macro-free text initially caused **3 failures and 9 passes** because the guidance-depth test assumed a macro in the shipped prompt. That test now supplies its own macro-bearing prompt and checks the complete expanded request; the corrected module passed **12 tests** both with the normal prompts and with the macro-free replacements. Separate prompt/resource/stage unit modules in the probe passed **206 tests**. One 10,000-image prompt-probe test timed out at the probe's 180-second harness limit; it is not claimed as a prompt-edit pass. The full suites above exercised the ordinary fixture, not the edited-prompt copy.
- Full suites include existing schema/provenance, selected-stage, XMP isolation, state, source-byte and artifact safety tests. Tests operate on synthetic fixtures; their success does not establish live-provider or consumer-GUI behavior.

## Installed-wheel verification

A wheel built with `uv build --wheel --out-dir <scratch-dist>` was installed with normal dependencies into a separate Python 3.12.14 virtual environment using `uv venv` and `uv pip install --python <venv-python> <wheel>`. An outside-checkout harness with `PYTHONPATH` unset passed the following checks at 0.3.57:

- CLI version and help; installed copies of both prompts and both schemas matched their source bytes.
- Native recursive, case-insensitive dry-run selected both synthetic images without calling the stub. Synthetic `desc,json` processing made two loopback requests, wrote both sidecars, and preserved source bytes.
- Category init/list/clear/rebuild/list completed; rebuilding restored the two synthetic category paths.
- `search` produced empty stdout, `search is not implemented in Slice 1` on stderr, and exit status **3**, with no provider request.

An initial harness resource lookup failed; after correction the complete harness passed. The installed-wheel smoke did not exercise XMP or ExifTool. Independent full-suite XMP coverage used real ExifTool. A subsequent build produced an sdist and a wheel from that sdist; the installed smoke above used the separately built wheel.

## Reachability, imports, privacy and documentation

- The bounded audit compared Slice 4 changed paths against the recorded baseline. The ordinary single-literal-file CLI route still calls `pipeline.run_pipeline`; batch paths resolve through the stage registry. The CLI, batch executor and rebuild retain production uses of state accumulation/extraction. These paths are not test-only orphans; no retention exception is asserted. Existing single-image pipeline tests remain relevant; the old glob-rejection assertion was reconciled to literal-first selection and pattern coverage. A defensive fallback in the old CLI route may still be reached if a file changes or becomes unreadable between checks; its full race reachability was not proven. No confirmed orphan was removed. This is a bounded audit, not a guarantee about every dynamically accessed symbol or unknown external Python consumer.
- An AST scan of **38 production modules**, including function-local static imports, found no static import cycle; dynamic imports can escape the scan. State extraction receives its envelope reader from callers rather than importing a stage. XMP's structure dependency was inspected alongside XMP isolation tests; deferred prompt-expansion imports are not themselves evidence of model execution.
- A targeted privacy scan of the C2/C3 changed public documents, tests and production files for secrets, identifying fixture metadata and internal infrastructure strings found no apparent leak in the inspected matches. This bounded scan does not prove every possible private value is absent.
- A path-aware check of README and 20 Slice 4 Markdown files found 50 local links; the only missing targets before this record was created were the then-future C3 and C4 records. All **19** summary step labels matched detailed headings. README process-option grammar was compared with CLI help; examples were not all executed as part of this audit. The C3 record is now present; C4 remains a future unchecked step.

## Acceptance

- [x] Required full/focused suites, lint/format, lock and build checks have recorded outcomes at stated versions.
- [x] Installed-wheel CLI/resources/batch/category smoke checks pass outside the checkout, including the provider-free search stub's not-implemented diagnostic and exit `3`, or have an explicit approved exception.
- [x] Existing prompts/schema/stages/state/XMP/source/safety contracts remain supported by regression evidence.
- [x] Reachability/import/privacy audits have explicit scope, findings and disposition; no unrecorded orphan exception remains.
- [x] Documentation/status/version references match actual evidence, including limitations and unperformed checks.

## Limits

These are Linux results; Windows runtime was not tested. The installed-wheel smoke did not run real ExifTool or a consumer GUI, and no live model was contacted. Prompt-edit and privacy probes are scoped as stated above. C4 owns final Slice 4 evidence reconciliation and its own delivery-version checks; this record does not claim C4 completion or review acceptance.
