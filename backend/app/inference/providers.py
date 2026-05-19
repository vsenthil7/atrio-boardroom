"""Provider client implementations.

Each provider speaks the same `InferenceClient` protocol: given a prompt and
model, yield tokens (streaming) and return the full text. Errors raise
`ProviderError` which the gateway catches to invoke the fallback chain.

In mock mode (no API keys or `ATRIO_MOCK_INFERENCE=true`), each provider
returns a deterministic stub response so the whole product works offline for
tests and demos.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

import httpx

from app.core.logging import get_logger

log = get_logger(__name__)


class ProviderError(Exception):
    """Raised by a provider client when the call fails. Triggers fallback."""


@dataclass(frozen=True)
class CompletionResult:
    text: str
    tokens_in: int
    tokens_out: int


class InferenceClient(ABC):
    """Abstract provider client."""

    name: str = "abstract"

    @abstractmethod
    async def stream(
        self,
        *,
        model: str,
        system: str,
        user: str,
        temperature: float,
        max_tokens: int,
        timeout_seconds: float = 30.0,
    ) -> AsyncIterator[str]:
        """Yield text tokens (or token-like chunks) from the provider."""
        ...

    @abstractmethod
    async def complete(
        self,
        *,
        model: str,
        system: str,
        user: str,
        temperature: float,
        max_tokens: int,
        timeout_seconds: float = 30.0,
    ) -> CompletionResult:
        """Non-streaming completion."""
        ...


# ---------------------------------------------------------------------------
# Mock provider
# ---------------------------------------------------------------------------


class MockClient(InferenceClient):
    """Deterministic mock — returns a templated answer based on the prompt hash.

    The output is shaped to look like an agent talking: a short paragraph
    that varies by agent_id (encoded into the system prompt). Crucially, the
    output is deterministic for a given input so tests can assert exactly.
    """

    name = "mock"

    def __init__(self, *, fail: bool = False) -> None:
        self._fail = fail

    def configure(self, *, fail: bool) -> None:
        self._fail = fail

    @staticmethod
    def _build_response(model: str, system: str, user: str) -> str:
        # Extract an agent identifier from the system prompt if present.
        agent_id = "agent"
        for token in ("facilitator", "cfo", "cto", "cmo", "coo", "counsel"):
            if token in system.lower():
                agent_id = token
                break
        digest = hashlib.sha256(f"{model}|{system}|{user}".encode()).hexdigest()[:8]
        return (
            f"[{agent_id.upper()}] "
            f"Considering the question — '{user[:80]}' — my position is that the right "
            f"call depends on three factors: time-to-impact, downside-of-being-wrong, "
            f"and reversibility. Mock signature: {digest}."
        )

    async def stream(
        self,
        *,
        model: str,
        system: str,
        user: str,
        temperature: float,
        max_tokens: int,
        timeout_seconds: float = 30.0,
    ) -> AsyncIterator[str]:
        if self._fail:
            raise ProviderError(f"mock provider configured to fail (model={model})")
        text = self._build_response(model, system, user)
        for word in text.split(" "):
            yield word + " "
            await asyncio.sleep(0)  # cooperative

    async def complete(
        self,
        *,
        model: str,
        system: str,
        user: str,
        temperature: float,
        max_tokens: int,
        timeout_seconds: float = 30.0,
    ) -> CompletionResult:
        if self._fail:
            raise ProviderError(f"mock provider configured to fail (model={model})")
        text = self._build_response(model, system, user)
        return CompletionResult(
            text=text,
            tokens_in=max(1, len(user.split())),
            tokens_out=max(1, len(text.split())),
        )


# ---------------------------------------------------------------------------
# Gemini
# ---------------------------------------------------------------------------


class GeminiClient(InferenceClient):
    """Google Gemini via generativelanguage.googleapis.com."""

    name = "gemini"

    def __init__(self, api_key: str, base_url: str | None = None) -> None:
        self._key = api_key
        self._base = base_url or "https://generativelanguage.googleapis.com/v1beta"

    def _build_payload(
        self, system: str, user: str, temperature: float, max_tokens: int
    ) -> dict[str, Any]:
        return {
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "systemInstruction": {"parts": [{"text": system}]},
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
            },
        }

    async def stream(
        self,
        *,
        model: str,
        system: str,
        user: str,
        temperature: float,
        max_tokens: int,
        timeout_seconds: float = 30.0,
    ) -> AsyncIterator[str]:
        url = f"{self._base}/models/{model}:streamGenerateContent"
        params = {"key": self._key, "alt": "sse"}
        payload = self._build_payload(system, user, temperature, max_tokens)
        try:
            async with httpx.AsyncClient(timeout=timeout_seconds) as client:
                async with client.stream("POST", url, params=params, json=payload) as resp:
                    if resp.status_code >= 400:
                        body = await resp.aread()
                        raise ProviderError(
                            f"gemini {model} returned {resp.status_code}: {body!r}"
                        )
                    async for line in resp.aiter_lines():
                        if not line or not line.startswith("data:"):
                            continue
                        chunk = line[5:].strip()
                        if not chunk:
                            continue
                        try:
                            obj = json.loads(chunk)
                        except json.JSONDecodeError:
                            continue
                        for cand in obj.get("candidates", []):
                            for part in cand.get("content", {}).get("parts", []):
                                text = part.get("text")
                                if text:
                                    yield text
        except httpx.HTTPError as e:
            raise ProviderError(f"gemini transport error: {e}") from e

    async def complete(
        self,
        *,
        model: str,
        system: str,
        user: str,
        temperature: float,
        max_tokens: int,
        timeout_seconds: float = 30.0,
    ) -> CompletionResult:
        url = f"{self._base}/models/{model}:generateContent"
        params = {"key": self._key}
        payload = self._build_payload(system, user, temperature, max_tokens)
        try:
            async with httpx.AsyncClient(timeout=timeout_seconds) as client:
                resp = await client.post(url, params=params, json=payload)
                if resp.status_code >= 400:
                    raise ProviderError(
                        f"gemini {model} returned {resp.status_code}: {resp.text[:300]}"
                    )
                data = resp.json()
        except httpx.HTTPError as e:
            raise ProviderError(f"gemini transport error: {e}") from e

        parts: list[str] = []
        for cand in data.get("candidates", []):
            for part in cand.get("content", {}).get("parts", []):
                if "text" in part:
                    parts.append(part["text"])
        text = "".join(parts)
        usage = data.get("usageMetadata") or {}
        return CompletionResult(
            text=text,
            tokens_in=int(usage.get("promptTokenCount", len(user.split()))),
            tokens_out=int(usage.get("candidatesTokenCount", len(text.split()))),
        )


# ---------------------------------------------------------------------------
# Featherless (OpenAI-compatible)
# ---------------------------------------------------------------------------


class FeatherlessClient(InferenceClient):
    """Featherless via OpenAI-compatible /v1/chat/completions."""

    name = "featherless"

    def __init__(self, api_key: str, base_url: str | None = None) -> None:
        self._key = api_key
        self._base = base_url or "https://api.featherless.ai/v1"

    def _messages(self, system: str, user: str) -> list[dict[str, str]]:
        return [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]

    async def stream(
        self,
        *,
        model: str,
        system: str,
        user: str,
        temperature: float,
        max_tokens: int,
        timeout_seconds: float = 30.0,
    ) -> AsyncIterator[str]:
        url = f"{self._base}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self._key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model,
            "messages": self._messages(system, user),
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }
        try:
            async with httpx.AsyncClient(timeout=timeout_seconds) as client:
                async with client.stream(
                    "POST", url, headers=headers, json=payload
                ) as resp:
                    if resp.status_code >= 400:
                        body = await resp.aread()
                        raise ProviderError(
                            f"featherless {model} returned {resp.status_code}: {body!r}"
                        )
                    async for line in resp.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        chunk = line[5:].strip()
                        if chunk == "[DONE]" or not chunk:
                            continue
                        try:
                            obj = json.loads(chunk)
                        except json.JSONDecodeError:
                            continue
                        for choice in obj.get("choices", []):
                            delta = choice.get("delta", {})
                            content = delta.get("content")
                            if content:
                                yield content
        except httpx.HTTPError as e:
            raise ProviderError(f"featherless transport error: {e}") from e

    async def complete(
        self,
        *,
        model: str,
        system: str,
        user: str,
        temperature: float,
        max_tokens: int,
        timeout_seconds: float = 30.0,
    ) -> CompletionResult:
        url = f"{self._base}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self._key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model,
            "messages": self._messages(system, user),
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }
        try:
            async with httpx.AsyncClient(timeout=timeout_seconds) as client:
                resp = await client.post(url, headers=headers, json=payload)
                if resp.status_code >= 400:
                    raise ProviderError(
                        f"featherless {model} returned {resp.status_code}: {resp.text[:300]}"
                    )
                data = resp.json()
        except httpx.HTTPError as e:
            raise ProviderError(f"featherless transport error: {e}") from e

        choice = (data.get("choices") or [{}])[0]
        text = choice.get("message", {}).get("content", "")
        usage = data.get("usage") or {}
        return CompletionResult(
            text=text,
            tokens_in=int(usage.get("prompt_tokens", len(user.split()))),
            tokens_out=int(usage.get("completion_tokens", len(text.split()))),
        )
