"""Unit tests for the PaperKrakenClient."""
from __future__ import annotations

from decimal import Decimal

import pytest

from app.treasury.kraken import (
    KrakenUnavailable,
    OrderResult,
    PaperKrakenClient,
    Quote,
    get_kraken_client,
    reset_kraken_client,
)


async def test_get_quote_known_instrument():
    c = PaperKrakenClient(latency_ms=0)
    q = await c.get_quote("SHV-xStock")
    assert isinstance(q, Quote)
    assert q.instrument == "SHV-xStock"
    assert q.price > Decimal("0")


async def test_get_quote_unknown_instrument_returns_default():
    c = PaperKrakenClient(latency_ms=0)
    q = await c.get_quote("WHATEVER")
    assert q.price >= Decimal("100")  # default base + jitter


async def test_get_quote_deterministic_jitter():
    c = PaperKrakenClient(latency_ms=0)
    q1 = await c.get_quote("SHV-xStock")
    q2 = await c.get_quote("SHV-xStock")
    assert q1.price == q2.price


async def test_place_order_returns_paper_id():
    c = PaperKrakenClient(latency_ms=0)
    r = await c.place_order("SHV-xStock", "buy", Decimal("10"))
    assert isinstance(r, OrderResult)
    assert r.order_id.startswith("PAPER-")
    assert r.executed_qty == Decimal("10")
    assert r.executed_price > Decimal("0")


async def test_failure_mode_raises_kraken_unavailable():
    c = PaperKrakenClient(fail=True, latency_ms=0)
    with pytest.raises(KrakenUnavailable):
        await c.get_quote("SHV-xStock")
    with pytest.raises(KrakenUnavailable):
        await c.place_order("SHV-xStock", "buy", Decimal("1"))


async def test_configure_method_toggles_fail():
    c = PaperKrakenClient(latency_ms=0)
    c.configure(fail=True)
    with pytest.raises(KrakenUnavailable):
        await c.get_quote("SHV-xStock")
    c.configure(fail=False)
    q = await c.get_quote("SHV-xStock")
    assert q.price > 0


def test_global_kraken_client_singleton():
    reset_kraken_client()
    c1 = get_kraken_client()
    c2 = get_kraken_client()
    assert c1 is c2
    reset_kraken_client()
    c3 = get_kraken_client()
    assert c3 is not c1
