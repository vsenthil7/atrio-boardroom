"""Integration tests for /audit endpoints + ZIP export."""
from __future__ import annotations

import io
import json
import zipfile


async def _create_session_with_event(app_client, auth_header):
    r = await app_client.post(
        "/api/v1/sessions", headers=auth_header, json={"title": "Audit me"}
    )
    sid = r.json()["id"]
    # Closing writes an audit event
    await app_client.post(f"/api/v1/sessions/{sid}/close", headers=auth_header)
    return sid


async def test_audit_session_returns_events(app_client, auth_header):
    sid = await _create_session_with_event(app_client, auth_header)
    r = await app_client.get(f"/api/v1/audit/sessions/{sid}", headers=auth_header)
    assert r.status_code == 200
    rows = r.json()
    assert rows
    kinds = {row["kind"] for row in rows}
    assert "session_closed" in kinds


async def test_audit_session_404_when_no_events(app_client, auth_header):
    r = await app_client.get(
        "/api/v1/audit/sessions/nonexistent", headers=auth_header
    )
    assert r.status_code == 404


async def test_audit_tenant_listing(app_client, auth_header):
    await _create_session_with_event(app_client, auth_header)
    r = await app_client.get("/api/v1/audit/tenant", headers=auth_header)
    assert r.status_code == 200
    assert r.json()


async def test_audit_tenant_filter_by_kind(app_client, auth_header):
    await _create_session_with_event(app_client, auth_header)
    r = await app_client.get(
        "/api/v1/audit/tenant?kind=session_closed", headers=auth_header
    )
    assert r.status_code == 200
    assert all(e["kind"] == "session_closed" for e in r.json())


async def test_audit_export_zip(app_client, auth_header):
    await _create_session_with_event(app_client, auth_header)
    r = await app_client.get("/api/v1/audit/export", headers=auth_header)
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/zip"
    assert "attachment" in r.headers.get("content-disposition", "")
    buf = io.BytesIO(r.content)
    with zipfile.ZipFile(buf) as zf:
        names = set(zf.namelist())
        assert "audit_events.jsonl" in names
        assert "manifest.json" in names
        manifest = json.loads(zf.read("manifest.json"))
        assert manifest["format_version"] == "1.0"
        assert manifest["event_count"] >= 1
        jsonl = zf.read("audit_events.jsonl").decode()
        lines = [line for line in jsonl.splitlines() if line.strip()]
        for line in lines:
            entry = json.loads(line)
            assert "id" in entry
            assert "kind" in entry
            assert "ts" in entry


async def test_audit_endpoints_require_auth(app_client):
    r = await app_client.get("/api/v1/audit/tenant")
    assert r.status_code == 401
    r = await app_client.get("/api/v1/audit/export")
    assert r.status_code == 401
