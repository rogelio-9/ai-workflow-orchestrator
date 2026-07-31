"""Sliding-window rate limiter, keyed per provider.

The plan called for a per-user limiter. That belongs in the API gateway, where
user identity exists -- here there is none, only run_id and step_id. What this
gateway is actually protecting is the *provider's* quota (Gemini's free tier is
~10 RPM), and that ceiling is shared by every user, so the key is the provider.
"""

import logging
import os
import time
import uuid

import redis

LOG = logging.getLogger("llm_gateway.ratelimit")

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")
WINDOW_SECONDS = int(os.environ.get("RATE_LIMIT_WINDOW_SECONDS", "60"))

# Check-and-admit has to be atomic: between ZCARD and ZADD, another thread in
# the gRPC pool can slip through and put us over the provider's quota. This is
# the Lua fix the worker's lock release still has parked as TODO(locking).
_ADMIT = """
local dropped = redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', ARGV[1])
if redis.call('ZCARD', KEYS[1]) >= tonumber(ARGV[3]) then
  return 0
end
redis.call('ZADD', KEYS[1], ARGV[2], ARGV[4])
redis.call('EXPIRE', KEYS[1], ARGV[5])
return 1
"""


class RateLimiter:
    def __init__(self, client=None, window_seconds: int = WINDOW_SECONDS):
        self._redis = client if client is not None else redis.from_url(REDIS_URL)
        self._window = window_seconds
        self._admit = self._redis.register_script(_ADMIT)

    @staticmethod
    def limit_for(provider: str) -> int:
        """Calls per window for a provider. 0 means unlimited."""
        return int(os.environ.get(f"RATE_LIMIT_{provider.upper()}", "0"))

    def admit(self, provider: str) -> bool:
        """Record a call and report whether it fits inside the window."""
        limit = self.limit_for(provider)
        if limit <= 0:
            return True

        now = time.time()
        try:
            allowed = self._admit(
                keys=[f"ratelimit:provider:{provider}"],
                args=[now - self._window, now, limit, uuid.uuid4().hex, self._window],
            )
        except redis.RedisError as exc:
            # Fail open. A limiter outage should not take inference down with
            # it -- the quota is a guard rail, not a correctness invariant.
            LOG.warning("rate limiter unavailable, allowing call: %s", exc)
            return True

        return bool(allowed)
