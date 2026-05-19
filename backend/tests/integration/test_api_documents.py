"""Integration tests for the /documents and session-scoped upload endpoints."""
from __future__ import annotations

import io

import pytest_asyncio
from PIL import Image
from reportlab.pdfgen import canvas


def _make_pdf(text: str = "Hello PDF") -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    c.drawString(72, 800, text)
    c.showPage()
    c.save()
    return buf.getvalue()


def _make_png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), "red").save(buf, format="PNG")
    return buf.getvalue()


@pytest_asyncio.fixture
async def open_session(app_client, auth_header):
    r = await app_client.post(
        "/api/v1/sessions", headers=auth_header, json={"title": "Doc session"}
    )
    return r.json()["id"]


async def test_upload_pdf_succeeds(app_client, auth_header, open_session):
    pdf = _make_pdf("ATRIO board")
    r = await app_client.post(
        f"/api/v1/sessions/{open_session}/documents",
        headers=auth_header,
        files={"file": ("plan.pdf", pdf, "application/pdf")},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["filename"] == "plan.pdf"
    assert body["kind"] == "pdf"
    assert body["extraction_status"] == "complete"
    assert "ATRIO" in (body["summary"] or "")


async def test_upload_png_succeeds(app_client, auth_header, open_session):
    r = await app_client.post(
        f"/api/v1/sessions/{open_session}/documents",
        headers=auth_header,
        files={"file": ("logo.png", _make_png(), "image/png")},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["kind"] == "png"


async def test_upload_unsupported_type_returns_415(
    app_client, auth_header, open_session
):
    r = await app_client.post(
        f"/api/v1/sessions/{open_session}/documents",
        headers=auth_header,
        files={"file": ("evil.exe", b"MZ\x00\x00", "application/octet-stream")},
    )
    assert r.status_code == 415


async def test_upload_empty_file_returns_422(app_client, auth_header, open_session):
    r = await app_client.post(
        f"/api/v1/sessions/{open_session}/documents",
        headers=auth_header,
        files={"file": ("empty.pdf", b"", "application/pdf")},
    )
    assert r.status_code == 422


async def test_upload_too_large_returns_413(
    app_client, auth_header, open_session, monkeypatch
):
    from app.core.config import get_settings

    s = get_settings()
    too_big = b"x" * (s.max_document_bytes + 100)
    r = await app_client.post(
        f"/api/v1/sessions/{open_session}/documents",
        headers=auth_header,
        files={"file": ("big.pdf", too_big, "application/pdf")},
    )
    assert r.status_code == 413


async def test_upload_session_not_found(app_client, auth_header):
    r = await app_client.post(
        "/api/v1/sessions/nope/documents",
        headers=auth_header,
        files={"file": ("a.pdf", _make_pdf(), "application/pdf")},
    )
    assert r.status_code == 404


async def test_list_documents_after_upload(app_client, auth_header, open_session):
    await app_client.post(
        f"/api/v1/sessions/{open_session}/documents",
        headers=auth_header,
        files={"file": ("a.pdf", _make_pdf(), "application/pdf")},
    )
    await app_client.post(
        f"/api/v1/sessions/{open_session}/documents",
        headers=auth_header,
        files={"file": ("b.pdf", _make_pdf("two"), "application/pdf")},
    )
    r = await app_client.get(
        f"/api/v1/sessions/{open_session}/documents", headers=auth_header
    )
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 2
    assert {i["filename"] for i in items} == {"a.pdf", "b.pdf"}


async def test_get_document_by_id(app_client, auth_header, open_session):
    r1 = await app_client.post(
        f"/api/v1/sessions/{open_session}/documents",
        headers=auth_header,
        files={"file": ("x.pdf", _make_pdf(), "application/pdf")},
    )
    did = r1.json()["id"]
    r2 = await app_client.get(f"/api/v1/documents/{did}", headers=auth_header)
    assert r2.status_code == 200
    assert r2.json()["id"] == did


async def test_get_document_not_found(app_client, auth_header):
    r = await app_client.get("/api/v1/documents/nonexistent", headers=auth_header)
    assert r.status_code == 404


async def test_upload_requires_auth(app_client, open_session):
    r = await app_client.post(
        f"/api/v1/sessions/{open_session}/documents",
        files={"file": ("x.pdf", _make_pdf(), "application/pdf")},
    )
    assert r.status_code == 401


async def test_max_documents_per_session(app_client, auth_header, open_session):
    from app.core.config import get_settings

    s = get_settings()
    # Upload up to the limit
    for i in range(s.max_documents_per_session):
        r = await app_client.post(
            f"/api/v1/sessions/{open_session}/documents",
            headers=auth_header,
            files={"file": (f"f{i}.pdf", _make_pdf(f"file {i}"), "application/pdf")},
        )
        assert r.status_code == 201
    # One more — must fail
    r = await app_client.post(
        f"/api/v1/sessions/{open_session}/documents",
        headers=auth_header,
        files={"file": ("toomany.pdf", _make_pdf(), "application/pdf")},
    )
    assert r.status_code == 422


async def test_upload_invalid_pdf_completes_with_failed_status(
    app_client, auth_header, open_session
):
    """Invalid PDF bytes shouldn't 500 — extraction_status should be 'failed'."""
    r = await app_client.post(
        f"/api/v1/sessions/{open_session}/documents",
        headers=auth_header,
        files={"file": ("bad.pdf", b"definitely not a pdf", "application/pdf")},
    )
    assert r.status_code == 201
    assert r.json()["extraction_status"] == "failed"
