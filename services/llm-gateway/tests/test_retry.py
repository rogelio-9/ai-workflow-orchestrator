import pytest

import llm_gateway_pb2 as pb

from app import providers, retry
from app.providers.mock import MockProvider


def _run(provider):
    return lambda: provider.complete("echo", "hi", pb.GenerationConfig())


@pytest.fixture(autouse=True)
def fast_backoff(monkeypatch):
    """Keep the suite from actually sleeping the real ladder's seconds."""
    monkeypatch.setattr(retry, "BASE_BACKOFF_SECONDS", 0.001)


def test_recovers_once_the_transient_failure_stops():
    # Two failures then success -- proves the ladder recovers, which failing
    # forever would not.
    provider = MockProvider(fail_mode="unavailable", fail_times=2)
    result = retry.call_with_retry(_run(provider))
    assert result.text.startswith("[mock:echo]")
    assert provider._calls == 3, "should have taken exactly three attempts"


def test_gives_up_after_max_attempts():
    provider = MockProvider(fail_mode="unavailable", fail_times=99)
    with pytest.raises(providers.ProviderUnavailable):
        retry.call_with_retry(_run(provider))
    assert provider._calls == retry.MAX_ATTEMPTS


def test_does_not_retry_terminal_failures():
    calls = []

    def operation():
        calls.append(1)
        raise providers.ProviderNotFound("no such model")

    with pytest.raises(providers.ProviderNotFound):
        retry.call_with_retry(operation)
    assert len(calls) == 1, "a missing model can never succeed on a later attempt"


def test_stops_rather_than_sleeping_past_the_deadline(monkeypatch):
    monkeypatch.setattr(retry, "BASE_BACKOFF_SECONDS", 5.0)
    provider = MockProvider(fail_mode="unavailable", fail_times=99)

    with pytest.raises(providers.ProviderUnavailable):
        # 0.01s left, backoff would be >=5s: sleeping just spends the caller's
        # budget to reach the same failure later.
        retry.call_with_retry(_run(provider), time_remaining=lambda: 0.01)

    assert provider._calls == 1


def test_backoff_grows_and_is_jittered(monkeypatch):
    monkeypatch.setattr(retry, "BASE_BACKOFF_SECONDS", 1.0)
    assert min(retry.backoff_for(2) for _ in range(50)) >= retry.backoff_for(1) / 2
    # Jitter means repeated calls must not collide, or every rate-limited
    # worker retries in lockstep and recreates the burst.
    assert len({retry.backoff_for(3) for _ in range(20)}) > 1
