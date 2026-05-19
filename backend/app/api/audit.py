"""Audit router — read-only export.

GET  /audit/sessions/{session_id}
GET  /audit/export                  → ZIP of JSONL + boardpack
"""
from __future__ import annotations

import io
import json
import zipfile
from datetime import datetime

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from app.api.deps import CurrentUserDep, DbSession
from app.api.schemas import AuditEventPublic
from app.audit.service import AuditReader
from app.core.errors import NotFoundError

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("/sessions/{session_id}", response_model=list[AuditEventPublic])
async def list_audit_for_session(
    session_id: str, user: CurrentUserDep, db: DbSession
) -> list[AuditEventPublic]:
    reader = AuditReader(db)
    events = await reader.list_for_session(
        tenant_id=user.tenant_id, session_id=session_id
    )
    if not events:
        raise NotFoundError(
            "no audit events for this session",
            details={"session_id": session_id},
        )
    return [
        AuditEventPublic(
            id=e.id,
            tenant_id=e.tenant_id,
            session_id=e.session_id,
            actor_user_id=e.actor_user_id,
            kind=e.kind,
            payload_json=e.payload_json,
            ts=e.ts,
        )
        for e in events
    ]


@router.get("/tenant", response_model=list[AuditEventPublic])
async def list_audit_for_tenant(
    user: CurrentUserDep,
    db: DbSession,
    since: datetime | None = Query(default=None),
    until: datetime | None = Query(default=None),
    kind: str | None = Query(default=None),
) -> list[AuditEventPublic]:
    reader = AuditReader(db)
    events = await reader.list_for_tenant(
        tenant_id=user.tenant_id,
        since=since,
        until=until,
        kinds=[kind] if kind else None,
    )
    return [
        AuditEventPublic(
            id=e.id,
            tenant_id=e.tenant_id,
            session_id=e.session_id,
            actor_user_id=e.actor_user_id,
            kind=e.kind,
            payload_json=e.payload_json,
            ts=e.ts,
        )
        for e in events
    ]


@router.get("/export")
async def export_zip(user: CurrentUserDep, db: DbSession) -> StreamingResponse:
    """Build an in-memory ZIP containing audit events JSONL + tenant summary."""
    reader = AuditReader(db)
    events = await reader.list_for_tenant(tenant_id=user.tenant_id, limit=100_000)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        jsonl = "\n".join(
            json.dumps(
                {
                    "id": e.id,
                    "tenant_id": e.tenant_id,
                    "session_id": e.session_id,
                    "actor_user_id": e.actor_user_id,
                    "kind": e.kind,
                    "payload": e.payload_json,
                    "ts": e.ts.isoformat(),
                },
                default=str,
            )
            for e in events
        )
        zf.writestr("audit_events.jsonl", jsonl)
        zf.writestr(
            "manifest.json",
            json.dumps(
                {
                    "tenant_id": user.tenant_id,
                    "exported_at": datetime.utcnow().isoformat(),
                    "event_count": len(events),
                    "format_version": "1.0",
                }
            ),
        )
    buf.seek(0)
    fname = f"atrio-audit-{user.tenant_id}-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}.zip"
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )
