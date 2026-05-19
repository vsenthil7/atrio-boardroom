# ATRIO Boardroom

**Your AI boardroom — built for Milan AI Week 2026.**

A voice-first multilingual multi-agent system. Six agents around a single boardroom table: a **Facilitator**, four domain specialists (**CFO · CTO · CMO · COO**), and a **Counsel**. Sessions produce a downloadable board-pack PDF, and when consensus implies a treasury move, ATRIO can execute a mandate-gated, two-party-authorised paper trade on Kraken.

---

## 🎬 Try the live demo

**Live URL:** http://45.77.52.54:8080
*(Hosted on Vultr in Frankfurt. HTTP only for now — the `Not secure` banner is cosmetic; nothing sensitive is exposed.)*

### Judge walkthrough — 6 minutes end-to-end

1. **Click "Demo founder"** on the sign-in screen (one click, no email needed).
2. On the **Sessions** page, paste this into "What's on the table?":
   > *Should we hire 4 senior engineers in Q3 given an 18-month runway and a tight product roadmap?*
3. Click **Open Session**. Watch five distinct agents stream their reasoning:
   - **CFO** does the math: ~$1M annual burn, runway shrinks 18→15 months
   - **CTO** raises ramp-up velocity concerns on a tight roadmap
   - **CMO** asks for market-validated demand signal
   - **COO** flags 3–6 month onboarding overhead
   - **Counsel** raises fiduciary risk + suggests contractors as a mitigant
   - Session ends with a **consensus + action list** (or a captured `split` if agents disagree)
   - **Real LLM calls** — Gemini 2.5 Flash for most agents, 2.5 Pro for Counsel. ~20–30 s total.
4. **Go to Treasury** → propose a SHV-xStock buy for €50,000.
5. Click **Authorise** as founder (1 of 2). Then try **Authorise** *again* — the API refuses self-second-signing. The attempt is captured in the audit log.
6. **Open a new tab** → http://45.77.52.54:8080/signin → click **Demo CEO**.
7. As CEO, find the pending proposal in Treasury → **Authorise** (2 of 2). Trade executes against the Kraken paper engine.
8. **Boardpack** → click the session → **Download PDF**. Real audit-grade document, brand-typeset.
9. **Audit** → see every turn, vote, mandate check, model invocation, treasury action — append-only, exportable as JSONL + manifest.

### What's live vs. simulated

| Component | State |
|---|---|
| Multi-agent debate · live LLMs | ✅ **Real Gemini calls** (verified end-to-end) |
| Mandate enforcement (4 gates, API-side) | ✅ Real |
| Two-party authorisation | ✅ Real (API + UI both enforce) |
| Audit log (append-only DB triggers) | ✅ Real |
| Boardpack PDF export | ✅ Real (PyMuPDF + reportlab) |
| Audit ZIP export (JSONL + manifest) | ✅ Real |
| LiveKit voice rooms | ✅ Token issuing live; sidecar STT bridge wired |
| **Kraken trading** | ⚠️ **Paper-mode only** — deliberate, audit-grade testnet for the hackathon |
| **Speechmatics STT** | ⚠️ Real client + real WS protocol; sidecar's LiveKit-subscription glue is v1.1 |
| **Email delivery** | ⚠️ Mailhog captures (visible at `:8025`); SMTP is v1.1 — judges sign in via the one-click panel |

See [`docs/SPONSOR_INTEGRATION_TRUTH.md`](./docs/SPONSOR_INTEGRATION_TRUTH.md) for the full A/B/C/D ladder per sponsor.

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
| Backend | Python 3.12 · FastAPI · SQLAlchemy 2.0 async · Postgres + pgvector | **381** ✅ | **90.68 %** |
| Frontend | React 18 · Vite · Tailwind · Zustand · React Query | **15** ✅ vitest + **16/20** Playwright | type-checked ✅ |
| E2E | Backend full demo flow + Playwright + Demo-video verification | 24/24 structural + 14/14 OCR | — |
| Pitch deck | 12 slides verified | 54/54 structural + 12/12 OCR | — |
| **Live LLM smoke** | 5-agent debate against real Gemini in 24.1 s | ✅ all `gemini/*`, consensus synthesised | — |

CI gate: `--cov-fail-under=85` (currently exceeding by 6 points).

---

## Quick start

### Local dev (no cloud accounts needed — uses mock inference)

```bash
git clone https://github.com/vsenthil7/atrio-boardroom
cd atrio-boardroom

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
# Backend — 381 tests
cd backend
python -m pytest

# Mandate violation corpus
python -m pytest tests/integration/test_mandate_violation_corpus.py -v

# Cross-tenant isolation
python -m pytest tests/integration/test_cross_tenant_isolation.py -v

# Full demo flow
python -m pytest tests/e2e/test_full_demo_flow.py -v

# Frontend unit
cd ../frontend
npm test

# Playwright E2E
npm run e2e:install   # once
npm run e2e

# Live-LLM smoke (requires real GEMINI_API_KEY in .env)
python demovideo/verification-a/smoke-live-gemini.py     # single agent
python demovideo/verification-a/smoke-live-debate.py     # full 5-agent debate
```

---

## Sponsor integrations

| Sponsor | Role | Where to look |
|---|---|---|
| **Vultr** | EU compute (Frankfurt, 4 vCPU/8 GB) | `deploy/01-bootstrap.sh`, `deploy/02-deploy.sh`, `deploy/03-tls.sh` |
| **Gemini** | Facilitator + Counsel primary model | `app/inference/providers.py` → `GeminiClient` |
| **Featherless** | CFO/CTO/CMO/COO primary models | `app/inference/providers.py` → `FeatherlessClient` |
| **Speechmatics** | Multilingual STT | `app/voice/speechmatics.py` |
| **Kraken** | Paper-trade execution | `app/treasury/kraken.py` |
| **LiveKit** | Voice rooms | `app/voice/service.py` |

Full honest inventory: [`docs/SPONSOR_INTEGRATION_TRUTH.md`](./docs/SPONSOR_INTEGRATION_TRUTH.md).

---

## Deploy to Vultr

See [`deploy/README.md`](./deploy/README.md) for the full playbook. Short version:

```bash
# On your laptop, with SSH access to a fresh Ubuntu 24.04 VM:
ssh root@<vm-ip> bash -s < deploy/01-bootstrap.sh    # OS + Docker
ssh root@<vm-ip> bash -s < deploy/02-deploy.sh       # repo + stack + migrations + seed
ssh root@<vm-ip> "DOMAIN=atrio.example.com bash" < deploy/03-tls.sh   # Caddy + Let's Encrypt
```

Total: ~15 minutes from blank VM to public HTTPS demo URL.

---

## What's NOT in this hackathon build

- **Authn**: magic-link only; no SSO/SAML.
- **Voice pipeline sidecar**: STT client real; LiveKit room-subscription glue is v1.1.
- **Email delivery**: Mailhog captures locally; production SMTP is v1.1. Judges use the one-click sign-in panel.
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
- [`docs/SPONSOR_INTEGRATION_TRUTH.md`](./docs/SPONSOR_INTEGRATION_TRUTH.md) — honest per-sponsor integration audit
- [`docs/ATRIO_Traceability_LIVE.md`](./docs/ATRIO_Traceability_LIVE.md) — live build status

---

## License

Apache 2.0 — see [LICENSE](./LICENSE).
