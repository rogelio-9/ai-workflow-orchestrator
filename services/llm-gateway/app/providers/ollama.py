"""Local inference via the Ollama HTTP API."""

import os

import httpx

from .base import (
    Completion,
    Provider,
    ProviderNotFound,
    ProviderRateLimited,
    ProviderTimeout,
    ProviderUnavailable,
    set_fields,
)

BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
TIMEOUT_SECONDS = float(os.environ.get("OLLAMA_TIMEOUT_SECONDS", "120"))


def _detail(response: httpx.Response) -> str:
    """Ollama puts a human-readable reason in an `error` field."""
    try:
        return response.json().get("error", response.text)
    except ValueError:
        return response.text


class OllamaProvider(Provider):
    def complete(self, model: str, prompt: str, config) -> Completion:
        options = set_fields(config)
        # Ollama calls the output cap num_predict.
        if "max_tokens" in options:
            options["num_predict"] = options.pop("max_tokens")

        try:
            response = httpx.post(
                f"{BASE_URL}/api/generate",
                json={
                    "model": model,
                    "prompt": prompt,
                    "stream": False,
                    "options": options,
                },
                timeout=TIMEOUT_SECONDS,
            )
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise ProviderTimeout(f"ollama timed out after {TIMEOUT_SECONDS}s") from exc
        except httpx.HTTPStatusError as exc:
            # Status class decides retryable vs not. A missing model is
            # permanent -- retrying it just burns the worker's backoff budget
            # before landing in the DLQ anyway.
            code = exc.response.status_code
            detail = _detail(exc.response)
            if code == 404:
                raise ProviderNotFound(f"ollama: {detail}") from exc
            if code == 429:
                raise ProviderRateLimited(f"ollama: {detail}") from exc
            raise ProviderUnavailable(f"ollama returned {code}: {detail}") from exc
        except httpx.HTTPError as exc:
            raise ProviderUnavailable(f"ollama at {BASE_URL}: {exc}") from exc

        body = response.json()
        return Completion(
            text=body["response"],
            # Reported by the model, not estimated.
            prompt_tokens=body.get("prompt_eval_count", 0),
            completion_tokens=body.get("eval_count", 0),
        )
