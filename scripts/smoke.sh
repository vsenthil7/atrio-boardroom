#!/usr/bin/env bash
# Curl-based smoke test.
#
# Hits a running ATRIO stack to verify:
#   1. /healthz returns 200
#   2. seed-demo populates the tenant
#   3. magic-link issue + consume returns a JWT
#   4. /auth/me with that JWT returns the user
#   5. session create works
#   6. POST a turn and confirm an SSE stream
#
# Usage:
#   ./scripts/smoke.sh                       # defaults to localhost:8000
#   API_URL=https://atrio.app/api/v1 ./scripts/smoke.sh

set -euo pipefail

API_URL="${API_URL:-http://localhost:8000/api/v1}"
RED=$'\e[31m'; GREEN=$'\e[32m'; CYAN=$'\e[36m'; RESET=$'\e[0m'

step() { echo "${CYAN}→ $1${RESET}"; }
pass() { echo "${GREEN}✓ $1${RESET}"; }
fail() { echo "${RED}✗ $1${RESET}"; exit 1; }

step "healthz"
curl -sf "$API_URL/healthz" | grep -q '"status":"ok"' || fail "healthz did not return ok"
pass "healthz"

step "seed demo tenant"
SEED=$(curl -sf -X POST "$API_URL/_test/seed-demo")
echo "$SEED" | grep -q '"founder_email":"founder@acme.co"' || fail "seed failed"
pass "seeded"

step "magic-link issue"
TOKEN=$(curl -sf -X POST "$API_URL/auth/magic-link" \
    -H 'Content-Type: application/json' \
    -d '{"email":"founder@acme.co"}' | python3 -c 'import sys,json; print(json.load(sys.stdin)["dev_token"])')
[[ -n "$TOKEN" ]] || fail "no dev_token returned"
pass "issued"

step "magic-link consume"
ACCESS=$(curl -sf -X POST "$API_URL/auth/magic-link/consume" \
    -H 'Content-Type: application/json' \
    -d "{\"token\":\"$TOKEN\"}" | python3 -c 'import sys,json; print(json.load(sys.stdin)["access_token"])')
[[ -n "$ACCESS" ]] || fail "no access_token returned"
pass "consumed"

step "auth/me"
ME=$(curl -sf "$API_URL/auth/me" -H "Authorization: Bearer $ACCESS")
echo "$ME" | grep -q 'founder@acme.co' || fail "/me did not match"
pass "me"

step "create session"
SID=$(curl -sf -X POST "$API_URL/sessions" \
    -H 'Content-Type: application/json' \
    -H "Authorization: Bearer $ACCESS" \
    -d '{"title":"smoke"}' | python3 -c 'import sys,json; print(json.load(sys.stdin)["id"])')
[[ -n "$SID" ]] || fail "no session id"
pass "session created: $SID"

step "post turn (SSE)"
SSE=$(curl -sf -N -X POST "$API_URL/sessions/$SID/turns" \
    -H 'Content-Type: application/json' \
    -H "Authorization: Bearer $ACCESS" \
    -d '{"text":"smoke test","mode":"single"}')
echo "$SSE" | grep -q 'event: consensus' || fail "no consensus event"
pass "stream received"

step "metrics endpoint"
METRICS=$(curl -sf "$API_URL/metrics")
echo "$METRICS" | grep -q "atrio_sessions_opened_total" || fail "metrics missing sessions counter"
echo "$METRICS" | grep -q "http_requests_total" || fail "metrics missing http counter"
pass "metrics endpoint exposes prometheus format"

echo
echo "${GREEN}All smoke checks passed against $API_URL${RESET}"
