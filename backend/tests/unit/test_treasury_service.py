"""Unit tests for TreasuryService — state machine + two-party gate."""
from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

import pytest
import pytest_asyncio

from app.audit.service import AuditService
from app.core.errors import (
    ConflictState,
    Forbidden,
    MandateViolation,
    NotFoundError,
    ProposalExpired,
    TwoPartyRequired,
)
from app.db.models import Session as SessionRow
from app.treasury.kraken import PaperKrakenClient
from app.treasury.mandate import MandateService
from app.treasury.service import TreasuryService


@pytest_asyncio.fixture
async def session_row(db_session, tenant, founder_user):
    s = SessionRow(
        tenant_id=tenant.id,
        created_by_user_id=founder_user.id,
        kind="boardroom",
        title="t",
    )
    db_session.add(s)
    await db_session.commit()
    await db_session.refresh(s)
    return s


@pytest_asyncio.fixture
async def svc(db_session):
    return TreasuryService(
        db_session,
        AuditService(db_session),
        MandateService(db_session),
        PaperKrakenClient(latency_ms=0),
    )


# ----------------------------------------------------- propose


async def test_propose_happy_path(svc, tenant, founder_user, session_row, active_mandate):
    action = await svc.propose(
        tenant_id=tenant.id,
        session_id=session_row.id,
        proposed_by_user_id=founder_user.id,
        instrument="SHV-xStock",
        side="buy",
        qty=Decimal("10"),
    )
    assert action.state == "proposed"
    assert action.instrument == "SHV-xStock"
    assert action.side == "buy"
    assert action.qty == Decimal("10")
    assert action.expected_price > Decimal("0")
    assert action.notional_eur > Decimal("0")
    assert action.expires_at > datetime.utcnow()
    assert action.proposed_by_user_id == founder_user.id


async def test_propose_with_explicit_price(svc, tenant, founder_user, session_row, active_mandate):
    action = await svc.propose(
        tenant_id=tenant.id,
        session_id=session_row.id,
        proposed_by_user_id=founder_user.id,
        instrument="SHV-xStock",
        side="buy",
        qty=Decimal("5"),
        expected_price=Decimal("110.00"),
    )
    assert action.expected_price == Decimal("110.00")
    assert action.notional_eur == Decimal("550.00")


async def test_propose_invalid_side_raises(svc, tenant, founder_user, session_row, active_mandate):
    with pytest.raises(MandateViolation, match="buy|sell"):
        await svc.propose(
            tenant_id=tenant.id,
            session_id=session_row.id,
            proposed_by_user_id=founder_user.id,
            instrument="SHV-xStock",
            side="hold",
            qty=Decimal("1"),
        )


async def test_propose_violates_mandate_raises(svc, tenant, founder_user, session_row, active_mandate):
    with pytest.raises(MandateViolation):
        await svc.propose(
            tenant_id=tenant.id,
            session_id=session_row.id,
            proposed_by_user_id=founder_user.id,
            instrument="BANNED-xStock",  # not in permitted list
            side="buy",
            qty=Decimal("1"),
        )


# ----------------------------------------------------- authorise


async def test_first_authorise_advances_state(
    svc, tenant, founder_user, session_row, active_mandate
):
    a = await svc.propose(
        tenant_id=tenant.id,
        session_id=session_row.id,
        proposed_by_user_id=founder_user.id,
        instrument="SHV-xStock",
        side="buy",
        qty=Decimal("1"),
    )
    a2 = await svc.authorise(tenant_id=tenant.id, proposal_id=a.id, user_id=founder_user.id)
    assert a2.state == "first_authorised"
    assert a2.auth1_user_id == founder_user.id
    assert a2.auth1_ts is not None


async def test_two_party_blocks_same_user_twice(
    svc, tenant, founder_user, session_row, active_mandate
):
    a = await svc.propose(
        tenant_id=tenant.id,
        session_id=session_row.id,
        proposed_by_user_id=founder_user.id,
        instrument="SHV-xStock",
        side="buy",
        qty=Decimal("1"),
    )
    await svc.authorise(tenant_id=tenant.id, proposal_id=a.id, user_id=founder_user.id)
    with pytest.raises(TwoPartyRequired):
        await svc.authorise(tenant_id=tenant.id, proposal_id=a.id, user_id=founder_user.id)


async def test_second_authorise_executes(
    svc, tenant, founder_user, second_authoriser, session_row, active_mandate
):
    a = await svc.propose(
        tenant_id=tenant.id,
        session_id=session_row.id,
        proposed_by_user_id=founder_user.id,
        instrument="SHV-xStock",
        side="buy",
        qty=Decimal("1"),
    )
    await svc.authorise(tenant_id=tenant.id, proposal_id=a.id, user_id=founder_user.id)
    a3 = await svc.authorise(tenant_id=tenant.id, proposal_id=a.id, user_id=second_authoriser.id)
    assert a3.state == "executed"
    assert a3.auth2_user_id == second_authoriser.id
    assert a3.kraken_order_id is not None
    assert a3.executed_at is not None


async def test_authorise_unknown_proposal_raises(svc, tenant, founder_user):
    with pytest.raises(NotFoundError):
        await svc.authorise(
            tenant_id=tenant.id, proposal_id="nonexistent", user_id=founder_user.id
        )


async def test_authorise_user_not_in_mandate_auth_list(
    db_session, svc, tenant, founder_user, session_row, active_mandate
):
    # Build a fresh user who is NOT in the mandate.auth_user_ids
    from app.db.models import User

    outsider = User(
        tenant_id=tenant.id,
        email="outsider@x.com",
        display_name="Outsider",
        role="authoriser",
    )
    db_session.add(outsider)
    await db_session.commit()
    a = await svc.propose(
        tenant_id=tenant.id,
        session_id=session_row.id,
        proposed_by_user_id=founder_user.id,
        instrument="SHV-xStock",
        side="buy",
        qty=Decimal("1"),
    )
    with pytest.raises(Forbidden, match="not an approved authoriser"):
        await svc.authorise(tenant_id=tenant.id, proposal_id=a.id, user_id=outsider.id)


async def test_authorise_viewer_role_blocked(db_session, svc, tenant, founder_user, session_row, active_mandate):
    from app.db.models import User

    viewer = User(
        tenant_id=tenant.id, email="v@x.com", display_name="V", role="viewer"
    )
    db_session.add(viewer)
    await db_session.commit()
    a = await svc.propose(
        tenant_id=tenant.id,
        session_id=session_row.id,
        proposed_by_user_id=founder_user.id,
        instrument="SHV-xStock",
        side="buy",
        qty=Decimal("1"),
    )
    with pytest.raises(Forbidden, match="role cannot authorise"):
        await svc.authorise(tenant_id=tenant.id, proposal_id=a.id, user_id=viewer.id)


async def test_authorise_expired_proposal_raises(
    db_session, svc, tenant, founder_user, session_row, active_mandate
):
    a = await svc.propose(
        tenant_id=tenant.id,
        session_id=session_row.id,
        proposed_by_user_id=founder_user.id,
        instrument="SHV-xStock",
        side="buy",
        qty=Decimal("1"),
    )
    a.expires_at = datetime.utcnow() - timedelta(seconds=1)
    await db_session.commit()
    with pytest.raises(ProposalExpired):
        await svc.authorise(tenant_id=tenant.id, proposal_id=a.id, user_id=founder_user.id)


async def test_authorise_already_executed_raises(
    svc, tenant, founder_user, second_authoriser, session_row, active_mandate
):
    a = await svc.propose(
        tenant_id=tenant.id,
        session_id=session_row.id,
        proposed_by_user_id=founder_user.id,
        instrument="SHV-xStock",
        side="buy",
        qty=Decimal("1"),
    )
    await svc.authorise(tenant_id=tenant.id, proposal_id=a.id, user_id=founder_user.id)
    await svc.authorise(tenant_id=tenant.id, proposal_id=a.id, user_id=second_authoriser.id)
    with pytest.raises(ConflictState):
        await svc.authorise(tenant_id=tenant.id, proposal_id=a.id, user_id=founder_user.id)


# ----------------------------------------------------- reject


async def test_reject_proposed_state(
    svc, tenant, founder_user, session_row, active_mandate
):
    a = await svc.propose(
        tenant_id=tenant.id,
        session_id=session_row.id,
        proposed_by_user_id=founder_user.id,
        instrument="SHV-xStock",
        side="buy",
        qty=Decimal("1"),
    )
    rejected = await svc.reject(
        tenant_id=tenant.id, proposal_id=a.id, user_id=founder_user.id, reason="oops"
    )
    assert rejected.state == "rejected"
    assert rejected.rejected_reason == "oops"


async def test_reject_after_execution_raises(
    svc, tenant, founder_user, second_authoriser, session_row, active_mandate
):
    a = await svc.propose(
        tenant_id=tenant.id,
        session_id=session_row.id,
        proposed_by_user_id=founder_user.id,
        instrument="SHV-xStock",
        side="buy",
        qty=Decimal("1"),
    )
    await svc.authorise(tenant_id=tenant.id, proposal_id=a.id, user_id=founder_user.id)
    await svc.authorise(tenant_id=tenant.id, proposal_id=a.id, user_id=second_authoriser.id)
    with pytest.raises(ConflictState):
        await svc.reject(
            tenant_id=tenant.id, proposal_id=a.id, user_id=founder_user.id, reason="too late"
        )


# ----------------------------------------------------- list / get


async def test_list_and_get(svc, tenant, founder_user, session_row, active_mandate):
    a = await svc.propose(
        tenant_id=tenant.id,
        session_id=session_row.id,
        proposed_by_user_id=founder_user.id,
        instrument="SHV-xStock",
        side="buy",
        qty=Decimal("1"),
    )
    rows = await svc.list_for_tenant(tenant.id)
    assert len(rows) == 1
    by_state = await svc.list_for_tenant(tenant.id, state="proposed")
    assert len(by_state) == 1
    got = await svc.get(tenant.id, a.id)
    assert got.id == a.id


# ----------------------------------------------------- execute failure


async def test_execute_kraken_unavailable_marks_failed(
    db_session, tenant, founder_user, second_authoriser, session_row, active_mandate
):
    kraken = PaperKrakenClient(latency_ms=0)
    svc = TreasuryService(db_session, AuditService(db_session), MandateService(db_session), kraken)
    a = await svc.propose(
        tenant_id=tenant.id,
        session_id=session_row.id,
        proposed_by_user_id=founder_user.id,
        instrument="SHV-xStock",
        side="buy",
        qty=Decimal("1"),
    )
    await svc.authorise(tenant_id=tenant.id, proposal_id=a.id, user_id=founder_user.id)
    # Now simulate outage right before second-auth-triggered execution
    kraken.configure(fail=True)
    a2 = await svc.authorise(tenant_id=tenant.id, proposal_id=a.id, user_id=second_authoriser.id)
    assert a2.state == "execution_failed"


async def test_authorise_user_not_in_tenant(db_session, svc, tenant, second_tenant, founder_user, session_row, active_mandate):
    from app.db.models import User
    # FIX 2026-05-19: use the `second_tenant` fixture so the FK constraint to
    # tenants(id) is satisfied. The previous "some-other-tenant-id" string
    # silently passed under SQLite (FKs off by default) but tripped the real
    # Postgres FK constraint when the suite ran against the docker stack.
    other_tenant_user = User(
        tenant_id=second_tenant.id,
        email="x@x.com",
        display_name="X",
        role="founder",
    )
    db_session.add(other_tenant_user)
    await db_session.commit()
    a = await svc.propose(
        tenant_id=tenant.id,
        session_id=session_row.id,
        proposed_by_user_id=founder_user.id,
        instrument="SHV-xStock",
        side="buy",
        qty=Decimal("1"),
    )
    with pytest.raises(Forbidden, match="user not found"):
        await svc.authorise(
            tenant_id=tenant.id, proposal_id=a.id, user_id=other_tenant_user.id
        )
