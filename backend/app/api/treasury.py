"""Treasury router — mandate-gated, two-party authorised.

POST   /treasury/proposals
GET    /treasury/proposals
GET    /treasury/proposals/{id}
POST   /treasury/proposals/{id}/authorise
POST   /treasury/proposals/{id}/reject
"""
from __future__ import annotations

from fastapi import APIRouter, status
from sqlalchemy import select

from app.api.deps import CurrentUserDep, DbSession
from app.api.schemas import (
    TreasuryAuthorise,
    TreasuryProposalCreate,
    TreasuryProposalPublic,
    TreasuryReject,
)
from app.audit.service import AuditService
from app.core.errors import Forbidden, NotFoundError
from app.db.models import Session as SessionRow, TreasuryAction
from app.treasury.kraken import get_kraken_client
from app.treasury.mandate import MandateService
from app.treasury.service import TreasuryService

router = APIRouter(prefix="/treasury", tags=["treasury"])


def _to_public(a: TreasuryAction) -> TreasuryProposalPublic:
    return TreasuryProposalPublic(
        id=a.id,
        session_id=a.session_id,
        instrument=a.instrument,
        side=a.side,
        qty=a.qty,
        expected_price=a.expected_price,
        notional_eur=a.notional_eur,
        state=a.state,
        proposed_at=a.proposed_at,
        expires_at=a.expires_at,
        auth1_user_id=a.auth1_user_id,
        auth2_user_id=a.auth2_user_id,
        kraken_order_id=a.kraken_order_id,
        executed_price=a.executed_price,
        executed_qty=a.executed_qty,
        mandate_check=a.mandate_check_json,
    )


@router.post(
    "/proposals", response_model=TreasuryProposalPublic, status_code=status.HTTP_201_CREATED
)
async def create_proposal(
    body: TreasuryProposalCreate, user: CurrentUserDep, db: DbSession
) -> TreasuryProposalPublic:
    # Validate session belongs to tenant
    sess = (
        await db.execute(
            select(SessionRow).where(
                SessionRow.id == body.session_id, SessionRow.tenant_id == user.tenant_id
            )
        )
    ).scalar_one_or_none()
    if sess is None:
        raise NotFoundError("session not found", details={"session_id": body.session_id})

    svc = TreasuryService(
        db, AuditService(db), MandateService(db), get_kraken_client()
    )
    action = await svc.propose(
        tenant_id=user.tenant_id,
        session_id=body.session_id,
        proposed_by_user_id=user.user_id,
        instrument=body.instrument,
        side=body.side,
        qty=body.qty,
        expected_price=body.expected_price,
    )
    return _to_public(action)


@router.get("/proposals", response_model=list[TreasuryProposalPublic])
async def list_proposals(
    user: CurrentUserDep, db: DbSession, state: str | None = None
) -> list[TreasuryProposalPublic]:
    svc = TreasuryService(db, AuditService(db), MandateService(db))
    actions = await svc.list_for_tenant(user.tenant_id, state=state)
    return [_to_public(a) for a in actions]


@router.get("/proposals/{proposal_id}", response_model=TreasuryProposalPublic)
async def get_proposal(
    proposal_id: str, user: CurrentUserDep, db: DbSession
) -> TreasuryProposalPublic:
    svc = TreasuryService(db, AuditService(db), MandateService(db))
    a = await svc.get(user.tenant_id, proposal_id)
    return _to_public(a)


@router.post(
    "/proposals/{proposal_id}/authorise", response_model=TreasuryProposalPublic
)
async def authorise_proposal(
    proposal_id: str,
    body: TreasuryAuthorise,
    user: CurrentUserDep,
    db: DbSession,
) -> TreasuryProposalPublic:
    if not user.can_authorise:
        raise Forbidden(
            "role cannot authorise treasury actions",
            details={"role": user.role},
        )
    if not body.confirm:
        raise Forbidden("confirm must be true to authorise")
    svc = TreasuryService(
        db, AuditService(db), MandateService(db), get_kraken_client()
    )
    action = await svc.authorise(
        tenant_id=user.tenant_id, proposal_id=proposal_id, user_id=user.user_id
    )
    return _to_public(action)


@router.post(
    "/proposals/{proposal_id}/reject", response_model=TreasuryProposalPublic
)
async def reject_proposal(
    proposal_id: str,
    body: TreasuryReject,
    user: CurrentUserDep,
    db: DbSession,
) -> TreasuryProposalPublic:
    if not user.can_authorise:
        raise Forbidden("role cannot reject treasury actions", details={"role": user.role})
    svc = TreasuryService(
        db, AuditService(db), MandateService(db), get_kraken_client()
    )
    action = await svc.reject(
        tenant_id=user.tenant_id,
        proposal_id=proposal_id,
        user_id=user.user_id,
        reason=body.reason,
    )
    return _to_public(action)
