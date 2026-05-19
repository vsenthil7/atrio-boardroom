"""initial schema

Creates all 11 tables. On Postgres it also installs:
  - pgvector extension + vector(64) column upgrade for agent_memories
  - append-only triggers on audit_events and treasury_actions
  - row-level security policies on every tenant-scoped table
  - IVFFlat index on agent_memories.embedding

On SQLite (tests) we skip the Postgres-only bits — the ORM models work as-is.

Revision ID: 0001_initial
Revises:
Create Date: 2026-05-18 12:45:00
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# ---------------------------------------------------------------------------
# Dialect helpers
# ---------------------------------------------------------------------------


def _is_postgres() -> bool:
    bind = op.get_bind()
    return bind.dialect.name == "postgresql"


def _json_type() -> sa.types.TypeEngine:
    return postgresql.JSONB(astext_type=sa.Text()) if _is_postgres() else sa.JSON()


# ---------------------------------------------------------------------------
# Upgrade
# ---------------------------------------------------------------------------


def upgrade() -> None:
    if _is_postgres():
        op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # -- tenants
    op.create_table(
        "tenants",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("slug", sa.String(64), nullable=False, unique=True),
        sa.Column("tier", sa.String(32), nullable=False, server_default="founder"),
        sa.Column("locale_default", sa.String(8), nullable=False, server_default="en"),
        sa.Column("data_residency", sa.String(8), nullable=False, server_default="eu"),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("retention_months", sa.Integer(), nullable=False, server_default="12"),
        sa.Column("contract_start_at", sa.DateTime(), nullable=False),
        sa.Column("contract_end_at", sa.DateTime(), nullable=True),
        sa.Column("kraken_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("kraken_live", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("meta_json", _json_type(), nullable=False, server_default=sa.text("'{}'::jsonb" if _is_postgres() else "'{}'")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )

    # -- users
    op.create_table(
        "users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("role", sa.String(32), nullable=False, server_default="founder"),
        sa.Column("idp_subject", sa.String(255), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("last_login_at", sa.DateTime(), nullable=True),
        sa.Column("meta_json", _json_type(), nullable=False, server_default=sa.text("'{}'::jsonb" if _is_postgres() else "'{}'")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("tenant_id", "email", name="uq_user_tenant_email"),
    )
    op.create_index("idx_users_tenant", "users", ["tenant_id"])

    # -- sessions
    op.create_table(
        "sessions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("created_by_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False, server_default="boardroom"),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("language_dominant", sa.String(8), nullable=False, server_default="en"),
        sa.Column("turn_taking_mode", sa.String(32), nullable=False, server_default="round_robin"),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("consensus_text", sa.Text(), nullable=True),
        sa.Column("consensus_kind", sa.String(16), nullable=True),
        sa.Column("action_list", _json_type(), nullable=True),
        sa.Column("boardpack_uri", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("ended_at", sa.DateTime(), nullable=True),
        sa.Column("meta_json", _json_type(), nullable=False, server_default=sa.text("'{}'::jsonb" if _is_postgres() else "'{}'")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("idx_sessions_tenant_started", "sessions", ["tenant_id", "started_at"])

    # -- turns
    op.create_table(
        "turns",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("session_id", sa.String(36), sa.ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("seq_no", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("agent_id", sa.String(32), nullable=True),
        sa.Column("language", sa.String(8), nullable=False, server_default="en"),
        sa.Column("payload_text", sa.Text(), nullable=False),
        sa.Column("payload_audio_uri", sa.Text(), nullable=True),
        sa.Column("tokens_in", sa.Integer(), nullable=True),
        sa.Column("tokens_out", sa.Integer(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("model_used", sa.String(128), nullable=True),
        sa.Column("model_was_fallback", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("prompt_version", sa.String(32), nullable=True),
        sa.Column("dissent_round", sa.Integer(), nullable=True),
        sa.Column("cited_evidence", _json_type(), nullable=True),
        sa.Column("confidence", sa.Numeric(3, 2), nullable=True),
        sa.Column("ts", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("session_id", "seq_no", name="uq_turn_session_seq"),
    )
    op.create_index("idx_turns_session_seq", "turns", ["session_id", "seq_no"])

    # -- agent_memories
    op.create_table(
        "agent_memories",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("agent_id", sa.String(32), nullable=False),
        sa.Column("source_session_id", sa.String(36), sa.ForeignKey("sessions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("embedding", _json_type(), nullable=False),  # vector(...) added below on PG
        sa.Column("weight", sa.Numeric(3, 1), nullable=False, server_default="1.0"),
        sa.Column("ts", sa.DateTime(), nullable=False),
        sa.Column("last_retrieved_at", sa.DateTime(), nullable=True),
        sa.Column("retrieval_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
    )
    op.create_index("idx_memory_tenant_agent", "agent_memories", ["tenant_id", "agent_id"])

    # -- documents
    op.create_table(
        "documents",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("session_id", sa.String(36), sa.ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("uploaded_by_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("byte_size", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("storage_uri", sa.Text(), nullable=False),
        sa.Column("extraction_status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("extraction_error", sa.Text(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("extracted_text_chunks", _json_type(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
    )
    op.create_index("idx_documents_session", "documents", ["session_id"])

    # -- audit_events
    op.create_table(
        "audit_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("session_id", sa.String(36), sa.ForeignKey("sessions.id"), nullable=True),
        sa.Column("actor_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("kind", sa.String(64), nullable=False),
        sa.Column("payload_json", _json_type(), nullable=False),
        sa.Column("request_fingerprint", sa.String(128), nullable=True),
        sa.Column("ts", sa.DateTime(), nullable=False),
    )
    op.create_index("idx_audit_tenant_ts", "audit_events", ["tenant_id", "ts"])
    op.create_index("idx_audit_session_kind", "audit_events", ["session_id", "kind"])

    # -- mandates
    op.create_table(
        "mandates",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("daily_loss_limit", sa.Numeric(16, 2), nullable=False),
        sa.Column("single_instrument_max", sa.Numeric(16, 2), nullable=False),
        sa.Column("permitted_instruments", _json_type(), nullable=False),
        sa.Column("permitted_sides", _json_type(), nullable=False),
        sa.Column("auth_user_ids", _json_type(), nullable=False),
        sa.Column("currency", sa.String(8), nullable=False, server_default="EUR"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("ts", sa.DateTime(), nullable=False),
    )
    op.create_index("idx_mandate_tenant_active", "mandates", ["tenant_id", "is_active"])

    # -- treasury_actions
    op.create_table(
        "treasury_actions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("session_id", sa.String(36), sa.ForeignKey("sessions.id"), nullable=False),
        sa.Column("mandate_id", sa.String(36), sa.ForeignKey("mandates.id"), nullable=False),
        sa.Column("instrument", sa.String(64), nullable=False),
        sa.Column("side", sa.String(8), nullable=False),
        sa.Column("qty", sa.Numeric(20, 8), nullable=False),
        sa.Column("expected_price", sa.Numeric(20, 8), nullable=True),
        sa.Column("notional_eur", sa.Numeric(16, 2), nullable=False),
        sa.Column("mandate_check_json", _json_type(), nullable=False),
        sa.Column("state", sa.String(32), nullable=False, server_default="proposed"),
        sa.Column("proposed_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("auth1_user_id", sa.String(36), nullable=True),
        sa.Column("auth1_ts", sa.DateTime(), nullable=True),
        sa.Column("auth2_user_id", sa.String(36), nullable=True),
        sa.Column("auth2_ts", sa.DateTime(), nullable=True),
        sa.Column("rejected_by_user_id", sa.String(36), nullable=True),
        sa.Column("rejected_reason", sa.Text(), nullable=True),
        sa.Column("rejected_at", sa.DateTime(), nullable=True),
        sa.Column("kraken_order_id", sa.String(64), nullable=True),
        sa.Column("executed_price", sa.Numeric(20, 8), nullable=True),
        sa.Column("executed_qty", sa.Numeric(20, 8), nullable=True),
        sa.Column("executed_at", sa.DateTime(), nullable=True),
        sa.Column("proposed_by_user_id", sa.String(36), nullable=True),
    )
    op.create_index("idx_treasury_tenant_state", "treasury_actions", ["tenant_id", "state"])

    # -- idempotency_keys
    op.create_table(
        "idempotency_keys",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("key", sa.String(128), nullable=False),
        sa.Column("method", sa.String(8), nullable=False),
        sa.Column("path", sa.String(255), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("response_status", sa.Integer(), nullable=False),
        sa.Column("response_body", _json_type(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("tenant_id", "key", name="uq_idempotency_tenant_key"),
    )

    # -- magic_link_tokens
    op.create_table(
        "magic_link_tokens",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("token_hash", sa.String(128), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("consumed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )

    # -----------------------------------------------------------------
    # Postgres-only: append-only triggers + RLS + pgvector vector column
    # -----------------------------------------------------------------
    if _is_postgres():
        # Append-only triggers
        op.execute(
            """
            CREATE OR REPLACE FUNCTION atrio_reject_update_delete()
            RETURNS trigger AS $$
            BEGIN
                RAISE EXCEPTION 'append-only table — UPDATE/DELETE forbidden';
            END;
            $$ LANGUAGE plpgsql;
            """
        )
        for tbl in ("audit_events", "treasury_actions"):
            op.execute(
                f"""
                CREATE TRIGGER trg_{tbl}_append_only
                BEFORE UPDATE OR DELETE ON {tbl}
                FOR EACH ROW EXECUTE FUNCTION atrio_reject_update_delete();
                """
            )

        # Postgres treasury_actions is special: state transitions DO need
        # to be permitted. We allow UPDATE on treasury_actions for the
        # workflow but forbid DELETE. Drop the UPDATE trigger and add DELETE-
        # only trigger instead.
        op.execute("DROP TRIGGER trg_treasury_actions_append_only ON treasury_actions")
        op.execute(
            """
            CREATE TRIGGER trg_treasury_actions_no_delete
            BEFORE DELETE ON treasury_actions
            FOR EACH ROW EXECUTE FUNCTION atrio_reject_update_delete();
            """
        )

        # Row-level security on tenant-scoped tables
        tenant_tables = [
            "users", "sessions", "turns", "agent_memories", "documents",
            "audit_events", "mandates", "treasury_actions", "idempotency_keys",
        ]
        for tbl in tenant_tables:
            op.execute(f"ALTER TABLE {tbl} ENABLE ROW LEVEL SECURITY")
            op.execute(
                f"""
                CREATE POLICY tenant_isolation_{tbl} ON {tbl}
                USING (tenant_id = current_setting('atrio.current_tenant_id', true))
                WITH CHECK (tenant_id = current_setting('atrio.current_tenant_id', true));
                """
            )

        # Upgrade embedding column to vector(64) — matches MemoryService.EMBEDDING_DIMS
        op.execute("ALTER TABLE agent_memories ALTER COLUMN embedding TYPE vector(64) USING embedding::text::vector")
        op.execute(
            "CREATE INDEX idx_agent_memories_embedding ON agent_memories "
            "USING ivfflat (embedding vector_cosine_ops) WITH (lists = 64)"
        )


# ---------------------------------------------------------------------------
# Downgrade
# ---------------------------------------------------------------------------


def downgrade() -> None:
    if _is_postgres():
        for tbl in ("users", "sessions", "turns", "agent_memories", "documents",
                    "audit_events", "mandates", "treasury_actions", "idempotency_keys"):
            op.execute(f"DROP POLICY IF EXISTS tenant_isolation_{tbl} ON {tbl}")
            op.execute(f"ALTER TABLE {tbl} DISABLE ROW LEVEL SECURITY")
        op.execute("DROP TRIGGER IF EXISTS trg_audit_events_append_only ON audit_events")
        op.execute("DROP TRIGGER IF EXISTS trg_treasury_actions_no_delete ON treasury_actions")
        op.execute("DROP FUNCTION IF EXISTS atrio_reject_update_delete()")
        op.execute("DROP INDEX IF EXISTS idx_agent_memories_embedding")

    op.drop_table("magic_link_tokens")
    op.drop_table("idempotency_keys")
    op.drop_table("treasury_actions")
    op.drop_table("mandates")
    op.drop_table("audit_events")
    op.drop_table("documents")
    op.drop_table("agent_memories")
    op.drop_table("turns")
    op.drop_table("sessions")
    op.drop_table("users")
    op.drop_table("tenants")
