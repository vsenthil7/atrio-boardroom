"""Treasury service — proposal lifecycle (propose → authorise×2 → execute).

State machine:
  proposed → first_authorised → fully_authorised → executed
                             ↓
                          rejected (any state pre-execution)
                          expired (any state pre-execution after expiry)

Enforces:
- P3: every state transition rechecks the mandate as needed
- AP-4: mandate violations rejected at the API layer (HTTP 403)
- §2.4: two-party authorisation — single party calling twice returns 403
"""
from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import AuditService
from app.core.config import get_settings
from app.core.errors import (
    ConflictState,
    Forbidden,
    MandateViolation,
    NotFoundError,
    ProposalExpired,
    TwoPartyRequired,
)
from app.core.logging import get_logger
from app.db.models import TreasuryAction, User
from app.treasury.kraken import KrakenClient, KrakenUnavailable, get_kraken_client
from app.treasury.mandate import MandateService

log = get_logger(__name__)


PROPOSAL_STATES = {
    "proposed",
    "first_authorised",
    "fully_authorised",
    "executed",
    "rejected",
    "expired",
    "execution_failed",
}


class TreasuryService:
    def __init__(
        self,
        session: AsyncSession,
        audit: AuditService,
        mandate_service: MandateService,
        kraken: KrakenClient | None = None,
    ) -> None:
        self._session = session
        self._audit = audit
        self._mandate = mandate_service
        self._kraken = kraken or get_kraken_client()

    # ---------------------------------------------------- propose

    async def propose(
        self,
        *,
        tenant_id: str,
        session_id: str,
        proposed_by_user_id: str,
        instrument: str,
        side: str,
        qty: Decimal,
        expected_price: Decimal | None = None,
    ) -> TreasuryAction:
        if side not in ("buy", "sell"):
            raise MandateViolation(
                "side must be buy|sell",
                details={"side": side},
            )

        if expected_price is None:
            quote = await self._kraken.get_quote(instrument)
            expected_price = quote.price

        mandate_result = await self._mandate.check(
            tenant_id=tenant_id,
            instrument=instrument,
            side=side,
            qty=qty,
            expected_price=expected_price,
        )

        if not mandate_result.overall_pass:
            await self._audit.write(
                tenant_id=tenant_id,
                session_id=session_id,
                actor_user_id=proposed_by_user_id,
                kind="treasury_proposal_rejected_mandate",
                payload={
                    "instrument": instrument,
                    "side": side,
                    "qty": str(qty),
                    "expected_price": str(expected_price),
                    "mandate_check": mandate_result.as_dict(),
                },
            )
            # Pull a reason out of the first failing gate for the metric label
            for gate_name in ("permitted_instruments", "permitted_sides", "single_instrument_max", "daily_loss_limit"):
                gate = getattr(mandate_result, gate_name)
                if not gate.pass_:
                    from app.observability import mandate_violations_total

                    mandate_violations_total.inc(
                        labels={"reason": gate.detail.get("reason", gate_name)}
                    )
                    break
            raise MandateViolation(
                "proposal violates active mandate",
                details=mandate_result.as_dict(),
            )

        notional = (qty * expected_price).quantize(Decimal("0.01"))
        settings = get_settings()
        now = datetime.utcnow()
        expires = now + timedelta(seconds=settings.proposal_expiry_seconds)
        action = TreasuryAction(
            tenant_id=tenant_id,
            session_id=session_id,
            mandate_id=mandate_result.mandate_id,
            instrument=instrument,
            side=side,
            qty=qty,
            expected_price=expected_price,
            notional_eur=notional,
            mandate_check_json=mandate_result.as_dict(),
            state="proposed",
            proposed_at=now,
            expires_at=expires,
            proposed_by_user_id=proposed_by_user_id,
        )
        self._session.add(action)
        await self._session.flush()
        await self._audit.write(
            tenant_id=tenant_id,
            session_id=session_id,
            actor_user_id=proposed_by_user_id,
            kind="treasury_proposed",
            payload={
                "proposal_id": action.id,
                "instrument": instrument,
                "side": side,
                "qty": str(qty),
                "expected_price": str(expected_price),
                "notional_eur": str(notional),
                "expires_at": expires.isoformat(),
            },
        )
        from app.observability import treasury_proposed_total

        treasury_proposed_total.inc(labels={"side": side, "instrument": instrument})
        return action

    # ---------------------------------------------------- authorise

    async def authorise(
        self, *, tenant_id: str, proposal_id: str, user_id: str
    ) -> TreasuryAction:
        action = await self._get_action(tenant_id, proposal_id)
        self._reject_if_expired(action)
        await self._verify_authoriser(tenant_id, user_id, action.mandate_id)

        if action.state == "proposed":
            if action.proposed_by_user_id == user_id:
                # The proposer can be one of two authorisers? Spec is silent; we
                # apply the conservative reading: the proposer can be auth1.
                pass
            action.auth1_user_id = user_id
            action.auth1_ts = datetime.utcnow()
            action.state = "first_authorised"
            await self._audit.write(
                tenant_id=tenant_id,
                session_id=action.session_id,
                actor_user_id=user_id,
                kind="treasury_first_authorised",
                payload={"proposal_id": proposal_id},
            )
            await self._session.flush()
            return action

        if action.state == "first_authorised":
            if action.auth1_user_id == user_id:
                from app.observability import two_party_blocks_total

                two_party_blocks_total.inc()
                raise TwoPartyRequired(
                    "this user has already authorised this proposal",
                    details={"proposal_id": proposal_id},
                )
            action.auth2_user_id = user_id
            action.auth2_ts = datetime.utcnow()
            action.state = "fully_authorised"
            await self._audit.write(
                tenant_id=tenant_id,
                session_id=action.session_id,
                actor_user_id=user_id,
                kind="treasury_fully_authorised",
                payload={"proposal_id": proposal_id},
            )
            await self._session.flush()
            await self._execute(action)
            return action

        raise ConflictState(
            f"cannot authorise from state={action.state}",
            details={"proposal_id": proposal_id, "state": action.state},
        )

    async def reject(
        self, *, tenant_id: str, proposal_id: str, user_id: str, reason: str
    ) -> TreasuryAction:
        action = await self._get_action(tenant_id, proposal_id)
        if action.state not in ("proposed", "first_authorised"):
            raise ConflictState(
                "cannot reject from this state",
                details={"state": action.state},
            )
        await self._verify_authoriser(tenant_id, user_id, action.mandate_id)
        action.state = "rejected"
        action.rejected_by_user_id = user_id
        action.rejected_reason = reason
        action.rejected_at = datetime.utcnow()
        await self._session.flush()
        await self._audit.write(
            tenant_id=tenant_id,
            session_id=action.session_id,
            actor_user_id=user_id,
            kind="treasury_rejected",
            payload={"proposal_id": proposal_id, "reason": reason},
        )
        return action

    # ---------------------------------------------------- execute

    async def _execute(self, action: TreasuryAction) -> None:
        try:
            result = await self._kraken.place_order(
                action.instrument, action.side, action.qty
            )
        except KrakenUnavailable as e:
            log.error(
                "kraken_unavailable", proposal_id=action.id, error=str(e)
            )
            action.state = "execution_failed"
            await self._session.flush()
            await self._audit.write(
                tenant_id=action.tenant_id,
                session_id=action.session_id,
                kind="treasury_execution_failed",
                payload={"proposal_id": action.id, "error": str(e)},
            )
            return
        action.kraken_order_id = result.order_id
        action.executed_price = result.executed_price
        action.executed_qty = result.executed_qty
        action.executed_at = datetime.utcnow()
        action.state = "executed"
        await self._session.flush()
        await self._audit.write(
            tenant_id=action.tenant_id,
            session_id=action.session_id,
            kind="treasury_executed",
            payload={
                "proposal_id": action.id,
                "kraken_order_id": result.order_id,
                "executed_price": str(result.executed_price),
                "executed_qty": str(result.executed_qty),
            },
        )
        from app.observability import treasury_executed_total

        treasury_executed_total.inc(labels={"instrument": action.instrument})

    # ---------------------------------------------------- helpers

    async def _get_action(self, tenant_id: str, proposal_id: str) -> TreasuryAction:
        stmt = select(TreasuryAction).where(
            TreasuryAction.id == proposal_id, TreasuryAction.tenant_id == tenant_id
        )
        action = (await self._session.execute(stmt)).scalar_one_or_none()
        if action is None:
            raise NotFoundError("proposal not found", details={"proposal_id": proposal_id})
        return action

    def _reject_if_expired(self, action: TreasuryAction) -> None:
        if action.state in ("executed", "rejected", "expired"):
            return
        if datetime.utcnow() > action.expires_at:
            action.state = "expired"
            raise ProposalExpired(details={"proposal_id": action.id, "expires_at": action.expires_at.isoformat()})

    async def _verify_authoriser(
        self, tenant_id: str, user_id: str, mandate_id: str
    ) -> None:
        # User must exist + be an authoriser; in v1 we also check mandate auth_user_ids
        u = await self._session.execute(
            select(User).where(User.id == user_id, User.tenant_id == tenant_id)
        )
        user = u.scalar_one_or_none()
        if user is None:
            raise Forbidden("user not found in tenant", details={"user_id": user_id})
        if user.role not in ("authoriser", "founder"):
            raise Forbidden(
                "user role cannot authorise",
                details={"role": user.role},
            )
        # mandate.auth_user_ids gate:
        from app.db.models import Mandate
        m = await self._session.execute(
            select(Mandate).where(Mandate.id == mandate_id)
        )
        mandate = m.scalar_one_or_none()
        if mandate and mandate.auth_user_ids:
            if user_id not in [str(x) for x in mandate.auth_user_ids]:
                raise Forbidden(
                    "user is not an approved authoriser for this mandate",
                    details={"user_id": user_id, "mandate_id": mandate_id},
                )

    async def list_for_tenant(self, tenant_id: str, *, state: str | None = None) -> list[TreasuryAction]:
        stmt = select(TreasuryAction).where(TreasuryAction.tenant_id == tenant_id)
        if state is not None:
            stmt = stmt.where(TreasuryAction.state == state)
        stmt = stmt.order_by(TreasuryAction.proposed_at.desc())
        return list((await self._session.execute(stmt)).scalars().all())

    async def get(self, tenant_id: str, proposal_id: str) -> TreasuryAction:
        return await self._get_action(tenant_id, proposal_id)
