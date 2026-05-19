"""Unit tests for the inference gateway."""
from __future__ import annotations

import textwrap
from collections.abc import AsyncIterator
from typing import Any

import pytest

from app.core.errors import InferenceFailure
from app.inference.gateway import (
    AgentInvocationContext,
    InferenceGateway,
    InvocationResult,
    _NoopSink,
    _build_default_gateway,
    get_gateway,
    reset_gateway,
)
from app.inference.providers import (
    CompletionResult,
    InferenceClient,
    MockClient,
    ProviderError,
)
from app.inference.registry import ModelRegistry


class _FailingClient(InferenceClient):
    name = "fail"

    async def complete(self, **kwargs: Any) -> CompletionResult:  # type: ignore[override]
        raise ProviderError("always fails")

    async def stream(self, **kwargs: Any) -> AsyncIterator[str]:  # type: ignore[override]
        raise ProviderError("always fails")
        yield  # pragma: no cover  (needed to make it an async generator)


class _CapturingSink:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, Any]]] = []

    def record(self, kind: str, payload: dict[str, Any]) -> None:
        self.events.append((kind, payload))


def _registry(tmp_path):
    p = tmp_path / "r.yaml"
    p.write_text(
        textwrap.dedent(
            """
            agents:
              cfo:
                primary:
                  provider: gemini
                  model: gemini-3-pro
                fallback:
                  - provider: featherless
                    model: llama-70b
                prompt_version: v1
                temperature: 0.5
                max_tokens: 256
              cto:
                primary:
                  provider: featherless
                  model: llama-70b
                fallback: []
                prompt_version: v1
                temperature: 0.5
                max_tokens: 256
            """
        )
    )
    return ModelRegistry(p)


async def test_gateway_picks_primary_when_ok(tmp_path):
    gw = InferenceGateway(
        registry=_registry(tmp_path),
        clients={"gemini": MockClient(), "featherless": MockClient()},
    )
    ctx = AgentInvocationContext(
        tenant_id="t", session_id="s", agent_id="cfo", user_message="hi"
    )
    r = await gw.invoke(ctx)
    assert r.provider_used == "gemini"
    assert r.model_used == "gemini-3-pro"
    assert r.was_fallback is False
    assert r.text != ""


async def test_gateway_falls_back_when_primary_fails(tmp_path):
    failing = MockClient(fail=True)
    ok = MockClient()
    gw = InferenceGateway(
        registry=_registry(tmp_path),
        clients={"gemini": failing, "featherless": ok},
    )
    ctx = AgentInvocationContext(tenant_id="t", session_id="s", agent_id="cfo", user_message="hi")
    r = await gw.invoke(ctx)
    assert r.was_fallback is True
    assert r.provider_used == "featherless"
    assert any("gemini" in reason for reason in r.fallback_reasons)


async def test_gateway_all_providers_fail_raises(tmp_path):
    gw = InferenceGateway(
        registry=_registry(tmp_path),
        clients={"gemini": MockClient(fail=True), "featherless": MockClient(fail=True)},
    )
    ctx = AgentInvocationContext(tenant_id="t", session_id="s", agent_id="cfo", user_message="hi")
    with pytest.raises(InferenceFailure):
        await gw.invoke(ctx)


async def test_gateway_skips_unconfigured_provider(tmp_path):
    # CTO has only featherless primary, no fallback. If featherless missing → fail.
    gw = InferenceGateway(
        registry=_registry(tmp_path),
        clients={"gemini": MockClient()},  # no featherless
    )
    ctx = AgentInvocationContext(tenant_id="t", session_id="s", agent_id="cto", user_message="hi")
    with pytest.raises(InferenceFailure):
        await gw.invoke(ctx)


async def test_gateway_emits_audit_event_on_success(tmp_path):
    sink = _CapturingSink()
    gw = InferenceGateway(
        registry=_registry(tmp_path),
        clients={"gemini": MockClient(), "featherless": MockClient()},
        audit_sink=sink,
    )
    ctx = AgentInvocationContext(tenant_id="t", session_id="s", agent_id="cfo", user_message="hi")
    await gw.invoke(ctx)
    assert sink.events
    kind, payload = sink.events[0]
    assert kind == "model_invocation"
    assert payload["model_used"] == "gemini/gemini-3-pro"
    assert payload["was_fallback"] is False
    assert payload["agent_id"] == "cfo"


async def test_gateway_emits_audit_on_all_failed(tmp_path):
    sink = _CapturingSink()
    gw = InferenceGateway(
        registry=_registry(tmp_path),
        clients={"gemini": _FailingClient(), "featherless": _FailingClient()},
        audit_sink=sink,
    )
    ctx = AgentInvocationContext(tenant_id="t", session_id="s", agent_id="cfo", user_message="hi")
    with pytest.raises(InferenceFailure):
        await gw.invoke(ctx)
    kinds = [e[0] for e in sink.events]
    assert "model_invocation_all_failed" in kinds


async def test_render_system_prompt_uses_template_file(tmp_path):
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()
    (prompts_dir / "cfo_v1.txt").write_text(
        "You are the CFO. {recall}\n{documents}\nAnswer briefly."
    )
    gw = InferenceGateway(
        registry=_registry(tmp_path),
        clients={"gemini": MockClient(), "featherless": MockClient()},
        prompts_dir=prompts_dir,
    )
    entry = gw.registry().get("cfo")
    rendered = gw.render_system_prompt(
        entry,
        AgentInvocationContext(
            tenant_id="t",
            session_id=None,
            agent_id="cfo",
            user_message="?",
            memory_snippets=["fact A", "fact B"],
            document_summaries=["doc 1"],
        ),
    )
    assert "fact A" in rendered
    assert "fact B" in rendered
    assert "doc 1" in rendered
    assert "You are the CFO" in rendered


async def test_render_system_prompt_default_when_file_missing(tmp_path):
    gw = InferenceGateway(
        registry=_registry(tmp_path),
        clients={"gemini": MockClient(), "featherless": MockClient()},
        prompts_dir=tmp_path / "nonexistent",
    )
    entry = gw.registry().get("cfo")
    out = gw.render_system_prompt(
        entry,
        AgentInvocationContext(
            tenant_id="t",
            session_id=None,
            agent_id="cfo",
            user_message="?",
        ),
    )
    assert "cfo" in out.lower()


async def test_stream_falls_back(tmp_path):
    sink = _CapturingSink()
    gw = InferenceGateway(
        registry=_registry(tmp_path),
        clients={"gemini": _FailingClient(), "featherless": MockClient()},
        audit_sink=sink,
    )
    ctx = AgentInvocationContext(tenant_id="t", session_id="s", agent_id="cfo", user_message="hi")
    out: list[str] = []
    async for tok in gw.stream(ctx):
        out.append(tok)
    assert out, "should produce tokens via fallback"
    # Audit event tagged as stream
    assert any(e[0] == "model_invocation_stream" for e in sink.events)


async def test_stream_all_fail(tmp_path):
    gw = InferenceGateway(
        registry=_registry(tmp_path),
        clients={"gemini": _FailingClient(), "featherless": _FailingClient()},
    )
    ctx = AgentInvocationContext(tenant_id="t", session_id="s", agent_id="cfo", user_message="hi")
    with pytest.raises(InferenceFailure):
        async for _ in gw.stream(ctx):
            pass


def test_noop_sink_is_callable():
    s = _NoopSink()
    s.record("k", {"a": 1})  # no-op, must not raise


def test_set_audit_sink_and_set_client(tmp_path):
    gw = InferenceGateway(
        registry=_registry(tmp_path),
        clients={"gemini": MockClient(), "featherless": MockClient()},
    )
    new_sink = _CapturingSink()
    gw.set_audit_sink(new_sink)
    new_client = MockClient()
    gw.set_client("gemini", new_client)
    assert "gemini" in gw.providers()


def test_list_agents_via_gateway(tmp_path):
    gw = InferenceGateway(
        registry=_registry(tmp_path),
        clients={"gemini": MockClient(), "featherless": MockClient()},
    )
    assert "cfo" in gw.list_agents()


def test_build_default_gateway_uses_mock_clients_when_mock_inference():
    reset_gateway()
    gw = get_gateway()
    assert "mock" in gw.providers()
    # In mock mode all named providers resolve to MockClient
    assert "gemini" in gw.providers()
    assert "featherless" in gw.providers()
    reset_gateway()


def test_reset_gateway_returns_new_instance():
    g1 = get_gateway()
    reset_gateway()
    g2 = get_gateway()
    assert g1 is not g2


def test_build_default_gateway_factory():
    # Build factory directly
    gw = _build_default_gateway()
    assert gw.list_agents()
