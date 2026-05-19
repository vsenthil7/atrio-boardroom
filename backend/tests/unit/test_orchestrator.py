"""Unit tests for the multi-agent Orchestrator."""
from __future__ import annotations

from typing import Any

import pytest_asyncio

from app.audit.service import AuditService
from app.db.models import Session as SessionRow, Turn
from app.inference.gateway import get_gateway, reset_gateway
from app.memory.service import MemoryService
from app.services.orchestrator import (
    AgentPosition,
    DEFAULT_S4_SPECIALISTS,
    DEFAULT_SPECIALISTS,
    Orchestrator,
    detect_stance,
    is_material_disagreement,
)


# ----------------------------------------------------- stance detection


def test_detect_stance_support():
    assert detect_stance("I support this approach because of X.") == "support"


def test_detect_stance_oppose():
    assert detect_stance("I oppose this — too risky.") == "oppose"


def test_detect_stance_hesitate():
    assert detect_stance("I'd hesitate — runway implications.") == "hesitate"


def test_detect_stance_unclear():
    assert detect_stance("Some neutral commentary without any stance.") == "unclear"


def test_detect_stance_case_insensitive():
    assert detect_stance("I SUPPORT this idea") == "support"


# ----------------------------------------------------- material disagreement


def _pos(agent: str, stance: str) -> AgentPosition:
    return AgentPosition(
        agent_id=agent,
        text="text",
        stance=stance,
        model_used="mock/mock",
        was_fallback=False,
        latency_ms=1,
        tokens_in=1,
        tokens_out=1,
        prompt_version="v1",
    )


def test_material_disagreement_with_support_and_oppose():
    assert is_material_disagreement([_pos("a", "support"), _pos("b", "oppose")])


def test_material_disagreement_with_support_plus_hesitate_plus_other():
    # support + hesitate + ≥2 stances = material
    assert is_material_disagreement([_pos("a", "support"), _pos("b", "hesitate")])


def test_no_material_disagreement_all_support():
    assert not is_material_disagreement(
        [_pos("a", "support"), _pos("b", "support"), _pos("c", "support")]
    )


def test_no_material_disagreement_all_unclear():
    assert not is_material_disagreement([_pos("a", "unclear")])


# ----------------------------------------------------- orchestrator paths


@pytest_asyncio.fixture
async def session_row(db_session, tenant, founder_user):
    s = SessionRow(
        tenant_id=tenant.id,
        created_by_user_id=founder_user.id,
        kind="boardroom",
        title="orchestration test",
        turn_taking_mode="dissent_driven",
    )
    db_session.add(s)
    await db_session.commit()
    await db_session.refresh(s)
    return s


@pytest_asyncio.fixture
async def orchestrator(db_session, session_row):
    reset_gateway()
    gw = get_gateway()
    return Orchestrator(
        db=db_session,
        gateway=gw,
        audit=AuditService(db_session),
        memory=MemoryService(db_session),
        agent_roster=DEFAULT_S4_SPECIALISTS,
        dissent_cap=2,
    )


async def test_run_single_agent_returns_one_position(orchestrator, tenant, session_row):
    result = await orchestrator.run_single_agent(
        tenant_id=tenant.id, session=session_row, user_message="should we hire 4 engineers?"
    )
    assert len(result.positions) == 1
    assert result.consensus_kind == "unanimous"
    assert result.positions[0].text


async def test_run_single_agent_with_documents(orchestrator, tenant, session_row):
    result = await orchestrator.run_single_agent(
        tenant_id=tenant.id,
        session=session_row,
        user_message="?",
        document_summaries=["summary A"],
    )
    assert result.positions[0].text


async def test_run_debate_returns_specialists_and_consensus(
    db_session, orchestrator, tenant, session_row
):
    result = await orchestrator.run_debate(
        tenant_id=tenant.id,
        session=session_row,
        user_message="should we hire 4 engineers?",
    )
    assert len(result.positions) == len(DEFAULT_S4_SPECIALISTS) - 0  # facilitator removed
    # All positions should have a stance
    assert all(p.stance in {"support", "oppose", "hesitate", "unclear"} for p in result.positions)
    # Consensus must be non-empty
    assert result.consensus_text
    # Turns persisted: at least N agent turns for the first round
    turns = (
        await db_session.execute(
            __import__("sqlalchemy").select(Turn).where(Turn.session_id == session_row.id)
        )
    ).scalars().all()
    assert len(turns) >= len(DEFAULT_S4_SPECIALISTS) - 1


async def test_orchestrator_persist_user_turn(orchestrator, tenant, session_row):
    t = await orchestrator.persist_user_turn(
        tenant_id=tenant.id, session_id=session_row.id, text="hello", language="en"
    )
    assert t.role == "user"
    assert t.seq_no == 1


async def test_classify_consensus_branches():
    assert Orchestrator._classify_consensus([]) == "split"
    assert Orchestrator._classify_consensus([_pos("a", "support")]) == "unanimous"
    assert Orchestrator._classify_consensus([_pos("a", "oppose"), _pos("b", "oppose")]) == "unanimous"
    assert (
        Orchestrator._classify_consensus(
            [_pos("a", "support"), _pos("b", "support"), _pos("c", "oppose")]
        )
        == "majority"
    )
    assert (
        Orchestrator._classify_consensus(
            [_pos("a", "oppose"), _pos("b", "oppose"), _pos("c", "support")]
        )
        == "majority"
    )
    assert (
        Orchestrator._classify_consensus([_pos("a", "support"), _pos("b", "oppose")])
        == "split"
    )


async def test_extract_actions_caps_at_three():
    positions = [_pos(f"a{i}", "support") for i in range(10)]
    actions = Orchestrator._extract_actions(positions)
    assert len(actions) <= 3


async def test_extract_actions_ignores_opposers():
    positions = [_pos("a", "oppose")]
    actions = Orchestrator._extract_actions(positions)
    assert actions == []


async def test_dissent_prompt_includes_positions():
    positions = [
        _pos("cfo", "support"),
        _pos("cto", "oppose"),
    ]
    out = Orchestrator._dissent_prompt("Should we ship?", positions)
    assert "Should we ship" in out
    assert "CFO" in out
    assert "CTO" in out


async def test_default_specialists_constant():
    assert "cfo" in DEFAULT_SPECIALISTS
    assert "counsel" not in DEFAULT_SPECIALISTS
    assert "counsel" in DEFAULT_S4_SPECIALISTS


async def test_run_debate_dissent_driven_when_disagreement(
    db_session, tenant, founder_user
):
    """With a custom gateway that returns deterministic 'oppose' for CFO and
    'support' for everyone else, we should trigger at least one dissent round."""
    from app.audit.service import AuditService as _AS
    from app.inference.gateway import AgentInvocationContext, InferenceGateway
    from app.inference.providers import CompletionResult, InferenceClient
    from app.inference.registry import ModelRegistry

    class _Echo(InferenceClient):
        name = "echo"

        async def complete(self, **kw: Any) -> CompletionResult:
            system = kw["system"].lower()
            if "cfo" in system:
                text = "I oppose this — too expensive."
            elif "cto" in system:
                text = "I support — engineering scope is reasonable."
            else:
                text = "I support — proceed."
            return CompletionResult(text=text, tokens_in=1, tokens_out=1)

        async def stream(self, **kw: Any):  # pragma: no cover - unused
            yield ""

    s = SessionRow(
        tenant_id=tenant.id,
        created_by_user_id=founder_user.id,
        kind="boardroom",
        turn_taking_mode="dissent_driven",
    )
    db_session.add(s)
    await db_session.commit()
    await db_session.refresh(s)

    # Build a tight registry where every agent uses our echo client
    from pathlib import Path
    import tempfile, textwrap

    p = Path(tempfile.mkstemp(suffix=".yaml")[1])
    p.write_text(textwrap.dedent("""
        agents:
          facilitator: {primary: {provider: e, model: m}, prompt_version: v1, temperature: 0.5, max_tokens: 256}
          cfo:         {primary: {provider: e, model: m}, prompt_version: v1, temperature: 0.5, max_tokens: 256}
          cto:         {primary: {provider: e, model: m}, prompt_version: v1, temperature: 0.5, max_tokens: 256}
          cmo:         {primary: {provider: e, model: m}, prompt_version: v1, temperature: 0.5, max_tokens: 256}
          coo:         {primary: {provider: e, model: m}, prompt_version: v1, temperature: 0.5, max_tokens: 256}
          counsel:     {primary: {provider: e, model: m}, prompt_version: v1, temperature: 0.5, max_tokens: 256}
    """))
    gw = InferenceGateway(registry=ModelRegistry(p), clients={"e": _Echo()})
    orch = Orchestrator(
        db=db_session,
        gateway=gw,
        audit=_AS(db_session),
        memory=MemoryService(db_session),
        agent_roster=("cfo", "cto", "cmo", "coo", "counsel"),
        dissent_cap=2,
    )
    res = await orch.run_debate(
        tenant_id=tenant.id,
        session=s,
        user_message="Should we hire 4 engineers?",
    )
    assert res.dissent_rounds, "expected at least one dissent round given mixed stances"
    # Capped at 2
    assert len(res.dissent_rounds) <= 2
    _ = AgentInvocationContext  # silence import-unused warning


async def test_memory_retrieval_failure_swallowed(
    db_session, tenant, session_row
):
    """If memory raises, the orchestrator still proceeds with empty snippets."""
    from app.inference.gateway import get_gateway as _g

    class BrokenMemory:
        async def retrieve(self, **kw):
            raise RuntimeError("simulated outage")

    orch = Orchestrator(
        db=db_session,
        gateway=_g(),
        audit=AuditService(db_session),
        memory=BrokenMemory(),  # type: ignore[arg-type]
    )
    snippets = await orch._retrieve_memory(tenant.id, "cfo", "q")
    assert snippets == []
