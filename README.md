# image-clarus
Image Clarus is an open-source CLI project for describing images and generating structured metadata. Slice 1 processes one image at a time using configurable OpenAI-compatible models. Search, XMP and batch processing are planned, not yet implemented.

## Install

Use Python 3.12 or newer and [uv](https://docs.astral.sh/uv/getting-started/installation/); Python 3.13 is the development baseline. From the project directory:

```sh
uv sync --locked
uv run --locked image-clarus --version
uv run --locked image-clarus --help
uv run --locked image-clarus process --help
uv run --locked image-clarus search --help
```

`uv sync` creates the project environment and installs the CLI; it does not require administrator privileges. Use `uv run --locked image-clarus` for the examples below. The equivalent `image-clarus` command is available when the project environment is activated.

## Configure

Start with [examples/config.yaml](examples/config.yaml). Replace the endpoint and model IDs with values supported by your provider. The description stage requires an image-capable model; the JSON stage requires a model that supports the adapter's structured requests. The sample names an environment variable, not a credential. Supply its value through your environment using your preferred secret manager. A configured but unset or empty credential variable fails authentication preflight; if the endpoint requires no authentication, remove `api_key_env` from your private configuration.

The sample endpoint is a placeholder, not a service started by this project. Supply the API base URL, not the full `/chat/completions` path; the adapter appends that path. The provider must support OpenAI-compatible Chat Completions, image data URLs for `desc`, and JSON-object response mode for `json`. HTTPS is supported; HTTP is restricted to `localhost`, loopback addresses and literal private-network IP addresses, not arbitrary private DNS names. Provider requests can transmit image bytes, descriptions, prompts, schemas and generated metadata. Never send private data, credentials or requests to an endpoint without authorization.

Precedence, lowest to highest: built-in defaults, one selected YAML file, repeated `--set PATH=VALUE` overrides (last assignment to the same path wins), then dedicated flags such as `--desc-prompt`, `--json-prompt`, `--json-schema`, `--regenerate` and `--missing-prerequisite`. `--stages` selects the current invocation. `--config FILE` uses only that file and disables discovery; otherwise the first existing user config is selected before the system config, with no merge or fallback after an invalid file. On Linux these are `~/.config/image-clarus/config.yaml` and `/etc/image-clarus/config.yaml`; macOS and Windows locations are documented in the [A2 contract](docs/slice-1/IMPL-A2-COMPLETED.md#discovery-precedence-and-path-bases).

Paths in a YAML file are relative to that file; explicit config and prompt/schema paths supplied on the command line or via `--set` are relative to the current working directory. Values in `--set` are parsed as YAML; quote the YAML string `off` (for example, `--set 'stages.desc.reasoning_effort="off"'`) so it is not parsed as a boolean. Do not put API key values in command-line arguments or `--set`; use a private configuration file or an environment-backed credential. JSON validation retries default to zero and may be set to 0–2 additional attempts through `stages.json.validation_retries`; these are not network retries.

## Process one image

The following are **manual provider examples**. They require a configured compatible endpoint, model IDs and, when configured, an environment credential. Run them only after explicitly authorizing the endpoint, model, any data transfer and potential costs. Use a synthetic or otherwise authorized image. Replace the example paths with your own files; do not commit personal images or device metadata.

```sh
# Description only: writes photo.jpg.desc.txt.
uv run --locked image-clarus process ./photo.jpg --config ./examples/config.yaml --stages desc

# JSON only: reads the existing photo.jpg.desc.txt; does not run desc.
uv run --locked image-clarus process ./photo.jpg --config ./examples/config.yaml --stages json

# Combined: desc then json, with the persisted description as the handoff.
uv run --locked image-clarus process ./photo.jpg --config ./examples/config.yaml --stages desc,json

# Supply independent prompt and schema replacements.
uv run --locked image-clarus process ./photo.jpg --config ./examples/config.yaml --desc-prompt ./description.txt --json-prompt ./structure.txt --json-schema ./schema.json

# Explicitly replace the selected outputs.
uv run --locked image-clarus process ./photo.jpg --config ./examples/config.yaml --stages desc,json --regenerate
```

Without `--stages`, both stages run in registry order. The source image is not modified. Sidecars use the complete source filename: `photo.jpg.desc.txt` and `photo.jpg.desc.json`. Existing valid outputs are skipped by default; `--regenerate` permits replacing selected outputs. Changes to the model, prompt or inputs do not automatically trigger regeneration. Selected-stage configuration and credentials are still checked before a skip. A structurally valid existing JSON sidecar can be skipped even if the description is missing or the selected schema changed; its fixed envelope is checked, not the current payload schema. If JSON needs a missing description, the default is failure; `--missing-prerequisite skip` changes that outcome without running `desc` implicitly. Failed or invalid output is not published as complete. A custom schema replaces the metadata payload schema, not the application-owned envelope; external references, nested `$id` and `$dynamicRef` are restricted. See the [A3 contract](docs/slice-1/IMPL-A3-COMPLETED.md) for schema replacement, provenance, and validation details.

Each selected stage prints a completed, skipped or failed summary on stdout; diagnostics go to stderr. Exit codes are `0` for success/skips, `1` for stage or authentication failure, `2` for usage/configuration errors, `3` for the search stub, and `130`/`143` for SIGINT/SIGTERM. Writes use backup/recovery mechanisms but no application-level locks: concurrent updates can overwrite one another, and filesystem durability varies.

## Current limits

Slice 1 accepts one image path, not directories, glob selection, traversal or batches. `search --help` works, but `search` reports not implemented and exits `3`; there is no search matching yet. XMP processing, ExifTool integration and an internal scheduler are not implemented. External schedulers may invoke the CLI. Linux is the required test platform; other operating systems are desirable but not claimed as fully tested.

## Project documents

- [Requirements](docs/REQ-image-clarus.md)
- [High-Level Design](docs/HLD-image-clarus.md)
- [Slice 1 implementation plan](docs/slice-1/IMPL-PLAN-slice-1.md) — in progress
