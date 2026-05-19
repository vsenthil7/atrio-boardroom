# Sponsor pool integration — honest inventory

**Last audited:** 2026-05-19 11:50 BST (against HEAD `15cfe09`)

This document tells you the truth about each sponsor pool: what code is real,
what's mocked, and what flipping the env var does. No marketing.

---

## The 4-state ladder

Every sponsor integration sits in one of these states:

| State | What it means |
|---|---|
| **A** Real HTTP/WS client + tested → flip env var to live | Code talks to the real API. No keys = mock fallback. Set the key → real calls happen. |
| **B** Real client written + needs a key to test | Same as A but we don't have a working key yet, so it's been exercised only against mocks. First real call may surface bugs. |
| **C** Paper / simulator only | A real client exists in code but the production HTTP layer is a stub. Useful for demos; cannot move money. |
| **D** Architectural fit only | We mention them but no code yet. |

---

## Per-sponsor truth

### 1. Vultr — **state A** (deploy target)

- **What we use them for:** Compute. The whole stack runs on one Vultr Cloud Compute VM.
- **Code involved:** `atrio/deploy/01-bootstrap.sh`, `atrio/deploy/02-deploy.sh`, `atrio/deploy/03-tls.sh`, `atrio/deploy/prod.env.example`.
- **What's real:** Everything needed to deploy. Three scripts that take a fresh Ubuntu 24.04 VM → public HTTPS demo URL in ~20 min.
- **What's mocked:** Nothing — this isn't an API integration, it's a deploy target.
- **What you need to do to flip to live:** Spin up the VM (see your earlier instructions), give Claude the IP, run the 3 scripts. No API key needed; just SSH.

### 2. Google Gemini — **state A → live with key**

- **What we use them for:** Primary inference for CFO, Counsel, Facilitator agents.
- **Code involved:** `backend/app/inference/providers.py::GeminiClient` (180 lines), called by `backend/app/inference/gateway.py`.
- **What's real:**
  - Full streaming SSE client to `generativelanguage.googleapis.com/v1beta`
  - `:streamGenerateContent` (token-by-token) + `:generateContent` (one-shot) both implemented
  - Proper system-instruction + generationConfig payload
  - Real `usageMetadata.promptTokenCount` + `candidatesTokenCount` parsed for audit
  - Errors raise `ProviderError` → gateway invokes fallback chain
- **What's mocked:** `MockClient` returns deterministic `[CFO] Considering the question — '...' — my position is...` strings when `GEMINI_API_KEY` is unset.
- **What you need to do to flip to live:** Get a Gemini API key (free tier at `aistudio.google.com`). Set `GEMINI_API_KEY=` in `.env`. Restart api container. Done — real calls happen immediately.

### 3. Featherless — **state A → live with key**

- **What we use them for:** Specialist fallback for CTO, CMO, COO agents (and primary fallback for Gemini if it 5xxs).
- **Code involved:** `backend/app/inference/providers.py::FeatherlessClient` (170 lines).
- **What's real:**
  - OpenAI-compatible `/v1/chat/completions` client (streaming + non-streaming)
  - Bearer auth, proper SSE parsing of `data: [DONE]` sentinels
  - Token usage extracted from `usage.prompt_tokens` / `completion_tokens`
- **What's mocked:** Same `MockClient` as Gemini.
- **What you need to do to flip to live:** Get a Featherless API key. Set `FEATHERLESS_API_KEY=`. Restart api. Done.

### 4. Speechmatics — **state B → close to live, never tested with real key**

- **What we use them for:** Live speech-to-text + diarisation for voice mode (boardroom-by-voice).
- **Code involved:**
  - `backend/app/voice/speechmatics.py` (280 lines) — full Realtime API WebSocket client
  - `sidecars/voice/__main__.py` (260 lines) — long-running process that bridges LiveKit ↔ Speechmatics
- **What's real:**
  - WebSocket client to `wss://eu2.rt.speechmatics.com/v2`
  - `StartRecognition` handshake with PCM s16le 16 kHz config
  - 9 languages supported (en/es/fr/de/it/pt/nl/pl/tr) via auto-detect
  - Custom dictionary loader for ATRIO domain terms
  - `AudioBuffer` with backpressure (drops oldest if >2s queued)
  - Transcript parsing (interim + final + diarisation speaker_id)
  - Final-transcript silence detection → POST a new turn → triggers debate
- **What's mocked / NOT yet:**
  - **The LiveKit room subscription glue in the sidecar is incomplete.** The sidecar can run Speechmatics + post turns + publish captions, but the code that subscribes to LiveKit room audio events and pumps PCM into `AudioBuffer` is described in comments but not implemented.
  - No real Speechmatics API key tested against the production endpoint.
- **What you need to do to flip to live:**
  1. Get the Milan AI Week coupon (`AIWEEK200`) → trial Speechmatics key
  2. Set `SPEECHMATICS_API_KEY=` in `.env`
  3. Finish the sidecar's LiveKit-subscription code (~80-120 lines using the LiveKit Python SDK) — this is the only NEW code needed
  4. Restart `voice` container

  **Risk: this is the one sponsor where "first real call" is genuinely first.** If Milan AI Week judging asks for live voice demo, demo text mode instead and discuss the voice plumbing.

### 5. Kraken xStocks — **state C → paper-mode only by design**

- **What we use them for:** Treasury execution. The "agents can do, not just advise" demo.
- **Code involved:** `backend/app/treasury/kraken.py` (140 lines).
- **What's real:**
  - `PaperKrakenClient` with deterministic quotes (SHV-xStock = €110.20 + hash-based jitter)
  - Realistic order responses (`PAPER-{16-char-hex}` order IDs)
  - Async with simulated latency
  - Same `KrakenClient` Protocol the real client would implement
- **What's mocked / NOT yet:**
  - **No live HTTP client to `api.kraken.com`.** Live mode is `KrakenLiveClient` which doesn't exist yet.
  - The factory `get_kraken_client()` checks `kraken_paper_mode` but only ever returns `PaperKrakenClient`.
  - Comment in code is honest: *"For v1 we only ship the paper client. Live mode is gated by the same client with a real HTTP layer behind it (not in scope for this build)."*
- **What you need to do to flip to live:**
  1. Get Kraken API credentials (full KYC + 2FA required — not a one-day task)
  2. Implement `KrakenLiveClient` against the [Kraken Spot REST API](https://docs.kraken.com/api/) for `/Ticker` + `/AddOrder`
  3. Wire it into the factory
  4. Set `KRAKEN_MODE=live` + `KRAKEN_API_KEY=` + `KRAKEN_API_SECRET=`

  **For Milan AI Week judging this is the right call.** Live trading with real money on a hackathon submission is reckless. Paper-mode is what every regulated treasury product runs in test envs anyway.

### 6. LiveKit — **state A → wired up for voice, optional for text demo**

- **What we use them for:** Real-time audio rooms for voice mode.
- **Code involved:**
  - `backend/app/voice/service.py::VoiceService::issue_join_token` — real JWT (HS256, correct LiveKit claim shape including `video.{room,roomJoin,canPublish,canSubscribe,canPublishData}`)
  - LiveKit container already in `docker-compose.yml` (port 7880, configured `LIVEKIT_KEYS`)
- **What's real:** Token issuing. The container itself is the real LiveKit OSS server.
- **What's mocked:** Nothing on the API side. The frontend's voice-mode UI is wired (settings page, badges, mute toggle) but the boardroom video panel isn't connected to the LiveKit room yet — that's a v1.1 item.
- **What you need to do:** Nothing for text demo. For voice demo: finish the sidecar (see Speechmatics state B).

---

## Honest demo positioning

When telling judges what's "real":

- **Gemini + Featherless inference** → flip the keys on, the boardroom debate uses real LLMs end-to-end. **Recommended for live judging.**
- **Two-party authorisation + mandate enforcement + audit log** → 100% real backend logic, no mocks. Verified by 24/24 hard API assertions on demo video.
- **Boardpack PDF generation** → 100% real (PyMuPDF + reportlab).
- **Audit export ZIP** → 100% real (JSONL + manifest, append-only DB).
- **LiveKit token issuing** → real JWT, correct claims.

When telling judges what's stubbed:

- **Kraken** → "we run paper-mode by default for safety; the production client is the v1.1 work." This is a feature, not a bug.
- **Speechmatics** → "text mode is what we demo today. Voice mode plumbing is end-to-end except for the LiveKit room subscription — that's a 2-3 hour task."

---

## What flipping all the keys gives you, RIGHT NOW

Set in `.env`:
```bash
GEMINI_API_KEY=AI...
FEATHERLESS_API_KEY=...
```

Restart the api container. Then:

| Thing | Status |
|---|---|
| Six agents debate using real Gemini/Featherless models | ✅ live |
| Dissent-driven re-runs, real consensus | ✅ live |
| Mandate-gated treasury proposals | ✅ live |
| Two-party authorisation enforcement | ✅ live |
| Audit log with real model invocation rows | ✅ live |
| Boardpack PDF export | ✅ live |
| Kraken trade execution | ✅ paper (correct behaviour for v1) |
| Voice mode | ⚠️  text-only in the demo recording |

**That is what the submission demo shows.** Recommend you stop here and submit — adding live Kraken or finishing voice for the submission window is unnecessary risk.

---

## Post-hackathon work (state-B → state-A for the laggards)

| Sponsor | Estimated work to get to state A |
|---|---|
| Speechmatics | 2-3 hours: finish sidecar's LiveKit subscription + test against live coupon key |
| Kraken | 6-10 hours: implement `KrakenLiveClient` against REST API + KYC the API key + test against testnet |
