# ATRIO Demo Video — verification-a · Structural review

Re-runs the same end-to-end demo flow as `creation/` but with **hard assertions** at every scene gate. No video frame inspection — this is logic-level checking. If every assertion passes, the recorded video has by-construction shown all the right states.

## What it asserts (24 assertions across 4 stages)

### Stage 0 — Pre-flight + seed (6 assertions)
- A0.1 `/healthz` returns 200
- A0.2 `db.ok=true`
- A0.3 `/_test/seed-demo` returns 200
- A0.4 tenant_id present in seed body
- A0.5 founder_email = founder@acme.co
- A0.6 second_email = ceo@acme.co

### Stage 1 — Boardroom session (6 assertions)
- A1.1 sessions POST returns 2xx
- A1.2 session.id present
- A1.3 session.tenant_id matches seed
- A1.4 session.kind=boardroom
- A1.5 sessions list returns 200
- A1.6 list contains >= 1 session

### Stage 2 — Treasury propose + first auth + self-second BLOCKED (10 assertions)
- A2.1 mandates/active returns 200
- A2.2 mandate is_active=true
- A2.3 mandate has permitted instruments
- A2.4 propose POST returns 2xx
- A2.5 proposal.id present
- A2.6 proposal.state=proposed
- A2.7 first authorise returns 2xx
- A2.8 state=first_authorised
- A2.9 self-second by same user is REFUSED (>= 400)
- A2.10 self-second is NOT a 5xx (it is a deliberate refusal, not a bug)

### Stage 3 — CEO authorises (2 of 2) → executed (3 assertions)
- A3.1 second authorise returns 2xx
- A3.2 state is second_authorised or executed
- A3.3 final state is executed (Kraken paper settled)

### Stage 4 — Close session + boardpack + audit (8 assertions)
- A4.1 close session returns < 300
- A4.2 boardpack GET returns 200
- A4.3 boardpack content-type is application/pdf
- A4.4 boardpack starts with %PDF-
- A4.5 audit GET returns 200
- A4.6 audit contains kinds: auth_signed_in, treasury_proposed, treasury_first_authorised, session_closed
- A4.7 audit/export returns 200
- A4.8 audit/export content-type is application/zip

## Run

```powershell
pwsh ./demovideo/verification-a/run-verify-a.ps1
```

Requirements:
- Docker stack up (`atrio-api-1`, `atrio-postgres-1` healthy)
- Isolated runner installed at `demovideo/.runner/`

Outputs:
- Console: pass/fail summary
- Full report: `verification-a/reports/structural-review-{timestamp}.txt`
