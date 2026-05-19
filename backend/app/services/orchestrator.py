"""Orchestrator service — turn-taking, parallel agent invocation, consensus.

The orchestrator is the heaviest component by complexity. It runs four sub-
modules:

  Planner            — Facilitator classifies the question + picks turn-mode.
  TurnTaking         — Round-robin / dissent-driven / expert-first state machine.
  ParallelInvoker    — Fan out agent invocations through the inference gateway.
  ConsensusSynth     — Facilitator collects positions and writes consensus + actions.

The orchestrator emits its own audit events (`debate_started`, `dissent_round`,
`consensus_synthesised`) and delegates per-call audit to the gateway sink.
"""
from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import AuditService
from app.core.logging import get_logger
from app.db.models import Session as SessionRow
from app.db.models import Turn
from app.inference.gateway import AgentInvocationContext, InferenceGateway, InvocationResult
from app.memory.service import MemoryService

log = get_logger(__name__)


# Built-in agent roster. Tests can substitute via `Orchestrator(agent_roster=...)`.
DEFAULT_SPECIALISTS = ("cfo", "cto", "cmo", "coo")
DEFAULT_S4_SPECIALISTS = ("cfo", "cto", "cmo", "coo", "counsel")


@dataclass
class AgentPosition:
    agent_id: str
    text: str
    stance: str  # "support" | "hesitate" | "oppose" | "unclear"
    model_used: str
    was_fallback: bool
    latency_ms: int
    tokens_in: int
    tokens_out: int
    prompt_version: str


@dataclass
class DebateResult:
    turn_taking_mode: str
    positions: list[AgentPosition]
    dissent_rounds: list[list[AgentPosition]] = field(default_factory=list)
    consensus_text: str = ""
    consensus_kind: str = "majority"
    action_list: list[dict[str, Any]] = field(default_factory=list)
    facilitator_plan: str = ""

    def all_turns_flat(self) -> list[AgentPosition]:
        out = list(self.positions)
        for r in self.dissent_rounds:
            out.extend(r)
        return out


# ---------------------------------------------------------------------------
# Stance detection (regex-based; works for our prompt template's "I support /
# I'd hesitate / I oppose — because ..." footer)
# ---------------------------------------------------------------------------

_STANCE_RE = re.compile(
    r"\bI(?:'d|\s+would)?\s+(support|hesitate|oppose)\b",
    re.IGNORECASE,
)


def detect_stance(text: str) -> str:
    m = _STANCE_RE.search(text)
    if not m:
        return "unclear"
    raw = m.group(1).lower().strip()
    if "hesitat" in raw:
        return "hesitate"
    if "oppos" in raw:
        return "oppose"
    if "support" in raw:
        return "support"
    return "unclear"


def is_material_disagreement(positions: list[AgentPosition]) -> bool:
    """Return True if the positions span both 'support' and 'oppose' camps."""
    stances = {p.stance for p in positions}
    return ("support" in stances and "oppose" in stances) or (
        "support" in stances and "hesitate" in stances and len(stances) >= 2
    )


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


class Orchestrator:
    """Run a multi-agent debate over a user question."""

    def __init__(
        self,
        db: AsyncSession,
        gateway: InferenceGateway,
        audit: AuditService,
        memory: MemoryService,
        *,
        agent_roster: tuple[str, ...] = DEFAULT_S4_SPECIALISTS,
        dissent_cap: int = 2,
    ) -> None:
        self._db = db
        self._gw = gateway
        self._audit = audit
        self._mem = memory
        self._roster = agent_roster
        self._dissent_cap = dissent_cap

    # ----------------------------------------------------- public

    async def run_single_agent(
        self,
        *,
        tenant_id: str,
        session: SessionRow,
        user_message: str,
        agent_id: str = "facilitator",
        document_summaries: list[str] | None = None,
    ) -> DebateResult:
        """Sprint-1 path: one agent, one answer. No debate."""
        await self._audit.write(
            tenant_id=tenant_id,
            session_id=session.id,
            kind="single_agent_debate_started",
            payload={"agent_id": agent_id, "user_message": user_message[:200]},
        )

        memory_snippets = await self._retrieve_memory(tenant_id, agent_id, user_message)
        ctx = AgentInvocationContext(
            tenant_id=tenant_id,
            session_id=session.id,
            agent_id=agent_id,
            user_message=user_message,
            language=session.language_dominant,
            memory_snippets=memory_snippets,
            document_summaries=list(document_summaries or []),
        )
        result = await self._gw.invoke(ctx)
        pos = self._to_position(agent_id, result)
        return DebateResult(
            turn_taking_mode=session.turn_taking_mode,
            positions=[pos],
            consensus_text=pos.text,
            consensus_kind="unanimous",
            action_list=[],
        )

    async def run_debate(
        self,
        *,
        tenant_id: str,
        session: SessionRow,
        user_message: str,
        document_summaries: list[str] | None = None,
    ) -> DebateResult:
        """Sprint 2+: full debate with Facilitator plan, specialists, optional dissent, synthesis."""
        documents = list(document_summaries or [])
        # 1) Facilitator plans
        plan = await self._gw.invoke(
            AgentInvocationContext(
                tenant_id=tenant_id,
                session_id=session.id,
                agent_id="facilitator",
                user_message=user_message,
                language=session.language_dominant,
                memory_snippets=await self._retrieve_memory(
                    tenant_id, "facilitator", user_message
                ),
                document_summaries=documents,
            )
        )
        await self._audit.write(
            tenant_id=tenant_id,
            session_id=session.id,
            kind="debate_planned",
            payload={
                "facilitator_text": plan.text[:400],
                "turn_taking_mode": session.turn_taking_mode,
                "roster": list(self._roster),
            },
        )

        # 2) Parallel specialists
        specialists_to_run = [a for a in self._roster if a != "facilitator"]
        round_results = await self._run_round(
            tenant_id,
            session,
            user_message,
            specialists_to_run,
            documents,
            dissent_round=None,
        )

        # 3) Dissent rounds (capped)
        dissent_rounds: list[list[AgentPosition]] = []
        round_idx = 0
        if session.turn_taking_mode == "dissent_driven":
            while (
                round_idx < self._dissent_cap
                and is_material_disagreement(round_results)
            ):
                round_idx += 1
                await self._audit.write(
                    tenant_id=tenant_id,
                    session_id=session.id,
                    kind="dissent_round_started",
                    payload={"round_no": round_idx, "agents": [p.agent_id for p in round_results]},
                )
                next_msg = self._dissent_prompt(user_message, round_results)
                round_results_round = await self._run_round(
                    tenant_id,
                    session,
                    next_msg,
                    specialists_to_run,
                    documents,
                    dissent_round=round_idx,
                )
                dissent_rounds.append(round_results_round)
                round_results = round_results_round

        # 4) Synthesis
        synth_text, kind, actions = await self._synthesise(
            tenant_id, session, user_message, round_results
        )

        await self._audit.write(
            tenant_id=tenant_id,
            session_id=session.id,
            kind="consensus_synthesised",
            payload={
                "consensus_kind": kind,
                "consensus_text_excerpt": synth_text[:240],
                "actions": actions,
            },
        )

        return DebateResult(
            turn_taking_mode=session.turn_taking_mode,
            positions=round_results,
            dissent_rounds=dissent_rounds,
            consensus_text=synth_text,
            consensus_kind=kind,
            action_list=actions,
            facilitator_plan=plan.text,
        )

    # ----------------------------------------------------- internals

    async def _retrieve_memory(
        self, tenant_id: str, agent_id: str, query: str
    ) -> list[str]:
        try:
            hits = await self._mem.retrieve(
                tenant_id=tenant_id, agent_id=agent_id, query=query, limit=5
            )
        except Exception as e:  # pragma: no cover - defensive
            log.warning("memory_retrieval_failed", error=str(e), agent=agent_id)
            return []
        return [m.content for (m, _) in hits]

    async def _run_round(
        self,
        tenant_id: str,
        session: SessionRow,
        user_message: str,
        agents: list[str],
        documents: list[str],
        *,
        dissent_round: int | None,
    ) -> list[AgentPosition]:
        # Pre-build contexts with per-agent memory retrieval
        contexts: list[AgentInvocationContext] = []
        for agent in agents:
            mem = await self._retrieve_memory(tenant_id, agent, user_message)
            contexts.append(
                AgentInvocationContext(
                    tenant_id=tenant_id,
                    session_id=session.id,
                    agent_id=agent,
                    user_message=user_message,
                    language=session.language_dominant,
                    memory_snippets=mem,
                    document_summaries=documents,
                )
            )
        # Fire in parallel
        results = await asyncio.gather(
            *[self._gw.invoke(c) for c in contexts], return_exceptions=False
        )
        positions = [
            self._to_position(c.agent_id, r) for c, r in zip(contexts, results, strict=True)
        ]
        # Persist turns to DB
        for p in positions:
            await self._persist_turn(
                tenant_id=tenant_id,
                session_id=session.id,
                agent_id=p.agent_id,
                text=p.text,
                model_used=p.model_used,
                was_fallback=p.was_fallback,
                prompt_version=p.prompt_version,
                tokens_in=p.tokens_in,
                tokens_out=p.tokens_out,
                latency_ms=p.latency_ms,
                dissent_round=dissent_round,
                language=session.language_dominant,
            )
        return positions

    @staticmethod
    def _to_position(agent_id: str, result: InvocationResult) -> AgentPosition:
        return AgentPosition(
            agent_id=agent_id,
            text=result.text,
            stance=detect_stance(result.text),
            model_used=f"{result.provider_used}/{result.model_used}",
            was_fallback=result.was_fallback,
            latency_ms=result.latency_ms,
            tokens_in=result.tokens_in,
            tokens_out=result.tokens_out,
            prompt_version=result.prompt_version,
        )

    @staticmethod
    def _dissent_prompt(original: str, positions: list[AgentPosition]) -> str:
        bullets = "\n".join(
            f"- {p.agent_id.upper()} ({p.stance}): {p.text[:160]}" for p in positions
        )
        return (
            f"Original question: {original}\n\n"
            f"You disagree materially with at least one colleague. "
            f"Here is the table of positions:\n{bullets}\n\n"
            f"Restate your position, addressing the strongest counter-argument."
        )

    async def _synthesise(
        self,
        tenant_id: str,
        session: SessionRow,
        user_message: str,
        positions: list[AgentPosition],
    ) -> tuple[str, str, list[dict[str, Any]]]:
        bullets = "\n".join(f"- {p.agent_id.upper()} ({p.stance}): {p.text}" for p in positions)
        synth_msg = (
            f"User question: {user_message}\n\n"
            f"Board positions:\n{bullets}\n\n"
            f"Produce: 1) one-paragraph consensus, 2) consensus kind "
            f"(unanimous / majority / split), 3) up to 3 actions with owner + due."
        )
        result = await self._gw.invoke(
            AgentInvocationContext(
                tenant_id=tenant_id,
                session_id=session.id,
                agent_id="facilitator",
                user_message=synth_msg,
                language=session.language_dominant,
                memory_snippets=[],
                document_summaries=[],
            )
        )
        kind = self._classify_consensus(positions)
        actions = self._extract_actions(positions)
        return result.text, kind, actions

    @staticmethod
    def _classify_consensus(positions: list[AgentPosition]) -> str:
        if not positions:
            return "split"
        stances = [p.stance for p in positions]
        s_count = stances.count("support")
        o_count = stances.count("oppose")
        h_count = stances.count("hesitate")
        if s_count == len(positions):
            return "unanimous"
        if o_count == len(positions):
            return "unanimous"
        if s_count > o_count + h_count:
            return "majority"
        if o_count > s_count + h_count:
            return "majority"
        return "split"

    @staticmethod
    def _extract_actions(positions: list[AgentPosition]) -> list[dict[str, Any]]:
        """In the mock-deterministic path, build placeholder actions per agent.

        Production prompts include `Output: actions: [...]` and we parse JSON.
        For Sprint 4 we keep this simple and synthesise from agents' roles.
        """
        owners = {
            "cfo": "CFO",
            "cto": "CTO",
            "cmo": "CMO",
            "coo": "COO",
            "counsel": "Counsel",
        }
        actions = []
        for p in positions:
            if p.stance in ("support", "unclear"):
                owner = owners.get(p.agent_id, p.agent_id.upper())
                actions.append(
                    {
                        "description": f"{owner} to validate position with current data",
                        "owner": owner,
                        "due_days": 7,
                    }
                )
        return actions[:3]

    # ------------------------------------------------ turn persistence

    async def _persist_turn(
        self,
        *,
        tenant_id: str,
        session_id: str,
        agent_id: str,
        text: str,
        model_used: str,
        was_fallback: bool,
        prompt_version: str,
        tokens_in: int,
        tokens_out: int,
        latency_ms: int,
        dissent_round: int | None,
        language: str,
    ) -> Turn:
        from sqlalchemy import select, func

        # Compute next seq_no
        result = await self._db.execute(
            select(func.coalesce(func.max(Turn.seq_no), 0)).where(Turn.session_id == session_id)
        )
        next_seq = int(result.scalar() or 0) + 1
        turn = Turn(
            tenant_id=tenant_id,
            session_id=session_id,
            seq_no=next_seq,
            role="agent",
            agent_id=agent_id,
            language=language,
            payload_text=text,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            latency_ms=latency_ms,
            model_used=model_used,
            model_was_fallback=was_fallback,
            prompt_version=prompt_version,
            dissent_round=dissent_round,
        )
        self._db.add(turn)
        await self._db.flush()
        return turn

    async def persist_user_turn(
        self,
        *,
        tenant_id: str,
        session_id: str,
        text: str,
        language: str,
        audio_uri: str | None = None,
        confidence: float | None = None,
    ) -> Turn:
        from decimal import Decimal as _D
        from sqlalchemy import select, func

        result = await self._db.execute(
            select(func.coalesce(func.max(Turn.seq_no), 0)).where(Turn.session_id == session_id)
        )
        next_seq = int(result.scalar() or 0) + 1
        turn = Turn(
            tenant_id=tenant_id,
            session_id=session_id,
            seq_no=next_seq,
            role="user",
            agent_id=None,
            language=language,
            payload_text=text,
            payload_audio_uri=audio_uri,
            confidence=_D(str(confidence)) if confidence is not None else None,
        )
        self._db.add(turn)
        await self._db.flush()
        return turn
