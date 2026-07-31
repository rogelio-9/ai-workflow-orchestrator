"""In-process retry for transient provider failures.

This is the inner of two ladders. The gateway retries fast and invisibly for
blips a single call can absorb -- one 429, one reset connection. The worker's
Kafka-level ladder is the outer one: slower, durable, and able to survive the
worker process dying. Keeping the gateway inside the caller's deadline is what
stops the two from multiplying into an unbounded number of provider calls.
"""

import logging
import os
import random
import time

from .providers import ProviderRateLimited, ProviderTimeout, ProviderUnavailable

LOG = logging.getLogger("llm_gateway.retry")

# Only failures that a later attempt could plausibly survive. NOT_FOUND and
# INVALID_ARGUMENT are absent deliberately: retrying them cannot help.
RETRYABLE = (ProviderRateLimited, ProviderUnavailable, ProviderTimeout)

MAX_ATTEMPTS = int(os.environ.get("GATEWAY_MAX_ATTEMPTS", "3"))
BASE_BACKOFF_SECONDS = float(os.environ.get("GATEWAY_BASE_BACKOFF_SECONDS", "0.5"))
# Full jitter. Without it, every worker that hit the same rate limit wakes at
# the same instant and reproduces the burst that caused it.
JITTER = 1.0


def backoff_for(attempt: int) -> float:
    """Exponential backoff with jitter, in seconds, for a 1-indexed attempt."""
    ceiling = BASE_BACKOFF_SECONDS * (2 ** (attempt - 1))
    return random.uniform(0, ceiling * JITTER) + ceiling


def call_with_retry(operation, time_remaining=None):
    """Run operation(), retrying transient provider failures.

    time_remaining: callable returning seconds left on the caller's deadline,
    or None when the caller set no deadline.
    """
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            return operation()
        except RETRYABLE as exc:
            if attempt == MAX_ATTEMPTS:
                LOG.warning("giving up after %d attempts: %s", attempt, exc)
                raise

            delay = backoff_for(attempt)

            if time_remaining is not None:
                left = time_remaining()
                if left is not None and delay >= left:
                    # Sleeping past the deadline spends the caller's remaining
                    # budget to arrive at the same failure, later.
                    LOG.warning(
                        "attempt %d failed (%s); %.2fs backoff exceeds %.2fs "
                        "remaining, not retrying",
                        attempt,
                        exc,
                        delay,
                        left,
                    )
                    raise

            LOG.info(
                "attempt %d failed (%s); retrying in %.2fs", attempt, exc, delay
            )
            time.sleep(delay)
