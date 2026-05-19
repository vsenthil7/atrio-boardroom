"""Seed a demo tenant, users, mandate, and per-agent memory.

Run from the host: `python -m app.scripts.seed_demo` (inside the api container)
or invoked by `make seed`.
"""
from __future__ import annotations

import asyncio
from decimal import Decimal

from sqlalchemy import select

from app.core.logging import configure_logging, get_logger
from app.db.base import get_sessionmaker
from app.db.models import Mandate, Tenant, User
from app.memory.service import MemoryService

log = get_logger(__name__)


DEMO_TENANT_SLUG = "acme-co"

SEED_USERS = [
    {
        "email": "founder@acme.co",
        "display_name": "Ada Founder",
        "role": "founder",
    },
    {
        "email": "ceo@acme.co",
        "display_name": "Carlos CEO",
        "role": "founder",
    },
    {
        "email": "treasurer@acme.co",
        "display_name": "Tess Treasurer",
        "role": "authoriser",
    },
]

SEED_MEMORIES = {
    "cfo": [
        ("Acme's monthly burn is €240k; runway to Q3 2026.", "salient_fact"),
        ("CFO previously advocated lower ad spend in favour of paid pilots.", "session_summary"),
    ],
    "cto": [
        ("Backend is Python + Postgres + pgvector on Vultr eu-central.", "salient_fact"),
        ("CTO opposed adding a fourth datastore last quarter.", "dissent_point"),
    ],
    "cmo": [
        ("Acme's wedge is family-office treasury for founders.", "salient_fact"),
    ],
    "coo": [
        ("Headcount plan: 14 → 18 by end of Q2 2026.", "salient_fact"),
    ],
    "counsel": [
        ("Acme is established in Italy; primary regulator is Banca d'Italia for treasury.", "salient_fact"),
    ],
    "treasury": [
        ("Approved instruments for Acme: SHV-xStock, IEF-xStock, EURUSD-xStock.", "salient_fact"),
    ],
}


async def seed() -> None:
    configure_logging()
    sm = get_sessionmaker()
    async with sm() as db:
        existing = (
            await db.execute(select(Tenant).where(Tenant.slug == DEMO_TENANT_SLUG))
        ).scalar_one_or_none()
        if existing is not None:
            log.info("seed_skipped_already_present", tenant=existing.id)
            return
        tenant = Tenant(
            name="Acme Co.",
            slug=DEMO_TENANT_SLUG,
            tier="founder",
            locale_default="en",
            data_residency="eu",
            kraken_enabled=True,
            kraken_live=False,
        )
        db.add(tenant)
        await db.flush()

        users: list[User] = []
        for u in SEED_USERS:
            user = User(
                tenant_id=tenant.id,
                email=u["email"],
                display_name=u["display_name"],
                role=u["role"],
            )
            db.add(user)
            users.append(user)
        await db.flush()

        # Mandate
        mandate = Mandate(
            tenant_id=tenant.id,
            version=1,
            daily_loss_limit=Decimal("25000.00"),
            single_instrument_max=Decimal("50000.00"),
            permitted_instruments=[
                "SHV-xStock",
                "IEF-xStock",
                "EURUSD-xStock",
                "SPY-xStock",
            ],
            permitted_sides=["buy", "sell"],
            auth_user_ids=[u.id for u in users if u.role in ("founder", "authoriser")],
            currency="EUR",
            is_active=True,
        )
        db.add(mandate)
        await db.flush()

        memory = MemoryService(db)
        for agent_id, items in SEED_MEMORIES.items():
            for content, kind in items:
                await memory.write(
                    tenant_id=tenant.id,
                    agent_id=agent_id,
                    content=content,
                    kind=kind,
                    weight=1.5 if kind == "salient_fact" else 1.0,
                )
        await db.commit()
        log.info("seed_complete", tenant=tenant.id, users=len(users))


if __name__ == "__main__":
    asyncio.run(seed())
