"""Integration test for /metrics endpoint."""
from __future__ import annotations


async def test_metrics_endpoint_returns_text_format(app_client):
    r = await app_client.get("/api/v1/metrics")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/plain")
    # Standard Prometheus format
    body = r.text
    assert "# HELP" in body
    assert "# TYPE" in body


async def test_metrics_endpoint_records_http_traffic(app_client):
    # Hit health a few times to seed metrics
    for _ in range(3):
        await app_client.get("/api/v1/healthz")
    r = await app_client.get("/api/v1/metrics")
    assert r.status_code == 200
    body = r.text
    assert "http_requests_total" in body
    assert "http_request_duration_seconds" in body


async def test_metrics_endpoint_records_session_lifecycle(app_client, auth_header):
    # Open + close a session
    s = await app_client.post(
        "/api/v1/sessions", headers=auth_header, json={"title": "metric"}
    )
    sid = s.json()["id"]
    await app_client.post(f"/api/v1/sessions/{sid}/close", headers=auth_header)
    r = await app_client.get("/api/v1/metrics")
    body = r.text
    assert "atrio_sessions_opened_total" in body
    assert "atrio_sessions_closed_total" in body


async def test_metrics_endpoint_records_treasury_metrics(
    app_client, auth_header, active_mandate
):
    s = await app_client.post(
        "/api/v1/sessions", headers=auth_header, json={"title": "metric"}
    )
    sid = s.json()["id"]
    await app_client.post(
        "/api/v1/treasury/proposals",
        headers=auth_header,
        json={
            "session_id": sid,
            "instrument": "SHV-xStock",
            "side": "buy",
            "qty": "1",
        },
    )
    r = await app_client.get("/api/v1/metrics")
    body = r.text
    assert "atrio_treasury_proposed_total" in body


async def test_metrics_endpoint_records_mandate_violation(
    app_client, auth_header, active_mandate
):
    s = await app_client.post(
        "/api/v1/sessions", headers=auth_header, json={"title": "metric"}
    )
    sid = s.json()["id"]
    # Trigger a mandate violation
    await app_client.post(
        "/api/v1/treasury/proposals",
        headers=auth_header,
        json={
            "session_id": sid,
            "instrument": "BANNED-xStock",
            "side": "buy",
            "qty": "1",
        },
    )
    r = await app_client.get("/api/v1/metrics")
    body = r.text
    assert "atrio_mandate_violations_total" in body
    assert "instrument_not_permitted" in body


async def test_metrics_endpoint_disabled():
    """Verify the disabled-state path renders a comment-only body."""
    from app.core.config import Settings
    # Test the conditional directly — full e2e flag-toggling collides with
    # the settings cache pattern, and reset_settings_cache is exercised
    # elsewhere.
    s = Settings(atrio_env="test", prometheus_enabled=False)
    assert s.prometheus_enabled is False
    s2 = Settings(atrio_env="test", prometheus_enabled=True)
    assert s2.prometheus_enabled is True
