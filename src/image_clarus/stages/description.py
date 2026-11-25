"""Image description stage and its resumable continuation."""

from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from image_clarus import resources
from image_clarus.artifacts import ArtifactError
from image_clarus.config import ConfigurationError
from image_clarus.results import StageResult
from image_clarus.stage_protocol import (
    ProviderResult,
    PublicationResult,
    Publish,
    Request,
    Terminal,
    WorkRequired,
    drive,
    mark_transform_started,
)


def _valid(data):
    try:
        return bool(data.decode("utf-8").strip())
    except UnicodeError:
        return False


@dataclass
class _Context:
    image: Path
    config: dict
    services: object
    output: Path
    phase: str = "start"
    request_id: tuple | None = None
    publication_id: str | None = None
    validation_category: str = "provider_unavailable"


def inspect(image, config, services, *, inference_allowed=True):
    image = Path(image)
    output = Path(str(image) + ".desc.txt")
    regenerate = config["stages"]["desc"]["regenerate"]
    try:
        exists = services.artifacts.recover(output, _valid, retain_backup=regenerate)
    except ArtifactError as error:
        if not (regenerate and error.category == "invalid_artifact"):
            return Terminal(
                StageResult(
                    "desc", "failed", error_category=error.category, message=str(error)
                )
            )
        exists = True
    if exists and not regenerate:
        return Terminal(
            StageResult(
                "desc", "skipped", output_path=output, reason_code="output_exists"
            )
        )
    if not inference_allowed:
        return Terminal(StageResult("desc", "skipped", reason_code="budget_excluded"))
    return WorkRequired(
        "desc", image, _Context(image, deepcopy(config), services, output)
    )


def start_or_resume(context, provider_result):
    if context.phase == "start":
        if provider_result is not None:
            raise ValueError("unexpected stage result")
        # The decision is authoritative again immediately before transformation.
        checked = inspect(context.image, context.config, context.services)
        if isinstance(checked, Terminal):
            context.phase = "done"
            return checked
        mark_transform_started(context.services)
        config, services, image = context.config, context.services, context.image
        settings = config["stages"]["desc"]
        model = config["models"][settings["model"]]
        provider = config["providers"][model["provider"]]
        try:
            prompt = (
                (settings["prompt_file"] or resources.description_prompt())
                .read_bytes()
                .decode("utf-8")
            )
        except (OSError, UnicodeError):
            context.phase = "done"
            return Terminal(
                StageResult(
                    "desc",
                    "failed",
                    error_category="configuration",
                    message="Unable to read description prompt",
                )
            )
        try:
            from image_clarus.prompt_expansion import (
                expand_prompt,
                safe_config_snapshot,
            )

            prompt = expand_prompt(
                prompt,
                safe_config_snapshot(config),
                getattr(services, "state", None),
                config.get("prompt_expansion", {}).get("macros", {}),
            )
        except ConfigurationError:
            context.phase = "done"
            return Terminal(
                StageResult(
                    "desc",
                    "failed",
                    error_category="configuration",
                    message="Invalid prompt expansion",
                )
            )
        try:
            image_bytes = image.read_bytes()
        except OSError:
            context.phase = "done"
            return Terminal(
                StageResult(
                    "desc",
                    "failed",
                    error_category="file_io",
                    message="Unable to read image",
                )
            )
        context.request_id = (str(image), "desc", 0, uuid4().hex)
        context.phase = "request"
        return Request(
            context.request_id,
            "image",
            {
                "provider": provider,
                "model": model,
                "arguments": {
                    "prompt": prompt,
                    "image_bytes": image_bytes,
                    "suffix": image.suffix,
                    "effort": settings["reasoning_effort"],
                },
            },
            context,
        )
    if context.phase == "request":
        if (
            not isinstance(provider_result, ProviderResult)
            or provider_result.request_id != context.request_id
        ):
            raise ValueError("stale or invalid provider result")
        if provider_result.error_category:
            context.phase = "done"
            if provider_result.error_category == "interrupted":
                return Terminal(
                    StageResult("desc", "skipped", reason_code="interrupted")
                )
            return Terminal(
                StageResult(
                    "desc",
                    "failed",
                    error_category=provider_result.error_category,
                    message="Description provider request failed",
                )
            )
        try:
            payload = provider_result.content.encode("utf-8")
        except (AttributeError, UnicodeError):
            payload = b""
        if not _valid(payload):
            context.phase = "done"
            return Terminal(
                StageResult(
                    "desc",
                    "failed",
                    error_category="provider_unavailable",
                    message="Description provider returned empty content",
                )
            )
        context.publication_id = uuid4().hex
        context.phase = "publish"
        return Publish(context.publication_id, payload, _valid, context)
    if context.phase == "publish":
        if (
            not isinstance(provider_result, PublicationResult)
            or provider_result.publication_id != context.publication_id
        ):
            raise ValueError("stale or invalid publication result")
        context.phase = "done"
        if provider_result.error:
            error = provider_result.error
            if error.category == "interrupted":
                return Terminal(
                    StageResult("desc", "skipped", reason_code="interrupted")
                )
            return Terminal(
                StageResult(
                    "desc",
                    "failed",
                    error_category=error.category,
                    message=f"Description artifact write failed: {error}",
                )
            )
        return Terminal(StageResult("desc", "completed", output_path=context.output))
    raise ValueError("continuation already consumed")


def run_description(image_path, config, services):
    import sys

    step = inspect(image_path, config, services)
    return (
        step.result
        if isinstance(step, Terminal)
        else drive(sys.modules[__name__], step, services)
    )
