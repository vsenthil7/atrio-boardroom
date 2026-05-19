"""Integration tests for /mandates endpoints."""
from __future__ import annotations


async def test_active_mandate_returns_404_when_none(app_client, auth_header):
    r = await app_client.get("/api/v1/mandates/active", headers=auth_header)
    assert r.status_code == 404


async def test_active_mandate_returns_existing(app_client, auth_header, active_mandate):
    r = await app_client.get("/api/v1/mandates/active", headers=auth_header)
    assert r.status_code == 200
    body = r.json()
    assert body["version"] == 1
    assert body["is_active"] is True


async def test_create_mandate_bumps_version(app_client, auth_header, active_mandate, founder_user):
    r = await app_client.post(
        "/api/v1/mandates",
        headers=auth_header,
        json={
            "daily_loss_limit": "30000",
            "single_instrument_max": "60000",
            "permitted_instruments": ["SHV-xStock"],
            "permitted_sides": ["buy"],
            "auth_user_ids": [founder_user.id],
            "currency": "EUR",
        },
    )
    assert r.status_code == 201
    assert r.json()["version"] == 2
    assert r.json()["is_active"] is True

    # Old one is deactivated
    r2 = await app_client.get("/api/v1/mandates", headers=auth_header)
    versions = {(m["version"], m["is_active"]) for m in r2.json()}
    assert (1, False) in versions
    assert (2, True) in versions


async def test_create_mandate_first_time(app_client, auth_header, founder_user):
    r = await app_client.post(
        "/api/v1/mandates",
        headers=auth_header,
        json={
            "daily_loss_limit": "10000",
            "single_instrument_max": "20000",
            "permitted_instruments": ["SHV-xStock"],
            "permitted_sides": ["buy", "sell"],
            "auth_user_ids": [founder_user.id],
            "currency": "EUR",
        },
    )
    assert r.status_code == 201
    assert r.json()["version"] == 1


async def test_create_mandate_blocked_for_viewer(
    app_client, make_token, viewer_user, tenant, founder_user
):
    viewer_tok = make_token(viewer_user.id, tenant.id, "viewer")
    r = await app_client.post(
        "/api/v1/mandates",
        headers={"Authorization": f"Bearer {viewer_tok}"},
        json={
            "daily_loss_limit": "10000",
            "single_instrument_max": "20000",
            "permitted_instruments": ["X"],
            "permitted_sides": ["buy"],
            "auth_user_ids": [founder_user.id],
            "currency": "EUR",
        },
    )
    assert r.status_code == 403


async def test_list_mandates(app_client, auth_header, active_mandate):
    r = await app_client.get("/api/v1/mandates", headers=auth_header)
    assert r.status_code == 200
    assert len(r.json()) == 1


async def test_mandate_requires_auth(app_client):
    r = await app_client.get("/api/v1/mandates/active")
    assert r.status_code == 401
