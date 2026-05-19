#!/usr/bin/env bash
# ATRIO Boardroom · Vultr deploy (02-deploy.sh)
#
#   ssh root@<IP> bash -s < deploy/02-deploy.sh
#
# Idempotent: clones (or pulls), brings up the stack, runs migrations,
# seeds the demo tenant, verifies the healthcheck.

set -euo pipefail
exec > >(tee -a /var/log/atrio-deploy.log) 2>&1

REPO_URL="${REPO_URL:-https://github.com/vsenthil7/atrio-boardroom.git}"
TARGET_DIR="/srv/atrio/atrio-boardroom"
BRANCH="${BRANCH:-main}"

echo "[deploy] start $(date -u +%FT%TZ)  repo=$REPO_URL  branch=$BRANCH"

# ----- Clone or pull -----
if [ -d "$TARGET_DIR/.git" ]; then
    echo "[deploy] existing checkout, pulling latest..."
    cd "$TARGET_DIR"
    git fetch --all --tags
    git checkout "$BRANCH"
    git reset --hard "origin/$BRANCH"
else
    echo "[deploy] fresh clone..."
    mkdir -p "$(dirname "$TARGET_DIR")"
    git clone --branch "$BRANCH" "$REPO_URL" "$TARGET_DIR"
fi
cd "$TARGET_DIR"

# ----- .env (production) -----
if [ ! -f .env ]; then
    if [ -f deploy/prod.env.example ]; then
        echo "[deploy] generating .env from deploy/prod.env.example"
        cp deploy/prod.env.example .env
        # Generate strong secrets in-place
        SED_INPLACE="sed -i"
        $SED_INPLACE "s|__JWT_SECRET__|$(openssl rand -base64 48 | tr -d '+/=' | head -c 48)|g" .env
        $SED_INPLACE "s|__POSTGRES_PASSWORD__|$(openssl rand -base64 24 | tr -d '+/=' | head -c 24)|g" .env
        $SED_INPLACE "s|__MINIO_ROOT_PASSWORD__|$(openssl rand -base64 24 | tr -d '+/=' | head -c 24)|g" .env
        $SED_INPLACE "s|__LIVEKIT_API_SECRET__|$(openssl rand -base64 32 | tr -d '+/=' | head -c 32)|g" .env
    else
        echo "[deploy] WARNING: no deploy/prod.env.example; copying .env.example" >&2
        cp .env.example .env
    fi
fi

# ----- Secrets dir for JWT signing keys -----
mkdir -p secrets
if [ ! -f secrets/jwt_private.pem ]; then
    openssl genpkey -algorithm RSA -out secrets/jwt_private.pem -pkeyopt rsa_keygen_bits:2048
    openssl rsa -pubout -in secrets/jwt_private.pem -out secrets/jwt_public.pem
    chmod 0644 secrets/jwt_*.pem
fi

# ----- Bring up the stack -----
echo "[deploy] docker compose up -d --build"
docker compose -f docker/docker-compose.yml --env-file .env up -d --build

# ----- Wait for healthcheck -----
echo "[deploy] waiting for api healthcheck..."
for i in $(seq 1 60); do
    if curl -fsS http://localhost:8000/api/v1/healthz >/dev/null 2>&1; then
        echo "[deploy] api OK after ${i}s"
        break
    fi
    sleep 1
done

curl -s http://localhost:8000/api/v1/healthz | jq . || true

# ----- Seed demo tenant -----
echo "[deploy] seeding demo tenant..."
curl -fsS -X POST http://localhost:8000/api/v1/_test/seed-demo | jq . || true

# ----- Summary -----
echo
echo "[deploy] done $(date -u +%FT%TZ)"
echo
docker compose -f docker/docker-compose.yml ps
echo
echo "Public so far: http://$(curl -fsS https://api.ipify.org || echo SERVER_IP):8080"
echo
echo "Next: DOMAIN=atrio.verixa.dev bash -s < deploy/03-tls.sh"
