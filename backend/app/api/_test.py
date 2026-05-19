"""Test-only admin endpoints for E2E seeding.

This router is ONLY mounted when ATRIO_ENV ∈ {test, demo, local}. In
staging/prod the routes do not exist at all, so there is no risk of
production users hitting them.

Endpoints:
  POST /_test/seed-demo   — wipes + reseeds an acme tenant with two users
                            and an active mandate, returns their emails.
"""
from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter
from sqlalchemy import delete

from app.api.deps import DbSession
from app.db.models import (
    AgentMemory,
    AuditEvent,
    Document,
    MagicLinkToken,
    Mandate,
    Session as SessionRow,
    Tenant,
    TreasuryAction,
    Turn,
    User,
)

router = APIRouter(prefix="/_test", tags=["test-only"])


@router.post("/seed-demo")
async def seed_demo(db: DbSession) -> dict[str, str]:
    """Wipe everything and write a fresh demo tenant + two users + mandate."""
    # Wipe in FK-safe order
    for tbl in (
        TreasuryAction,
        AuditEvent,
        Turn,
        Document,
        AgentMemory,
        Mandate,
        SessionRow,
        MagicLinkToken,
        User,
        Tenant,
    ):
        await db.execute(delete(tbl))
    await db.flush()

    tenant = Tenant(
        name="Acme Co",
        slug="acme-co",
        tier="founder",
        locale_default="en",
        data_residency="eu",
        kraken_enabled=True,
        kraken_live=False,
    )
    db.add(tenant)
    await db.flush()

    founder = User(
        tenant_id=tenant.id,
        email="founder@acme.co",
        display_name="Founder",
        role="founder",
    )
    second = User(
        tenant_id=tenant.id,
        email="ceo@acme.co",
        display_name="CEO",
        role="authoriser",
    )
    db.add_all([founder, second])
    await db.flush()

    mandate = Mandate(
        tenant_id=tenant.id,
        version=1,
        daily_loss_limit=Decimal("25000.00"),
        single_instrument_max=Decimal("50000.00"),
        permitted_instruments=["SHV-xStock", "IEF-xStock", "EURUSD-xStock"],
        permitted_sides=["buy", "sell"],
        auth_user_ids=[founder.id, second.id],
        currency="EUR",
        is_active=True,
    )
    db.add(mandate)
    await db.commit()

    return {
        "founder_email": founder.email,
        "second_email": second.email,
        "tenant_id": tenant.id,
    }
