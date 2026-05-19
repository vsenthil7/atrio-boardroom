# ATRIO Demo Runbook — Milan AI Week 2026

This is the exact script for the 4-minute pitch. Read it cold; every action
maps to a UI element that has a deterministic `data-testid` and an existing
Playwright spec that asserts the same flow.

---

## Pre-demo (90 seconds before going live)

1. **Set the room up**
   ```bash
   cd atrio
   make up                                 # bring the full stack online
   ./scripts/smoke.sh                      # verify all endpoints are green
   curl -X POST http://localhost:8000/api/v1/_test/seed-demo
   ```

2. **Two browsers, side by side**
   - Browser A (founder): `http://localhost:8080/signin` — sign in as `founder@acme.co`
   - Browser B (authoriser): `http://localhost:8080/signin` — sign in as `ceo@acme.co`
   - Position them on stage so the audience can see both.

3. **A clean projector**: zoom to 110%. Dark mode off.

---

## The 4-minute script

### Minute 0:00 — Open (30 s)

> "Founders and family offices today either delegate big decisions to a single
> advisor — who can be wrong — or to a committee, which is slow. We built a
> third option: a six-agent AI boardroom that holds an audited debate, then
> executes inside hard guardrails. Watch."

### Minute 0:30 — Boardroom debate (60 s)

**Browser A (founder)**:
1. Click **Open session**: title "Should we hire 4 senior engineers in Q3?"
2. Drop the PDF `demo/q3-burn-plan.pdf` into the upload zone.
3. Type: *"Should we hire 4 senior engineers in Q3 given our 18-month runway?"*
4. Click **Ask**.

> "Six specialists arrive at once: CFO worries burn, CTO confirms scope is
> reasonable, CMO ties hiring to a Q4 narrative, COO flags onboarding load,
> Counsel does an employment-law check, Facilitator decides which threads
> need a second round. They argue — when they disagree, we re-run the
> dissenters. Look at this row..."

Point to the **Dissent round 1** label. Point to the `↺ fallback` badge if
visible. Point to the **Consensus** card and the **Action list**.

### Minute 1:30 — Treasury proposal (60 s)

**Browser A (founder)**:
1. Click **Open treasury** in the sidebar.
2. Pick the session, instrument **SHV-xStock**, side **buy**, qty **10**.
3. Click **Propose**.

> "Watch the mandate badges — instrument permitted, side permitted,
> single-instrument cap OK, daily-loss limit OK. **All four gates pass at
> the API layer, not the UI.** A bad client cannot bypass these."

4. Click **Authorise (1 of 2)**.

> "First authorisation. Now I'll try to second-authorise as myself..."

5. Try to click **Authorise** again on Browser A.

> "Blocked. **Two-party authorisation** is enforced by the API. A founder
> cannot self-execute a trade. The audit log already records the attempt."

### Minute 2:30 — The second human (40 s)

**Browser B (CEO)**:
1. Open the Treasury page.
2. Show the same proposal sitting in `first_authorised` state.
3. Click **Authorise (2 of 2)**.

> "Second human, different role. The trade executes against Kraken's paper
> book, the order ID and execution price come back, the state machine
> advances to **executed**, the audit log gains five new entries."

Show the executed row, point to the order ID and price.

### Minute 3:10 — Boardpack + audit (40 s)

**Browser A (founder)**:
1. Back to the session, click **Close session**.
2. Click **Download boardpack** — show the PDF.

> "The boardpack PDF is the receipt of the conversation: every turn, every
> dissent, every model invocation, the consensus, the action list, the
> treasury actions. It's signed with the request ID chain."

3. Navigate to **Audit**.
4. Click **Export ZIP**.

> "Every event since the tenant was created — `auth_signed_in`,
> `model_invocation`, `treasury_proposed`, `treasury_first_authorised`,
> `treasury_executed`, `session_closed` — exported as JSON-Lines plus a
> manifest. Compliance teams can ingest this directly."

### Minute 3:50 — Close (10 s)

> "Audit-grade from line one. Mandate-enforced at the API. Multi-tenant
> from the database. 319 backend tests, 91% coverage, 16 Playwright specs
> including the two-party-authorisation bypass attempt. Open source under
> Apache 2.0. Thank you."

---

## Anti-failure drills

| If… | Then… |
|---|---|
| Stack didn't start | `make down && make up` — postgres needs ~10s |
| Mock inference looks "wrong" | The Mock returns deterministic per-agent text; that IS correct |
| Browser B doesn't see the proposal | Hit `Cmd-R` — React Query refetches |
| Boardpack download is empty | Close the session first — boardpack regenerates on close |
| Mic permission denied | Voice controls show join button; demo doesn't depend on voice |
| LiveKit room not joinable | Skip voice; the SSE debate is the main act |

---

## Phrases the audience will remember

Pick **three** and lean on them:

- *"Mandate enforcement at the API, not the UI."*
- *"Two-party authorisation is impossible to bypass — we have a test that proves it."*
- *"Cross-tenant access is impossible — 17 dedicated tests."*
- *"Audit-grade by default."*
- *"The model registry is the only path to inference."*

---

## Setup checklist (the night before)

- [ ] `.env` populated with real Gemini + Featherless keys (if running live, not mock)
- [ ] `.env` has `ATRIO_MOCK_INFERENCE=false` for real demo, `true` for fallback
- [ ] `secrets/jwt_private.pem` and `jwt_public.pem` generated
- [ ] `make up` and `./scripts/smoke.sh` both green
- [ ] PDF `demo/q3-burn-plan.pdf` exists (Acme Q3 hiring plan)
- [ ] Browser A and B signed in
- [ ] LiveKit room reachable (optional)
- [ ] Backup laptop running the same stack
