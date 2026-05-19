"""Session service — close lifecycle.

When a session closes:
  1) Persist the consensus to the session row (already happened during debate).
  2) Write per-agent memory entries (session_summary + salient + dissent).
  3) Generate the boardpack PDF and store its URI (local for hackathon).
  4) Emit `session_closed` audit event.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import AuditService
from app.core.logging import get_logger
from app.db.models import Session as SessionRow, Turn
from app.memory.service import MemoryService
from app.services.export import BoardpackExporter

log = get_logger(__name__)

DEFAULT_AGENT_ROSTER = ("cfo", "cto", "cmo", "coo", "counsel")


class SessionService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def close(
        self,
        *,
        session: SessionRow,
        tenant_id: str,
        actor_user_id: str,
        boardpack_storage_root: Path | None = None,
    ) -> SessionRow:
        session.status = "closed"
        session.ended_at = datetime.utcnow()
        await self._db.flush()

        # Pull all turns + dissent rounds for memory
        turns = (
            await self._db.execute(
                select(Turn)
                .where(Turn.tenant_id == tenant_id, Turn.session_id == session.id)
                .order_by(Turn.seq_no.asc())
            )
        ).scalars().all()
        consensus = session.consensus_text or "no consensus recorded"
        salient_facts = self._extract_salient_facts(turns)
        dissent_points = self._extract_dissent_points(turns)

        memory = MemoryService(self._db)
        for agent_id in DEFAULT_AGENT_ROSTER:
            await memory.write_session_summary(
                tenant_id=tenant_id,
                agent_id=agent_id,
                source_session_id=session.id,
                summary=consensus,
                salient_facts=salient_facts,
                dissent_points=dissent_points,
            )

        # Boardpack PDF
        exporter = BoardpackExporter(self._db)
        pdf_bytes = await exporter.build_for_session(tenant_id=tenant_id, session=session)
        root = boardpack_storage_root or Path("/tmp/atrio-boardpacks")  # noqa: S108
        root.mkdir(parents=True, exist_ok=True)
        path = root / f"{session.id}.pdf"
        path.write_bytes(pdf_bytes)
        session.boardpack_uri = f"file://{path}"
        await self._db.flush()

        await AuditService(self._db).write(
            tenant_id=tenant_id,
            session_id=session.id,
            actor_user_id=actor_user_id,
            kind="session_closed",
            payload={
                "consensus_kind": session.consensus_kind,
                "boardpack_uri": session.boardpack_uri,
                "ended_at": session.ended_at.isoformat() if session.ended_at else None,
            },
        )
        return session

    @staticmethod
    def _extract_salient_facts(turns: list[Turn]) -> list[str]:
        # Heuristic — pull the first sentence of each unique agent turn.
        seen: set[str] = set()
        facts: list[str] = []
        for t in turns:
            if t.role != "agent" or t.agent_id is None:
                continue
            if t.agent_id in seen:
                continue
            seen.add(t.agent_id)
            sent = t.payload_text.split(".")[0].strip()
            if sent:
                facts.append(f"{t.agent_id.upper()}: {sent[:240]}")
            if len(facts) >= 5:
                break
        return facts

    @staticmethod
    def _extract_dissent_points(turns: list[Turn]) -> list[str]:
        return [
            f"{t.agent_id.upper()} (round {t.dissent_round}): "
            f"{t.payload_text.split('.')[0].strip()[:240]}"
            for t in turns
            if t.dissent_round and t.payload_text and t.agent_id
        ][:3]
