"""Unit tests for AuditService + AuditReader."""
from __future__ import annotations

from app.audit.service import AuditReader, AuditService


async def test_write_event_persists(db_session, tenant, founder_user):
    svc = AuditService(db_session)
    e = await svc.write(
        tenant_id=tenant.id,
        actor_user_id=founder_user.id,
        kind="thing_happened",
        payload={"a": 1, "b": "two"},
    )
    assert e.id
    assert e.kind == "thing_happened"
    assert e.tenant_id == tenant.id
    assert e.payload_json["a"] == 1
    assert e.request_fingerprint is not None  # auto-fingerprint


async def test_write_with_session_and_explicit_fingerprint(db_session, tenant, founder_user):
    svc = AuditService(db_session)
    e = await svc.write(
        tenant_id=tenant.id,
        session_id=None,
        actor_user_id=founder_user.id,
        kind="x",
        payload={"a": 1},
        request_fingerprint="fp-explicit",
    )
    assert e.request_fingerprint == "fp-explicit"


async def test_write_non_serialisable_payload_is_handled(db_session, tenant):
    """Custom objects are stringified rather than rejected."""

    class NotJSON:
        def __repr__(self) -> str:
            return "<NotJSON instance>"

    svc = AuditService(db_session)
    e = await svc.write(
        tenant_id=tenant.id,
        kind="oops",
        payload={"obj": NotJSON()},
    )
    # Round-tripped via default=str → the value is now a string repr.
    assert isinstance(e.payload_json["obj"], str)
    assert "NotJSON" in e.payload_json["obj"]


async def test_audit_reader_list_for_session(db_session, tenant, founder_user):
    svc = AuditService(db_session)
    # Create a session row first
    from app.db.models import Session as SessionRow

    sess = SessionRow(
        tenant_id=tenant.id, created_by_user_id=founder_user.id, kind="boardroom"
    )
    db_session.add(sess)
    await db_session.flush()
    for i in range(3):
        await svc.write(
            tenant_id=tenant.id, session_id=sess.id, kind=f"k{i}", payload={"i": i}
        )
    rows = await AuditReader(db_session).list_for_session(
        tenant_id=tenant.id, session_id=sess.id
    )
    assert len(rows) == 3
    assert [r.kind for r in rows] == ["k0", "k1", "k2"]


async def test_audit_reader_list_for_tenant_filters(db_session, tenant):
    svc = AuditService(db_session)
    await svc.write(tenant_id=tenant.id, kind="foo", payload={})
    await svc.write(tenant_id=tenant.id, kind="bar", payload={})
    await svc.write(tenant_id=tenant.id, kind="baz", payload={})

    all_rows = await AuditReader(db_session).list_for_tenant(tenant_id=tenant.id)
    assert len(all_rows) == 3
    only_bar = await AuditReader(db_session).list_for_tenant(
        tenant_id=tenant.id, kinds=["bar"]
    )
    assert [r.kind for r in only_bar] == ["bar"]


async def test_audit_reader_tenant_scoping(db_session, tenant, second_tenant):
    svc = AuditService(db_session)
    await svc.write(tenant_id=tenant.id, kind="t1", payload={})
    await svc.write(tenant_id=second_tenant.id, kind="t2", payload={})
    rows = await AuditReader(db_session).list_for_tenant(tenant_id=tenant.id)
    assert all(r.tenant_id == tenant.id for r in rows)
    assert len(rows) == 1


async def test_audit_reader_time_window(db_session, tenant):
    from datetime import datetime, timedelta

    svc = AuditService(db_session)
    await svc.write(tenant_id=tenant.id, kind="k", payload={})
    far_future = datetime.utcnow() + timedelta(days=30)
    rows = await AuditReader(db_session).list_for_tenant(
        tenant_id=tenant.id, since=far_future
    )
    assert rows == []
