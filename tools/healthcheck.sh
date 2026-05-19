#!/usr/bin/env bash
# ATRIO Boardroom -- healthcheck.sh
#
# Per claude-memory/global/HEALTH_CHECK_RULES.md:
#   - dual-mode: local | docker | both
#   - reads ports from .env (do NOT hardcode 8000/5432/8080)
#   - hits /healthz, frontend /
#   - exit 0 with one-line OK summary; exit non-zero with the failing surface
#
# Usage:
#   ./tools/healthcheck.sh          # default docker
#   ./tools/healthcheck.sh docker
#   ./tools/healthcheck.sh local
#   ./tools/healthcheck.sh both
#   ./tools/healthcheck.sh docker -v  # verbose (show full bodies)
#
# Exit codes match healthcheck.ps1:
#   0 = all green | 1 = api unreachable | 2 = db down | 3 = inference misconfig
#   4 = frontend unreachable | 5 = bad mode arg / env file missing

set -e

MODE="${1:-docker}"
VERBOSE=""
[ "${2:-}" = "-v" ] && VERBOSE=1

case "$MODE" in
  local|docker|both) ;;
  *) echo "[healthcheck] bad mode: $MODE (use local|docker|both)" >&2; exit 5 ;;
esac

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

ENV_FILE=".env"
[ -f "$ENV_FILE" ] || { echo "[healthcheck $MODE] $ENV_FILE not found in $REPO_ROOT" >&2; exit 5; }

env_var() {
  local name="$1" default="$2"
  local v
  v="$(grep -E "^${name}=" "$ENV_FILE" 2>/dev/null | head -1 | cut -d= -f2- || true)"
  echo "${v:-$default}"
}

API_PORT="$(env_var API_HOST_PORT 8000)"
FRONTEND_PORT="$(env_var FRONTEND_HOST_PORT 8080)"
[ "$MODE" = "local" ] && FRONTEND_PORT="$(env_var FRONTEND_BASE_URL_PORT 5173)"

API_BASE="http://localhost:${API_PORT}"
FRONTEND_BASE="http://localhost:${FRONTEND_PORT}"

[ -z "${QUIET:-}" ] && echo "[healthcheck $MODE] api=$API_BASE frontend=$FRONTEND_BASE"

started="$(date +%s)"

# --- api healthz ---
HEALTHZ_URL="${API_BASE}/api/v1/healthz"
api_body="$(curl -sf --max-time 5 "$HEALTHZ_URL" || true)"
if [ -z "$api_body" ]; then
  echo "[health $MODE] FAIL api unreachable at $HEALTHZ_URL"
  exit 1
fi

db_state="$(echo "$api_body" | grep -oE '"db":"[^"]*"' | cut -d: -f2 | tr -d '"' || echo unknown)"
inference="$(echo "$api_body" | grep -oE '"inference_providers":\{[^}]*\}' | sed 's/"inference_providers"://' || echo unknown)"

case "$db_state" in
  ok|up|healthy) ;;
  *) echo "[health $MODE] PARTIAL api=OK db=$db_state"; exit 2 ;;
esac

case "$inference" in
  ""|"{}") echo "[health $MODE] PARTIAL api=OK db=$db_state but inference_providers empty"; exit 3 ;;
esac

# --- frontend ---
frontend_code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 "$FRONTEND_BASE" || echo 0)"
if [ "$frontend_code" != "200" ] && [ "$frontend_code" != "304" ]; then
  echo "[health $MODE] FAIL frontend unreachable at $FRONTEND_BASE (HTTP $frontend_code)"
  exit 4
fi

elapsed="$(( $(date +%s) - started ))"

echo "[health $MODE] api=OK db=$db_state inference=$inference frontend=OK($frontend_code) -- ${elapsed}s"

if [ -n "$VERBOSE" ]; then
  echo
  echo "--- /healthz body ---"
  echo "$api_body"
fi

exit 0
