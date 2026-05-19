"""Unit tests for SessionService close lifecycle."""
from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest_asyncio

from app.db.models import AgentMemory, Session as SessionRow, Turn
from app.services.session_service import SessionService


@pytest_asyncio.fixture
async def session_with_turns(db_session, tenant, founder_user):
    s = SessionRow(
        tenant_id=tenant.id,
        created_by_user_id=founder_user.id,
        kind="boardroom",
        title="close-me",
        consensus_text="Ship it. Quietly.",
        consensus_kind="majority",
        action_list=[{"owner": "CFO", "description": "validate burn", "due_days": 7}],
    )
    db_session.add(s)
    await db_session.flush()
    # Add a user turn + agent turns + a dissent turn
    db_session.add(
        Turn(
            tenant_id=tenant.id,
            session_id=s.id,
            seq_no=1,
            role="user",
            language="en",
            payload_text="Should we ship?",
        )
    )
    db_session.add(
        Turn(
            tenant_id=tenant.id,
            session_id=s.id,
            seq_no=2,
            role="agent",
            agent_id="cfo",
            language="en",
            payload_text="I support — burn is manageable.",
            model_used="mock/mock",
            confidence=Decimal("0.8"),
        )
    )
    db_session.add(
        Turn(
            tenant_id=tenant.id,
            session_id=s.id,
            seq_no=3,
            role="agent",
            agent_id="cto",
            language="en",
            payload_text="I support — tech debt is contained.",
            model_used="mock/mock",
        )
    )
    db_session.add(
        Turn(
            tenant_id=tenant.id,
            session_id=s.id,
            seq_no=4,
            role="agent",
            agent_id="cmo",
            language="en",
            payload_text="I oppose — narrative is wrong.",
            model_used="mock/mock",
            dissent_round=1,
        )
    )
    await db_session.commit()
    await db_session.refresh(s)
    return s


async def test_close_persists_status_and_ended_at(
    db_session, tenant, founder_user, session_with_turns, tmp_path
):
    svc = SessionService(db_session)
    closed = await svc.close(
        session=session_with_turns,
        tenant_id=tenant.id,
        actor_user_id=founder_user.id,
        boardpack_storage_root=tmp_path,
    )
    assert closed.status == "closed"
    assert closed.ended_at is not None
    assert closed.boardpack_uri is not None
    assert closed.boardpack_uri.startswith("file://")
    # File exists
    path = closed.boardpack_uri.replace("file://", "")
    assert Path(path).exists()
    assert Path(path).stat().st_size > 1000  # real PDF, not empty


async def test_close_writes_memory_for_every_default_agent(
    db_session, tenant, founder_user, session_with_turns, tmp_path
):
    svc = SessionService(db_session)
    await svc.close(
        session=session_with_turns,
        tenant_id=tenant.id,
        actor_user_id=founder_user.id,
        boardpack_storage_root=tmp_path,
    )
    # Verify per-agent memories were written
    for agent in ("cfo", "cto", "cmo", "coo", "counsel"):
        from sqlalchemy import select

        rows = (
            await db_session.execute(
                select(AgentMemory).where(
                    AgentMemory.tenant_id == tenant.id, AgentMemory.agent_id == agent
                )
            )
        ).scalars().all()
        assert rows, f"no memories for {agent}"
        kinds = {r.kind for r in rows}
        assert "session_summary" in kinds


async def test_close_idempotency_audit_event(
    db_session, tenant, founder_user, session_with_turns, tmp_path
):
    from sqlalchemy import select

    from app.db.models import AuditEvent

    svc = SessionService(db_session)
    await svc.close(
        session=session_with_turns,
        tenant_id=tenant.id,
        actor_user_id=founder_user.id,
        boardpack_storage_root=tmp_path,
    )
    events = (
        await db_session.execute(
            select(AuditEvent).where(
                AuditEvent.tenant_id == tenant.id, AuditEvent.kind == "session_closed"
            )
        )
    ).scalars().all()
    assert len(events) == 1
    assert events[0].payload_json["consensus_kind"] == "majority"


async def test_extract_salient_facts_dedupes_by_agent():
    turns = [
        Turn(
            id="t1",
            tenant_id="x",
            session_id="s",
            seq_no=1,
            role="agent",
            agent_id="cfo",
            language="en",
            payload_text="cfo a",
        ),
        Turn(
            id="t2",
            tenant_id="x",
            session_id="s",
            seq_no=2,
            role="agent",
            agent_id="cfo",
            language="en",
            payload_text="cfo b",
        ),
        Turn(
            id="t3",
            tenant_id="x",
            session_id="s",
            seq_no=3,
            role="agent",
            agent_id="cto",
            language="en",
            payload_text="cto a",
        ),
    ]
    facts = SessionService._extract_salient_facts(turns)  # type: ignore[arg-type]
    # only one fact per agent
    agents = [f.split(":")[0] for f in facts]
    assert agents == ["CFO", "CTO"]


async def test_extract_dissent_points():
    turns = [
        Turn(
            id="t1",
            tenant_id="x",
            session_id="s",
            seq_no=1,
            role="agent",
            agent_id="cfo",
            language="en",
            payload_text="dissent text from cfo",
            dissent_round=1,
        ),
        Turn(
            id="t2",
            tenant_id="x",
            session_id="s",
            seq_no=2,
            role="agent",
            agent_id="cto",
            language="en",
            payload_text="normal turn",
            dissent_round=None,
        ),
    ]
    out = SessionService._extract_dissent_points(turns)  # type: ignore[arg-type]
    assert len(out) == 1
    assert "CFO" in out[0]
