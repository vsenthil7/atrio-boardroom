# Voice sidecar — LiveKit ↔ Speechmatics bridge.
# Built from the repo root; shares the backend app for the Speechmatics client.

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system atrio \
    && useradd --system --gid atrio --home /app atrio

# Install deps — small set, the sidecar only needs httpx + websockets + structlog
RUN pip install --upgrade pip && pip install \
    "httpx==0.28.1" \
    "websockets==13.1" \
    "structlog==24.4.0" \
    "pydantic==2.10.3" \
    "pydantic-settings==2.7.0" \
    "PyYAML==6.0.2"

# Copy the backend app (we re-use the Speechmatics client) and the sidecar
COPY --chown=atrio:atrio backend/app /app/backend/app
COPY --chown=atrio:atrio sidecars /app/sidecars

ENV PYTHONPATH=/app:/app/backend

USER atrio

CMD ["python", "-m", "sidecars.voice"]
