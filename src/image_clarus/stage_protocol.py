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


def _provider_outcome(client: Any, step: Request) -> ProviderResult:
    """Run one operation through a resolved adapter; never raises."""
    try:
        content = getattr(client, step.operation)(**step.private_payload["arguments"])
        return ProviderResult(step.request_id, content=content)
    except ProviderError as error:
        return ProviderResult(step.request_id, error_category=error.category)
    except Exception:  # noqa: BLE001 - request-local provider fault
        return ProviderResult(step.request_id, error_category="provider_unavailable")


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
    call_provider: Callable[[Request], ProviderResult] | None = None,
    on_provider_request: Callable[[Request], None] | None = None,
    on_provider_result: Callable[[Request, ProviderResult], None] | None = None,
    submit_provider: Callable[[Request], Any] | None = None,
    await_provider: Callable[[Any], ProviderResult] | None = None,
    defer_transformation: bool = False,
    resume: Any = None,
):
    """Drive exactly the same stage continuation using the local adapters.

    When `submit_provider` and `await_provider` are supplied, the provider call
    is issued as an outstanding request and only joined through
    `await_provider`. That lets the owning stage actor keep servicing other
    images between submission and join (A2 §4) without moving any stage decision
    out of the stage.

    With `defer_transformation`, a `WorkRequired` step is returned untouched
    instead of being executed. The caller keeps the continuation and runs it
    when that stage has inference capacity, so a confirmation turn can never
    start a transformation or a provider request.
    """
    advance = start_or_resume or stage.start_or_resume
    # A deferred continuation resumes exactly where it left off: no re-run of
    # the stage's inspection, which could disagree with the earlier decision.
    step = resume if resume is not None else advance(work.context, None)
    while not isinstance(step, Terminal):
        if defer_transformation and isinstance(step, WorkRequired):
            return step
        if isinstance(step, Request):
            payload = step.private_payload
            if on_provider_request is not None:
                on_provider_request(step)
            if submit_provider is not None and await_provider is not None:
                pending = submit_provider(step)
                result = await_provider(pending)
            elif call_provider is not None:
                result = call_provider(step)
            else:
                client = services.provider_factory(
                    payload["provider"], payload["model"]
                )
                result = _provider_outcome(client, step)
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
