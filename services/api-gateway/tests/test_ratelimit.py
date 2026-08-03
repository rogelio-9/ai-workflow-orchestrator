import uuid

import pytest
import redis

from app.ratelimit import RateLimitExceeded, UserRateLimiter


@pytest.fixture
def limiter():
    client = redis.from_url("redis://localhost:6379")
    try:
        client.ping()
    except redis.RedisError:
        pytest.skip("redis not running")
    return UserRateLimiter(client=client, window_seconds=60)


@pytest.fixture
def user():
    # Unique per test so a leftover window cannot leak between runs.
    return f"user-{uuid.uuid4().hex[:10]}"


def test_admits_up_to_the_limit_then_refuses(limiter, user):
    assert [limiter.admit(user, limit=3) for _ in range(5)] == [
        True, True, True, False, False,
    ]


def test_one_user_cannot_consume_another_users_budget(limiter, user):
    other = f"{user}-other"
    assert limiter.admit(user, limit=1) is True
    assert limiter.admit(user, limit=1) is False
    # The whole point of keying on the user: exhausting one must not throttle
    # everybody else.
    assert limiter.admit(other, limit=1) is True


def test_zero_means_unlimited(limiter, user):
    assert all(limiter.admit(user, limit=0) for _ in range(50))


def test_check_raises_once_over(limiter, user):
    limiter.check(user, limit=1)
    with pytest.raises(RateLimitExceeded) as exc:
        limiter.check(user, limit=1)
    # The message has to name the budget, or a client cannot tell whether to
    # retry in a second or an hour.
    assert "1 requests per 60s" in str(exc.value)


def test_fails_open_when_redis_is_unreachable(user):
    unreachable = UserRateLimiter(client=redis.from_url("redis://localhost:6399"))
    # An outage in the thing that throttles requests must not become an outage
    # in the thing that serves them.
    assert unreachable.admit(user, limit=1) is True
