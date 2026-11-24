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


def drive(stage, work, services):
    """Drive exactly the same stage continuation using the local adapters."""
    step = stage.start_or_resume(work.context, None)
    while not isinstance(step, Terminal):
        if isinstance(step, Request):
            payload = step.private_payload
            try:
                client = services.provider_factory(
                    payload["provider"], payload["model"]
                )
                content = getattr(client, step.operation)(**payload["arguments"])
                result = ProviderResult(step.request_id, content=content)
            except ProviderError as error:
                result = ProviderResult(step.request_id, error_category=error.category)
            step = stage.start_or_resume(step.continuation, result)
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
            step = stage.start_or_resume(step.continuation, result)
        else:
            raise TypeError("invalid stage continuation")
    return step.result
