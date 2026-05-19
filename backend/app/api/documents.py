"""Documents router.

POST /sessions/{session_id}/documents  (multipart)  → DocumentPublic
GET  /sessions/{session_id}/documents
GET  /documents/{id}
"""
from __future__ import annotations

import hashlib

from fastapi import APIRouter, File, Form, UploadFile, status
from sqlalchemy import select

from app.api.deps import CurrentUserDep, DbSession
from app.api.schemas import DocumentPublic
from app.audit.service import AuditService
from app.core.config import get_settings
from app.core.errors import (
    NotFoundError,
    UnsupportedMediaType,
    UploadTooLarge,
    ValidationFailed,
)
from app.db.models import Document, Session as SessionRow
from app.documents.service import DocumentService

router = APIRouter(tags=["documents"])

_KIND_BY_EXT = {
    ".pdf": "pdf",
    ".docx": "docx",
    ".xlsx": "xlsx",
    ".png": "png",
    ".jpg": "image",
    ".jpeg": "image",
}


@router.post(
    "/sessions/{session_id}/documents",
    response_model=DocumentPublic,
    status_code=status.HTTP_201_CREATED,
)
async def upload_document(
    session_id: str,
    user: CurrentUserDep,
    db: DbSession,
    file: UploadFile = File(...),
    description: str = Form(""),
) -> DocumentPublic:
    settings = get_settings()
    # Session ownership check
    sess = (
        await db.execute(
            select(SessionRow).where(
                SessionRow.id == session_id, SessionRow.tenant_id == user.tenant_id
            )
        )
    ).scalar_one_or_none()
    if sess is None:
        raise NotFoundError("session not found", details={"session_id": session_id})

    filename = file.filename or "upload.bin"
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    kind = _KIND_BY_EXT.get(ext)
    if kind is None:
        raise UnsupportedMediaType(
            f"unsupported extension: {ext}",
            details={"allowed": list(_KIND_BY_EXT.keys())},
        )

    raw = await file.read()
    if len(raw) == 0:
        raise ValidationFailed("upload is empty", details={"filename": filename})
    if len(raw) > settings.max_document_bytes:
        raise UploadTooLarge(
            f"file exceeds {settings.max_document_bytes} bytes",
            details={"size": len(raw)},
        )

    # Count existing docs
    existing = (
        await db.execute(
            select(Document).where(
                Document.tenant_id == user.tenant_id, Document.session_id == session_id
            )
        )
    ).scalars().all()
    if len(existing) >= settings.max_documents_per_session:
        raise ValidationFailed(
            "session has reached max documents",
            details={"limit": settings.max_documents_per_session},
        )

    sha = hashlib.sha256(raw).hexdigest()
    # Mock storage URI — production wires S3
    storage_uri = f"local://{user.tenant_id}/{session_id}/{sha}/{filename}"

    doc = Document(
        tenant_id=user.tenant_id,
        session_id=session_id,
        uploaded_by_user_id=user.user_id,
        kind=kind,
        filename=filename,
        byte_size=len(raw),
        sha256=sha,
        storage_uri=storage_uri,
        extraction_status="pending",
    )
    db.add(doc)
    await db.flush()

    # Inline extraction (we're not running background workers for the hackathon)
    svc = DocumentService()
    try:
        extracted = svc.extract(kind=kind, content=raw, filename=filename)
        doc.extraction_status = "complete"
        doc.summary = extracted.summary
        doc.extracted_text_chunks = extracted.chunks
    except Exception as e:
        doc.extraction_status = "failed"
        doc.extraction_error = str(e)[:500]

    await db.flush()
    await AuditService(db).write(
        tenant_id=user.tenant_id,
        session_id=session_id,
        actor_user_id=user.user_id,
        kind="document_uploaded",
        payload={
            "document_id": doc.id,
            "filename": filename,
            "kind": kind,
            "sha256": sha,
            "byte_size": len(raw),
            "extraction_status": doc.extraction_status,
        },
    )

    return DocumentPublic(
        id=doc.id,
        session_id=doc.session_id,
        filename=doc.filename,
        byte_size=doc.byte_size,
        sha256=doc.sha256,
        kind=doc.kind,
        extraction_status=doc.extraction_status,
        summary=doc.summary,
    )


@router.get(
    "/sessions/{session_id}/documents",
    response_model=list[DocumentPublic],
)
async def list_documents(
    session_id: str, user: CurrentUserDep, db: DbSession
) -> list[DocumentPublic]:
    sess = (
        await db.execute(
            select(SessionRow).where(
                SessionRow.id == session_id, SessionRow.tenant_id == user.tenant_id
            )
        )
    ).scalar_one_or_none()
    if sess is None:
        raise NotFoundError("session not found", details={"session_id": session_id})
    rows = (
        await db.execute(
            select(Document)
            .where(Document.tenant_id == user.tenant_id, Document.session_id == session_id)
            .order_by(Document.created_at.asc())
        )
    ).scalars().all()
    return [
        DocumentPublic(
            id=d.id,
            session_id=d.session_id,
            filename=d.filename,
            byte_size=d.byte_size,
            sha256=d.sha256,
            kind=d.kind,
            extraction_status=d.extraction_status,
            summary=d.summary,
        )
        for d in rows
    ]


@router.get("/documents/{document_id}", response_model=DocumentPublic)
async def get_document(
    document_id: str, user: CurrentUserDep, db: DbSession
) -> DocumentPublic:
    row = (
        await db.execute(
            select(Document).where(
                Document.id == document_id, Document.tenant_id == user.tenant_id
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise NotFoundError("document not found", details={"document_id": document_id})
    return DocumentPublic(
        id=row.id,
        session_id=row.session_id,
        filename=row.filename,
        byte_size=row.byte_size,
        sha256=row.sha256,
        kind=row.kind,
        extraction_status=row.extraction_status,
        summary=row.summary,
    )
