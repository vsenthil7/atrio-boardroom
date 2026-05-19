"""Mandate-check service.

Enforces principle P3: every treasury proposal is checked at the API layer
**before** any Kraken call. A UI-only edit cannot bypass this.

A mandate has four gates:
1. `permitted_instruments` — instrument must be in the list (case-insensitive)
2. `permitted_sides` — side ('buy' / 'sell') must be in the list
3. `single_instrument_max` — proposed notional ≤ limit
4. `daily_loss_limit` — today's realised losses + this notional (if loss-side) ≤ limit

Each gate produces a structured result; the proposal stores the full trace
so the audit log captures every gate decision.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Mandate, TreasuryAction


@dataclass
class GateResult:
    pass_: bool
    detail: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {"pass": self.pass_, **self.detail}


@dataclass
class MandateCheckResult:
    overall_pass: bool
    permitted_instruments: GateResult
    permitted_sides: GateResult
    single_instrument_max: GateResult
    daily_loss_limit: GateResult
    mandate_id: str
    mandate_version: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "mandate_id": self.mandate_id,
            "mandate_version": self.mandate_version,
            "overall_pass": self.overall_pass,
            "permitted_instruments": self.permitted_instruments.as_dict(),
            "permitted_sides": self.permitted_sides.as_dict(),
            "single_instrument_max": self.single_instrument_max.as_dict(),
            "daily_loss_limit": self.daily_loss_limit.as_dict(),
        }


class MandateService:
    """Read mandates and run gate checks."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_active_for_tenant(self, tenant_id: str) -> Mandate | None:
        stmt = (
            select(Mandate)
            .where(Mandate.tenant_id == tenant_id, Mandate.is_active.is_(True))
            .order_by(Mandate.version.desc())
            .limit(1)
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def check(
        self,
        *,
        tenant_id: str,
        instrument: str,
        side: str,
        qty: Decimal,
        expected_price: Decimal,
    ) -> MandateCheckResult:
        mandate = await self.get_active_for_tenant(tenant_id)
        if mandate is None:
            return MandateCheckResult(
                overall_pass=False,
                permitted_instruments=GateResult(False, {"reason": "no_active_mandate"}),
                permitted_sides=GateResult(False, {"reason": "no_active_mandate"}),
                single_instrument_max=GateResult(False, {"reason": "no_active_mandate"}),
                daily_loss_limit=GateResult(False, {"reason": "no_active_mandate"}),
                mandate_id="",
                mandate_version=0,
            )

        # Gate 1: permitted instruments
        permitted_set = {str(s).lower() for s in (mandate.permitted_instruments or [])}
        if "*" in permitted_set:
            g_instr = GateResult(True, {"wildcard": True})
        elif instrument.lower() in permitted_set:
            g_instr = GateResult(True, {"instrument": instrument})
        else:
            g_instr = GateResult(
                False,
                {
                    "instrument": instrument,
                    "permitted": sorted(permitted_set),
                    "reason": "instrument_not_permitted",
                },
            )

        # Gate 2: permitted sides
        permitted_sides = {str(s).lower() for s in (mandate.permitted_sides or [])}
        if side.lower() in permitted_sides:
            g_side = GateResult(True, {"side": side})
        else:
            g_side = GateResult(
                False,
                {
                    "side": side,
                    "permitted": sorted(permitted_sides),
                    "reason": "side_not_permitted",
                },
            )

        # Gate 3: notional ≤ single_instrument_max
        notional = (qty * expected_price).quantize(Decimal("0.01"))
        limit_single = mandate.single_instrument_max
        if notional <= limit_single:
            g_single = GateResult(
                True, {"notional": str(notional), "limit": str(limit_single)}
            )
        else:
            g_single = GateResult(
                False,
                {
                    "notional": str(notional),
                    "limit": str(limit_single),
                    "reason": "notional_exceeds_single_instrument_max",
                },
            )

        # Gate 4: daily loss limit. Sum today's executed sells minus buys at cost
        # (a rough proxy; for paper trading this is the conservative formulation).
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = today_start + timedelta(days=1)
        stmt = select(TreasuryAction).where(
            TreasuryAction.tenant_id == tenant_id,
            TreasuryAction.state == "executed",
            TreasuryAction.executed_at >= today_start,
            TreasuryAction.executed_at < today_end,
        )
        executed_today = (await self._session.execute(stmt)).scalars().all()
        today_loss_proxy = sum(
            (a.notional_eur for a in executed_today if a.side == "sell"), Decimal("0")
        )
        loss_limit = mandate.daily_loss_limit
        projected = today_loss_proxy + (notional if side == "sell" else Decimal("0"))
        if projected <= loss_limit:
            g_loss = GateResult(
                True,
                {
                    "today_so_far": str(today_loss_proxy),
                    "this_proposal": str(notional if side == "sell" else Decimal("0")),
                    "limit": str(loss_limit),
                },
            )
        else:
            g_loss = GateResult(
                False,
                {
                    "today_so_far": str(today_loss_proxy),
                    "this_proposal": str(notional if side == "sell" else Decimal("0")),
                    "projected_total": str(projected),
                    "limit": str(loss_limit),
                    "reason": "daily_loss_limit_exceeded",
                },
            )

        overall = (
            g_instr.pass_
            and g_side.pass_
            and g_single.pass_
            and g_loss.pass_
        )
        return MandateCheckResult(
            overall_pass=overall,
            permitted_instruments=g_instr,
            permitted_sides=g_side,
            single_instrument_max=g_single,
            daily_loss_limit=g_loss,
            mandate_id=mandate.id,
            mandate_version=mandate.version,
        )
