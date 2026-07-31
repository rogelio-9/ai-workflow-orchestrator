"""In-process provider: no network, no cost, no latency variance.

Backs the unit tests and the load test, where the number being measured is
orchestrator throughput rather than someone else's inference. Faults are
injectable so the retry ladder and the rate limiter have something
deterministic to exercise -- a real provider only fails when it feels like it.
"""

import os
import threading
import time

from .base import (
    Completion,
    Provider,
    ProviderRateLimited,
    ProviderTimeout,
    ProviderUnavailable,
    set_fields,
)

_FAULTS = {
    "rate_limit": ProviderRateLimited,
    "unavailable": ProviderUnavailable,
    "timeout": ProviderTimeout,
}


class MockProvider(Provider):
    def __init__(
        self,
        fail_mode: str | None = None,
        fail_times: int | None = None,
        latency_ms: int | None = None,
    ):
        self.fail_mode = fail_mode or os.environ.get("MOCK_FAIL_MODE", "")
        # Fail this many calls, then succeed. Failing forever only proves the
        # ladder gives up; a finite count proves it recovers.
        self.fail_times = (
            fail_times
            if fail_times is not None
            else int(os.environ.get("MOCK_FAIL_TIMES", "0"))
        )
        self.latency_ms = (
            latency_ms
            if latency_ms is not None
            else int(os.environ.get("MOCK_LATENCY_MS", "0"))
        )
        self._calls = 0
        # The gRPC thread pool calls this concurrently.
        self._lock = threading.Lock()

    def complete(
        self, model: str, prompt: str, config, timeout: float | None = None
    ) -> Completion:
        with self._lock:
            self._calls += 1
            attempt = self._calls

        if self.latency_ms:
            time.sleep(self.latency_ms / 1000)

        if self.fail_mode and attempt <= self.fail_times:
            error = _FAULTS.get(self.fail_mode)
            if error is None:
                raise ValueError(
                    f"unknown MOCK_FAIL_MODE {self.fail_mode!r}; "
                    f"expected one of {sorted(_FAULTS)}"
                )
            raise error(f"injected {self.fail_mode} on call {attempt}")

        opts = set_fields(config)
        text = f"[mock:{model}] {prompt[:200]}"
        if opts:
            text += f" (config: {opts})"

        # TODO(tokens): char heuristic. A real tokenizer only matters once
        # token counts drive cost reporting.
        return Completion(
            text=text,
            prompt_tokens=len(prompt) // 4,
            completion_tokens=len(text) // 4,
        )
