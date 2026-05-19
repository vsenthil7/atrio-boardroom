"""Pydantic schemas for API request/response shapes.

These mirror the API Spec section 5–13 exactly. Internal models are SQLAlchemy
rows; these are the wire format.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, EmailStr, Field


# --------------------------------------------------------------------------- auth


class MagicLinkRequest(BaseModel):
    email: EmailStr


class MagicLinkConsume(BaseModel):
    token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int


class RefreshRequest(BaseModel):
    refresh_token: str


class UserPublic(BaseModel):
    id: str
    email: str
    display_name: str
    role: str
    tenant_id: str


# --------------------------------------------------------------------------- sessions


class SessionCreate(BaseModel):
    title: str | None = None
    language_dominant: str = "en"
    turn_taking_mode: Literal["round_robin", "dissent_driven", "expert_first"] = "round_robin"


class SessionPublic(BaseModel):
    id: str
    tenant_id: str
    title: str | None
    language_dominant: str
    turn_taking_mode: str
    status: str
    consensus_text: str | None
    consensus_kind: str | None
    boardpack_uri: str | None
    started_at: datetime
    ended_at: datetime | None


class SessionList(BaseModel):
    items: list[SessionPublic]
    next_cursor: str | None = None


# --------------------------------------------------------------------------- turns


class TurnCreate(BaseModel):
    text: str = Field(min_length=1, max_length=10_000)
    language: str = "en"
    audio_uri: str | None = None
    mode: Literal["single", "debate"] = "debate"


class TurnPublic(BaseModel):
    id: str
    seq_no: int
    role: str
    agent_id: str | None
    language: str
    payload_text: str
    model_used: str | None
    model_was_fallback: bool
    dissent_round: int | None
    ts: datetime


class TurnList(BaseModel):
    items: list[TurnPublic]


# --------------------------------------------------------------------------- treasury


class TreasuryProposalCreate(BaseModel):
    session_id: str
    instrument: str = Field(min_length=1, max_length=64)
    side: Literal["buy", "sell"]
    qty: Decimal = Field(gt=Decimal("0"))
    expected_price: Decimal | None = None


class MandateCheckSummary(BaseModel):
    overall_pass: bool
    permitted_instruments: dict[str, Any]
    permitted_sides: dict[str, Any]
    single_instrument_max: dict[str, Any]
    daily_loss_limit: dict[str, Any]


class TreasuryProposalPublic(BaseModel):
    id: str
    session_id: str
    instrument: str
    side: str
    qty: Decimal
    expected_price: Decimal | None
    notional_eur: Decimal
    state: str
    proposed_at: datetime
    expires_at: datetime
    auth1_user_id: str | None
    auth2_user_id: str | None
    kraken_order_id: str | None
    executed_price: Decimal | None
    executed_qty: Decimal | None
    mandate_check: dict[str, Any]


class TreasuryAuthorise(BaseModel):
    confirm: bool = True


class TreasuryReject(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


# --------------------------------------------------------------------------- mandates


class MandateCreate(BaseModel):
    daily_loss_limit: Decimal = Field(ge=Decimal("0"))
    single_instrument_max: Decimal = Field(ge=Decimal("0"))
    permitted_instruments: list[str]
    permitted_sides: list[Literal["buy", "sell"]]
    auth_user_ids: list[str]
    currency: str = "EUR"


class MandatePublic(BaseModel):
    id: str
    version: int
    daily_loss_limit: Decimal
    single_instrument_max: Decimal
    permitted_instruments: list[str]
    permitted_sides: list[str]
    auth_user_ids: list[str]
    currency: str
    is_active: bool


# --------------------------------------------------------------------------- documents


class DocumentPublic(BaseModel):
    id: str
    session_id: str
    filename: str
    byte_size: int
    sha256: str
    kind: str
    extraction_status: str
    summary: str | None


# --------------------------------------------------------------------------- audit


class AuditEventPublic(BaseModel):
    id: str
    tenant_id: str
    session_id: str | None
    actor_user_id: str | None
    kind: str
    payload_json: dict[str, Any]
    ts: datetime


# --------------------------------------------------------------------------- voice


class LiveKitJoinResponse(BaseModel):
    livekit_url: str
    room: str
    token: str
    identity: str


# --------------------------------------------------------------------------- generic


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded", "down"]
    build_sha: str
    version: str
    db: Literal["ok", "down"]
    inference_providers: dict[str, str]
