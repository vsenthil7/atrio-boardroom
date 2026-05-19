# ATRIO API — multi-stage build for a small, secure production image.
# Build context is the `backend/` directory.

# ----- Stage 1: deps -----
FROM python:3.12-slim AS deps

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY pyproject.toml ./
COPY app ./app
RUN pip install --upgrade pip && \
    pip install --prefix=/install -e ".[]" --no-deps && \
    pip install --prefix=/install \
        "fastapi==0.115.6" \
        "uvicorn[standard]==0.34.0" \
        "pydantic==2.10.3" \
        "pydantic-settings==2.7.0" \
        "sqlalchemy[asyncio]==2.0.36" \
        "asyncpg==0.30.0" \
        "aiosqlite==0.20.0" \
        "alembic==1.14.0" \
        "pgvector==0.3.6" \
        "python-jose[cryptography]==3.3.0" \
        "passlib[bcrypt]==1.7.4" \
        "bcrypt==4.0.1" \
        "httpx==0.28.1" \
        "structlog==24.4.0" \
        "PyYAML==6.0.2" \
        "reportlab==4.2.5" \
        "PyMuPDF==1.24.13" \
        "python-docx==1.1.2" \
        "openpyxl==3.1.5" \
        "Pillow==11.0.0" \
        "python-multipart==0.0.20" \
        "email-validator==2.2.0"

# ----- Stage 2: runtime -----
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/install/bin:${PATH}" \
    PYTHONPATH="/install/lib/python3.12/site-packages:/app"

RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 \
        curl \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system atrio \
    && useradd --system --gid atrio --home /app atrio

COPY --from=deps /install /install

WORKDIR /app
COPY --chown=atrio:atrio app ./app
COPY --chown=atrio:atrio migrations ./migrations
COPY --chown=atrio:atrio alembic.ini ./
COPY --chown=atrio:atrio pyproject.toml ./

USER atrio
EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=3s --start-period=15s --retries=5 \
    CMD python -c "import urllib.request,sys; urllib.request.urlopen('http://localhost:8000/api/v1/healthz', timeout=2)" || exit 1

CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:create_app --factory --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips=*"]
