"""Mandate violation corpus.

Every entry in this list represents a category of "things a treasury agent
might try to do that a mandate must reject". This test makes the corpus a
first-class enforcement artifact — if the API ever lets one of these slip
through, CI breaks.
"""
from __future__ import annotations

from decimal import Decimal

import pytest
import pytest_asyncio


@pytest_asyncio.fixture
async def session_id(app_client, auth_header):
    r = await app_client.post(
        "/api/v1/sessions", headers=auth_header, json={"title": "corpus"}
    )
    return r.json()["id"]


# Each tuple: (id, body, expected_error_code, scenario)
CORPUS = [
    (
        "01_banned_instrument",
        {"instrument": "BANNED-xStock", "side": "buy", "qty": "1"},
        "MANDATE_VIOLATION",
        "Instrument not on the permitted list",
    ),
    (
        "02_short_when_short_disallowed",
        # We'll mutate mandate to permit only buys for this test
        {"instrument": "SHV-xStock", "side": "sell", "qty": "1"},
        "MANDATE_VIOLATION",
        "Side not in permitted set (after mandate restricted to buy-only)",
    ),
    (
        "03_qty_blows_single_instrument_cap",
        # 5000 * 110 = 550k > 50k single-instrument max
        {"instrument": "SHV-xStock", "side": "buy", "qty": "5000"},
        "MANDATE_VIOLATION",
        "Notional exceeds single-instrument max",
    ),
    (
        "04_negative_qty",
        {"instrument": "SHV-xStock", "side": "buy", "qty": "-5"},
        "VALIDATION_FAILED",
        "Negative quantities are invalid input",
    ),
    (
        "05_zero_qty",
        {"instrument": "SHV-xStock", "side": "buy", "qty": "0"},
        "VALIDATION_FAILED",
        "Zero quantity is meaningless",
    ),
    (
        "06_huge_notional_explicit_price",
        {
            "instrument": "SHV-xStock",
            "side": "buy",
            "qty": "100",
            "expected_price": "10000",
        },
        "MANDATE_VIOLATION",
        "Explicit absurd price blows single-instrument cap",
    ),
    (
        "07_unknown_instrument_kind",
        {"instrument": "SPACEX-PRIVATE-X", "side": "buy", "qty": "1"},
        "MANDATE_VIOLATION",
        "Off-list private instrument cannot be traded",
    ),
    (
        "08_uppercase_side_typo",
        {"instrument": "SHV-xStock", "side": "BUY", "qty": "1"},
        "VALIDATION_FAILED",
        "Side must be lowercase per schema",
    ),
    (
        "09_price_blows_cap_via_fractional_qty",
        {
            "instrument": "SHV-xStock",
            "side": "buy",
            "qty": "999.999",
            "expected_price": "9999",
        },
        "MANDATE_VIOLATION",
        "Fractional qty * inflated price still blows single-instrument cap",
    ),
    (
        "10_extra_long_instrument_string",
        {"instrument": "A" * 500, "side": "buy", "qty": "1"},
        "VALIDATION_FAILED",
        "Instrument string max length enforced by schema",
    ),
]


@pytest.mark.parametrize(
    "case_id,body,expected_code,scenario",
    CORPUS,
    ids=[c[0] for c in CORPUS],
)
async def test_mandate_corpus_rejects(
    app_client,
    auth_header,
    active_mandate,
    session_id,
    db_session,
    case_id,
    body,
    expected_code,
    scenario,
):
    # Special-case: ensure scenario 02 has a buy-only mandate
    if case_id == "02_short_when_short_disallowed":
        active_mandate.permitted_sides = ["buy"]
        await db_session.commit()

    payload = {"session_id": session_id, **body}
    r = await app_client.post(
        "/api/v1/treasury/proposals", headers=auth_header, json=payload
    )
    assert r.status_code in (403, 422), (
        f"[{case_id}] {scenario} — got status {r.status_code} body {r.text}"
    )
    err = r.json().get("error", {})
    assert err.get("code") == expected_code, (
        f"[{case_id}] {scenario} — expected {expected_code}, got {err}"
    )


async def test_mandate_corpus_is_at_least_ten():
    assert len(CORPUS) >= 10


def test_corpus_covers_distinct_violation_types():
    """Diversity check — make sure we cover multiple violation categories."""
    codes_seen = {c[2] for c in CORPUS}
    # Both API-layer validation AND mandate-layer enforcement must be covered
    assert "MANDATE_VIOLATION" in codes_seen
    assert "VALIDATION_FAILED" in codes_seen
