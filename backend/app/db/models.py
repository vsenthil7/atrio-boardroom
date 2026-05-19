"""SQLAlchemy ORM models for ATRIO entities.

These mirror the Data Model spec §3–§10. Append-only tables are guarded by
trigger in `migrations/001_initial.py`; the ORM only knows about INSERT-and-
SELECT for those tables, never UPDATE.

We use String UUIDs (stored as TEXT) to keep the schema portable between
Postgres (production) and SQLite (tests). In production the `migrations`
folder upgrades to native UUID columns.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.utcnow()


# ---------------------------------------------------------------------------
# Tenant + access
# ---------------------------------------------------------------------------


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    slug: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    tier: Mapped[str] = mapped_column(String(32), nullable=False, default="founder")
    locale_default: Mapped[str] = mapped_column(String(8), nullable=False, default="en")
    data_residency: Mapped[str] = mapped_column(String(8), nullable=False, default="eu")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    retention_months: Mapped[int] = mapped_column(Integer, nullable=False, default=12)
    contract_start_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_now)
    contract_end_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    kraken_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    kraken_live: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    meta_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_now, onupdate=_now
    )


class User(Base):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("tenant_id", "email", name="uq_user_tenant_email"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False, default="founder")
    idp_subject: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    meta_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_now, onupdate=_now
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


# ---------------------------------------------------------------------------
# Session + turn
# ---------------------------------------------------------------------------


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(36), ForeignKey("tenants.id"), nullable=False)
    created_by_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False, default="boardroom")
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    language_dominant: Mapped[str] = mapped_column(String(8), nullable=False, default="en")
    turn_taking_mode: Mapped[str] = mapped_column(
        String(32), nullable=False, default="round_robin"
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    consensus_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    consensus_kind: Mapped[str | None] = mapped_column(String(16), nullable=True)
    action_list: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    boardpack_uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_now)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    meta_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_now, onupdate=_now
    )

    turns: Mapped[list[Turn]] = relationship(  # type: ignore[name-defined]
        "Turn", back_populates="session", cascade="all, delete-orphan", order_by="Turn.seq_no"
    )


class Turn(Base):
    __tablename__ = "turns"
    __table_args__ = (UniqueConstraint("session_id", "seq_no", name="uq_turn_session_seq"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(36), ForeignKey("tenants.id"), nullable=False)
    session_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False
    )
    seq_no: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    agent_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    language: Mapped[str] = mapped_column(String(8), nullable=False, default="en")
    payload_text: Mapped[str] = mapped_column(Text, nullable=False)
    payload_audio_uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    tokens_in: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tokens_out: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    model_used: Mapped[str | None] = mapped_column(String(128), nullable=True)
    model_was_fallback: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    prompt_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    dissent_round: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cited_evidence: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(3, 2), nullable=True)
    ts: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_now)

    session: Mapped[Session] = relationship("Session", back_populates="turns")


# ---------------------------------------------------------------------------
# Agent memory (pgvector — column type adapts per dialect)
# ---------------------------------------------------------------------------


class AgentMemory(Base):
    __tablename__ = "agent_memories"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(36), ForeignKey("tenants.id"), nullable=False)
    agent_id: Mapped[str] = mapped_column(String(32), nullable=False)
    source_session_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("sessions.id", ondelete="SET NULL"), nullable=True
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # Embedding stored as JSON list[float] for portability between sqlite + pgvector.
    # In production the migration script swaps in pgvector vector(1536).
    embedding: Mapped[list[float]] = mapped_column(JSON, nullable=False, default=list)
    weight: Mapped[Decimal] = mapped_column(Numeric(3, 1), nullable=False, default=Decimal("1.0"))
    ts: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_now)
    last_retrieved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    retrieval_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


# ---------------------------------------------------------------------------
# Documents
# ---------------------------------------------------------------------------


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(36), ForeignKey("tenants.id"), nullable=False)
    session_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False
    )
    uploaded_by_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    byte_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_uri: Mapped[str] = mapped_column(Text, nullable=False)
    extraction_status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    extraction_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    extracted_text_chunks: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_now, onupdate=_now
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


# ---------------------------------------------------------------------------
# Audit log (append-only)
# ---------------------------------------------------------------------------


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(36), ForeignKey("tenants.id"), nullable=False)
    session_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("sessions.id"), nullable=True
    )
    actor_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True
    )
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    request_fingerprint: Mapped[str | None] = mapped_column(String(128), nullable=True)
    ts: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_now)


# ---------------------------------------------------------------------------
# Treasury
# ---------------------------------------------------------------------------


class Mandate(Base):
    __tablename__ = "mandates"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(36), ForeignKey("tenants.id"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    daily_loss_limit: Mapped[Decimal] = mapped_column(Numeric(16, 2), nullable=False)
    single_instrument_max: Mapped[Decimal] = mapped_column(Numeric(16, 2), nullable=False)
    permitted_instruments: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)
    permitted_sides: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)
    auth_user_ids: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="EUR")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    ts: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_now)


class TreasuryAction(Base):
    __tablename__ = "treasury_actions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(36), ForeignKey("tenants.id"), nullable=False)
    session_id: Mapped[str] = mapped_column(String(36), ForeignKey("sessions.id"), nullable=False)
    mandate_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("mandates.id"), nullable=False
    )
    instrument: Mapped[str] = mapped_column(String(64), nullable=False)
    side: Mapped[str] = mapped_column(String(8), nullable=False)
    qty: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    expected_price: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    notional_eur: Mapped[Decimal] = mapped_column(Numeric(16, 2), nullable=False)
    mandate_check_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    state: Mapped[str] = mapped_column(String(32), nullable=False, default="proposed")
    proposed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_now)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    auth1_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    auth1_ts: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    auth2_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    auth2_ts: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    rejected_by_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    rejected_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    kraken_order_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    executed_price: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    executed_qty: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    executed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    proposed_by_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------


class IdempotencyKey(Base):
    __tablename__ = "idempotency_keys"
    __table_args__ = (UniqueConstraint("tenant_id", "key", name="uq_idempotency_tenant_key"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False)
    key: Mapped[str] = mapped_column(String(128), nullable=False)
    method: Mapped[str] = mapped_column(String(8), nullable=False)
    path: Mapped[str] = mapped_column(String(255), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    response_status: Mapped[int] = mapped_column(Integer, nullable=False)
    response_body: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_now)


# ---------------------------------------------------------------------------
# Magic-link sign-in
# ---------------------------------------------------------------------------


class MagicLinkToken(Base):
    __tablename__ = "magic_link_tokens"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_now)


# All-models accessor for tests/migrations.
ALL_MODELS = [
    Tenant,
    User,
    Session,
    Turn,
    AgentMemory,
    Document,
    AuditEvent,
    Mandate,
    TreasuryAction,
    IdempotencyKey,
    MagicLinkToken,
]
