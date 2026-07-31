"""Google AI Studio (Gemini) over its REST API.

The free tier is what makes the deployed demo cost nothing -- Ollama cannot
follow us to Railway or Fly, which have no GPU. Its ~10 RPM ceiling is also
the reason the rate limiter and the retry ladder exist.
"""

import os

import httpx

from .base import (
    Completion,
    Provider,
    ProviderNotFound,
    ProviderRateLimited,
    ProviderRejected,
    ProviderTimeout,
    ProviderUnavailable,
    set_fields,
)

BASE_URL = os.environ.get(
    "GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta"
)
TIMEOUT_SECONDS = float(os.environ.get("GEMINI_TIMEOUT_SECONDS", "60"))

# Gemini camel-cases its generation config and renames the output cap. Same
# knobs, different spelling -- exactly the per-provider divergence the nested
# GenerationConfig message was shaped for.
_CONFIG_KEYS = {
    "temperature": "temperature",
    "max_tokens": "maxOutputTokens",
    "top_k": "topK",
    "top_p": "topP",
}


def _detail(response: httpx.Response) -> str:
    try:
        return response.json().get("error", {}).get("message", response.text)
    except ValueError:
        return response.text


class GeminiProvider(Provider):
    def complete(
        self, model: str, prompt: str, config, timeout: float | None = None
    ) -> Completion:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            # Terminal, not retryable: a missing key never appears on attempt 2.
            raise ProviderRejected("GEMINI_API_KEY is not set")

        generation_config = {
            _CONFIG_KEYS[name]: value
            for name, value in set_fields(config).items()
            if name in _CONFIG_KEYS
        }

        try:
            response = httpx.post(
                f"{BASE_URL}/models/{model}:generateContent",
                headers={"x-goog-api-key": api_key},
                json={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": generation_config,
                },
                timeout=min(TIMEOUT_SECONDS, timeout) if timeout else TIMEOUT_SECONDS,
            )
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise ProviderTimeout(f"gemini timed out: {exc}") from exc
        except httpx.HTTPStatusError as exc:
            code = exc.response.status_code
            detail = _detail(exc.response)
            if code == 429:
                raise ProviderRateLimited(f"gemini: {detail}") from exc
            if code == 404:
                raise ProviderNotFound(f"gemini: {detail}") from exc
            if 400 <= code < 500:
                # Bad key, malformed request, blocked prompt -- none survive a
                # retry.
                raise ProviderRejected(f"gemini returned {code}: {detail}") from exc
            raise ProviderUnavailable(f"gemini returned {code}: {detail}") from exc
        except httpx.HTTPError as exc:
            raise ProviderUnavailable(f"gemini at {BASE_URL}: {exc}") from exc

        body = response.json()
        candidates = body.get("candidates") or []
        if not candidates:
            # Safety filters return 200 with no candidate and a promptFeedback
            # block; treating that as success would write an empty completion
            # into step_results.
            raise ProviderRejected(f"gemini returned no candidate: {body.get('promptFeedback')}")

        parts = candidates[0].get("content", {}).get("parts", [])
        usage = body.get("usageMetadata", {})
        return Completion(
            text="".join(part.get("text", "") for part in parts),
            prompt_tokens=usage.get("promptTokenCount", 0),
            completion_tokens=usage.get("candidatesTokenCount", 0),
        )
