"""Audit service — write-only append log.

Wraps `audit_events` INSERT with structlog emission. Callers do
`await audit.write(...)`; they never read. Reads go through a separate
`AuditReader` service that enforces tenant scope.

Sprint-2: append-only is enforced at the DB layer via a trigger created in
the migration that rejects UPDATE and DELETE on audit_events. The application
layer here only ever INSERTs.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.models import AuditEvent

log = get_logger(__name__)


class AuditService:
    """Write side of the audit log."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def write(
        self,
        *,
        tenant_id: str,
        kind: str,
        payload: dict[str, Any],
        session_id: str | None = None,
        actor_user_id: str | None = None,
        request_fingerprint: str | None = None,
    ) -> AuditEvent:
        # Sanitise payload — must be JSON serialisable.
        safe = self._sanitise(payload)
        fp = request_fingerprint or self._fingerprint(kind, safe)
        event = AuditEvent(
            tenant_id=tenant_id,
            session_id=session_id,
            actor_user_id=actor_user_id,
            kind=kind,
            payload_json=safe,
            request_fingerprint=fp,
        )
        self._session.add(event)
        await self._session.flush()
        log.info(
            "audit_write",
            kind=kind,
            tenant_id=tenant_id,
            session_id=session_id,
            actor_user_id=actor_user_id,
            event_id=event.id,
        )
        return event

    @staticmethod
    def _sanitise(payload: dict[str, Any]) -> dict[str, Any]:
        try:
            # Round-trip through default=str so non-JSON values become strings.
            return json.loads(json.dumps(payload, default=str))
        except (TypeError, ValueError):
            return {"_serialisation_error": True, "repr": repr(payload)[:1024]}

    @staticmethod
    def _fingerprint(kind: str, payload: dict[str, Any]) -> str:
        blob = json.dumps({"kind": kind, "payload": payload}, sort_keys=True, default=str)
        return hashlib.sha256(blob.encode()).hexdigest()


class AuditReader:
    """Tenant-scoped read API for the audit log (used by export)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_for_session(
        self, *, tenant_id: str, session_id: str, limit: int = 1000
    ) -> list[AuditEvent]:
        stmt = (
            select(AuditEvent)
            .where(AuditEvent.tenant_id == tenant_id, AuditEvent.session_id == session_id)
            .order_by(AuditEvent.ts.asc())
            .limit(limit)
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return list(rows)

    async def list_for_tenant(
        self,
        *,
        tenant_id: str,
        since: datetime | None = None,
        until: datetime | None = None,
        kinds: list[str] | None = None,
        limit: int = 1000,
    ) -> list[AuditEvent]:
        stmt = select(AuditEvent).where(AuditEvent.tenant_id == tenant_id)
        if since:
            stmt = stmt.where(AuditEvent.ts >= since)
        if until:
            stmt = stmt.where(AuditEvent.ts <= until)
        if kinds:
            stmt = stmt.where(AuditEvent.kind.in_(kinds))
        stmt = stmt.order_by(AuditEvent.ts.asc()).limit(limit)
        rows = (await self._session.execute(stmt)).scalars().all()
        return list(rows)
