"""In-process provider: no network, no cost, no latency variance.

Backs the unit tests and the load test, where the number being measured is
orchestrator throughput rather than someone else's inference.
"""

from .base import Completion, Provider, set_fields


class MockProvider(Provider):
    def complete(self, model: str, prompt: str, config) -> Completion:
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

    # TODO(faults): configurable failure/latency injection so the retry ladder
    # and the load test have something deterministic to exercise.
