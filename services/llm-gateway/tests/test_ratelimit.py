import uuid

import pytest
import redis

from app.ratelimit import RateLimiter


@pytest.fixture
def limiter():
    client = redis.from_url("redis://localhost:6379")
    try:
        client.ping()
    except redis.RedisError:
        pytest.skip("redis not running")
    return RateLimiter(client=client, window_seconds=60)


@pytest.fixture
def provider():
    # Unique per test so a leftover window cannot leak between runs.
    return f"testprov{uuid.uuid4().hex[:8]}"


def test_unlimited_when_no_limit_configured(limiter, provider):
    assert all(limiter.admit(provider) for _ in range(50))


def test_admits_up_to_the_limit_then_rejects(limiter, provider, monkeypatch):
    monkeypatch.setenv(f"RATE_LIMIT_{provider.upper()}", "3")
    assert [limiter.admit(provider) for _ in range(5)] == [True, True, True, False, False]


def test_window_is_per_provider(limiter, provider, monkeypatch):
    other = f"{provider}other"
    monkeypatch.setenv(f"RATE_LIMIT_{provider.upper()}", "1")
    monkeypatch.setenv(f"RATE_LIMIT_{other.upper()}", "1")

    assert limiter.admit(provider) is True
    assert limiter.admit(provider) is False
    # Exhausting one provider's quota must not touch another's.
    assert limiter.admit(other) is True


def test_fails_open_when_redis_is_down(provider, monkeypatch):
    monkeypatch.setenv(f"RATE_LIMIT_{provider.upper()}", "1")
    unreachable = RateLimiter(client=redis.from_url("redis://localhost:6399"))
    # A limiter outage must not take inference down with it.
    assert unreachable.admit(provider) is True
