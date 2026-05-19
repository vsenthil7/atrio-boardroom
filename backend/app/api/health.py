"""Health + readiness."""
from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse
from sqlalchemy import text

from app import __version__
from app.api.deps import DbSession
from app.api.schemas import HealthResponse
from app.core.config import get_settings
from app.inference.gateway import get_gateway
from app.observability import get_registry

router = APIRouter(tags=["health"])


@router.get("/healthz", response_model=HealthResponse)
async def healthz(db: DbSession) -> HealthResponse:
    settings = get_settings()
    db_status: str = "ok"
    try:
        await db.execute(text("SELECT 1"))
    except Exception:  # pragma: no cover - defensive
        db_status = "down"
    gw = get_gateway()
    providers = {name: "configured" for name in gw.providers()}
    return HealthResponse(
        status="ok" if db_status == "ok" else "degraded",
        build_sha=settings.atrio_build_sha,
        version=__version__,
        db=db_status,  # type: ignore[arg-type]
        inference_providers=providers,
    )


@router.get("/readyz")
async def readyz(db: DbSession) -> dict[str, str]:
    await db.execute(text("SELECT 1"))
    return {"status": "ready"}


@router.get("/metrics", response_class=PlainTextResponse)
async def metrics() -> PlainTextResponse:
    """Prometheus exposition endpoint.

    Not authenticated — Prometheus scrapers don't carry tokens. In production
    this is reachable only inside the docker network (Traefik doesn't expose
    /metrics externally per the production Caddyfile rule).
    """
    settings = get_settings()
    if not settings.prometheus_enabled:
        return PlainTextResponse("# metrics disabled\n", status_code=200)
    body = get_registry().render()
    return PlainTextResponse(body, media_type="text/plain; version=0.0.4")
