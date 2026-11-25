"""Stage-owned resumable operations and the synchronous adapter."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from image_clarus.artifacts import ArtifactError
from image_clarus.providers.openai_compatible import ProviderError


@dataclass(frozen=True)
class Terminal:
    result: Any


@dataclass(frozen=True)
class WorkRequired:
    stage: str
    image: Any
    context: Any


@dataclass(frozen=True)
class Request:
    request_id: tuple
    operation: str
    private_payload: dict
    continuation: Any


@dataclass(frozen=True)
class Publish:
    publication_id: str
    validated_bytes: bytes
    validator: Callable
    continuation: Any


@dataclass(frozen=True)
class ProviderResult:
    request_id: tuple
    content: str | None = None
    error_category: str | None = None


@dataclass(frozen=True)
class PublicationResult:
    publication_id: str
    error: ArtifactError | None = None


def mark_transform_started(services: Any) -> None:
    callback = getattr(services, "on_transform_started", None)
    if callback is not None:
        if not callable(callback):
            raise TypeError("invalid transformation callback")
        callback()


def drive(
    stage,
    work,
    services,
    *,
    start_or_resume: Callable | None = None,
    on_provider_request: Callable[[Request], None] | None = None,
    on_provider_result: Callable[[Request, ProviderResult], None] | None = None,
):
    """Drive exactly the same stage continuation using the local adapters."""
    advance = start_or_resume or stage.start_or_resume
    step = advance(work.context, None)
    while not isinstance(step, Terminal):
        if isinstance(step, Request):
            payload = step.private_payload
            if on_provider_request is not None:
                on_provider_request(step)
            try:
                client = services.provider_factory(
                    payload["provider"], payload["model"]
                )
                content = getattr(client, step.operation)(**payload["arguments"])
                result = ProviderResult(step.request_id, content=content)
            except ProviderError as error:
                result = ProviderResult(step.request_id, error_category=error.category)
            except Exception:  # noqa: BLE001 - request-local provider fault
                result = ProviderResult(
                    step.request_id, error_category="provider_unavailable"
                )
            if on_provider_result is not None:
                on_provider_result(step, result)
            step = advance(step.continuation, result)
        elif isinstance(step, Publish):
            try:
                services.artifacts.write(
                    step.continuation.output,
                    step.validated_bytes,
                    step.validator,
                    validation_category=step.continuation.validation_category,
                )
                result = PublicationResult(step.publication_id)
            except ArtifactError as error:
                result = PublicationResult(step.publication_id, error)
            step = advance(step.continuation, result)
        else:
            raise TypeError("invalid stage continuation")
    return step.result
