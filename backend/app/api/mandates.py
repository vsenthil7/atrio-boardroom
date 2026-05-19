"""Mandates router — view + (founders only) update."""
from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, status
from sqlalchemy import select

from app.api.deps import CurrentUserDep, DbSession
from app.api.schemas import MandateCreate, MandatePublic
from app.audit.service import AuditService
from app.core.errors import Forbidden, NotFoundError
from app.db.models import Mandate

router = APIRouter(prefix="/mandates", tags=["mandates"])


def _to_public(m: Mandate) -> MandatePublic:
    return MandatePublic(
        id=m.id,
        version=m.version,
        daily_loss_limit=m.daily_loss_limit,
        single_instrument_max=m.single_instrument_max,
        permitted_instruments=list(m.permitted_instruments or []),
        permitted_sides=list(m.permitted_sides or []),
        auth_user_ids=list(m.auth_user_ids or []),
        currency=m.currency,
        is_active=m.is_active,
    )


@router.get("/active", response_model=MandatePublic)
async def get_active_mandate(user: CurrentUserDep, db: DbSession) -> MandatePublic:
    row = (
        await db.execute(
            select(Mandate)
            .where(Mandate.tenant_id == user.tenant_id, Mandate.is_active.is_(True))
            .order_by(Mandate.version.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if row is None:
        raise NotFoundError("no active mandate", details={"tenant_id": user.tenant_id})
    return _to_public(row)


@router.post("", response_model=MandatePublic, status_code=status.HTTP_201_CREATED)
async def create_mandate(
    body: MandateCreate, user: CurrentUserDep, db: DbSession
) -> MandatePublic:
    if not user.is_founder:
        raise Forbidden("only founders may create mandates", details={"role": user.role})

    # Deactivate prior active mandate (version-bumped)
    prior = (
        await db.execute(
            select(Mandate)
            .where(Mandate.tenant_id == user.tenant_id, Mandate.is_active.is_(True))
            .order_by(Mandate.version.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    next_version = (prior.version + 1) if prior else 1
    if prior:
        prior.is_active = False

    m = Mandate(
        tenant_id=user.tenant_id,
        version=next_version,
        daily_loss_limit=Decimal(str(body.daily_loss_limit)),
        single_instrument_max=Decimal(str(body.single_instrument_max)),
        permitted_instruments=list(body.permitted_instruments),
        permitted_sides=list(body.permitted_sides),
        auth_user_ids=list(body.auth_user_ids),
        currency=body.currency,
        is_active=True,
    )
    db.add(m)
    await db.flush()
    await AuditService(db).write(
        tenant_id=user.tenant_id,
        actor_user_id=user.user_id,
        kind="mandate_created",
        payload={
            "mandate_id": m.id,
            "version": m.version,
            "daily_loss_limit": str(m.daily_loss_limit),
            "single_instrument_max": str(m.single_instrument_max),
        },
    )
    return _to_public(m)


@router.get("", response_model=list[MandatePublic])
async def list_mandates(user: CurrentUserDep, db: DbSession) -> list[MandatePublic]:
    rows = (
        await db.execute(
            select(Mandate)
            .where(Mandate.tenant_id == user.tenant_id)
            .order_by(Mandate.version.desc())
        )
    ).scalars().all()
    return [_to_public(m) for m in rows]
