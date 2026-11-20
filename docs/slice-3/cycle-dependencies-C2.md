The original inspection covered all 24 Python modules in the public `image-clarus` source tree at version `0.2.16`. The prompt-expansion correction was delivered in `0.2.18`; the schema utility separations were delivered in `0.3.1`.

**The three identified dependency relationships have been corrected.** The original cycles each involved a deferred import inside a function, which allowed ordinary imports and tests to succeed despite the static cycles.

Before the schema utility separations, the remaining identified cycles involved three modules:

- `config`
- `schema_worker`
- `stages.structure`

The original inspection found no cycles involving the state storage, category accumulation, provider adapter, or artifact modules. This update is not a new exhaustive graph audit.

### **Cycles found**

| Dependency cycle                                                                  | Why it exists                                                                                                       | Assessment                                                                |
| --------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------- |
| `config ↔ schema_worker`                                                          | Configuration invokes the schema worker for preflight; the worker formerly imported configuration's `_check_schema` | Resolved in `0.3.1`: shared validation module                            |
| `schema_worker ↔ stages.structure`                                                | The JSON stage invokes the worker; the worker formerly imported schema-feedback utilities from the JSON stage       | Resolved in `0.3.1`: stage-independent feedback module                    |
| `stages.structure → prompt_expansion → config → schema_worker → stages.structure` | Previously, prompt expansion imported `ConfigurationError` from `config`                                            | Resolved in `0.2.18` by removing that import edge                        |

The longer route `config → schema_worker → stages.structure → config` was formed by the first two relationships and is also broken by their removal.

### **What I recommend**

1\. **Completed:** Extract `ConfigurationError` into a dependency-free module.

`prompt_expansion` now imports the exception from `config_errors`; `config` re-exports the same class for compatibility. This removes the identified prompt-expansion cycle. The fresh-process import and class-identity regression evidence is recorded in [C2 completion](IMPL-C2-COMPLETED.md).

2\. **Completed:** Separate schema validation from configuration resolution.

`_check_schema` and its required JSON parsing utilities now live in `schema_validation`; both `config` and `schema_worker` use it.

This removes `schema_worker → config` while retaining compatibility exports from `config`.

3\. **Completed:** Separate schema-feedback utilities from the JSON stage.

`_feedback`, `_schema_nodes`, `_resolve_ref`, and their supporting functions now live in the stage-independent `schema_feedback` module.

Both `schema_worker` and `stages.structure` use the utilities without depending on each other in both directions; compatibility exports remain in the stage module.

The extracted utilities have direct tests in addition to the existing schema and stage regressions.

### **Priority**

The exception extraction and both schema utility separations are complete.

The schema worker no longer imports the JSON stage or configuration module.

The schema separations move existing functionality rather than intentionally changing algorithms or behavior.

**Bottom line:** The identified cycles are resolved. A targeted static dependency test includes deferred imports across the affected modules; it is not an exhaustive repository-wide cycle audit.

*Inspection basis: public `main` at version `0.2.16`; the `0.2.17` privacy corrections did not change application code. The `0.2.18` exception extraction and `0.3.1` schema separations are subsequent corrections, not the original inspection baseline. The historical origin of the schema cycles was not independently established.*