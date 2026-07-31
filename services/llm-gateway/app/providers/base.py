"""Shared contract every LLM backend implements."""

from abc import ABC, abstractmethod
from dataclasses import dataclass


class ProviderError(Exception):
    """Base for failures the servicer maps onto gRPC status codes."""


class UnknownProvider(ProviderError):
    """Model string named a provider that is not registered. Not retryable."""


class ProviderNotFound(ProviderError):
    """Backend is up but does not have that model. Not retryable."""


class ProviderRateLimited(ProviderError):
    """Backend refused for quota reasons. Retryable after a backoff."""


class ProviderUnavailable(ProviderError):
    """Backend unreachable or erroring. Retryable."""


class ProviderTimeout(ProviderError):
    """Backend did not answer in time. Retryable."""


@dataclass(frozen=True)
class Completion:
    text: str
    prompt_tokens: int
    completion_tokens: int


def set_fields(config) -> dict:
    """Only the GenerationConfig fields the caller actually set.

    ListFields() skips absent fields, which is why the proto marks them
    `optional` -- it keeps temperature=0 distinguishable from unset.
    """
    return {field.name: value for field, value in config.ListFields()}


class Provider(ABC):
    @abstractmethod
    def complete(self, model: str, prompt: str, config) -> Completion:
        """Run one completion. Raise a ProviderError subclass on failure."""
