"""Shared pytest fixtures.

We use SQLite-in-memory (aiosqlite) for all backend tests. Postgres-only
features (RLS, append-only triggers, pgvector) are exercised in a separate
docker-compose-based smoke run, not in unit CI.

Every test gets a fresh DB schema via `metadata.create_all()` and the
inference gateway is reset so each test gets a clean MockClient.
"""
from __future__ import annotations

import asyncio
import os
import uuid
from collections.abc import AsyncIterator, Iterator
from decimal import Decimal
from pathlib import Path

# CRITICAL: set env BEFORE importing anything from `app`.
os.environ.setdefault("ATRIO_ENV", "test")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("ATRIO_MOCK_INFERENCE", "true")
os.environ.setdefault("LOG_LEVEL", "WARNING")
os.environ.setdefault("RATE_LIMIT_ENABLED", "false")
os.environ.setdefault("JWT_TEST_SECRET", "test-secret-for-unit-tests-only-not-prod-32chars")
os.environ.setdefault("MODEL_REGISTRY_PATH", str(Path(__file__).resolve().parents[2] / "config" / "models" / "atrio.yaml"))
os.environ.setdefault("PROMPTS_DIR", str(Path(__file__).resolve().parents[2] / "prompts"))

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from app.core.config import reset_settings_cache  # noqa: E402
from app.db.base import Base, get_sessionmaker, reset_engine  # noqa: E402
from app.db.models import Mandate, Tenant, User  # noqa: E402
from app.inference.gateway import reset_gateway  # noqa: E402
from app.treasury.kraken import reset_kraken_client  # noqa: E402


# ---------------------------------------------------------------------------
# Event loop
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def event_loop() -> Iterator[asyncio.AbstractEventLoop]:
    """Reuse one event loop for the whole test session (faster)."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# ---------------------------------------------------------------------------
# DB lifecycle — one fresh schema per test
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(autouse=True)
async def _fresh_db() -> AsyncIterator[None]:
    """Drop + recreate schema between every test."""
    reset_settings_cache()
    await reset_engine()
    reset_gateway()
    reset_kraken_client()
    # Need to re-import engine/sessionmaker because reset cleared the globals
    from app.db.base import get_engine

    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    await reset_engine()


@pytest_asyncio.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    """Yield a fresh AsyncSession bound to the test DB."""
    sm = get_sessionmaker()
    async with sm() as session:
        yield session
        await session.rollback()


# ---------------------------------------------------------------------------
# Domain factories
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def tenant(db_session: AsyncSession) -> Tenant:
    t = Tenant(
        name="Test Tenant",
        slug=f"test-tenant-{uuid.uuid4().hex[:6]}",
        tier="founder",
        locale_default="en",
        data_residency="eu",
        kraken_enabled=True,
        kraken_live=False,
    )
    db_session.add(t)
    await db_session.commit()
    await db_session.refresh(t)
    return t


@pytest_asyncio.fixture
async def second_tenant(db_session: AsyncSession) -> Tenant:
    t = Tenant(
        name="Other Tenant",
        slug=f"other-{uuid.uuid4().hex[:6]}",
        tier="founder",
    )
    db_session.add(t)
    await db_session.commit()
    await db_session.refresh(t)
    return t


@pytest_asyncio.fixture
async def founder_user(db_session: AsyncSession, tenant: Tenant) -> User:
    u = User(
        tenant_id=tenant.id,
        email="founder@test.com",
        display_name="Founder Test",
        role="founder",
    )
    db_session.add(u)
    await db_session.commit()
    await db_session.refresh(u)
    return u


@pytest_asyncio.fixture
async def second_authoriser(db_session: AsyncSession, tenant: Tenant) -> User:
    u = User(
        tenant_id=tenant.id,
        email="auth2@test.com",
        display_name="Auth Two",
        role="authoriser",
    )
    db_session.add(u)
    await db_session.commit()
    await db_session.refresh(u)
    return u


@pytest_asyncio.fixture
async def viewer_user(db_session: AsyncSession, tenant: Tenant) -> User:
    u = User(
        tenant_id=tenant.id,
        email="viewer@test.com",
        display_name="Viewer Only",
        role="viewer",
    )
    db_session.add(u)
    await db_session.commit()
    await db_session.refresh(u)
    return u


@pytest_asyncio.fixture
async def active_mandate(
    db_session: AsyncSession, tenant: Tenant, founder_user: User, second_authoriser: User
) -> Mandate:
    m = Mandate(
        tenant_id=tenant.id,
        version=1,
        daily_loss_limit=Decimal("25000.00"),
        single_instrument_max=Decimal("50000.00"),
        permitted_instruments=["SHV-xStock", "IEF-xStock", "EURUSD-xStock"],
        permitted_sides=["buy", "sell"],
        auth_user_ids=[founder_user.id, second_authoriser.id],
        currency="EUR",
        is_active=True,
    )
    db_session.add(m)
    await db_session.commit()
    await db_session.refresh(m)
    return m


# ---------------------------------------------------------------------------
# HTTP client
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def app_client() -> AsyncIterator[AsyncClient]:
    """ASGI test client — used by all integration tests."""
    # Import lazily so env is set first
    from app.main import create_app

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def make_token():
    """Return a callable that mints an access token for any (user_id, tenant_id, role)."""
    from app.core.security import create_access_token

    def _make(user_id: str, tenant_id: str, role: str = "founder") -> str:
        return create_access_token(subject=user_id, tenant_id=tenant_id, role=role)

    return _make


@pytest.fixture
def auth_header(make_token, founder_user, tenant) -> dict[str, str]:
    tok = make_token(founder_user.id, tenant.id, founder_user.role)
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture
def second_auth_header(make_token, second_authoriser, tenant) -> dict[str, str]:
    tok = make_token(second_authoriser.id, tenant.id, second_authoriser.role)
    return {"Authorization": f"Bearer {tok}"}
