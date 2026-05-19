"""Security primitives: JWT issuance & verification, password/token hashing.

In test mode we use HS256 with a literal secret to avoid needing key files.
In prod we use RS256 with an asymmetric keypair so the public key can be
distributed to clients (e.g. for offline JWT validation in v1.1).
"""
from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import Settings, get_settings


class TokenError(ValueError):
    """Raised when a JWT cannot be decoded or has expired."""


_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ---------------------------------------------------------------------------
# Key resolution
# ---------------------------------------------------------------------------


def _load_key(path: str) -> str | None:
    p = Path(path)
    if p.exists():
        return p.read_text(encoding="utf-8")
    return None


def _signing_material(settings: Settings) -> tuple[str, str]:
    """Return (private/secret, public/secret) material based on env."""
    if settings.is_test or settings.atrio_env == "local":
        private = _load_key(settings.jwt_private_key_path)
        public = _load_key(settings.jwt_public_key_path)
        if private and public:
            return private, public
        # Test/local fallback: HS256 with shared secret
        return settings.jwt_test_secret, settings.jwt_test_secret
    private = _load_key(settings.jwt_private_key_path)
    public = _load_key(settings.jwt_public_key_path)
    if not private or not public:
        raise RuntimeError(
            f"JWT keys not found at {settings.jwt_private_key_path}/"
            f"{settings.jwt_public_key_path} in env={settings.atrio_env}"
        )
    return private, public


def _algorithm(settings: Settings) -> str:
    """Pick RS256 if keypair present, otherwise HS256 (test/local)."""
    private, public = _signing_material(settings)
    if private == public:  # symmetric secret used
        return "HS256"
    return settings.jwt_algorithm


# ---------------------------------------------------------------------------
# Token issuance
# ---------------------------------------------------------------------------


def create_access_token(
    *,
    subject: str,
    tenant_id: str,
    role: str,
    extra_claims: dict[str, Any] | None = None,
    settings: Settings | None = None,
) -> str:
    """Create a short-lived access token."""
    settings = settings or get_settings()
    now = datetime.now(UTC)
    expires_at = now + timedelta(seconds=settings.jwt_access_expires_seconds)
    claims: dict[str, Any] = {
        "sub": subject,
        "tenant_id": tenant_id,
        "role": role,
        "type": "access",
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
        "jti": str(uuid.uuid4()),
    }
    if extra_claims:
        claims.update(extra_claims)
    private, _ = _signing_material(settings)
    return jwt.encode(claims, private, algorithm=_algorithm(settings))


def create_refresh_token(
    *,
    subject: str,
    tenant_id: str,
    settings: Settings | None = None,
) -> str:
    """Create a long-lived refresh token."""
    settings = settings or get_settings()
    now = datetime.now(UTC)
    expires_at = now + timedelta(seconds=settings.jwt_refresh_expires_seconds)
    claims: dict[str, Any] = {
        "sub": subject,
        "tenant_id": tenant_id,
        "type": "refresh",
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
        "jti": str(uuid.uuid4()),
    }
    private, _ = _signing_material(settings)
    return jwt.encode(claims, private, algorithm=_algorithm(settings))


def decode_token(token: str, settings: Settings | None = None) -> dict[str, Any]:
    """Decode and validate a token. Raises TokenError on any issue."""
    settings = settings or get_settings()
    _, public = _signing_material(settings)
    try:
        return jwt.decode(token, public, algorithms=[_algorithm(settings)])
    except JWTError as e:
        raise TokenError(str(e)) from e


# ---------------------------------------------------------------------------
# Magic-link tokens (single-use, short-lived)
# ---------------------------------------------------------------------------


def create_magic_link_token(*, email: str, settings: Settings | None = None) -> str:
    """Create a one-time magic-link token valid for 15 minutes."""
    settings = settings or get_settings()
    now = datetime.now(UTC)
    expires_at = now + timedelta(minutes=15)
    claims = {
        "sub": email.lower(),
        "type": "magic_link",
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
        "jti": str(uuid.uuid4()),
    }
    private, _ = _signing_material(settings)
    return jwt.encode(claims, private, algorithm=_algorithm(settings))


# ---------------------------------------------------------------------------
# Passwords / one-way hashes (used for idempotency-key dedup, etc.)
# ---------------------------------------------------------------------------


def hash_password(password: str) -> str:
    """Hash a password with bcrypt."""
    return _pwd_context.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    """Verify a bcrypt-hashed password."""
    return _pwd_context.verify(password, hashed)


def random_token(length: int = 32) -> str:
    """Generate a URL-safe random token."""
    return secrets.token_urlsafe(length)


def constant_time_eq(a: str, b: str) -> bool:
    """Constant-time string comparison."""
    return secrets.compare_digest(a, b)
