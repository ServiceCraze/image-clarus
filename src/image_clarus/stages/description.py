"""Image description stage."""

from pathlib import Path

from image_clarus import resources
from image_clarus.artifacts import ArtifactError
from image_clarus.config import ConfigurationError
from image_clarus.providers.openai_compatible import ProviderError
from image_clarus.results import StageResult


def _valid(data):
    try:
        return bool(data.decode("utf-8").strip())
    except UnicodeError:
        return False


def run_description(image_path, config, services):
    image_path = Path(image_path)
    output = Path(str(image_path) + ".desc.txt")
    regenerate = config["stages"]["desc"]["regenerate"]
    try:
        exists = services.artifacts.recover(output, _valid, retain_backup=regenerate)
    except ArtifactError as error:
        if not (regenerate and error.category == "invalid_artifact"):
            return StageResult(
                "desc", "failed", error_category=error.category, message=str(error)
            )
        exists = True
    if exists and not regenerate:
        return StageResult(
            "desc", "skipped", output_path=output, reason_code="output_exists"
        )
    settings = config["stages"]["desc"]
    model = config["models"][settings["model"]]
    provider = config["providers"][model["provider"]]
    try:
        prompt_path = settings["prompt_file"] or resources.description_prompt()
        prompt = prompt_path.read_bytes().decode("utf-8")
    except (OSError, UnicodeError):
        return StageResult(
            "desc",
            "failed",
            error_category="configuration",
            message="Unable to read description prompt",
        )
    try:
        # Deferred so importing stages for other work never opens state.
        from image_clarus.prompt_expansion import expand_prompt, safe_config_snapshot

        prompt = expand_prompt(
            prompt,
            safe_config_snapshot(config),
            getattr(services, "state", None),
            config.get("prompt_expansion", {}).get("macros", {}),
        )
    except ConfigurationError:
        return StageResult(
            "desc",
            "failed",
            error_category="configuration",
            message="Invalid prompt expansion",
        )
    try:
        image_bytes = image_path.read_bytes()
    except OSError:
        return StageResult(
            "desc", "failed", error_category="file_io", message="Unable to read image"
        )
    try:
        content = services.provider_factory(provider, model).image(
            prompt=prompt,
            image_bytes=image_bytes,
            suffix=image_path.suffix,
            effort=settings["reasoning_effort"],
        )
    except ProviderError as error:
        return StageResult(
            "desc",
            "failed",
            error_category=error.category,
            message="Description provider request failed",
        )
    payload = content.encode("utf-8")
    if not _valid(payload):
        return StageResult(
            "desc",
            "failed",
            error_category="provider_unavailable",
            message="Description provider returned empty content",
        )
    try:
        services.artifacts.write(
            output, payload, _valid, validation_category="provider_unavailable"
        )
    except ArtifactError as error:
        return StageResult(
            "desc",
            "failed",
            error_category=error.category,
            message=f"Description artifact write failed: {error}",
        )
    return StageResult("desc", "completed", output_path=output)
