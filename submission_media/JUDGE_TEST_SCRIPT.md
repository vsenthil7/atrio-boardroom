# ATRIO Boardroom — Judge Test Script

**Live URL:** http://45.77.52.54:8080
**Time required:** 6 minutes
**What you'll see:** a real 5-agent AI boardroom debate · real mandate-gated treasury · two-party authorisation enforced by API · audit-grade everything.

This script is the exact walkthrough we recommend during judging. Every click is real. Every number lands. Every screen is reproducible.

---

## ⏱ 0:00 — Sign in (1 click, 1 second)

1. Open **http://45.77.52.54:8080** in any modern browser.
2. On the sign-in page you'll see a **"Judges · sign in with one click"** panel at the top with two buttons.
3. Click **"Demo founder"**.
4. ✅ You land on the **Sessions** page as `founder@acme.co`.

**Why no email?** Mailhog (the dev mail capture) holds the magic-link emails inside the VM — they're real, just not delivered externally. The one-click panel calls a separate `POST /auth/dev-signin` endpoint that's allowlisted to the two seeded demo accounts only. On a real production deploy this panel disappears and the standard magic-link email flow takes over.

---

## ⏱ 0:30 — Open a boardroom session (real LLMs, ~25 s)

1. In the **"What's on the table?"** input, paste:

   > **Should we hire 4 senior engineers in Q3 given an 18-month runway and a tight product roadmap?**

2. Click **OPEN SESSION**.
3. Watch the agents stream their answers, one at a time:

| Agent | Model | What it does | Typical latency |
|---|---|---|---|
| **CFO** | gemini/gemini-2.5-flash | Burn-rate math, runway impact, ROI framing | 4-5 s |
| **CTO** | gemini/gemini-2.5-flash (via Featherless→Gemini fallback) | Ramp-up velocity, technical risk, sequencing | 4-6 s |
| **CMO** | gemini/gemini-2.5-flash (fallback) | Market signal, demand validation | 4-6 s |
| **COO** | gemini/gemini-2.5-flash (fallback) | Onboarding overhead, operational feasibility | 4-5 s |
| **Counsel** | **gemini/gemini-2.5-pro** | Fiduciary duty, regulatory risk, governance | 13-16 s |

Total: **20-30 seconds** end-to-end. Real LLM calls — verified empirically on this exact URL (see commit `e54b911` smoke results).

**What you should see** (one example excerpt, from a live run):

> **CFO:** *"Hiring 4 senior engineers would increase our annual burn by approximately $1 million, reducing our current 18-month runway to about 15 months."*
>
> **Counsel:** *"This hiring plan materially accelerates our cash burn, heightening the fiduciary risk of insolvency... The board must be satisfied that the expected product velocity from these hires directly and demonstrably de-risks our next financing round. We must document this justification to fulfill our duty of care to the company and its investors."*

Each agent's answer ends with an **explicit stance** (`support` / `oppose` / `caveated` / `unclear`), and the system synthesises a **consensus**. If the agents split, the consensus is tagged `kind=split` with an **action list** that captures what would need to happen for the dissent to resolve.

---

## ⏱ 3:00 — Treasury proposal (mandate-enforced, API-gated)

1. In the top nav, click **TREASURY**.
2. You'll see the active **Mandate v1** for Acme Co:
   - Permitted instruments: `SHV-xStock, IEF-xStock, EURUSD-xStock`
   - Daily loss limit: **€25,000**
   - Single-instrument max: **€50,000**
   - Permitted sides: `buy, sell`
3. Click **PROPOSE TRADE**.
4. Fill in:
   - Instrument: **SHV-xStock**
   - Side: **buy**
   - Notional: **45000** (just under the cap, deliberately)
5. Click **PROPOSE**.
6. ✅ Proposal appears in state `mandate_passed → pending_first_auth`.

**Try a violation first if you want.** Set notional to **75000** (above the €50k cap). The API returns `409 Conflict` with `{"error":"mandate_violation","gate":"single_instrument_max","limit":50000,"requested":75000}`. The audit log captures the attempt. Try `tlt-xStock` (not in the permitted list) — refused at the `instrument_allowlist` gate. **4 gates run server-side**, not in the UI.

---

## ⏱ 4:00 — Two-party authorisation (cannot be bypassed)

1. As `founder@acme.co`, click **AUTHORISE** on the proposal.
2. ✅ Proposal moves to state `first_authorised`. You see *"1 of 2 signatures · awaiting second authoriser."*
3. **Now try to authorise it AGAIN as yourself.** Click **AUTHORISE** again.
4. ❌ API refuses: *"Same-user cannot self-second-sign."* The audit log captures the attempted self-second.

This is **not** a UI lock — the API enforces it. Pin the network tab if you want to see the `403 Forbidden`.

---

## ⏱ 4:30 — Bring in the second human (one more click)

1. Open a **new browser tab** (or incognito window): http://45.77.52.54:8080
2. On the sign-in screen, click **"Demo CEO"** in the judges panel.
3. ✅ You're signed in as `ceo@acme.co` in the same Acme Co tenant.
4. Click **TREASURY**.
5. The pending proposal shows in state `first_authorised` with founder's signature timestamped.
6. Click **AUTHORISE**.
7. ✅ Proposal advances to `second_authorised → executed`. The Kraken paper engine returns an order ID (e.g. `PAPER-D5C9F70AC0B8AAFD`) with executed price and quantity.
8. The audit log gains 5 new rows in real time.

---

## ⏱ 5:00 — Boardpack PDF + audit export

1. Back in either tab, go to **SESSIONS**.
2. Click the session you opened in step 0:30.
3. Click **DOWNLOAD BOARDPACK**. A real PDF downloads — typeset, brand-consistent, contains the question, every agent's response, consensus, action list, model attribution per turn, request IDs, timestamps.
4. Click **AUDIT** in the top nav.
5. You see every row chronologically:
   - `auth_signed_in` (×2 — both demo logins)
   - `session_opened`
   - `turn_submitted`
   - `agent_responded` × 5 (each with model, tokens-in/out, latency)
   - `consensus_synthesised`
   - `treasury_proposed`
   - `mandate_check_passed` × 4 (one row per gate)
   - `treasury_first_authorised`
   - `treasury_self_second_refused` (the attempt we made in step 4)
   - `treasury_second_authorised`
   - `treasury_executed`
   - `boardpack_generated`
6. Click **EXPORT AS JSONL**. You get a streamable JSON-lines file plus a SHA-256 manifest — exactly what compliance asks for.

---

## What you've just seen

| Promise | Evidence |
|---|---|
| **Real multi-agent debate** | 5 distinct agents, distinct models (Gemini 2.5 Flash + Pro), 20-30 s total, real intelligible content |
| **Mandate enforcement at API** | Try the €75k violation — refused server-side, not UI |
| **Two-party authorisation** | Self-second refused, audit captures attempt |
| **Audit-grade** | Every row exportable as JSONL + manifest |
| **Voice-first multilingual** | LiveKit token issuing live (sidecar finished v1.1) |
| **Production deploy** | Vultr Frankfurt, 4 vCPU / 8 GB, single public URL |

---

## Reproducing the proof yourself

Every test number in the pitch deck is reproducible from the repo:

```bash
git clone https://github.com/vsenthil7/atrio-boardroom
cd atrio-boardroom
docker compose -f docker/docker-compose.yml --env-file .env up

# 381 backend tests
docker exec atrio-api-1 pytest

# 5-agent live debate against your local stack
python demovideo/verification-a/smoke-live-debate.py

# 5-agent live debate against the production URL above
python demovideo/verification-a/smoke-live-prod.py
```

**Key verified numbers:**
- `381 / 381` backend tests pass at `90.68 %` line coverage
- `15 / 15` vitest pass · typecheck clean
- `16 / 20` Playwright (4 flakes are UI-text drift, not infrastructure)
- `24 / 24` demo-video structural verification
- `14 / 14` demo-video OCR verification at 100 %
- `54 / 54` pitch-deck structural verification
- `12 / 12` pitch-deck OCR verification at 100 %
- `5 / 5` agents return real LLM content in 20-30 s on production

---

## Questions to ask the team

We expect (and welcome) judges to push on:

1. **"How do you know it's not slideware?"** → smoke-live-prod.py runs against the public URL; we ran it 3× this morning, prints model_used + latency_ms + text for every agent.
2. **"What's the difference between 2.5-pro and 2.5-flash for your use case?"** → 2.5-flash for cost-sensitive specialist agents (4-5 s); 2.5-pro for Counsel where reasoning is the value (13-16 s, max_tokens=4096 to give the reasoning tokens budget — we shipped a fix for this in commit `a61e46f` when 2.5-pro at max_tokens=1024 was returning empty text).
3. **"Where does the audit log live? Can I tamper with it?"** → Postgres append-only triggers reject UPDATEs and DELETEs on the `audit_events` table; integration test `test_audit_immutability.py` pins this.
4. **"Can the founder bypass the second authoriser by editing the database?"** → No. The trade-execution path requires a state transition through `second_authorised` which the API will not write without two distinct user IDs.
5. **"What's actually production-ready vs paper here?"** → `docs/SPONSOR_INTEGRATION_TRUTH.md` is the honest A/B/C/D ladder per sponsor. Kraken is paper-mode by design (live trading on a hackathon submission is reckless). Speechmatics has the real WS client; LiveKit room-subscription glue is v1.1.

---

## License

Apache 2.0 — fork it, run it, ship it.

— *Verixa · Milan AI Week 2026*
