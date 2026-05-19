#!/usr/bin/env bash
# One-shot: ensure prod .env has the right inference + judge-mode vars,
# then rebuild api + frontend. Idempotent.
set -euo pipefail

cd /srv/atrio/atrio-boardroom

# git pull first so we have the latest compose + auth.py + SignIn.tsx
git pull --ff-only

# set_or_append KEY VAL: edits .env -- replaces existing KEY=, or appends.
set_or_append() {
  local k="$1"
  local v="$2"
  if grep -q "^${k}=" .env; then
    # use a delimiter that won't appear in API keys
    sed -i "s#^${k}=.*#${k}=${v}#" .env
  else
    echo "${k}=${v}" >> .env
  fi
}

set_or_append GEMINI_API_KEY AIzaSyBxr919IRV-c5jzvZdn002F4Ks1inF3Z1k
set_or_append ATRIO_MOCK_INFERENCE false
set_or_append DEV_MAGIC_LINK_ECHO true
set_or_append ATRIO_ENV demo

echo "--- FINAL .env relevant lines ---"
grep -E "^(GEMINI_API_KEY|ATRIO_MOCK_INFERENCE|DEV_MAGIC_LINK_ECHO|ATRIO_ENV)=" .env \
  | sed -E "s|(_KEY=).{8,}|\1***REDACTED***|"

echo
echo "--- REBUILDING api + frontend ---"
docker compose -f docker/docker-compose.yml --env-file .env up -d --force-recreate --build api frontend

echo
echo "--- waiting 12 s for boot ---"
sleep 12

echo
echo "--- CONTAINER ENV (live) ---"
docker exec atrio-api-1 env \
  | grep -E "^(GEMINI_API_KEY|ATRIO_MOCK_INFERENCE|DEV_MAGIC_LINK_ECHO|ATRIO_ENV)=" \
  | sed -E "s|(_KEY=).{8,}|\1***REDACTED***|"

echo
echo "--- PROBE GET /auth/dev-signin ---"
curl -s http://localhost:8000/api/v1/auth/dev-signin
echo

echo
echo "--- HEALTHZ ---"
curl -s http://localhost:8000/api/v1/healthz
echo

echo
echo "--- DONE ---"
