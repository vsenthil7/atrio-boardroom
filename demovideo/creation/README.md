# ATRIO Demo Video — Creation pipeline

Builds the full 4-minute walkthrough video using an isolated Playwright runner.

## Run

```powershell
pwsh ./demovideo/creation/run-creation.ps1
```

Steps the script performs:
1. **Pre-flight** — verifies `atrio-api-1`, `atrio-frontend-1`, `atrio-postgres-1` are up;
   runs `tools/healthcheck.ps1 docker` and aborts if any service is unhealthy.
2. **Reset** — POSTs `/api/v1/_test/seed-demo` to install a clean tenant
   (founder@acme.co + ceo@acme.co + mandate v1) so the recording is deterministic.
3. **Record** — runs the captioned `full-walkthrough.spec.ts` against
   `http://localhost:8080` (Caddy SPA) + `http://localhost:8000` (FastAPI).
4. **Archive** — trims leading 0.5s blank frame, transcodes to MP4
   (h264/crf22) for lablab.ai upload, copies both webm + mp4 into `demo/`
   and `demo/_backup/`. Pointer in `results/creation/latest.txt`.

## Outputs

- `demo/atrio-walkthrough-{stamp}-main.mp4`   — founder browser (PRIMARY upload)
- `demo/atrio-walkthrough-{stamp}-main.webm`  — same, webm source
- `demo/atrio-walkthrough-{stamp}-secondary-2.{mp4,webm}` — CEO browser
- `demo/_backup/`                             — backups (gitignored)
- `demovideo/results/creation/latest.txt`     — pointer (gitignored)

## Demo flow (matches `docs/DEMO_RUNBOOK.md`)

| Stage | Actor | What happens | Duration |
|---|---|---|---|
| Opening title | — | ATRIO branding | 7s |
| 1 — Boardroom debate | Founder | Sign in, open session, upload PDF, ask Q3 hiring question, watch 6 agents debate | ~60s |
| 2 — Treasury propose | Founder | Open treasury, propose SHV-xStock buy, authorise (1 of 2), TRY to self-second → BLOCKED | ~40s |
| 3 — Second human | CEO  | Sign in (separate browser), open treasury, authorise (2 of 2), trade executes | ~40s |
| 4 — Boardpack + audit | Founder | Close session, audit page, export ZIP | ~40s |
| Closing title | — | Test counts + repo link | 7s |
| **Total** | | | **~4-5 min** |

## Prerequisites

- Docker Desktop running, `docker compose -f docker/docker-compose.yml up -d` complete
- Frontend on `http://localhost:8080` (Caddy)
- API on `http://localhost:8000` (FastAPI)
- Node 20+ on host (for isolated runner)
- ffmpeg on PATH (Windows: `winget install Gyan.FFmpeg`)
- `demo/q3-burn-plan.pdf` present (ships with repo)

## First-time setup

The isolated runner installs its own Playwright at `demovideo/.runner/` so it
cannot collide with frontend dev deps:

```powershell
Set-Location demovideo/.runner
npm install
.\node_modules\.bin\playwright.cmd install chromium
```

Subsequent runs just use `pwsh ./demovideo/creation/run-creation.ps1`.

## Two browser contexts

The spec uses TWO browser contexts (founder + ceo) to demonstrate the
two-party authorisation rule. Playwright records each context separately,
so you get two webm files. The PRIMARY upload to lablab.ai should be the
**founder context** (it covers Stages 1, 2, 4); the CEO context covers
Stage 3 alone. For a single combined video you can use OBS or ffmpeg
side-by-side (post-processing — not done here).
