#!/usr/bin/env bash
# Deploy ATRIO to a Vultr VM via rsync + docker-compose.
#
# Prereqs on the remote host:
#   - docker + docker compose plugin installed
#   - SSH key authorised for $REMOTE_USER
#   - .env file already present at $REMOTE_PATH/.env
#   - secrets/ directory already populated
#
# Usage:
#   REMOTE=user@1.2.3.4 ./scripts/deploy.sh
#   REMOTE=user@1.2.3.4 BRANCH=main ./scripts/deploy.sh

set -euo pipefail

REMOTE="${REMOTE:?must set REMOTE=user@host}"
REMOTE_PATH="${REMOTE_PATH:-/srv/atrio}"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "Deploying to $REMOTE:$REMOTE_PATH"

# Build the frontend locally so the remote doesn't need Node
echo "→ Building frontend"
( cd "$REPO_ROOT/frontend" && npm ci --no-audit --no-fund && npm run build )

echo "→ Syncing files"
rsync -avz --delete \
    --exclude=node_modules \
    --exclude=__pycache__ \
    --exclude=.pytest_cache \
    --exclude=.mypy_cache \
    --exclude=dist \
    --exclude=.git \
    --exclude=.env \
    --exclude=secrets/jwt_*.pem \
    "$REPO_ROOT/" "$REMOTE:$REMOTE_PATH/"

# Push the freshly-built dist separately (excluded above to avoid local dist
# being clobbered by stale remote)
rsync -avz --delete "$REPO_ROOT/frontend/dist/" "$REMOTE:$REMOTE_PATH/frontend/dist/"

echo "→ Rebuilding + restarting containers"
ssh "$REMOTE" "cd $REMOTE_PATH/docker && docker compose --env-file ../.env up -d --build --remove-orphans"

echo "→ Running database migrations"
ssh "$REMOTE" "cd $REMOTE_PATH/docker && docker compose exec -T api alembic upgrade head"

echo "→ Smoke test against deployed stack"
ssh "$REMOTE" "cd $REMOTE_PATH && API_URL=http://localhost:8000/api/v1 ./scripts/smoke.sh"

echo "✓ Deploy complete."
