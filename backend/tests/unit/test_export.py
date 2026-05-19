"""Unit tests for BoardpackExporter."""
from __future__ import annotations

from decimal import Decimal

import pytest_asyncio

from app.db.models import Document, Session as SessionRow, Turn
from app.services.export import BoardpackExporter


@pytest_asyncio.fixture
async def populated_session(db_session, tenant, founder_user):
    s = SessionRow(
        tenant_id=tenant.id,
        created_by_user_id=founder_user.id,
        title="Boardpack test",
        consensus_text="Ship it.",
        consensus_kind="majority",
        action_list=[
            {"owner": "CFO", "description": "validate burn", "due_days": 7},
        ],
    )
    db_session.add(s)
    await db_session.flush()
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
            payload_text="I support — burn ok.",
            model_used="mock/mock",
            model_was_fallback=False,
            latency_ms=12,
            dissent_round=None,
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
            payload_text="<I oppose — too risky.>",  # has <> to test html-escape
            model_used="mock/mock",
            dissent_round=1,
        )
    )
    db_session.add(
        Document(
            tenant_id=tenant.id,
            session_id=s.id,
            uploaded_by_user_id=founder_user.id,
            kind="pdf",
            filename="plan.pdf",
            byte_size=1234,
            sha256="abc" * 21 + "d",  # 64 chars
            storage_uri="local://x",
            extraction_status="complete",
            summary="A plan",
        )
    )
    await db_session.commit()
    await db_session.refresh(s)
    return s


async def test_build_pdf_for_session(db_session, tenant, populated_session):
    pdf = await BoardpackExporter(db_session).build_for_session(
        tenant_id=tenant.id, session=populated_session
    )
    assert pdf.startswith(b"%PDF-")
    assert len(pdf) > 2000


async def test_build_pdf_empty_session(db_session, tenant, founder_user):
    s = SessionRow(
        tenant_id=tenant.id, created_by_user_id=founder_user.id, kind="boardroom"
    )
    db_session.add(s)
    await db_session.commit()
    await db_session.refresh(s)
    pdf = await BoardpackExporter(db_session).build_for_session(
        tenant_id=tenant.id, session=s
    )
    assert pdf.startswith(b"%PDF-")


def test_html_safe_escapes():
    assert BoardpackExporter._html_safe("<a&b>") == "&lt;a&amp;b&gt;"
    assert BoardpackExporter._html_safe("") == ""
    assert BoardpackExporter._html_safe(None) == ""  # type: ignore[arg-type]


async def test_build_pdf_with_action_list_and_no_consensus(
    db_session, tenant, founder_user
):
    s = SessionRow(
        tenant_id=tenant.id,
        created_by_user_id=founder_user.id,
        consensus_text=None,
        consensus_kind=None,
        action_list=[{"owner": "X", "description": "y", "due_days": 3}],
    )
    db_session.add(s)
    await db_session.commit()
    pdf = await BoardpackExporter(db_session).build_for_session(
        tenant_id=tenant.id, session=s
    )
    assert pdf.startswith(b"%PDF-")


# Force a non-trivial confidence column path
async def test_turn_with_confidence_renders(db_session, tenant, founder_user):
    s = SessionRow(
        tenant_id=tenant.id, created_by_user_id=founder_user.id, kind="boardroom"
    )
    db_session.add(s)
    await db_session.flush()
    db_session.add(
        Turn(
            tenant_id=tenant.id,
            session_id=s.id,
            seq_no=1,
            role="user",
            language="en",
            payload_text="hi",
            confidence=Decimal("0.92"),
        )
    )
    await db_session.commit()
    pdf = await BoardpackExporter(db_session).build_for_session(
        tenant_id=tenant.id, session=s
    )
    assert pdf.startswith(b"%PDF-")
