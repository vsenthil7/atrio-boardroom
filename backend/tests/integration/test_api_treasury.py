"""Integration tests for /treasury endpoints.

Covers: propose happy path, mandate violation 403, two-party gate,
expiry, reject, viewer-blocked, list & get.
"""
from __future__ import annotations

import pytest_asyncio


@pytest_asyncio.fixture
async def open_session(app_client, auth_header):
    r = await app_client.post(
        "/api/v1/sessions", headers=auth_header, json={"title": "Trade session"}
    )
    return r.json()["id"]


async def test_propose_happy_path(app_client, auth_header, active_mandate, open_session):
    r = await app_client.post(
        "/api/v1/treasury/proposals",
        headers=auth_header,
        json={
            "session_id": open_session,
            "instrument": "SHV-xStock",
            "side": "buy",
            "qty": "10",
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["state"] == "proposed"
    assert body["instrument"] == "SHV-xStock"
    assert body["mandate_check"]["overall_pass"] is True


async def test_propose_violates_mandate_returns_403(
    app_client, auth_header, active_mandate, open_session
):
    r = await app_client.post(
        "/api/v1/treasury/proposals",
        headers=auth_header,
        json={
            "session_id": open_session,
            "instrument": "BANNED-xStock",
            "side": "buy",
            "qty": "1",
        },
    )
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "MANDATE_VIOLATION"


async def test_propose_session_not_found(app_client, auth_header, active_mandate):
    r = await app_client.post(
        "/api/v1/treasury/proposals",
        headers=auth_header,
        json={
            "session_id": "nonexistent",
            "instrument": "SHV-xStock",
            "side": "buy",
            "qty": "1",
        },
    )
    assert r.status_code == 404


async def test_authorise_single_party_returns_403_two_party_required(
    app_client, auth_header, active_mandate, open_session
):
    # First propose
    r1 = await app_client.post(
        "/api/v1/treasury/proposals",
        headers=auth_header,
        json={
            "session_id": open_session,
            "instrument": "SHV-xStock",
            "side": "buy",
            "qty": "1",
        },
    )
    pid = r1.json()["id"]
    # First authorise — same user is fine
    r2 = await app_client.post(
        f"/api/v1/treasury/proposals/{pid}/authorise",
        headers=auth_header,
        json={"confirm": True},
    )
    assert r2.status_code == 200
    assert r2.json()["state"] == "first_authorised"
    # Same user attempts second authorise — must fail TWO_PARTY_REQUIRED
    r3 = await app_client.post(
        f"/api/v1/treasury/proposals/{pid}/authorise",
        headers=auth_header,
        json={"confirm": True},
    )
    assert r3.status_code == 403
    assert r3.json()["error"]["code"] == "TWO_PARTY_REQUIRED"


async def test_two_party_authorise_executes(
    app_client, auth_header, second_auth_header, active_mandate, open_session
):
    r1 = await app_client.post(
        "/api/v1/treasury/proposals",
        headers=auth_header,
        json={
            "session_id": open_session,
            "instrument": "SHV-xStock",
            "side": "buy",
            "qty": "1",
        },
    )
    pid = r1.json()["id"]
    await app_client.post(
        f"/api/v1/treasury/proposals/{pid}/authorise",
        headers=auth_header,
        json={"confirm": True},
    )
    r2 = await app_client.post(
        f"/api/v1/treasury/proposals/{pid}/authorise",
        headers=second_auth_header,
        json={"confirm": True},
    )
    assert r2.status_code == 200
    body = r2.json()
    assert body["state"] == "executed"
    assert body["kraken_order_id"] is not None
    assert body["executed_price"] is not None


async def test_authorise_without_confirm_returns_403(
    app_client, auth_header, active_mandate, open_session
):
    r1 = await app_client.post(
        "/api/v1/treasury/proposals",
        headers=auth_header,
        json={
            "session_id": open_session,
            "instrument": "SHV-xStock",
            "side": "buy",
            "qty": "1",
        },
    )
    pid = r1.json()["id"]
    r2 = await app_client.post(
        f"/api/v1/treasury/proposals/{pid}/authorise",
        headers=auth_header,
        json={"confirm": False},
    )
    assert r2.status_code == 403


async def test_viewer_cannot_authorise(
    app_client, make_token, viewer_user, tenant, active_mandate, open_session, auth_header
):
    r1 = await app_client.post(
        "/api/v1/treasury/proposals",
        headers=auth_header,
        json={
            "session_id": open_session,
            "instrument": "SHV-xStock",
            "side": "buy",
            "qty": "1",
        },
    )
    pid = r1.json()["id"]
    viewer_token = make_token(viewer_user.id, tenant.id, "viewer")
    r2 = await app_client.post(
        f"/api/v1/treasury/proposals/{pid}/authorise",
        headers={"Authorization": f"Bearer {viewer_token}"},
        json={"confirm": True},
    )
    assert r2.status_code == 403


async def test_reject_proposal(
    app_client, auth_header, active_mandate, open_session
):
    r1 = await app_client.post(
        "/api/v1/treasury/proposals",
        headers=auth_header,
        json={
            "session_id": open_session,
            "instrument": "SHV-xStock",
            "side": "buy",
            "qty": "1",
        },
    )
    pid = r1.json()["id"]
    r2 = await app_client.post(
        f"/api/v1/treasury/proposals/{pid}/reject",
        headers=auth_header,
        json={"reason": "changed mind"},
    )
    assert r2.status_code == 200
    assert r2.json()["state"] == "rejected"


async def test_list_proposals_filters_by_state(
    app_client, auth_header, active_mandate, open_session
):
    # Two proposals
    for _ in range(2):
        await app_client.post(
            "/api/v1/treasury/proposals",
            headers=auth_header,
            json={
                "session_id": open_session,
                "instrument": "SHV-xStock",
                "side": "buy",
                "qty": "1",
            },
        )
    r = await app_client.get("/api/v1/treasury/proposals", headers=auth_header)
    assert r.status_code == 200
    assert len(r.json()) == 2
    r2 = await app_client.get(
        "/api/v1/treasury/proposals?state=proposed", headers=auth_header
    )
    assert len(r2.json()) == 2


async def test_get_proposal(app_client, auth_header, active_mandate, open_session):
    r1 = await app_client.post(
        "/api/v1/treasury/proposals",
        headers=auth_header,
        json={
            "session_id": open_session,
            "instrument": "SHV-xStock",
            "side": "buy",
            "qty": "1",
        },
    )
    pid = r1.json()["id"]
    r2 = await app_client.get(
        f"/api/v1/treasury/proposals/{pid}", headers=auth_header
    )
    assert r2.status_code == 200
    assert r2.json()["id"] == pid


async def test_get_proposal_not_found(app_client, auth_header):
    r = await app_client.get(
        "/api/v1/treasury/proposals/nonexistent", headers=auth_header
    )
    assert r.status_code == 404


async def test_propose_invalid_side_validation(
    app_client, auth_header, active_mandate, open_session
):
    r = await app_client.post(
        "/api/v1/treasury/proposals",
        headers=auth_header,
        json={
            "session_id": open_session,
            "instrument": "SHV-xStock",
            "side": "hold",  # invalid
            "qty": "1",
        },
    )
    assert r.status_code in (422, 403)
