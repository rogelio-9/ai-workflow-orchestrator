"""Per-user sliding-window rate limiter.

This is the second limiter in the system and deliberately not shared with the
LLM gateway's. That one keys on the *provider* and defends a ceiling imposed
from outside -- Gemini's free tier is ~10 RPM whoever is calling. This one keys
on the *user* and defends a ceiling we choose, so one caller cannot monopolise
the workers. Same Redis and the same Lua, different threat.

Duplicated rather than extracted into a shared package for the same reason the
worker duplicated the producer config on D10: a shared library would couple two
services' deploys, and this is thirty lines.
"""

import logging
import os
import time
import uuid

import redis

LOG = logging.getLogger("api_gateway.ratelimit")

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")
WINDOW_SECONDS = int(os.environ.get("RATE_LIMIT_WINDOW_SECONDS", "60"))
# 0 disables. Deliberately not the default -- an unlimited public endpoint
# should be a choice someone made, not one they inherited.
PER_USER_LIMIT = int(os.environ.get("RATE_LIMIT_PER_USER", "30"))

# Atomic check-and-admit: between ZCARD and ZADD two concurrent requests from
# the same user can both see room and both be admitted.
_ADMIT = """
redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', ARGV[1])
if redis.call('ZCARD', KEYS[1]) >= tonumber(ARGV[3]) then
  return 0
end
redis.call('ZADD', KEYS[1], ARGV[2], ARGV[4])
redis.call('EXPIRE', KEYS[1], ARGV[5])
return 1
"""


class RateLimitExceeded(Exception):
    """Raised into the GraphQL layer, which renders it as a query error."""


class UserRateLimiter:
    def __init__(self, client=None, window_seconds: int = WINDOW_SECONDS):
        self._redis = client if client is not None else redis.from_url(REDIS_URL)
        self._window = window_seconds
        self._admit = self._redis.register_script(_ADMIT)

    def admit(self, user_id: str, limit: int = PER_USER_LIMIT) -> bool:
        if limit <= 0:
            return True

        now = time.time()
        try:
            allowed = self._admit(
                keys=[f"ratelimit:user:{user_id}"],
                args=[now - self._window, now, limit, uuid.uuid4().hex, self._window],
            )
        except redis.RedisError as exc:
            # Fail open, matching the gateway's limiter: an outage in the thing
            # that throttles requests should not become an outage in the thing
            # that serves them.
            LOG.warning("rate limiter unavailable, allowing request: %s", exc)
            return True

        return bool(allowed)

    def check(self, user_id: str, limit: int = PER_USER_LIMIT) -> None:
        if not self.admit(user_id, limit):
            raise RateLimitExceeded(
                f"rate limit exceeded: {limit} requests per {self._window}s"
            )
