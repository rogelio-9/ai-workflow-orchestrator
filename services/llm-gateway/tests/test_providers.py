import pytest

import llm_gateway_pb2 as pb

from app import providers
from app.providers.base import set_fields
from app.providers.mock import MockProvider


def test_resolves_registered_provider():
    provider, model = providers.resolve("mock:echo")
    assert isinstance(provider, MockProvider)
    assert model == "echo"


def test_keeps_colons_inside_the_model_tag():
    # Ollama tags are `name:tag`, so only the first colon separates the
    # provider -- splitting on every colon would drop the tag.
    _, model = providers.resolve("ollama:llama3.2:3b")
    assert model == "llama3.2:3b"


@pytest.mark.parametrize("model", ["openai:gpt-4o", "llama3.2", "", ":", "mock:"])
def test_unroutable_models_raise(model):
    with pytest.raises(providers.UnknownProvider):
        providers.resolve(model)


def test_set_fields_distinguishes_unset_from_zero():
    assert set_fields(pb.GenerationConfig()) == {}
    assert set_fields(pb.GenerationConfig(temperature=0.0)) == {"temperature": 0.0}


def test_set_fields_returns_only_what_was_set():
    config = pb.GenerationConfig(temperature=0.3, max_tokens=500)
    assert set_fields(config) == {"temperature": pytest.approx(0.3), "max_tokens": 500}


def test_every_provider_error_maps_to_a_status_code():
    # Guards the bug this file was written after: an unmapped error type falls
    # through to INTERNAL, which the worker treats as retryable even when the
    # failure is permanent.
    from app.server import _STATUS_FOR

    assert set(providers.ProviderError.__subclasses__()) == set(_STATUS_FOR)


def test_mock_completion_reports_nonzero_tokens():
    result = MockProvider().complete("echo", "summarize this", pb.GenerationConfig())
    assert "summarize this" in result.text
    assert result.prompt_tokens > 0
    assert result.completion_tokens > 0
