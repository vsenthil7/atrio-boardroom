"""FastAPI app factory.

Single entry point. Wires middleware (request-id, logging, CORS),
exception handlers (turn AtrioError into spec-shaped JSON), and all routers.
"""
from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app import __version__
from app.api import (
    audit,
    auth,
    boardpack,
    documents,
    health,
    mandates,
    sessions,
    treasury,
    turns,
    voice,
)
from app.core.config import get_settings
from app.core.errors import AtrioError, Unauthenticated, ValidationFailed
from app.core.logging import configure_logging, get_logger

log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Assign a request ID and add it to the response headers + logs.
    Also records HTTP-level Prometheus metrics."""

    async def dispatch(self, request: Request, call_next):
        rid = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = rid
        import time as _time

        start = _time.perf_counter()
        try:
            response = await call_next(request)
            status_code = response.status_code
        except Exception:
            status_code = 500
            raise
        finally:
            elapsed = _time.perf_counter() - start
            # Don't pull /metrics into its own metric
            path = request.url.path
            if not path.endswith("/metrics"):
                from app.observability import (
                    http_request_duration_seconds,
                    http_requests_total,
                )

                # Strip path params from the route template to keep cardinality low
                route = request.scope.get("route")
                route_path = getattr(route, "path", path) if route else path
                labels = {
                    "method": request.method,
                    "path": route_path,
                    "status": str(status_code),
                }
                http_requests_total.inc(labels=labels)
                http_request_duration_seconds.observe(elapsed, labels=labels)
        response.headers["X-Request-ID"] = rid
        settings = get_settings()
        response.headers["X-ATRIO-Version"] = settings.atrio_build_sha
        return response


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:  # noqa: ARG001 - signature required
    configure_logging()
    log.info("atrio_starting", version=__version__)
    # SQLite has no Alembic migrations applied via `alembic upgrade head` at
    # container boot — for in-memory or file-based SQLite dev/test, we create
    # the schema directly from the ORM metadata. Postgres always uses Alembic.
    settings = get_settings()
    if settings.database_url.startswith("sqlite"):
        from app.db.base import Base, get_engine

        engine = get_engine()
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        log.info("sqlite_schema_bootstrapped")
    yield
    log.info("atrio_stopping")


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def create_app() -> FastAPI:
    """Build the FastAPI application."""
    settings = get_settings()
    app = FastAPI(
        title="ATRIO Boardroom API",
        version=__version__,
        description="AI Boardroom for founders — multi-agent, audit-grade, mandate-bound.",
        lifespan=_lifespan,
        docs_url="/docs",
        redoc_url=None,
    )

    # ---- middleware
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID", "X-ATRIO-Version"],
    )

    # ---- exception handlers
    @app.exception_handler(AtrioError)
    async def _atrio_handler(request: Request, exc: AtrioError) -> JSONResponse:
        rid = getattr(request.state, "request_id", None)
        return JSONResponse(status_code=exc.http_status, content=exc.to_payload(rid))

    @app.exception_handler(RequestValidationError)
    async def _validation_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        rid = getattr(request.state, "request_id", None)
        # exc.errors() may contain non-serialisable values (Decimal, bytes).
        # Round-trip through json with default=str to make them safe.
        import json as _json
        safe_errors = _json.loads(_json.dumps(exc.errors(), default=str))
        wrapped = ValidationFailed(
            "request validation failed",
            details={"errors": safe_errors},
        )
        return JSONResponse(status_code=wrapped.http_status, content=wrapped.to_payload(rid))

    @app.exception_handler(Exception)
    async def _fallback_handler(request: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled_exception", error=str(exc))
        rid = getattr(request.state, "request_id", None)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": {
                    "code": "INTERNAL",
                    "message": "internal server error",
                    "request_id": rid,
                }
            },
        )

    @app.exception_handler(Unauthenticated)
    async def _unauth_handler(request: Request, exc: Unauthenticated) -> JSONResponse:
        rid = getattr(request.state, "request_id", None)
        resp = JSONResponse(status_code=401, content=exc.to_payload(rid))
        resp.headers["WWW-Authenticate"] = 'Bearer realm="atrio"'
        return resp

    # ---- routers
    app.include_router(health.router, prefix="/api/v1")
    app.include_router(auth.router, prefix="/api/v1")
    app.include_router(sessions.router, prefix="/api/v1")
    app.include_router(turns.router, prefix="/api/v1")
    app.include_router(documents.router, prefix="/api/v1")
    app.include_router(treasury.router, prefix="/api/v1")
    app.include_router(mandates.router, prefix="/api/v1")
    app.include_router(audit.router, prefix="/api/v1")
    app.include_router(voice.router, prefix="/api/v1")
    app.include_router(boardpack.router, prefix="/api/v1")

    # Test-only admin endpoints — never mounted in prod/staging.
    if settings.atrio_env in ("local", "test", "demo"):
        from app.api import _test as _test_router

        app.include_router(_test_router.router, prefix="/api/v1")

    @app.get("/", include_in_schema=False)
    async def _root() -> dict[str, str]:
        return {
            "name": "ATRIO Boardroom",
            "version": __version__,
            "docs": "/docs",
            "health": "/api/v1/healthz",
        }

    return app


# uvicorn entrypoint
app = create_app()
