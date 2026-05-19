"""End-to-end demo flow.

This is the script we will run for the judges in Milan. Each step is exactly
what the operator will do, and each step is asserted. If any of these
break, the demo breaks.

Flow:
  1. Sign in via magic link
  2. Create a boardroom session
  3. Upload a PDF document
  4. Submit a user turn (consume the full SSE stream)
  5. Verify turns were persisted
  6. Propose a treasury action
  7. First authorise (founder)
  8. Second authorise (different user) → execution
  9. Close the session
 10. Download the boardpack PDF
 11. Export the audit ZIP and inspect contents
"""
from __future__ import annotations

import io
import json
import zipfile

from PIL import Image  # noqa: F401  (kept for future image-tests)
from reportlab.pdfgen import canvas


def _pdf_bytes(text: str) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    c.drawString(72, 800, text)
    c.showPage()
    c.save()
    return buf.getvalue()


def _parse_sse(body: str):
    out = []
    for block in body.split("\n\n"):
        if not block.strip():
            continue
        event = None
        data = None
        for line in block.splitlines():
            if line.startswith("event:"):
                event = line.split(":", 1)[1].strip()
            elif line.startswith("data:"):
                data = line.split(":", 1)[1].strip()
        if event and data:
            try:
                out.append((event, json.loads(data)))
            except json.JSONDecodeError:
                out.append((event, {"raw": data}))
    return out


async def test_full_demo_flow(
    app_client, founder_user, second_authoriser, active_mandate
):
    # ------------------------------------------------------- 1. magic link
    r = await app_client.post(
        "/api/v1/auth/magic-link", json={"email": founder_user.email}
    )
    assert r.status_code == 202
    token = r.json()["dev_token"]
    r = await app_client.post(
        "/api/v1/auth/magic-link/consume", json={"token": token}
    )
    assert r.status_code == 200
    founder_access = r.json()["access_token"]
    founder_hdr = {"Authorization": f"Bearer {founder_access}"}

    # ------------------------------------------------------- 2. create session
    r = await app_client.post(
        "/api/v1/sessions",
        headers=founder_hdr,
        json={"title": "Hire 4 engineers?", "language_dominant": "en"},
    )
    assert r.status_code == 201
    sid = r.json()["id"]

    # ------------------------------------------------------- 3. upload doc
    r = await app_client.post(
        f"/api/v1/sessions/{sid}/documents",
        headers=founder_hdr,
        files={
            "file": (
                "plan.pdf",
                _pdf_bytes("Q3 hiring plan: 4 senior engineers, EUR 60k/mo."),
                "application/pdf",
            )
        },
    )
    assert r.status_code == 201
    assert r.json()["extraction_status"] == "complete"

    # ------------------------------------------------------- 4. user turn (SSE)
    r = await app_client.post(
        f"/api/v1/sessions/{sid}/turns",
        headers=founder_hdr,
        json={
            "text": "Should we hire 4 senior engineers in Q3?",
            "language": "en",
            "mode": "debate",
        },
    )
    assert r.status_code == 200
    events = _parse_sse(r.text)
    kinds = [k for k, _ in events]
    assert "turn_started" in kinds
    assert "agent_done" in kinds
    assert "consensus" in kinds
    assert kinds[-1] == "stream_complete"
    # The mocked stance is "support" for every specialist
    consensus_event = [d for k, d in events if k == "consensus"][0]
    assert consensus_event["kind"] in {"unanimous", "majority", "split"}

    # ------------------------------------------------------- 5. turns persisted
    r = await app_client.get(f"/api/v1/sessions/{sid}/turns", headers=founder_hdr)
    items = r.json()["items"]
    # 1 user + at least 5 specialists
    assert len(items) >= 6
    seq_nos = [t["seq_no"] for t in items]
    assert seq_nos == sorted(seq_nos)  # in order
    assert seq_nos[0] == 1

    # ------------------------------------------------------- 6. propose
    r = await app_client.post(
        "/api/v1/treasury/proposals",
        headers=founder_hdr,
        json={
            "session_id": sid,
            "instrument": "SHV-xStock",
            "side": "buy",
            "qty": "10",
        },
    )
    assert r.status_code == 201
    proposal = r.json()
    assert proposal["state"] == "proposed"
    assert proposal["mandate_check"]["overall_pass"] is True
    pid = proposal["id"]

    # ------------------------------------------------------- 7. first authorise
    r = await app_client.post(
        f"/api/v1/treasury/proposals/{pid}/authorise",
        headers=founder_hdr,
        json={"confirm": True},
    )
    assert r.status_code == 200
    assert r.json()["state"] == "first_authorised"

    # 7b. Same user attempts second authorise → must FAIL
    r = await app_client.post(
        f"/api/v1/treasury/proposals/{pid}/authorise",
        headers=founder_hdr,
        json={"confirm": True},
    )
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "TWO_PARTY_REQUIRED"

    # ------------------------------------------------------- 8. second user authorises
    # Sign in as the second authoriser
    r = await app_client.post(
        "/api/v1/auth/magic-link", json={"email": second_authoriser.email}
    )
    second_token = r.json()["dev_token"]
    r = await app_client.post(
        "/api/v1/auth/magic-link/consume", json={"token": second_token}
    )
    second_access = r.json()["access_token"]
    second_hdr = {"Authorization": f"Bearer {second_access}"}

    r = await app_client.post(
        f"/api/v1/treasury/proposals/{pid}/authorise",
        headers=second_hdr,
        json={"confirm": True},
    )
    assert r.status_code == 200
    executed = r.json()
    assert executed["state"] == "executed"
    assert executed["kraken_order_id"]
    assert executed["executed_price"]
    from decimal import Decimal as _D
    assert _D(executed["executed_qty"]) == _D("10")

    # ------------------------------------------------------- 9. close session
    r = await app_client.post(f"/api/v1/sessions/{sid}/close", headers=founder_hdr)
    assert r.status_code == 200
    closed = r.json()
    assert closed["status"] == "closed"
    assert closed["boardpack_uri"]
    assert closed["ended_at"]

    # ------------------------------------------------------- 10. boardpack PDF
    r = await app_client.get(
        f"/api/v1/sessions/{sid}/boardpack.pdf", headers=founder_hdr
    )
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content.startswith(b"%PDF-")
    assert len(r.content) > 2000

    # ------------------------------------------------------- 11. audit ZIP
    r = await app_client.get("/api/v1/audit/export", headers=founder_hdr)
    assert r.status_code == 200
    with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
        names = zf.namelist()
        assert "audit_events.jsonl" in names
        assert "manifest.json" in names
        manifest = json.loads(zf.read("manifest.json"))
        # We should have at minimum:
        # - magic_link_issued + signed_in (×2 users)
        # - session creation isn't audited, but session_closed is
        # - document_uploaded
        # - treasury proposal authorised/executed (multiple events)
        assert manifest["event_count"] >= 5
        events_text = zf.read("audit_events.jsonl").decode()
        # Look for the key kinds
        for required in (
            "auth_signed_in",
            "session_closed",
            "document_uploaded",
            "treasury_first_authorised",
            "treasury_executed",
        ):
            assert required in events_text, f"missing audit kind {required}"


async def test_full_demo_flow_fallback_to_text_mode(
    app_client, founder_user, active_mandate
):
    """Same as above but uses single-agent mode for a faster path.

    Useful for the demo's 'quick read' moment that shows the same machinery
    works without the full debate roster.
    """
    # Sign in
    r = await app_client.post(
        "/api/v1/auth/magic-link", json={"email": founder_user.email}
    )
    token = r.json()["dev_token"]
    r = await app_client.post(
        "/api/v1/auth/magic-link/consume", json={"token": token}
    )
    hdr = {"Authorization": f"Bearer {r.json()['access_token']}"}
    # Create session + post single-agent turn
    sid = (
        await app_client.post(
            "/api/v1/sessions", headers=hdr, json={"title": "Quick"}
        )
    ).json()["id"]
    r = await app_client.post(
        f"/api/v1/sessions/{sid}/turns",
        headers=hdr,
        json={"text": "Quick read please", "language": "en", "mode": "single"},
    )
    assert r.status_code == 200
    events = _parse_sse(r.text)
    # Only one agent_done in single mode
    done = [d for k, d in events if k == "agent_done"]
    assert len(done) == 1
