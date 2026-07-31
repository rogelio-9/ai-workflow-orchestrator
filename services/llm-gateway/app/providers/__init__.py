"""Routes a `provider:model` string to a backend.

Uniform prefixing keeps routing unambiguous and means a DAG node names its
backend explicitly rather than the gateway inferring one from a bare model id.
"""

from .base import (
    Completion,
    Provider,
    ProviderError,
    ProviderNotFound,
    ProviderRateLimited,
    ProviderTimeout,
    ProviderUnavailable,
    UnknownProvider,
)
from .mock import MockProvider
from .ollama import OllamaProvider

# Built once at import: providers are stateless and hold only connection config.
_PROVIDERS: dict[str, Provider] = {
    "mock": MockProvider(),
    "ollama": OllamaProvider(),
}


def resolve(model: str) -> tuple[Provider, str]:
    """Split `provider:model` into the backend and the bare model id."""
    name, separator, bare_model = model.partition(":")
    if not separator or not bare_model:
        raise UnknownProvider(
            f"model {model!r} must be '<provider>:<model>'; "
            f"known providers: {sorted(_PROVIDERS)}"
        )

    try:
        return _PROVIDERS[name], bare_model
    except KeyError:
        raise UnknownProvider(
            f"unknown provider {name!r}; known: {sorted(_PROVIDERS)}"
        ) from None


__all__ = [
    "Completion",
    "Provider",
    "ProviderError",
    "ProviderNotFound",
    "ProviderRateLimited",
    "ProviderTimeout",
    "ProviderUnavailable",
    "UnknownProvider",
    "resolve",
]
