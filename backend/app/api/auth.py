"""Auth router — magic-link sign-in.

POST /auth/magic-link        { email }                → 202 always (no enum)
POST /auth/magic-link/consume { token }               → tokens
POST /auth/refresh           { refresh_token }        → new tokens
GET  /auth/me                                         → CurrentUser
"""
from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, status
from jose import JWTError, jwt
from sqlalchemy import select

from app.api.deps import CurrentUserDep, DbSession
from app.api.schemas import (
    MagicLinkConsume,
    MagicLinkRequest,
    RefreshRequest,
    TokenResponse,
    UserPublic,
)
from app.audit.service import AuditService
from app.core.config import get_settings
from app.core.errors import Unauthenticated
from app.core.logging import get_logger
from app.core.security import (
    create_access_token,
    create_magic_link_token,
    create_refresh_token,
    decode_token,
)
from app.db.models import MagicLinkToken, User

router = APIRouter(prefix="/auth", tags=["auth"])
log = get_logger(__name__)


def _hash_token(t: str) -> str:
    return hashlib.sha256(t.encode()).hexdigest()


@router.post(
    "/magic-link",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Request a magic-link email",
)
async def request_magic_link(body: MagicLinkRequest, db: DbSession) -> dict[str, str]:
    """Always returns 202 regardless of whether the email exists (no user enumeration)."""
    email = body.email.lower()
    # Resolve user
    user = (
        await db.execute(select(User).where(User.email == email, User.status == "active"))
    ).scalar_one_or_none()
    if user is not None:
        token = create_magic_link_token(email=email)
        row = MagicLinkToken(
            email=email,
            token_hash=_hash_token(token),
            expires_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(minutes=15),
        )
        db.add(row)
        await db.flush()
        # In production we send via SMTP; for the hackathon log + return for inspection.
        log.info("magic_link_issued", email=email, token_hash=row.token_hash[:12])
        # Send the actual email (NullMailer in test, LogMailer in local, SMTP elsewhere)
        try:
            from app.mail import build_mailer, render_magic_link_email

            settings_local = get_settings()
            link_url = f"{settings_local.frontend_base_url}/signin?token={token}"
            mailer = build_mailer(settings_local)
            mailer.send(render_magic_link_email(email=email, link_url=link_url))
        except Exception as e:  # noqa: BLE001 — don't leak errors back to the user
            log.warning("magic_link_email_failed", email=email, error=str(e))
        await AuditService(db).write(
            tenant_id=user.tenant_id,
            actor_user_id=user.id,
            kind="auth_magic_link_issued",
            payload={"email": email},
        )
        # Return token in dev/test mode so tests/Playwright can sign in headlessly.
        settings = get_settings()
        if settings.atrio_env in ("local", "test", "demo"):
            return {"status": "ok", "dev_token": token}
    return {"status": "ok"}


@router.post(
    "/magic-link/consume", response_model=TokenResponse, summary="Consume a magic link"
)
async def consume_magic_link(body: MagicLinkConsume, db: DbSession) -> TokenResponse:
    settings = get_settings()
    # Decode token to extract email + verify expiry/signature
    try:
        claims = decode_token(body.token)
    except Exception as e:
        raise Unauthenticated(f"invalid magic-link token: {e}") from e
    if claims.get("type") != "magic_link":
        raise Unauthenticated("not a magic-link token")
    email = (claims.get("sub") or "").lower()
    if not email:
        raise Unauthenticated("token missing email")

    # Verify the token hash matches an un-consumed DB row
    th = _hash_token(body.token)
    row = (
        await db.execute(
            select(MagicLinkToken).where(MagicLinkToken.token_hash == th)
        )
    ).scalar_one_or_none()
    if row is None:
        raise Unauthenticated("magic-link token unknown")
    if row.consumed_at is not None:
        raise Unauthenticated("magic-link token already consumed")
    if row.expires_at < datetime.utcnow():
        raise Unauthenticated("magic-link token expired")

    user = (
        await db.execute(select(User).where(User.email == email, User.status == "active"))
    ).scalar_one_or_none()
    if user is None:
        raise Unauthenticated("user no longer active")

    row.consumed_at = datetime.utcnow()
    user.last_login_at = datetime.utcnow()
    await db.flush()

    access = create_access_token(subject=user.id, tenant_id=user.tenant_id, role=user.role)
    refresh = create_refresh_token(subject=user.id, tenant_id=user.tenant_id)
    await AuditService(db).write(
        tenant_id=user.tenant_id,
        actor_user_id=user.id,
        kind="auth_signed_in",
        payload={"method": "magic_link"},
    )
    return TokenResponse(
        access_token=access,
        refresh_token=refresh,
        expires_in=settings.jwt_access_expires_seconds,
    )


@router.post("/refresh", response_model=TokenResponse, summary="Refresh access token")
async def refresh_token(body: RefreshRequest, db: DbSession) -> TokenResponse:
    settings = get_settings()
    try:
        claims = decode_token(body.refresh_token)
    except Exception as e:
        raise Unauthenticated(f"invalid refresh token: {e}") from e
    if claims.get("type") != "refresh":
        raise Unauthenticated("not a refresh token")
    user_id = claims.get("sub")
    tenant_id = claims.get("tenant_id")
    if not user_id or not tenant_id:
        raise Unauthenticated("token missing claims")
    user = (
        await db.execute(select(User).where(User.id == user_id, User.tenant_id == tenant_id))
    ).scalar_one_or_none()
    if user is None or user.status != "active":
        raise Unauthenticated("user inactive")
    access = create_access_token(subject=user.id, tenant_id=user.tenant_id, role=user.role)
    refresh_new = create_refresh_token(subject=user.id, tenant_id=user.tenant_id)
    return TokenResponse(
        access_token=access,
        refresh_token=refresh_new,
        expires_in=settings.jwt_access_expires_seconds,
    )


@router.get("/me", response_model=UserPublic)
async def me(user: CurrentUserDep) -> UserPublic:
    return UserPublic(
        id=user.user_id,
        email=user.email,
        display_name=user.display_name,
        role=user.role,
        tenant_id=user.tenant_id,
    )
