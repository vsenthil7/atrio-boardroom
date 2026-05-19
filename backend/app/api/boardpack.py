"""Boardpack router — generate + download the per-session PDF."""
from __future__ import annotations

import io

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from app.api.deps import CurrentUserDep, DbSession
from app.core.errors import NotFoundError
from app.db.models import Session as SessionRow
from app.services.export import BoardpackExporter

router = APIRouter(tags=["boardpack"])


@router.get("/sessions/{session_id}/boardpack.pdf")
async def download_boardpack(
    session_id: str, user: CurrentUserDep, db: DbSession
) -> StreamingResponse:
    sess = (
        await db.execute(
            select(SessionRow).where(
                SessionRow.id == session_id, SessionRow.tenant_id == user.tenant_id
            )
        )
    ).scalar_one_or_none()
    if sess is None:
        raise NotFoundError("session not found", details={"session_id": session_id})

    exporter = BoardpackExporter(db)
    pdf_bytes = await exporter.build_for_session(tenant_id=user.tenant_id, session=sess)
    buf = io.BytesIO(pdf_bytes)
    fname = f"atrio-boardpack-{session_id}.pdf"
    return StreamingResponse(
        buf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )
