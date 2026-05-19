# ATRIO Boardroom

**Your AI boardroom — built for Milan AI Week 2026.**

A voice-first multilingual multi-agent system. Six agents around a single boardroom table: a **Facilitator**, four domain specialists (**CFO · CTO · CMO · COO**), and a **Counsel**. Sessions produce a downloadable board-pack PDF, and when consensus implies a treasury move, ATRIO can execute a mandate-gated, two-party-authorised paper trade on Kraken.

---

## Why this is interesting

| | |
|---|---|
| **Audit-grade by default** | append-only DB triggers, request-id propagation, every model invocation logged with provider/model/tokens/latency, full tenant-scoped ZIP export |
| **Mandate-enforced treasury** | four-gate check (instrument, side, single-instrument cap, daily-loss cap) runs at the API layer, *not* the UI |
| **Two-party authorisation** | one founder cannot self-execute a trade — a different authoriser must confirm; the front-end blocks it, the API blocks it again, an integration test pins the behaviour |
| **Multi-tenant from line one** | cross-tenant access is provably impossible — 17 dedicated security tests + Postgres row-level security policies |
| **Model registry as single source of truth** | provider/model names live in YAML and are the *only* path to inference; supports primary→fallback chains (Gemini → Featherless) |

---

## Status at a glance

| Layer | Stack | Tests | Coverage |
|---|---|---|---|
| Backend | Python 3.12 · FastAPI · SQLAlchemy 2.0 async · Postgres + pgvector | **319** ✅ | **91%** |
| Frontend | React 18 · Vite · Tailwind · Zustand · React Query | **10** ✅ unit + **6** Playwright suites | type-checked ✅ |
| E2E | Backend full demo flow + Playwright two-party + 5 more | covered | — |

Every test currently passes.  CI gate: `--cov-fail-under=85`.

---

## Quick start

### Local dev (no cloud accounts needed — uses mock inference)

```bash
git clone <this repo>
cd atrio

# Generate the JWT keypair (one-off)
./scripts/gen-keys.sh

# Copy env template
cp .env.example .env

# Spin up the stack
cd docker
docker compose up --build
```

Then open:

- **App**: http://localhost:8080
- **API docs**: http://localhost:8000/api/v1/docs
- **MailHog (magic links)**: http://localhost:8025
- **MinIO console**: http://localhost:9001

Seed and sign in:

```bash
curl -X POST http://localhost:8000/api/v1/_test/seed-demo
./scripts/smoke.sh
```

### Backend only (no Docker)

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[test]"

ATRIO_ENV=test \
DATABASE_URL=sqlite+aiosqlite:///:memory: \
ATRIO_MOCK_INFERENCE=true \
MODEL_REGISTRY_PATH=../config/models/atrio.yaml \
PROMPTS_DIR=../prompts \
  uvicorn app.main:create_app --factory --reload
```

### Frontend only

```bash
cd frontend
npm ci
npm run dev
```

---

## Tests

```bash
# Backend — 319 tests
cd backend
python -m pytest

# Mandate violation corpus (12 cases)
python -m pytest tests/integration/test_mandate_violation_corpus.py -v

# Cross-tenant isolation (17 cases)
python -m pytest tests/integration/test_cross_tenant_isolation.py -v

# Full demo flow
python -m pytest tests/e2e/test_full_demo_flow.py -v

# Frontend unit
cd ../frontend
npm test

# Playwright E2E (auto-starts backend + frontend on 8000/5173)
npm run e2e:install   # once
npm run e2e
```

---

## Sponsor integrations

| Sponsor | Role | Where to look |
|---|---|---|
| **Vultr** | EU compute + object storage | `docker-compose.yml`, `scripts/deploy.sh` |
| **Gemini** | Facilitator + Counsel primary model | `app/inference/providers.py` → `GeminiClient` |
| **Featherless** | CFO/CTO/CMO/COO primary models | `app/inference/providers.py` → `FeatherlessClient` |
| **Speechmatics** | Multilingual STT | `voice/service.py` + `config/dictionaries/demo_en.txt` |
| **Kraken** | Paper-trade execution | `app/treasury/kraken.py` |
| **LiveKit** | Voice rooms | `app/voice/service.py` |

When `ATRIO_MOCK_INFERENCE=true`, every provider is replaced by the deterministic `MockClient` so the entire flow runs offline. Set `ATRIO_MOCK_INFERENCE=false` and supply the API keys in `.env` to talk to real providers.

---

## Deploy

```bash
REMOTE=root@your.vultr.vm ./scripts/deploy.sh
```

The script rsyncs the repo, runs `docker compose up -d --build`, applies migrations, and verifies a green smoke test before exiting.

---

## What's NOT in this hackathon build

- **Authn**: magic-link only; no SSO/SAML.
- **Voice pipeline**: token issuance is wired, but the Speechmatics + LiveKit sidecar is stubbed (will run live during the demo).
- **Email delivery**: dev mode echoes the magic-link token in the response body; production wires SMTP.
- **Kraken live trading**: hard-disabled (`kraken_live=false`); only paper trades for the duration of the hackathon.

---

## Architecture / specs

See the full project documents in this repo:
- [`AT-Hack0021_Claude_MilanAIWeek_BRDv1_20260518.md`](./AT-Hack0021_Claude_MilanAIWeek_BRDv1_20260518.md) — Business Requirements
- [`AT-Hack0021_Claude_ATRIO_Architecture_20260518.md`](./AT-Hack0021_Claude_ATRIO_Architecture_20260518.md) — Architecture
- [`AT-Hack0021_Claude_ATRIO_APISpec_20260518.md`](./AT-Hack0021_Claude_ATRIO_APISpec_20260518.md) — API spec
- [`AT-Hack0021_Claude_ATRIO_DataModel_20260518.md`](./AT-Hack0021_Claude_ATRIO_DataModel_20260518.md) — Data model
- [`AT-Hack0021_Claude_ATRIO_StoryBacklog_20260518.md`](./AT-Hack0021_Claude_ATRIO_StoryBacklog_20260518.md) — Sprint backlog
- [`AT-Hack0021_Claude_ATRIO_TestStrategy_20260518.md`](./AT-Hack0021_Claude_ATRIO_TestStrategy_20260518.md) — Test strategy

---

## License

Apache 2.0 — see [LICENSE](./LICENSE).
