"""Integration tests for /healthz and /readyz."""
from __future__ import annotations


async def test_healthz_returns_ok(app_client):
    r = await app_client.get("/api/v1/healthz")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "version" in body
    assert "X-Request-ID" in r.headers
    assert "X-ATRIO-Version" in r.headers


async def test_readyz_returns_ok_when_db_reachable(app_client):
    r = await app_client.get("/api/v1/readyz")
    assert r.status_code == 200
    assert r.json()["status"] == "ready"
