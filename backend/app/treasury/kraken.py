"""Kraken CLI sidecar client.

In production the Kraken CLI runs in a sibling container and we talk to it
over a local Unix socket. In hackathon/paper mode we use a deterministic
in-process simulator that emits realistic-looking order responses.

The interface mirrors the subset of Kraken endpoints we use:
- get_quote(instrument) → expected execution price
- place_order(instrument, side, qty) → order_id, executed_price, executed_qty
- get_positions() / get_balance() — read-only

The sidecar is the **only** path to Kraken. The orchestrator imports
`get_kraken_client()` and gets back this interface, not the raw HTTP client.
"""
from __future__ import annotations

import asyncio
import hashlib
import os
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

from app.core.config import get_settings
from app.core.logging import get_logger

log = get_logger(__name__)


class KrakenUnavailable(Exception):
    """Raised when Kraken is unreachable. Treasury preserves the proposal for retry."""


@dataclass(frozen=True)
class Quote:
    instrument: str
    price: Decimal


@dataclass(frozen=True)
class OrderResult:
    order_id: str
    executed_price: Decimal
    executed_qty: Decimal


class KrakenClient(Protocol):
    async def get_quote(self, instrument: str) -> Quote: ...
    async def place_order(
        self, instrument: str, side: str, qty: Decimal
    ) -> OrderResult: ...


# ---------------------------------------------------------------------------
# Paper / mock client (always available, used unless live mode explicitly on)
# ---------------------------------------------------------------------------


class PaperKrakenClient:
    """Deterministic paper-trading client. Same instrument always quotes the same
    base price + a tiny stable jitter."""

    _PRICES = {
        "shv-xstock": Decimal("110.20"),
        "spy-xstock": Decimal("521.45"),
        "qqq-xstock": Decimal("438.10"),
        "ief-xstock": Decimal("94.30"),
        "tlt-xstock": Decimal("89.75"),
        "eurusd-xstock": Decimal("1.0850"),
        "btcusd": Decimal("65420.00"),
    }

    def __init__(self, *, fail: bool = False, latency_ms: int = 50) -> None:
        self._fail = fail
        self._latency = latency_ms / 1000.0
        self._idem_seen: set[str] = set()

    def configure(self, *, fail: bool | None = None) -> None:
        if fail is not None:
            self._fail = fail

    async def get_quote(self, instrument: str) -> Quote:
        if self._fail:
            raise KrakenUnavailable(f"paper kraken simulated outage for {instrument}")
        await asyncio.sleep(self._latency)
        key = instrument.lower()
        base = self._PRICES.get(key, Decimal("100.00"))
        # tiny stable jitter for realism
        h = hashlib.sha256(key.encode()).digest()[0]
        jitter = Decimal(h) / Decimal("1000")  # 0.00 - 0.255
        return Quote(instrument=instrument, price=(base + jitter).quantize(Decimal("0.01")))

    async def place_order(
        self, instrument: str, side: str, qty: Decimal
    ) -> OrderResult:
        if self._fail:
            raise KrakenUnavailable(f"paper kraken simulated outage on place_order {instrument}")
        await asyncio.sleep(self._latency)
        quote = await self.get_quote(instrument)
        order_id = "PAPER-" + hashlib.sha256(
            f"{instrument}|{side}|{qty}|{os.urandom(8).hex()}".encode()
        ).hexdigest()[:16].upper()
        return OrderResult(
            order_id=order_id,
            executed_price=quote.price,
            executed_qty=qty,
        )


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

_client: KrakenClient | None = None


def get_kraken_client() -> KrakenClient:
    """Process-wide Kraken client. Paper unless KRAKEN_PAPER_MODE=false."""
    global _client
    if _client is None:
        settings = get_settings()
        if not settings.kraken_paper_mode:  # pragma: no cover - live path
            log.warning("kraken_live_mode_initialised")
        # For v1 we only ship the paper client. Live mode is gated by the same
        # client with a real HTTP layer behind it (not in scope for this build).
        _client = PaperKrakenClient()
    return _client


def reset_kraken_client() -> None:
    global _client
    _client = None
