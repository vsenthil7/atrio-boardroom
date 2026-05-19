"""Unit tests for inference provider clients."""
from __future__ import annotations

import httpx
import pytest
import respx

from app.inference.providers import (
    CompletionResult,
    FeatherlessClient,
    GeminiClient,
    MockClient,
    ProviderError,
)


# ---------------------------------------------------------------- mock client


async def test_mock_complete_deterministic():
    c = MockClient()
    r1 = await c.complete(
        model="m", system="You are the CFO.", user="hello", temperature=0.5, max_tokens=128
    )
    r2 = await c.complete(
        model="m", system="You are the CFO.", user="hello", temperature=0.5, max_tokens=128
    )
    assert r1.text == r2.text
    assert "CFO" in r1.text
    assert r1.tokens_in > 0
    assert r1.tokens_out > 0


async def test_mock_complete_picks_agent_from_system():
    c = MockClient()
    for agent, marker in [("cto", "CTO"), ("cmo", "CMO"), ("coo", "COO"), ("counsel", "COUNSEL")]:
        r = await c.complete(
            model="m",
            system=f"You are the {agent} of the boardroom.",
            user="q",
            temperature=0.5,
            max_tokens=128,
        )
        assert marker in r.text


async def test_mock_stream_yields_tokens():
    c = MockClient()
    pieces = []
    async for tok in c.stream(
        model="m", system="You are the cfo.", user="hi", temperature=0.5, max_tokens=128
    ):
        pieces.append(tok)
    assert len(pieces) > 1
    assert "CFO" in "".join(pieces)


async def test_mock_configure_fail_then_raises():
    c = MockClient()
    c.configure(fail=True)
    with pytest.raises(ProviderError):
        await c.complete(model="m", system="sys", user="u", temperature=0.5, max_tokens=128)
    with pytest.raises(ProviderError):
        async for _ in c.stream(
            model="m", system="sys", user="u", temperature=0.5, max_tokens=128
        ):
            pass


# ---------------------------------------------------------------- gemini


@respx.mock
async def test_gemini_complete_happy_path():
    route = respx.post("https://generativelanguage.googleapis.com/v1beta/models/gemini-3-pro:generateContent").mock(
        return_value=httpx.Response(
            200,
            json={
                "candidates": [
                    {"content": {"parts": [{"text": "hello world"}]}}
                ],
                "usageMetadata": {"promptTokenCount": 4, "candidatesTokenCount": 2},
            },
        )
    )
    c = GeminiClient("test-key")
    r = await c.complete(
        model="gemini-3-pro",
        system="be helpful",
        user="hi",
        temperature=0.5,
        max_tokens=64,
    )
    assert route.called
    assert isinstance(r, CompletionResult)
    assert r.text == "hello world"
    assert r.tokens_in == 4
    assert r.tokens_out == 2


@respx.mock
async def test_gemini_complete_http_error_raises():
    respx.post(
        "https://generativelanguage.googleapis.com/v1beta/models/gemini-3-pro:generateContent"
    ).mock(return_value=httpx.Response(500, text="boom"))
    c = GeminiClient("k")
    with pytest.raises(ProviderError, match="500"):
        await c.complete(model="gemini-3-pro", system="s", user="u", temperature=0.5, max_tokens=10)


@respx.mock
async def test_gemini_complete_transport_error():
    respx.post(
        "https://generativelanguage.googleapis.com/v1beta/models/gemini-3-pro:generateContent"
    ).mock(side_effect=httpx.ConnectError("connection failed"))
    c = GeminiClient("k")
    with pytest.raises(ProviderError, match="transport error"):
        await c.complete(model="gemini-3-pro", system="s", user="u", temperature=0.5, max_tokens=10)


@respx.mock
async def test_gemini_stream_happy_path():
    # SSE-style stream
    body = (
        'data: {"candidates":[{"content":{"parts":[{"text":"hello "}]}}]}\n'
        'data: {"candidates":[{"content":{"parts":[{"text":"world"}]}}]}\n'
    )
    respx.post(
        "https://generativelanguage.googleapis.com/v1beta/models/gemini-3-pro:streamGenerateContent"
    ).mock(return_value=httpx.Response(200, content=body))
    c = GeminiClient("k")
    tokens = []
    async for tok in c.stream(
        model="gemini-3-pro", system="s", user="u", temperature=0.5, max_tokens=10
    ):
        tokens.append(tok)
    assert "".join(tokens) == "hello world"


@respx.mock
async def test_gemini_stream_error_status():
    respx.post(
        "https://generativelanguage.googleapis.com/v1beta/models/gemini-3-pro:streamGenerateContent"
    ).mock(return_value=httpx.Response(401, text="unauthorised"))
    c = GeminiClient("k")
    with pytest.raises(ProviderError, match="401"):
        async for _ in c.stream(model="gemini-3-pro", system="s", user="u", temperature=0.5, max_tokens=10):
            pass


# ---------------------------------------------------------------- featherless


@respx.mock
async def test_featherless_complete_happy_path():
    route = respx.post("https://api.featherless.ai/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "yo"}}],
                "usage": {"prompt_tokens": 3, "completion_tokens": 1},
            },
        )
    )
    c = FeatherlessClient("k")
    r = await c.complete(model="llama", system="s", user="u", temperature=0.5, max_tokens=10)
    assert route.called
    assert r.text == "yo"
    assert r.tokens_in == 3
    assert r.tokens_out == 1


@respx.mock
async def test_featherless_complete_http_error():
    respx.post("https://api.featherless.ai/v1/chat/completions").mock(
        return_value=httpx.Response(503, text="overloaded")
    )
    c = FeatherlessClient("k")
    with pytest.raises(ProviderError, match="503"):
        await c.complete(model="llama", system="s", user="u", temperature=0.5, max_tokens=10)


@respx.mock
async def test_featherless_stream_happy_path():
    body = (
        'data: {"choices":[{"delta":{"content":"foo "}}]}\n'
        'data: {"choices":[{"delta":{"content":"bar"}}]}\n'
        "data: [DONE]\n"
    )
    respx.post("https://api.featherless.ai/v1/chat/completions").mock(
        return_value=httpx.Response(200, content=body)
    )
    c = FeatherlessClient("k")
    tokens = []
    async for t in c.stream(model="llama", system="s", user="u", temperature=0.5, max_tokens=10):
        tokens.append(t)
    assert "".join(tokens) == "foo bar"


@respx.mock
async def test_featherless_stream_error_status():
    respx.post("https://api.featherless.ai/v1/chat/completions").mock(
        return_value=httpx.Response(429, text="rate limited")
    )
    c = FeatherlessClient("k")
    with pytest.raises(ProviderError, match="429"):
        async for _ in c.stream(model="llama", system="s", user="u", temperature=0.5, max_tokens=10):
            pass


@respx.mock
async def test_featherless_transport_error():
    respx.post("https://api.featherless.ai/v1/chat/completions").mock(
        side_effect=httpx.ConnectError("nope")
    )
    c = FeatherlessClient("k")
    with pytest.raises(ProviderError, match="transport"):
        await c.complete(model="llama", system="s", user="u", temperature=0.5, max_tokens=10)


@respx.mock
async def test_gemini_complete_with_usage_default(monkeypatch):
    respx.post(
        "https://generativelanguage.googleapis.com/v1beta/models/gemini-3-pro:generateContent"
    ).mock(
        return_value=httpx.Response(
            200,
            json={"candidates": [{"content": {"parts": [{"text": "hi"}]}}]},
        )
    )
    c = GeminiClient("k")
    r = await c.complete(model="gemini-3-pro", system="s", user="hello world", temperature=0.1, max_tokens=10)
    # No usageMetadata → counts approximated from word counts
    assert r.tokens_in == 2  # "hello world"


@respx.mock
async def test_featherless_complete_missing_usage_falls_back_to_wordcount():
    respx.post("https://api.featherless.ai/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={"choices": [{"message": {"content": "yo"}}]},
        )
    )
    c = FeatherlessClient("k")
    r = await c.complete(model="llama", system="s", user="abc def ghi", temperature=0.1, max_tokens=10)
    assert r.tokens_in == 3


@respx.mock
async def test_gemini_stream_handles_malformed_chunks():
    body = (
        "data: not-json\n"
        'data: {"candidates":[{"content":{"parts":[{"text":"ok"}]}}]}\n'
    )
    respx.post(
        "https://generativelanguage.googleapis.com/v1beta/models/x:streamGenerateContent"
    ).mock(return_value=httpx.Response(200, content=body))
    c = GeminiClient("k")
    out = []
    async for tok in c.stream(model="x", system="s", user="u", temperature=0.5, max_tokens=10):
        out.append(tok)
    assert out == ["ok"]


@respx.mock
async def test_featherless_stream_handles_malformed_chunks():
    body = (
        "data: not-json\n"
        'data: {"choices":[{"delta":{"content":"ok"}}]}\n'
        "data: [DONE]\n"
    )
    respx.post("https://api.featherless.ai/v1/chat/completions").mock(
        return_value=httpx.Response(200, content=body)
    )
    c = FeatherlessClient("k")
    out = []
    async for tok in c.stream(model="x", system="s", user="u", temperature=0.5, max_tokens=10):
        out.append(tok)
    assert out == ["ok"]


@respx.mock
async def test_featherless_stream_transport_error():
    respx.post("https://api.featherless.ai/v1/chat/completions").mock(
        side_effect=httpx.ConnectError("boom")
    )
    c = FeatherlessClient("k")
    with pytest.raises(ProviderError, match="transport"):
        async for _ in c.stream(model="x", system="s", user="u", temperature=0.5, max_tokens=10):
            pass


@respx.mock
async def test_gemini_stream_transport_error():
    respx.post(
        "https://generativelanguage.googleapis.com/v1beta/models/x:streamGenerateContent"
    ).mock(side_effect=httpx.ConnectError("nope"))
    c = GeminiClient("k")
    with pytest.raises(ProviderError, match="transport"):
        async for _ in c.stream(model="x", system="s", user="u", temperature=0.5, max_tokens=10):
            pass
