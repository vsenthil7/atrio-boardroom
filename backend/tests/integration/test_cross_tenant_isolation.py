"""Cross-tenant isolation — the MOST IMPORTANT security test.

Each test in this file verifies that a token issued for Tenant A cannot read,
modify, or list any resource owned by Tenant B. This is the app-layer
enforcement of the same rule that Postgres RLS enforces in production.
"""
from __future__ import annotations

import io

import pytest_asyncio
from PIL import Image
from reportlab.pdfgen import canvas


@pytest_asyncio.fixture
async def tenant_b_user(db_session, second_tenant):
    """A second user in a totally different tenant."""
    from app.db.models import User

    u = User(
        tenant_id=second_tenant.id,
        email="founder@otherco.com",
        display_name="Other Founder",
        role="founder",
    )
    db_session.add(u)
    await db_session.commit()
    await db_session.refresh(u)
    return u


@pytest_asyncio.fixture
async def tenant_b_mandate(db_session, second_tenant, tenant_b_user):
    """An active mandate in Tenant B with different rules."""
    from decimal import Decimal

    from app.db.models import Mandate

    m = Mandate(
        tenant_id=second_tenant.id,
        version=1,
        daily_loss_limit=Decimal("100000.00"),
        single_instrument_max=Decimal("100000.00"),
        permitted_instruments=["BTC-USD"],
        permitted_sides=["buy"],
        auth_user_ids=[tenant_b_user.id],
        currency="USD",
        is_active=True,
    )
    db_session.add(m)
    await db_session.commit()
    await db_session.refresh(m)
    return m


@pytest_asyncio.fixture
def b_header(make_token, tenant_b_user, second_tenant):
    tok = make_token(tenant_b_user.id, second_tenant.id, "founder")
    return {"Authorization": f"Bearer {tok}"}


# ----------------------------------------------------- sessions


async def test_tenant_cannot_see_other_tenants_sessions(
    app_client, auth_header, b_header
):
    # Tenant A creates a session
    r_a = await app_client.post(
        "/api/v1/sessions", headers=auth_header, json={"title": "A-secret"}
    )
    a_session_id = r_a.json()["id"]

    # Tenant B's list must NOT include it
    r_b = await app_client.get("/api/v1/sessions", headers=b_header)
    assert r_b.status_code == 200
    b_ids = {item["id"] for item in r_b.json()["items"]}
    assert a_session_id not in b_ids


async def test_tenant_cannot_get_other_tenants_session_by_id(
    app_client, auth_header, b_header
):
    r_a = await app_client.post(
        "/api/v1/sessions", headers=auth_header, json={"title": "A"}
    )
    a_id = r_a.json()["id"]
    r_b = await app_client.get(f"/api/v1/sessions/{a_id}", headers=b_header)
    assert r_b.status_code == 404  # not 403 — pretend it doesn't exist


async def test_tenant_cannot_close_other_tenants_session(
    app_client, auth_header, b_header
):
    r_a = await app_client.post(
        "/api/v1/sessions", headers=auth_header, json={"title": "A"}
    )
    a_id = r_a.json()["id"]
    r_b = await app_client.post(f"/api/v1/sessions/{a_id}/close", headers=b_header)
    assert r_b.status_code == 404


async def test_tenant_cannot_post_turn_to_other_tenants_session(
    app_client, auth_header, b_header
):
    r_a = await app_client.post(
        "/api/v1/sessions", headers=auth_header, json={"title": "A"}
    )
    a_id = r_a.json()["id"]
    r_b = await app_client.post(
        f"/api/v1/sessions/{a_id}/turns", headers=b_header, json={"text": "hi"}
    )
    assert r_b.status_code == 404


async def test_tenant_cannot_list_other_tenants_session_turns(
    app_client, auth_header, b_header
):
    r_a = await app_client.post(
        "/api/v1/sessions", headers=auth_header, json={"title": "A"}
    )
    a_id = r_a.json()["id"]
    r_b = await app_client.get(f"/api/v1/sessions/{a_id}/turns", headers=b_header)
    assert r_b.status_code == 404


# ----------------------------------------------------- documents


async def test_tenant_cannot_upload_to_other_tenants_session(
    app_client, auth_header, b_header
):
    r_a = await app_client.post(
        "/api/v1/sessions", headers=auth_header, json={"title": "A"}
    )
    a_id = r_a.json()["id"]
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    c.drawString(72, 800, "secret")
    c.showPage()
    c.save()
    r_b = await app_client.post(
        f"/api/v1/sessions/{a_id}/documents",
        headers=b_header,
        files={"file": ("x.pdf", buf.getvalue(), "application/pdf")},
    )
    assert r_b.status_code == 404


async def test_tenant_cannot_list_other_tenants_documents(
    app_client, auth_header, b_header
):
    r_a = await app_client.post(
        "/api/v1/sessions", headers=auth_header, json={"title": "A"}
    )
    a_id = r_a.json()["id"]
    r_b = await app_client.get(
        f"/api/v1/sessions/{a_id}/documents", headers=b_header
    )
    assert r_b.status_code == 404


async def test_tenant_cannot_get_other_tenants_document(
    app_client, auth_header, b_header
):
    # Tenant A uploads a doc
    r_a = await app_client.post(
        "/api/v1/sessions", headers=auth_header, json={"title": "A"}
    )
    a_id = r_a.json()["id"]
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    c.drawString(72, 800, "secret")
    c.showPage()
    c.save()
    r_doc = await app_client.post(
        f"/api/v1/sessions/{a_id}/documents",
        headers=auth_header,
        files={"file": ("a.pdf", buf.getvalue(), "application/pdf")},
    )
    doc_id = r_doc.json()["id"]
    r_b = await app_client.get(f"/api/v1/documents/{doc_id}", headers=b_header)
    assert r_b.status_code == 404


# ----------------------------------------------------- treasury


async def test_tenant_cannot_propose_against_other_tenants_session(
    app_client, auth_header, b_header, active_mandate, tenant_b_mandate
):
    r_a = await app_client.post(
        "/api/v1/sessions", headers=auth_header, json={"title": "A"}
    )
    a_id = r_a.json()["id"]
    r_b = await app_client.post(
        "/api/v1/treasury/proposals",
        headers=b_header,
        json={
            "session_id": a_id,  # B uses A's session
            "instrument": "BTC-USD",
            "side": "buy",
            "qty": "1",
        },
    )
    assert r_b.status_code == 404


async def test_tenant_cannot_see_other_tenants_proposals(
    app_client, auth_header, b_header, active_mandate, tenant_b_mandate
):
    # A creates a proposal
    r_sess = await app_client.post(
        "/api/v1/sessions", headers=auth_header, json={"title": "A"}
    )
    sid = r_sess.json()["id"]
    r_a = await app_client.post(
        "/api/v1/treasury/proposals",
        headers=auth_header,
        json={
            "session_id": sid,
            "instrument": "SHV-xStock",
            "side": "buy",
            "qty": "1",
        },
    )
    a_pid = r_a.json()["id"]

    # B lists — should be empty (B has no proposals)
    r_b_list = await app_client.get("/api/v1/treasury/proposals", headers=b_header)
    assert r_b_list.status_code == 200
    b_pids = [p["id"] for p in r_b_list.json()]
    assert a_pid not in b_pids

    # B tries to GET A's proposal — 404
    r_b_get = await app_client.get(
        f"/api/v1/treasury/proposals/{a_pid}", headers=b_header
    )
    assert r_b_get.status_code == 404


async def test_tenant_cannot_authorise_other_tenants_proposal(
    app_client, auth_header, b_header, active_mandate, tenant_b_mandate
):
    r_sess = await app_client.post(
        "/api/v1/sessions", headers=auth_header, json={"title": "A"}
    )
    sid = r_sess.json()["id"]
    r_a = await app_client.post(
        "/api/v1/treasury/proposals",
        headers=auth_header,
        json={
            "session_id": sid,
            "instrument": "SHV-xStock",
            "side": "buy",
            "qty": "1",
        },
    )
    a_pid = r_a.json()["id"]
    r_b = await app_client.post(
        f"/api/v1/treasury/proposals/{a_pid}/authorise",
        headers=b_header,
        json={"confirm": True},
    )
    assert r_b.status_code == 404


# ----------------------------------------------------- mandates


async def test_tenant_cannot_see_other_tenants_mandate(
    app_client, b_header, active_mandate, tenant_b_mandate
):
    # B's active mandate is in USD with BTC-USD. A's is EUR with SHV-xStock.
    r = await app_client.get("/api/v1/mandates/active", headers=b_header)
    assert r.status_code == 200
    body = r.json()
    assert body["currency"] == "USD"
    assert "BTC-USD" in body["permitted_instruments"]
    assert "SHV-xStock" not in body["permitted_instruments"]


async def test_tenant_b_list_mandates_only_shows_own(
    app_client, b_header, active_mandate, tenant_b_mandate
):
    r = await app_client.get("/api/v1/mandates", headers=b_header)
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 1
    assert rows[0]["currency"] == "USD"


# ----------------------------------------------------- audit


async def test_tenant_cannot_see_other_tenants_audit(
    app_client, auth_header, b_header
):
    # A creates + closes a session → audit events
    r = await app_client.post(
        "/api/v1/sessions", headers=auth_header, json={"title": "A"}
    )
    sid = r.json()["id"]
    await app_client.post(f"/api/v1/sessions/{sid}/close", headers=auth_header)

    # B's audit tenant feed must not include any event from A's session
    r_b = await app_client.get("/api/v1/audit/tenant", headers=b_header)
    assert r_b.status_code == 200
    for e in r_b.json():
        assert e["session_id"] != sid


async def test_tenant_cannot_export_other_tenants_audit(
    app_client, auth_header, b_header
):
    """B's audit export ZIP contains only B's events (so 0 for our fixtures)."""
    import io
    import json
    import zipfile

    r = await app_client.post(
        "/api/v1/sessions", headers=auth_header, json={"title": "A"}
    )
    sid = r.json()["id"]
    await app_client.post(f"/api/v1/sessions/{sid}/close", headers=auth_header)

    r_b = await app_client.get("/api/v1/audit/export", headers=b_header)
    assert r_b.status_code == 200
    with zipfile.ZipFile(io.BytesIO(r_b.content)) as zf:
        jsonl = zf.read("audit_events.jsonl").decode()
        for line in jsonl.splitlines():
            if line.strip():
                entry = json.loads(line)
                # No events from A
                assert entry["session_id"] != sid


# ----------------------------------------------------- voice + boardpack


async def test_tenant_cannot_join_other_tenants_voice(
    app_client, auth_header, b_header
):
    r = await app_client.post(
        "/api/v1/sessions", headers=auth_header, json={"title": "A"}
    )
    sid = r.json()["id"]
    r_b = await app_client.post(
        f"/api/v1/voice/sessions/{sid}/join", headers=b_header
    )
    assert r_b.status_code == 404


async def test_tenant_cannot_download_other_tenants_boardpack(
    app_client, auth_header, b_header
):
    r = await app_client.post(
        "/api/v1/sessions", headers=auth_header, json={"title": "A"}
    )
    sid = r.json()["id"]
    r_b = await app_client.get(
        f"/api/v1/sessions/{sid}/boardpack.pdf", headers=b_header
    )
    assert r_b.status_code == 404
