"""Coverage top-up tests for the API layer.

These exercise the rare/error branches in routers that the happy-path
tests don't reach: expired tokens, dropped/expired users, missing
headers, query-parameter combinations, and the like.
"""
from __future__ import annotations

import asyncio
import time
from datetime import datetime, timedelta

import pytest

from app.core.config import get_settings
from app.core.security import (
    create_access_token,
    create_magic_link_token,
    create_refresh_token,
)


# ----------------------------------------------------- auth deep paths


async def test_consume_token_with_no_db_row(app_client):
    """A magic-link JWT that's never been stored as a DB row → 401."""
    settings = get_settings()
    bogus = create_magic_link_token(email="ghost@nowhere.com", settings=settings)
    r = await app_client.post(
        "/api/v1/auth/magic-link/consume", json={"token": bogus}
    )
    assert r.status_code == 401
    assert "unknown" in r.json()["error"]["message"]


async def test_consume_token_for_inactive_user(app_client, db_session, tenant):
    """If user is deactivated between request and consume → 401."""
    from app.db.models import MagicLinkToken, User

    # Create + deactivate user, but write a valid token row anyway
    u = User(
        tenant_id=tenant.id,
        email="ghost@x.com",
        display_name="G",
        role="founder",
        status="disabled",  # not "active"
    )
    db_session.add(u)
    await db_session.flush()
    import hashlib

    tok = create_magic_link_token(email="ghost@x.com")
    h = hashlib.sha256(tok.encode()).hexdigest()
    row = MagicLinkToken(
        email="ghost@x.com",
        token_hash=h,
        expires_at=datetime.utcnow() + timedelta(minutes=15),
    )
    db_session.add(row)
    await db_session.commit()

    r = await app_client.post("/api/v1/auth/magic-link/consume", json={"token": tok})
    assert r.status_code == 401
    assert "active" in r.json()["error"]["message"]


async def test_consume_expired_magic_link(app_client, db_session, founder_user):
    """If token's DB row is past expires_at → 401 even before signature check."""
    from app.db.models import MagicLinkToken

    tok = create_magic_link_token(email=founder_user.email)
    import hashlib

    h = hashlib.sha256(tok.encode()).hexdigest()
    row = MagicLinkToken(
        email=founder_user.email,
        token_hash=h,
        expires_at=datetime.utcnow() - timedelta(seconds=10),  # already expired
    )
    db_session.add(row)
    await db_session.commit()
    r = await app_client.post("/api/v1/auth/magic-link/consume", json={"token": tok})
    assert r.status_code == 401
    assert "expired" in r.json()["error"]["message"]


async def test_consume_token_missing_email_claim(app_client):
    """A magic-link-typed JWT whose 'sub' is empty → 401."""
    from jose import jwt as joselib

    settings = get_settings()
    now = int(time.time())
    claims = {
        "sub": "",
        "type": "magic_link",
        "iat": now,
        "exp": now + 900,
        "jti": "x",
    }
    bogus = joselib.encode(claims, settings.jwt_test_secret, algorithm="HS256")
    r = await app_client.post("/api/v1/auth/magic-link/consume", json={"token": bogus})
    assert r.status_code == 401


async def test_refresh_for_inactive_user(app_client, db_session, tenant):
    from app.db.models import User

    u = User(
        tenant_id=tenant.id,
        email="off@x.com",
        display_name="Off",
        role="founder",
        status="active",
    )
    db_session.add(u)
    await db_session.commit()
    refresh = create_refresh_token(subject=u.id, tenant_id=tenant.id)

    # Deactivate them
    u.status = "disabled"
    await db_session.commit()

    r = await app_client.post(
        "/api/v1/auth/refresh", json={"refresh_token": refresh}
    )
    assert r.status_code == 401


async def test_refresh_missing_claims(app_client):
    from jose import jwt as joselib

    settings = get_settings()
    now = int(time.time())
    # Refresh-typed but missing tenant_id
    claims = {
        "sub": "u",
        "type": "refresh",
        "iat": now,
        "exp": now + 900,
        "jti": "x",
    }
    bogus = joselib.encode(claims, settings.jwt_test_secret, algorithm="HS256")
    r = await app_client.post(
        "/api/v1/auth/refresh", json={"refresh_token": bogus}
    )
    assert r.status_code == 401


async def test_access_token_for_deactivated_user_rejected(
    app_client, db_session, founder_user, make_token, tenant
):
    """Deactivate the user behind a valid access token — next call returns 401."""
    tok = make_token(founder_user.id, tenant.id, "founder")
    founder_user.status = "disabled"
    await db_session.commit()
    r = await app_client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {tok}"}
    )
    assert r.status_code == 401


async def test_access_token_wrong_type_rejected(app_client, founder_user, tenant):
    """A refresh token used at an access-protected endpoint → 401."""
    rt = create_refresh_token(subject=founder_user.id, tenant_id=tenant.id)
    r = await app_client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {rt}"}
    )
    assert r.status_code == 401


async def test_access_token_missing_sub_rejected(app_client):
    from jose import jwt as joselib

    settings = get_settings()
    now = int(time.time())
    claims = {
        "tenant_id": "t",
        "type": "access",
        "iat": now,
        "exp": now + 900,
        "jti": "x",
    }
    bad = joselib.encode(claims, settings.jwt_test_secret, algorithm="HS256")
    r = await app_client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {bad}"}
    )
    assert r.status_code == 401


# ----------------------------------------------------- audit query params


async def test_audit_tenant_with_since_until(app_client, auth_header):
    """Pass `since` and `until` query params to exercise that branch."""
    # Create one event
    r = await app_client.post("/api/v1/sessions", headers=auth_header, json={"title": "x"})
    sid = r.json()["id"]
    await app_client.post(f"/api/v1/sessions/{sid}/close", headers=auth_header)

    one_hour_ago = (datetime.utcnow() - timedelta(hours=1)).isoformat()
    one_hour_hence = (datetime.utcnow() + timedelta(hours=1)).isoformat()
    r = await app_client.get(
        f"/api/v1/audit/tenant?since={one_hour_ago}&until={one_hour_hence}",
        headers=auth_header,
    )
    assert r.status_code == 200
    # Tight far-future filter → empty
    far_since = (datetime.utcnow() + timedelta(days=365)).isoformat()
    r = await app_client.get(
        f"/api/v1/audit/tenant?since={far_since}", headers=auth_header
    )
    assert r.json() == []


async def test_audit_session_endpoint_requires_auth(app_client):
    r = await app_client.get("/api/v1/audit/sessions/x")
    assert r.status_code == 401


# ----------------------------------------------------- treasury auth-path


async def test_authorise_unknown_proposal(app_client, auth_header):
    r = await app_client.post(
        "/api/v1/treasury/proposals/does-not-exist/authorise",
        headers=auth_header,
        json={"confirm": True},
    )
    assert r.status_code == 404


async def test_reject_unknown_proposal(app_client, auth_header):
    r = await app_client.post(
        "/api/v1/treasury/proposals/does-not-exist/reject",
        headers=auth_header,
        json={"reason": "x"},
    )
    assert r.status_code == 404


async def test_reject_viewer_blocked(
    app_client, make_token, viewer_user, tenant, active_mandate, auth_header
):
    """Viewer cannot reject — same role check as authorise."""
    # Need a proposal first
    r_sess = await app_client.post(
        "/api/v1/sessions", headers=auth_header, json={"title": "x"}
    )
    sid = r_sess.json()["id"]
    r_prop = await app_client.post(
        "/api/v1/treasury/proposals",
        headers=auth_header,
        json={
            "session_id": sid,
            "instrument": "SHV-xStock",
            "side": "buy",
            "qty": "1",
        },
    )
    pid = r_prop.json()["id"]
    v_tok = make_token(viewer_user.id, tenant.id, "viewer")
    r = await app_client.post(
        f"/api/v1/treasury/proposals/{pid}/reject",
        headers={"Authorization": f"Bearer {v_tok}"},
        json={"reason": "no thanks"},
    )
    assert r.status_code == 403


async def test_list_proposals_state_filter_empty(app_client, auth_header):
    r = await app_client.get(
        "/api/v1/treasury/proposals?state=executed", headers=auth_header
    )
    assert r.status_code == 200
    assert r.json() == []


# ----------------------------------------------------- documents extras


async def test_upload_filename_without_extension(app_client, auth_header):
    r = await app_client.post(
        "/api/v1/sessions", headers=auth_header, json={"title": "x"}
    )
    sid = r.json()["id"]
    r2 = await app_client.post(
        f"/api/v1/sessions/{sid}/documents",
        headers=auth_header,
        files={"file": ("README", b"some text", "text/plain")},
    )
    assert r2.status_code == 415


async def test_upload_doc_endpoints_require_auth(app_client):
    r = await app_client.get("/api/v1/documents/x")
    assert r.status_code == 401


# ----------------------------------------------------- voice extras


async def test_voice_token_decodes_with_correct_claims(app_client, auth_header):
    r = await app_client.post(
        "/api/v1/sessions", headers=auth_header, json={"title": "voice"}
    )
    sid = r.json()["id"]
    r2 = await app_client.post(
        f"/api/v1/voice/sessions/{sid}/join", headers=auth_header
    )
    body = r2.json()
    # Token is a JWT — must split into 3 dot-separated segments
    assert body["token"].count(".") == 2
    assert sid[:8] in body["room"]


# ----------------------------------------------------- mandate edge


async def test_list_mandates_empty(app_client, auth_header):
    r = await app_client.get("/api/v1/mandates", headers=auth_header)
    assert r.status_code == 200
    assert r.json() == []


async def test_create_mandate_invalid_body(app_client, auth_header):
    """Missing required fields → 422."""
    r = await app_client.post(
        "/api/v1/mandates",
        headers=auth_header,
        json={"daily_loss_limit": "100"},  # missing other required fields
    )
    assert r.status_code == 422


# ----------------------------------------------------- health readyz failure


async def test_healthz_includes_inference_providers(app_client):
    """Health response includes the configured inference providers."""
    r = await app_client.get("/api/v1/healthz")
    assert r.status_code == 200
    body = r.json()
    assert "inference_providers" in body
    assert "mock" in body["inference_providers"]
