"""Integration tests for /sessions endpoints."""
from __future__ import annotations


async def test_create_session(app_client, auth_header):
    r = await app_client.post(
        "/api/v1/sessions",
        headers=auth_header,
        json={"title": "Q3 strategy", "language_dominant": "en"},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["title"] == "Q3 strategy"
    assert body["status"] == "active"
    assert body["id"]


async def test_create_session_defaults(app_client, auth_header):
    r = await app_client.post("/api/v1/sessions", headers=auth_header, json={})
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "active"
    assert body["language_dominant"] == "en"


async def test_list_sessions_empty(app_client, auth_header):
    r = await app_client.get("/api/v1/sessions", headers=auth_header)
    assert r.status_code == 200
    assert r.json()["items"] == []


async def test_list_sessions_after_create(app_client, auth_header):
    await app_client.post(
        "/api/v1/sessions", headers=auth_header, json={"title": "S1"}
    )
    await app_client.post(
        "/api/v1/sessions", headers=auth_header, json={"title": "S2"}
    )
    r = await app_client.get("/api/v1/sessions", headers=auth_header)
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) == 2
    titles = {i["title"] for i in items}
    assert titles == {"S1", "S2"}


async def test_get_session_by_id(app_client, auth_header):
    r1 = await app_client.post(
        "/api/v1/sessions", headers=auth_header, json={"title": "X"}
    )
    sid = r1.json()["id"]
    r2 = await app_client.get(f"/api/v1/sessions/{sid}", headers=auth_header)
    assert r2.status_code == 200
    assert r2.json()["id"] == sid


async def test_get_session_not_found(app_client, auth_header):
    r = await app_client.get(
        "/api/v1/sessions/00000000-0000-0000-0000-000000000000",
        headers=auth_header,
    )
    assert r.status_code == 404


async def test_session_endpoints_require_auth(app_client):
    r = await app_client.get("/api/v1/sessions")
    assert r.status_code == 401
    r = await app_client.post("/api/v1/sessions", json={})
    assert r.status_code == 401


async def test_list_session_turns_empty(app_client, auth_header):
    r1 = await app_client.post(
        "/api/v1/sessions", headers=auth_header, json={"title": "X"}
    )
    sid = r1.json()["id"]
    r = await app_client.get(f"/api/v1/sessions/{sid}/turns", headers=auth_header)
    assert r.status_code == 200
    assert r.json()["items"] == []


async def test_close_session(app_client, auth_header):
    r1 = await app_client.post(
        "/api/v1/sessions", headers=auth_header, json={"title": "Close me"}
    )
    sid = r1.json()["id"]
    r2 = await app_client.post(f"/api/v1/sessions/{sid}/close", headers=auth_header)
    assert r2.status_code == 200
    assert r2.json()["status"] == "closed"
    # boardpack_uri populated
    assert r2.json()["boardpack_uri"]


async def test_double_close_idempotent_409(app_client, auth_header):
    r1 = await app_client.post(
        "/api/v1/sessions", headers=auth_header, json={"title": "X"}
    )
    sid = r1.json()["id"]
    await app_client.post(f"/api/v1/sessions/{sid}/close", headers=auth_header)
    r3 = await app_client.post(f"/api/v1/sessions/{sid}/close", headers=auth_header)
    assert r3.status_code == 409
