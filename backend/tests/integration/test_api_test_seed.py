"""Tests for the test-only seed endpoint."""
from __future__ import annotations


async def test_seed_demo_creates_tenant_and_users(app_client):
    r = await app_client.post("/api/v1/_test/seed-demo")
    assert r.status_code == 200
    body = r.json()
    assert body["founder_email"] == "founder@acme.co"
    assert body["second_email"] == "ceo@acme.co"
    assert body["tenant_id"]


async def test_seed_demo_is_idempotent(app_client):
    r1 = await app_client.post("/api/v1/_test/seed-demo")
    r2 = await app_client.post("/api/v1/_test/seed-demo")
    assert r1.status_code == 200
    assert r2.status_code == 200
    # Different tenant id each call (because wipe creates a new row)
    assert r1.json()["tenant_id"] != r2.json()["tenant_id"]


async def test_seed_endpoint_enables_signin_flow(app_client):
    """After seeding, the magic-link flow should work end-to-end."""
    seed = (await app_client.post("/api/v1/_test/seed-demo")).json()
    email = seed["founder_email"]
    r1 = await app_client.post("/api/v1/auth/magic-link", json={"email": email})
    assert r1.status_code == 202
    dev_token = r1.json()["dev_token"]
    r2 = await app_client.post(
        "/api/v1/auth/magic-link/consume", json={"token": dev_token}
    )
    assert r2.status_code == 200
    access = r2.json()["access_token"]
    r3 = await app_client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {access}"}
    )
    assert r3.status_code == 200
    assert r3.json()["email"] == email
