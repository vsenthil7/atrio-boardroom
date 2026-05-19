# ATRIO Demo Video Pipeline

Captioned, narration-free 4-5 minute walkthrough recorded via Playwright,
with **two independent verifications** (structural + vision) that prove
the recording shows the right states.

Ported from the MendoraCI (AT-Hack0020) and Auditex (AT-Hack0014) sibling
projects. Same isolated-runner pattern, same caption-overlay helper,
same verification-a + verification-b split.

## Folder layout

```
demovideo/
  README.md                                 # this file
  creation/
    run-creation.ps1                        # 4-step orchestrator: preflight -> seed -> record -> archive
    README.md
  verification-a/
    structural-review.spec.ts               # 24 hard assertions against live API
    run-verify-a.ps1
    README.md
  verification-b/
    extract-frames.py                       # ffmpeg wrapper
    grade-frames.py                         # OCR + rubric
    run-verify-b.ps1                        # pre-flight + extract + grade + report
    requirements.txt
    README.md
  .runner/                                  # isolated Playwright install (gitignored)
    package.json
    playwright.demo.config.ts
    specs/
      caption-overlay.ts
      full-walkthrough.spec.ts
  results/
    creation/
      latest.txt                            # pointer to most recent recording (gitignored)
```

## End-to-end pipeline

```powershell
# 0) bring stack up
cd atrio
docker compose -f docker/docker-compose.yml --env-file .env up -d

# 1) install isolated runner (first time only)
cd demovideo/.runner
npm install
.\node_modules\.bin\playwright.cmd install chromium
cd ../..

# 2) RECORD the demo
pwsh ./demovideo/creation/run-creation.ps1
#    -> demo/atrio-walkthrough-{stamp}-main.mp4

# 3) VERIFY-A — structural review (24 hard assertions, ~30s)
pwsh ./demovideo/verification-a/run-verify-a.ps1
#    -> verification-a/reports/structural-review-{stamp}.txt

# 4) VERIFY-B — vision review (OCR + rubric, ~2-3min)
pwsh ./demovideo/verification-b/run-verify-b.ps1
#    -> verification-b/reports/vision-review-{stamp}.json
```

Both verifications passing on the same commit is the by-construction proof
that the recorded video shows the right states. We commit the verification
reports alongside the video.

## What the 4-minute video shows

Per `docs/DEMO_RUNBOOK.md`:

| Stage | Actor | What | Duration |
|---|---|---|---|
| Opening title | — | ATRIO branding + Milan AI Week 2026 marker | 7s |
| 1 — Boardroom debate | Founder | Sign in · open session · upload Q3 burn-plan PDF · ask hiring question · 6 agents debate · consensus + action list | ~60s |
| 2 — Treasury propose + self-second BLOCKED | Founder | Propose SHV-xStock buy · authorise (1 of 2) · TRY to self-second → **REFUSED by API** · audit captures attempt | ~40s |
| 3 — Second human (CEO) | CEO | Sign in (separate browser, same tenant) · open Treasury · authorise (2 of 2) · trade EXECUTES on Kraken paper | ~40s |
| 4 — Boardpack + audit | Founder | Close session · download boardpack PDF · audit page · export ZIP (JSONL + manifest) | ~40s |
| Closing title | — | 381 tests · 90.68% coverage · Apache 2.0 · repo URL | 7s |

## Prerequisites

- Docker Desktop running
- `atrio-api-1`, `atrio-frontend-1`, `atrio-postgres-1` all healthy
- Frontend on `http://localhost:8080`, API on `http://localhost:8000`
- Node 20+ on host
- ffmpeg + Tesseract on PATH (for verification-b)
- Python 3.10+ with pillow + pytesseract (for verification-b)

## Outputs committed to git

| Path | What | Tracked? |
|---|---|---|
| `demo/atrio-walkthrough-*.mp4` | MP4 recording (lablab.ai upload) | ✅ yes (via `git add -f`) |
| `demo/atrio-walkthrough-*.webm` | WebM source | ❌ gitignored |
| `demo/_backup/` | Backups | ❌ gitignored |
| `demovideo/.runner/` | Isolated Playwright install | ❌ gitignored |
| `demovideo/results/creation/latest.txt` | Pointer | ❌ gitignored |
| `demovideo/verification-a/reports/*.txt` | Structural review reports | ✅ yes |
| `demovideo/verification-b/reports/*.json` | Vision review reports | ✅ yes |
| `demovideo/verification-b/frames/` | OCR working dir | ❌ gitignored |
