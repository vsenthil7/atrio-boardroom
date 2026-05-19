"""Integration tests for /voice and /sessions/{id}/boardpack.pdf."""
from __future__ import annotations


async def test_voice_join_returns_token(app_client, auth_header):
    r = await app_client.post(
        "/api/v1/sessions", headers=auth_header, json={"title": "Voice"}
    )
    sid = r.json()["id"]
    r2 = await app_client.post(
        f"/api/v1/voice/sessions/{sid}/join", headers=auth_header
    )
    assert r2.status_code == 200
    body = r2.json()
    assert body["token"]
    assert body["room"].startswith("atrio-")
    assert body["identity"]
    assert body["livekit_url"]


async def test_voice_join_session_not_found(app_client, auth_header):
    r = await app_client.post(
        "/api/v1/voice/sessions/nope/join", headers=auth_header
    )
    assert r.status_code == 404


async def test_voice_join_requires_auth(app_client):
    r = await app_client.post("/api/v1/voice/sessions/x/join")
    assert r.status_code == 401


async def test_boardpack_download(app_client, auth_header):
    r = await app_client.post(
        "/api/v1/sessions", headers=auth_header, json={"title": "Pack me"}
    )
    sid = r.json()["id"]
    r2 = await app_client.get(
        f"/api/v1/sessions/{sid}/boardpack.pdf", headers=auth_header
    )
    assert r2.status_code == 200
    assert r2.headers["content-type"] == "application/pdf"
    assert r2.content.startswith(b"%PDF-")
    assert "attachment" in r2.headers["content-disposition"]


async def test_boardpack_session_not_found(app_client, auth_header):
    r = await app_client.get(
        "/api/v1/sessions/nope/boardpack.pdf", headers=auth_header
    )
    assert r.status_code == 404


async def test_boardpack_requires_auth(app_client):
    r = await app_client.get("/api/v1/sessions/x/boardpack.pdf")
    assert r.status_code == 401


async def test_voice_config_returns_supported_languages(app_client, auth_header):
    r = await app_client.get("/api/v1/voice/config", headers=auth_header)
    assert r.status_code == 200
    body = r.json()
    assert "supported_languages" in body
    assert "en" in body["supported_languages"]
    assert "es" in body["supported_languages"]
    assert body["default_language"] == "en"
    assert body["custom_dictionary_size"] >= 1


async def test_voice_config_requires_auth(app_client):
    r = await app_client.get("/api/v1/voice/config")
    assert r.status_code == 401
