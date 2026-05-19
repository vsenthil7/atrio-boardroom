"""Unit tests for MandateService — the four-gate check."""
from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

from app.db.models import Mandate, TreasuryAction
from app.treasury.mandate import MandateService


async def test_check_passes_with_valid_inputs(db_session, tenant, active_mandate):
    svc = MandateService(db_session)
    r = await svc.check(
        tenant_id=tenant.id,
        instrument="SHV-xStock",
        side="buy",
        qty=Decimal("100"),
        expected_price=Decimal("110.20"),
    )
    assert r.overall_pass is True
    assert r.permitted_instruments.pass_
    assert r.permitted_sides.pass_
    assert r.single_instrument_max.pass_
    assert r.daily_loss_limit.pass_
    assert r.mandate_id == active_mandate.id


async def test_no_active_mandate_fails_all_gates(db_session, tenant):
    svc = MandateService(db_session)
    r = await svc.check(
        tenant_id=tenant.id,
        instrument="SHV-xStock",
        side="buy",
        qty=Decimal("10"),
        expected_price=Decimal("100"),
    )
    assert r.overall_pass is False
    assert r.permitted_instruments.detail.get("reason") == "no_active_mandate"


async def test_instrument_not_permitted(db_session, tenant, active_mandate):
    svc = MandateService(db_session)
    r = await svc.check(
        tenant_id=tenant.id,
        instrument="EVIL-xStock",
        side="buy",
        qty=Decimal("1"),
        expected_price=Decimal("100"),
    )
    assert r.overall_pass is False
    assert r.permitted_instruments.pass_ is False
    assert "instrument_not_permitted" in r.permitted_instruments.detail["reason"]


async def test_side_not_permitted(db_session, tenant, active_mandate):
    # Mutate the mandate to only allow buy
    active_mandate.permitted_sides = ["buy"]
    await db_session.commit()
    svc = MandateService(db_session)
    r = await svc.check(
        tenant_id=tenant.id,
        instrument="SHV-xStock",
        side="sell",
        qty=Decimal("1"),
        expected_price=Decimal("100"),
    )
    assert r.overall_pass is False
    assert r.permitted_sides.pass_ is False


async def test_single_instrument_max_breached(db_session, tenant, active_mandate):
    svc = MandateService(db_session)
    r = await svc.check(
        tenant_id=tenant.id,
        instrument="SHV-xStock",
        side="buy",
        qty=Decimal("1000"),  # 1000 * 110.20 = 110_200 > 50_000
        expected_price=Decimal("110.20"),
    )
    assert r.overall_pass is False
    assert r.single_instrument_max.pass_ is False
    detail = r.single_instrument_max.detail
    assert detail["reason"] == "notional_exceeds_single_instrument_max"


async def test_daily_loss_limit_breached(db_session, tenant, founder_user, active_mandate):
    # Insert an executed sell today equal to the daily loss limit
    from app.db.models import Session as SessionRow

    sess = SessionRow(
        tenant_id=tenant.id, created_by_user_id=founder_user.id, kind="boardroom"
    )
    db_session.add(sess)
    await db_session.flush()
    a = TreasuryAction(
        tenant_id=tenant.id,
        session_id=sess.id,
        mandate_id=active_mandate.id,
        instrument="SHV-xStock",
        side="sell",
        qty=Decimal("200"),
        expected_price=Decimal("110"),
        notional_eur=Decimal("24000.00"),  # under single-instrument max
        mandate_check_json={},
        state="executed",
        proposed_at=datetime.utcnow(),
        expires_at=datetime.utcnow() + timedelta(minutes=15),
        executed_at=datetime.utcnow(),
    )
    db_session.add(a)
    await db_session.commit()

    svc = MandateService(db_session)
    r = await svc.check(
        tenant_id=tenant.id,
        instrument="SHV-xStock",
        side="sell",
        qty=Decimal("20"),  # 20 * 110 = 2200 — pushes total over 25k
        expected_price=Decimal("110"),
    )
    assert r.overall_pass is False
    assert r.daily_loss_limit.pass_ is False
    assert "daily_loss_limit_exceeded" in r.daily_loss_limit.detail["reason"]


async def test_wildcard_instrument_permitted(db_session, tenant):
    m = Mandate(
        tenant_id=tenant.id,
        version=1,
        daily_loss_limit=Decimal("1000000"),
        single_instrument_max=Decimal("1000000"),
        permitted_instruments=["*"],
        permitted_sides=["buy", "sell"],
        auth_user_ids=[],
        currency="EUR",
        is_active=True,
    )
    db_session.add(m)
    await db_session.commit()
    svc = MandateService(db_session)
    r = await svc.check(
        tenant_id=tenant.id,
        instrument="ANY-WEIRD-THING",
        side="buy",
        qty=Decimal("1"),
        expected_price=Decimal("100"),
    )
    assert r.permitted_instruments.pass_ is True


async def test_check_picks_latest_version_only(db_session, tenant, founder_user):
    # Old inactive mandate
    db_session.add(
        Mandate(
            tenant_id=tenant.id,
            version=1,
            daily_loss_limit=Decimal("1"),
            single_instrument_max=Decimal("1"),
            permitted_instruments=["FOO"],
            permitted_sides=["buy"],
            auth_user_ids=[],
            is_active=False,
        )
    )
    # New active mandate, different rules
    db_session.add(
        Mandate(
            tenant_id=tenant.id,
            version=2,
            daily_loss_limit=Decimal("99999"),
            single_instrument_max=Decimal("99999"),
            permitted_instruments=["BAR"],
            permitted_sides=["buy"],
            auth_user_ids=[],
            is_active=True,
        )
    )
    await db_session.commit()
    svc = MandateService(db_session)
    r = await svc.check(
        tenant_id=tenant.id,
        instrument="BAR",
        side="buy",
        qty=Decimal("1"),
        expected_price=Decimal("1"),
    )
    assert r.overall_pass is True
    assert r.mandate_version == 2


async def test_as_dict_round_trips(db_session, tenant, active_mandate):
    svc = MandateService(db_session)
    r = await svc.check(
        tenant_id=tenant.id,
        instrument="SHV-xStock",
        side="buy",
        qty=Decimal("1"),
        expected_price=Decimal("100"),
    )
    d = r.as_dict()
    assert d["overall_pass"] is True
    assert d["permitted_instruments"]["pass"] is True
    assert "mandate_version" in d
