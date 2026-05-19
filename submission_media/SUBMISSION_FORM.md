# lablab.ai submission — copy-paste reference

All fields below are ready to paste directly into the lablab.ai form for
AT-Hack0021 / Milan AI Week 2026. Numbers are reproducible on the repo
(see verification-a / verification-b reports).

**🎬 LIVE DEMO IS UP:** `http://45.77.52.54:8080` (Vultr · Frankfurt · 4 vCPU / 8 GB)

---

## Project name (1 line, ≤ 60 chars)

```
ATRIO Boardroom — your AI boardroom
```

(36 chars; under any sensible cap)

---

## Tagline / one-liner (1 line, ≤ 140 chars)

```
Voice-first multilingual AI boardroom. Six specialist agents. Mandate-enforced treasury. Audit-grade by default.
```

(112 chars)

---

## Short description (1-2 sentences, ≤ 250 chars)

```
ATRIO turns one founder's question into a 60-second multi-agent debate with six specialist personas (CFO, CTO, CMO, COO, Counsel, Facilitator). Every turn, vote, and treasury action is mandate-checked at the API and written to an append-only audit log.
```

(248 chars)

---

## Long description (Markdown allowed)

```
**Founders and family offices decide alone.** Big calls today get either delegated
to a single advisor (fast, single point of failure) or convened with a committee
(slow, hard to schedule, hard to audit). ATRIO Boardroom is the middle option:
an AI boardroom that holds a real debate, enforces a per-tenant mandate at machine
speed, and replays every decision in six months.

## Try it now

**Live demo (Vultr, Frankfurt):** http://45.77.52.54:8080

Click **"Demo founder"** on the sign-in screen — one click, no email needed —
then in "What's on the table?" type:

> *Should we hire 4 senior engineers in Q3 given an 18-month runway?*

Watch 5 distinct AI specialists stream their reasoning live (real Gemini 2.5 calls,
~25 s end-to-end), then go to Treasury, propose a SHV-xStock buy, try to self-second
(API refuses), open a new tab → sign in as **Demo CEO** → second-authorise → trade
executes against the Kraken paper engine. Download the boardpack PDF. Open the audit
log. Six minutes, full lifecycle.

## Why we built it

The wedge isn't "better LLM responses." It's the **boardroom seat between**
one-expert-on-a-call and a full human board:

- **Debate**, not consensus-on-rails. Six personas with distinct system prompts,
  distinct model assignments, and dissent-driven turn-taking. Dissent triggers
  re-runs until either consensus emerges or the action list captures the
  unresolved trade-off.
- **Enforce**, at the API. A per-tenant `Mandate v1` (permitted instruments,
  daily loss limit, single-instrument max, permitted side) is the only path
  to a treasury action. Two-party authorisation cannot be bypassed by the UI.
- **Audit**, by default. Every turn, vote, model invocation, and state
  transition writes to an append-only log. Exportable as JSONL + manifest;
  ingestable by compliance.

## What the demo video shows (2 minutes)

1. **Boardroom debate** — Founder asks "Should we hire 4 senior engineers in Q3
   given our 18-month runway?". Six agents stream their reasoning live. Dissent
   rounds logged. Consensus + action list rendered.
2. **Treasury proposal · two-party blocked** — Founder proposes a SHV-xStock buy.
   Mandate gates check at the API. Founder authorises (1 of 2). Founder TRIES
   to self-second — REFUSED. Audit captures the attempt.
3. **Second human** — CEO signs in on a separate browser (same tenant), sees the
   proposal in `first_authorised`, authorises (2 of 2). Trade executes against
   Kraken paper. Audit gains 5 rows.
4. **Boardpack PDF + audit ZIP** — Session closed. Boardpack regenerated and
   downloaded. Audit page rendered. Export as JSONL + manifest.

## Why this isn't slideware

Everything is reproducible from the repo:

- **381 / 381** backend tests pass at **90.68 %** line coverage (gate 85 %)
- **15 / 15** vitest pass · typecheck clean
- **16 / 20** Playwright pass against the live Docker stack
- **24 / 24** demo-video structural verification (hard API assertions)
- **14 / 14** demo-video OCR verification at 100 %
- **54 / 54** pitch-deck structural verification
- **12 / 12** pitch-deck OCR verification at 100 %
- **5 / 5** live multi-agent debate against real Gemini in 24.1 s (no mocks)
- **15** real bugs found and fixed during the sprint, documented in the commit ledger

## Sponsor pools utilised

- **Vultr** — EU compute (Frankfurt, 4 vCPU / 8 GB) — the public demo URL above
- **Google Gemini** — Primary inference for Facilitator + CFO + Counsel + treasury
- **Featherless** — Specialist routes for CTO + CMO + COO (with Gemini fallback)
- **Speechmatics** — Live STT WebSocket client (sidecar wiring is v1.1)
- **Kraken xStocks** — Treasury execution (paper-mode for the hackathon; live mode is one config flip)
- **LiveKit** — Voice rooms (token issuing live)

See `docs/SPONSOR_INTEGRATION_TRUTH.md` for the full A/B/C/D honest inventory.

## Tech stack

- Backend: FastAPI · SQLAlchemy 2.0 async · Alembic · Postgres 16 + pgvector · uvicorn
- Frontend: React 18 · Vite · Tailwind · Zustand · React Query
- Infra: Docker Compose (6 services) · Caddy · LiveKit · MinIO · Mailhog
- Quality gates: pytest · vitest · Playwright · custom PDF + video verifications
- License: Apache 2.0
```

---

## Tags / categories (pick from lablab.ai's list)

**Primary track:**
```
Collaborative Systems
```

**Secondary tracks (if multi-select allowed):**
```
Agentic Workflows
Multimodal Intelligence
```

**Technologies / topics (tag soup):**
```
multi-agent
voice-first
treasury
audit
fastapi
react
postgres
docker
gemini
featherless
speechmatics
kraken
livekit
pgvector
caddy
playwright
pytest
boardroom
governance
mandate
two-party-authorisation
fintech
agents
debate
consensus
sponsorship-vultr
sponsorship-google
sponsorship-featherless
sponsorship-speechmatics
sponsorship-kraken
milan-ai-week
hackathon
ai-boardroom
verixa
```

---

## Submission artefacts checklist

| Artefact | Path | Status |
|---|---|---|
| Pitch deck PDF | `atrio/submission_media/atrio-pitch-deck-20260519_105149.pdf` (402 KB) | ✅ verified |
| Pitch deck PPTX (editable) | `atrio/submission_media/atrio-pitch-deck-20260519_105149.pptx` (49 KB) | ✅ |
| Demo video (primary) | `atrio/demo/atrio-walkthrough-20260519_090929-main.mp4` (2.7 MB) | ✅ verified |
| Demo video (CEO secondary) | `atrio/demo/atrio-walkthrough-20260519_090929-secondary-2.mp4` (1.05 MB) | ✅ |
| Cover image square | `atrio/submission_media/cover-square-1200x1200.png` (60 KB) | ✅ |
| Cover image banner | `atrio/submission_media/cover-banner-1600x900.png` (66 KB) | ✅ |
| Cover image OG | `atrio/submission_media/cover-og-1200x630.png` (46 KB) | ✅ |
| GitHub repo | https://github.com/vsenthil7/atrio-boardroom (33 commits, public) | ✅ |
| **Live demo URL** | **http://45.77.52.54:8080** (Vultr, Frankfurt) | ✅ LIVE |

---

## Field-by-field paste cheatsheet (when filling lablab.ai)

| lablab field | Source above |
|---|---|
| Project name | "Project name" |
| Tagline / catchphrase | "Tagline / one-liner" |
| Short description | "Short description" |
| Description (main body) | "Long description" (Markdown) |
| Cover image upload | `cover-square-1200x1200.png` |
| GitHub URL | `https://github.com/vsenthil7/atrio-boardroom` |
| **Demo URL** | **`http://45.77.52.54:8080`** |
| Pitch video URL (or upload) | `atrio-walkthrough-20260519_090929-main.mp4` |
| Pitch deck (PDF upload) | `atrio-pitch-deck-20260519_105149.pdf` |
| Track / challenge | Collaborative Systems (+ Agentic Workflows + Multimodal Intelligence) |
| Tags | from "Technologies / topics" list |
| Team | Verixa (solo founder + Claude as paired engineer) |
| License | Apache 2.0 |

---

## Judge instructions to add to the description

If lablab.ai's description supports a short "How to try the demo" callout, use:

```
1. Open http://45.77.52.54:8080
2. Click "Demo founder" — signs you in with one click
3. Type a boardroom question (suggested: "Should we hire 4 senior engineers in Q3 given an 18-month runway?")
4. Watch live multi-agent debate (real Gemini calls, ~25s)
5. Open second tab → click "Demo CEO" → second-authorise a treasury proposal to see two-party flow
```
