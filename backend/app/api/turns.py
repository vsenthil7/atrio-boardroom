"""Turn submission — SSE streaming.

POST /sessions/{session_id}/turns → text/event-stream

Emits events:
  turn_started      — session_id, seq_no, user_text
  token             — { agent_id, text }  (streaming)
  agent_done        — { agent_id, model_used, tokens_in/out, latency_ms, stance }
  dissent_round     — { round_no }
  consensus         — { text, kind, action_list }
  stream_complete   — { positions_summary }
"""
from __future__ import annotations

import json
from typing import AsyncIterator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from app.api.deps import CurrentUserDep, DbSession
from app.api.schemas import TurnCreate
from app.audit.service import AuditService
from app.core.errors import ConflictState, NotFoundError
from app.db.base import get_sessionmaker
from app.db.models import Document, Session as SessionRow
from app.inference.gateway import get_gateway
from app.memory.service import MemoryService
from app.services.orchestrator import (
    DEFAULT_S4_SPECIALISTS,
    Orchestrator,
)

router = APIRouter(prefix="/sessions", tags=["turns"])


def _sse(event: str, payload: dict) -> bytes:
    return f"event: {event}\ndata: {json.dumps(payload)}\n\n".encode()


@router.post(
    "/{session_id}/turns",
    summary="Submit a user turn (SSE stream)",
)
async def stream_turn(
    session_id: str,
    body: TurnCreate,
    user: CurrentUserDep,
    db: DbSession,
) -> StreamingResponse:
    # Load session (commit at end of dependency)
    row = (
        await db.execute(
            select(SessionRow).where(
                SessionRow.id == session_id, SessionRow.tenant_id == user.tenant_id
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise NotFoundError("session not found", details={"session_id": session_id})
    if row.status != "active":
        raise ConflictState(
            "cannot post a turn to a closed session", details={"status": row.status}
        )

    # Pull document summaries for context (already extracted)
    docs = (
        await db.execute(
            select(Document)
            .where(Document.tenant_id == user.tenant_id, Document.session_id == session_id)
            .order_by(Document.created_at.asc())
        )
    ).scalars().all()
    doc_summaries = [d.summary for d in docs if d.summary]

    snapshot = {
        "session_id": session_id,
        "tenant_id": user.tenant_id,
        "actor_user_id": user.user_id,
        "text": body.text,
        "language": body.language,
        "mode": body.mode,
        "language_dominant": row.language_dominant,
        "turn_taking_mode": row.turn_taking_mode,
        "doc_summaries": doc_summaries,
    }

    async def streamer() -> AsyncIterator[bytes]:
        sm = get_sessionmaker()
        async with sm() as bg_db:
            try:
                # Persist user turn first
                gw = get_gateway()
                audit = AuditService(bg_db)
                memory = MemoryService(bg_db)
                # Re-load the session inside the bg session
                bg_row = (
                    await bg_db.execute(
                        select(SessionRow).where(SessionRow.id == snapshot["session_id"])
                    )
                ).scalar_one()
                orch = Orchestrator(
                    db=bg_db,
                    gateway=gw,
                    audit=audit,
                    memory=memory,
                    agent_roster=DEFAULT_S4_SPECIALISTS,
                )
                user_turn = await orch.persist_user_turn(
                    tenant_id=snapshot["tenant_id"],
                    session_id=snapshot["session_id"],
                    text=snapshot["text"],
                    language=snapshot["language"],
                )
                await bg_db.flush()
                yield _sse(
                    "turn_started",
                    {
                        "session_id": snapshot["session_id"],
                        "seq_no": user_turn.seq_no,
                        "user_text": snapshot["text"],
                    },
                )
                if snapshot["mode"] == "single":
                    result = await orch.run_single_agent(
                        tenant_id=snapshot["tenant_id"],
                        session=bg_row,
                        user_message=snapshot["text"],
                        document_summaries=snapshot["doc_summaries"],
                    )
                else:
                    result = await orch.run_debate(
                        tenant_id=snapshot["tenant_id"],
                        session=bg_row,
                        user_message=snapshot["text"],
                        document_summaries=snapshot["doc_summaries"],
                    )
                # Emit each position as a token block (since mock returns whole text)
                for pos in result.positions:
                    yield _sse(
                        "agent_done",
                        {
                            "agent_id": pos.agent_id,
                            "text": pos.text,
                            "model_used": pos.model_used,
                            "was_fallback": pos.was_fallback,
                            "tokens_in": pos.tokens_in,
                            "tokens_out": pos.tokens_out,
                            "latency_ms": pos.latency_ms,
                            "stance": pos.stance,
                            "dissent_round": None,
                        },
                    )
                for idx, dissent in enumerate(result.dissent_rounds, start=1):
                    yield _sse("dissent_round", {"round_no": idx})
                    for pos in dissent:
                        yield _sse(
                            "agent_done",
                            {
                                "agent_id": pos.agent_id,
                                "text": pos.text,
                                "model_used": pos.model_used,
                                "was_fallback": pos.was_fallback,
                                "tokens_in": pos.tokens_in,
                                "tokens_out": pos.tokens_out,
                                "latency_ms": pos.latency_ms,
                                "stance": pos.stance,
                                "dissent_round": idx,
                            },
                        )
                yield _sse(
                    "consensus",
                    {
                        "text": result.consensus_text,
                        "kind": result.consensus_kind,
                        "action_list": result.action_list,
                    },
                )
                yield _sse(
                    "stream_complete",
                    {
                        "positions": [
                            {"agent_id": p.agent_id, "stance": p.stance}
                            for p in result.positions
                        ],
                        "dissent_rounds": len(result.dissent_rounds),
                    },
                )
                await bg_db.commit()
            except Exception as e:  # pragma: no cover - defensive
                await bg_db.rollback()
                yield _sse("error", {"message": str(e)})

    return StreamingResponse(streamer(), media_type="text/event-stream")
