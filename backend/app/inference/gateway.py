"""AI Inference Gateway — the single entry point for all model calls.

Implements principle P5: every inference call resolves the agent through the
registry, picks the primary provider, on failure walks the fallback chain,
and emits audit + observability per call. No agent in code may call a
provider client directly.
"""
from __future__ import annotations

import time
from collections.abc import AsyncIterator, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.core.config import get_settings, project_root
from app.core.errors import InferenceFailure
from app.core.logging import get_logger
from app.inference.providers import (
    FeatherlessClient,
    GeminiClient,
    InferenceClient,
    MockClient,
    ProviderError,
)
from app.inference.registry import AgentEntry, ModelRegistry

log = get_logger(__name__)


@dataclass
class AgentInvocationContext:
    """Structured context object — only thing the gateway accepts.

    Enforces §5.5 data minimisation: callers cannot smuggle audit logs,
    other agents' raw memory, or other sessions' transcripts in.
    """

    tenant_id: str
    session_id: str | None
    agent_id: str
    user_message: str
    language: str = "en"
    memory_snippets: list[str] = field(default_factory=list)
    document_summaries: list[str] = field(default_factory=list)
    history: list[dict[str, str]] = field(default_factory=list)  # [{role, text}]
    overrides: dict[str, Any] = field(default_factory=dict)


@dataclass
class InvocationResult:
    """Result of one (primary or fallback) provider call."""

    text: str
    tokens_in: int
    tokens_out: int
    latency_ms: int
    model_used: str
    provider_used: str
    was_fallback: bool
    prompt_version: str
    fallback_reasons: list[str] = field(default_factory=list)


class _AuditSink:
    """Audit sink protocol satisfied by the audit service.

    The gateway publishes a `model_invocation` event for every call. In test
    mode this is a no-op; production wires it to AuditService.
    """

    def record(self, kind: str, payload: dict[str, Any]) -> None:  # pragma: no cover
        ...


class _NoopSink(_AuditSink):
    def record(self, kind: str, payload: dict[str, Any]) -> None:
        return None


class InferenceGateway:
    """Resolve agent → provider; primary → fallback; emit audit."""

    def __init__(
        self,
        registry: ModelRegistry,
        clients: dict[str, InferenceClient] | None = None,
        audit_sink: _AuditSink | None = None,
        prompts_dir: Path | None = None,
    ) -> None:
        self._registry = registry
        self._clients = clients or {}
        self._sink: _AuditSink = audit_sink or _NoopSink()
        self._prompts_dir = prompts_dir or project_root() / get_settings().prompts_dir

    # ---------------------------------------------------- registry access

    def registry(self) -> ModelRegistry:
        return self._registry

    def list_agents(self) -> list[str]:
        return self._registry.list_agents()

    # ------------------------------------------------------- prompts

    def render_system_prompt(self, entry: AgentEntry, ctx: AgentInvocationContext) -> str:
        """Load `prompts/<agent>_<version>.txt` and inject the context."""
        prompt_path = self._prompts_dir / f"{entry.agent_id}_{entry.prompt_version}.txt"
        if not prompt_path.exists():
            template = (
                f"You are the {entry.agent_id} of an AI boardroom. Speak in role.\n\n"
                "{recall}\n{documents}\n"
                "Use plain professional English. Output 2–4 sentences."
            )
        else:
            template = prompt_path.read_text(encoding="utf-8")

        recall = (
            "Recall:\n" + "\n".join(f" - {m}" for m in ctx.memory_snippets)
            if ctx.memory_snippets
            else ""
        )
        documents = (
            "Documents in scope:\n" + "\n".join(f" - {d}" for d in ctx.document_summaries)
            if ctx.document_summaries
            else ""
        )
        return template.replace("{recall}", recall).replace("{documents}", documents)

    # ------------------------------------------------------- invocation

    async def invoke(self, ctx: AgentInvocationContext) -> InvocationResult:
        """Run the full primary-then-fallback chain. Raises InferenceFailure if all fail."""
        entry = self._registry.get(ctx.agent_id)
        system_prompt = self.render_system_prompt(entry, ctx)
        reasons: list[str] = []

        for idx, choice in enumerate(entry.chain):
            client = self._clients.get(choice.provider)
            if client is None:
                reasons.append(f"{choice.provider}:unconfigured")
                continue
            start = time.perf_counter()
            try:
                result = await client.complete(
                    model=choice.model,
                    system=system_prompt,
                    user=ctx.user_message,
                    temperature=entry.temperature,
                    max_tokens=entry.max_tokens,
                )
                latency_ms = int((time.perf_counter() - start) * 1000)
                was_fallback = idx > 0
                invocation = InvocationResult(
                    text=result.text,
                    tokens_in=result.tokens_in,
                    tokens_out=result.tokens_out,
                    latency_ms=latency_ms,
                    model_used=choice.model,
                    provider_used=choice.provider,
                    was_fallback=was_fallback,
                    prompt_version=entry.prompt_version,
                    fallback_reasons=list(reasons),
                )
                self._sink.record(
                    "model_invocation",
                    {
                        "tenant_id": ctx.tenant_id,
                        "session_id": ctx.session_id,
                        "agent_id": ctx.agent_id,
                        "model_used": choice.label(),
                        "was_fallback": was_fallback,
                        "tokens_in": result.tokens_in,
                        "tokens_out": result.tokens_out,
                        "latency_ms": latency_ms,
                        "prompt_version": entry.prompt_version,
                        "fallback_reasons": reasons,
                    },
                )
                # Prometheus metrics
                from app.observability import (
                    inference_invocations_total,
                    inference_fallbacks_total,
                    inference_latency_seconds,
                )

                m_labels = {"agent_id": ctx.agent_id, "provider": choice.provider}
                inference_invocations_total.inc(labels=m_labels)
                if was_fallback:
                    inference_fallbacks_total.inc(labels=m_labels)
                inference_latency_seconds.observe(latency_ms / 1000.0, labels=m_labels)
                return invocation
            except ProviderError as e:
                latency_ms = int((time.perf_counter() - start) * 1000)
                reasons.append(f"{choice.provider}:{e}")
                log.warning(
                    "inference_provider_failed",
                    agent_id=ctx.agent_id,
                    provider=choice.provider,
                    model=choice.model,
                    latency_ms=latency_ms,
                    error=str(e),
                )
                continue

        # All providers failed.
        self._sink.record(
            "model_invocation_all_failed",
            {
                "tenant_id": ctx.tenant_id,
                "session_id": ctx.session_id,
                "agent_id": ctx.agent_id,
                "fallback_reasons": reasons,
            },
        )
        from app.observability import inference_failures_total

        inference_failures_total.inc(labels={"agent_id": ctx.agent_id})
        raise InferenceFailure(
            f"All providers failed for agent={ctx.agent_id}",
            details={"chain": reasons},
        )

    async def stream(self, ctx: AgentInvocationContext) -> AsyncIterator[str]:
        """Stream tokens from the first successful provider in the chain."""
        entry = self._registry.get(ctx.agent_id)
        system_prompt = self.render_system_prompt(entry, ctx)
        reasons: list[str] = []

        for idx, choice in enumerate(entry.chain):
            client = self._clients.get(choice.provider)
            if client is None:
                reasons.append(f"{choice.provider}:unconfigured")
                continue
            try:
                # We have to attempt the stream and yield from it; if the
                # first iteration fails we move to fallback.
                async for token in self._stream_once(client, choice.model, entry, system_prompt, ctx):
                    yield token
                # success
                self._sink.record(
                    "model_invocation_stream",
                    {
                        "tenant_id": ctx.tenant_id,
                        "session_id": ctx.session_id,
                        "agent_id": ctx.agent_id,
                        "model_used": choice.label(),
                        "was_fallback": idx > 0,
                        "prompt_version": entry.prompt_version,
                    },
                )
                return
            except ProviderError as e:
                reasons.append(f"{choice.provider}:{e}")
                continue
        raise InferenceFailure(
            f"All providers failed (streaming) for agent={ctx.agent_id}",
            details={"chain": reasons},
        )

    @staticmethod
    async def _stream_once(
        client: InferenceClient,
        model: str,
        entry: AgentEntry,
        system: str,
        ctx: AgentInvocationContext,
    ) -> AsyncIterator[str]:
        async for token in client.stream(
            model=model,
            system=system,
            user=ctx.user_message,
            temperature=entry.temperature,
            max_tokens=entry.max_tokens,
        ):
            yield token

    # -------------------------------------------- gateway-level utilities

    def set_audit_sink(self, sink: _AuditSink) -> None:
        self._sink = sink

    def set_client(self, provider: str, client: InferenceClient) -> None:
        self._clients[provider] = client

    def providers(self) -> Iterable[str]:
        return tuple(self._clients.keys())


# ---------------------------------------------------------------------------
# Process-wide gateway factory
# ---------------------------------------------------------------------------

_gateway: InferenceGateway | None = None


def _build_default_gateway() -> InferenceGateway:
    settings = get_settings()
    registry_path = project_root() / settings.model_registry_path
    if not registry_path.exists():
        registry_path = Path(settings.model_registry_path)
    registry = ModelRegistry(registry_path)

    clients: dict[str, InferenceClient] = {}
    # Mock provider always available; agents listing 'mock' as primary use it.
    clients["mock"] = MockClient()
    if settings.atrio_mock_inference:
        # In mock mode, register all providers as the mock client so any
        # registry routing resolves successfully without real API calls.
        clients["gemini"] = MockClient()
        clients["featherless"] = MockClient()
    else:  # pragma: no cover - prod path
        if settings.gemini_api_key:
            clients["gemini"] = GeminiClient(settings.gemini_api_key)
        if settings.featherless_api_key:
            clients["featherless"] = FeatherlessClient(settings.featherless_api_key)

    return InferenceGateway(registry=registry, clients=clients)


def get_gateway() -> InferenceGateway:
    global _gateway
    if _gateway is None:
        _gateway = _build_default_gateway()
    return _gateway


def reset_gateway() -> None:
    global _gateway
    _gateway = None
