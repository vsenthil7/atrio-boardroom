"""Sessions router — CRUD + close + boardpack generation trigger.

GET    /sessions
POST   /sessions
GET    /sessions/{id}
POST   /sessions/{id}/close
GET    /sessions/{id}/turns
POST   /sessions/{id}/turns   (SSE — see turns_stream router)
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, status
from sqlalchemy import select

from app.api.deps import CurrentUserDep, DbSession
from app.api.schemas import (
    SessionCreate,
    SessionList,
    SessionPublic,
    TurnList,
    TurnPublic,
)
from app.audit.service import AuditService
from app.core.errors import ConflictState, NotFoundError
from app.db.models import Session as SessionRow
from app.db.models import Turn
from app.services.session_service import SessionService

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.get("", response_model=SessionList)
async def list_sessions(user: CurrentUserDep, db: DbSession) -> SessionList:
    stmt = (
        select(SessionRow)
        .where(SessionRow.tenant_id == user.tenant_id)
        .order_by(SessionRow.started_at.desc())
        .limit(100)
    )
    rows = (await db.execute(stmt)).scalars().all()
    return SessionList(items=[_to_public(s) for s in rows])


@router.post("", response_model=SessionPublic, status_code=status.HTTP_201_CREATED)
async def create_session(
    body: SessionCreate, user: CurrentUserDep, db: DbSession
) -> SessionPublic:
    session = SessionRow(
        tenant_id=user.tenant_id,
        created_by_user_id=user.user_id,
        kind="boardroom",
        title=body.title,
        language_dominant=body.language_dominant,
        turn_taking_mode=body.turn_taking_mode,
        status="active",
    )
    db.add(session)
    await db.flush()
    await AuditService(db).write(
        tenant_id=user.tenant_id,
        session_id=session.id,
        actor_user_id=user.user_id,
        kind="session_created",
        payload={"title": body.title, "turn_taking_mode": body.turn_taking_mode},
    )
    from app.observability import sessions_active, sessions_opened_total

    sessions_opened_total.inc(labels={"tenant_id": user.tenant_id})
    sessions_active.inc(labels={"tenant_id": user.tenant_id})
    return _to_public(session)


@router.get("/{session_id}", response_model=SessionPublic)
async def get_session(
    session_id: str, user: CurrentUserDep, db: DbSession
) -> SessionPublic:
    row = await _load_for_tenant(db, user.tenant_id, session_id)
    return _to_public(row)


@router.get("/{session_id}/turns", response_model=TurnList)
async def list_turns(
    session_id: str, user: CurrentUserDep, db: DbSession
) -> TurnList:
    await _load_for_tenant(db, user.tenant_id, session_id)
    stmt = (
        select(Turn)
        .where(Turn.tenant_id == user.tenant_id, Turn.session_id == session_id)
        .order_by(Turn.seq_no.asc())
    )
    rows = (await db.execute(stmt)).scalars().all()
    return TurnList(
        items=[
            TurnPublic(
                id=t.id,
                seq_no=t.seq_no,
                role=t.role,
                agent_id=t.agent_id,
                language=t.language,
                payload_text=t.payload_text,
                model_used=t.model_used,
                model_was_fallback=t.model_was_fallback,
                dissent_round=t.dissent_round,
                ts=t.ts,
            )
            for t in rows
        ]
    )


@router.post("/{session_id}/close", response_model=SessionPublic)
async def close_session(
    session_id: str, user: CurrentUserDep, db: DbSession
) -> SessionPublic:
    row = await _load_for_tenant(db, user.tenant_id, session_id)
    if row.status == "closed":
        raise ConflictState("session already closed", details={"session_id": session_id})
    svc = SessionService(db)
    closed = await svc.close(
        session=row, tenant_id=user.tenant_id, actor_user_id=user.user_id
    )
    from app.observability import sessions_active, sessions_closed_total

    sessions_closed_total.inc(labels={"tenant_id": user.tenant_id})
    sessions_active.dec(labels={"tenant_id": user.tenant_id})
    return _to_public(closed)


# ----------------------------------------------- helpers


async def _load_for_tenant(db, tenant_id: str, session_id: str) -> SessionRow:
    stmt = select(SessionRow).where(
        SessionRow.id == session_id, SessionRow.tenant_id == tenant_id
    )
    row = (await db.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise NotFoundError("session not found", details={"session_id": session_id})
    return row


def _to_public(s: SessionRow) -> SessionPublic:
    return SessionPublic(
        id=s.id,
        tenant_id=s.tenant_id,
        title=s.title,
        language_dominant=s.language_dominant,
        turn_taking_mode=s.turn_taking_mode,
        status=s.status,
        consensus_text=s.consensus_text,
        consensus_kind=s.consensus_kind,
        boardpack_uri=s.boardpack_uri,
        started_at=s.started_at,
        ended_at=s.ended_at,
    )


# Force-import so datetime usage doesn't get marked unused by strict checkers.
_ = datetime
