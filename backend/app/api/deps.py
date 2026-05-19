"""FastAPI shared dependencies.

Auth resolution: extracts the bearer token, decodes it, fetches the User
row, and returns a typed `CurrentUser` carrying tenant_id + role. Anything
that hits a tenant-scoped table goes through this dependency so a token
cannot resolve to a tenant_id outside its claim.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import Forbidden, Unauthenticated
from app.core.security import TokenError, decode_token
from app.db.base import get_session
from app.db.models import User

DbSession = Annotated[AsyncSession, Depends(get_session)]


@dataclass(frozen=True)
class CurrentUser:
    """Authenticated user context."""

    user_id: str
    tenant_id: str
    email: str
    role: str
    display_name: str

    @property
    def is_founder(self) -> bool:
        return self.role == "founder"

    @property
    def can_authorise(self) -> bool:
        return self.role in ("founder", "authoriser")


def get_bearer_token(authorization: Annotated[str | None, Header()] = None) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise Unauthenticated("missing or malformed Authorization header")
    return authorization.split(" ", 1)[1].strip()


async def get_current_user(
    request: Request,
    token: Annotated[str, Depends(get_bearer_token)],
    db: DbSession,
) -> CurrentUser:
    try:
        claims = decode_token(token)
    except TokenError as e:
        raise Unauthenticated(f"token decode failed: {e}") from e
    if claims.get("type") != "access":
        raise Unauthenticated("not an access token")
    user_id = claims.get("sub")
    tenant_id = claims.get("tenant_id")
    if not user_id or not tenant_id:
        raise Unauthenticated("token missing required claims")
    row = (
        await db.execute(select(User).where(User.id == user_id, User.tenant_id == tenant_id))
    ).scalar_one_or_none()
    if row is None or row.status != "active":
        raise Unauthenticated("user no longer active")
    cu = CurrentUser(
        user_id=row.id,
        tenant_id=row.tenant_id,
        email=row.email,
        role=row.role,
        display_name=row.display_name,
    )
    # Stash on request for logging.
    request.state.current_user = cu
    return cu


CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]


def require_role(*roles: str):
    """Build a dep that asserts current user has one of the given roles."""

    async def _check(user: CurrentUserDep) -> CurrentUser:
        if user.role not in roles:
            raise Forbidden(
                f"role '{user.role}' is not allowed",
                details={"required": list(roles), "actual": user.role},
            )
        return user

    return _check


def get_request_id(request: Request) -> str:
    return getattr(request.state, "request_id", str(uuid.uuid4()))
