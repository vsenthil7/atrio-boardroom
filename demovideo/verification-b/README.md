# ATRIO Demo Video — verification-b · Vision-based review

Genuinely watches the recorded demo video. Uses **ffmpeg** to extract still frames at 1 per 2 seconds, then **Tesseract OCR** to read the captions and UI text in each frame, and grades against a rubric.

## Why both verifications

| | verification-a (structural) | verification-b (vision) |
|---|---|---|
| **Checks** | Backend state at each scene gate | Caption + UI text visible on-screen |
| **Method** | Live API calls + assert | OCR every Nth frame |
| **Catches** | Wrong proposal state · missing audit kind · no PDF · wrong content-type | Caption typo · scene card missing · pill never shown · video clipped |
| **Speed** | ~30s | ~2-3 min |
| **Stand-alone evidence** | "If A passes, the API was demonstrably correct" | "If B passes, the viewer literally saw the right text" |

Both passing together is the "by-construction proof" that the video shows the right story.

## Modular pieces

- `extract-frames.py` — ffmpeg wrapper, 1 frame per 2s default
- `grade-frames.py` — OCR + RUBRIC list; outputs JSON
- `run-verify-b.ps1` — pre-flight + extract + grade + report
- `requirements.txt` — Python deps (pillow, pytesseract, opencv-headless)

## One-time prerequisites

```powershell
winget install Gyan.FFmpeg
winget install UB-Mannheim.TesseractOCR
pip install -r demovideo/verification-b/requirements.txt
```

## Run

```powershell
pwsh ./demovideo/verification-b/run-verify-b.ps1
```

Reads the latest recorded video from `demovideo/results/creation/latest.txt`.

## Rubric (14 items)

| Rubric item | Required substrings |
|---|---|
| title-card-opening | ATRIO · MILAN AI WEEK |
| stage-1-scene-card | STAGE 1 · BOARDROOM DEBATE · GIVEN · WHEN · THEN |
| stage-1-six-agents-pill | six agents · streaming |
| stage-1-consensus-pill | Consensus · action list |
| stage-2-scene-card | STAGE 2 · TREASURY · MANDATE · TWO-PARTY |
| stage-2-propose-pill | Proposed · SHV-xStock |
| stage-2-self-second-blocked | Self-second BLOCKED · audit recorded |
| stage-3-scene-card | STAGE 3 · SECOND HUMAN · AUTHORISE |
| stage-3-ceo-signed-in | CEO signed in · same tenant |
| stage-3-trade-executed | EXECUTED · Kraken paper |
| stage-4-scene-card | STAGE 4 · BOARDPACK · AUDIT EXPORT |
| stage-4-session-closed | Session closed |
| stage-4-audit-export | Audit · JSONL |
| title-card-closing | ATRIO · Mandate-enforced · Apache 2.0 |

To extend, edit `RUBRIC` in `grade-frames.py`.

## Output

`verification-b/reports/vision-review-{timestamp}.json` — per-rubric pass/fail + overall pass rate.

Example:
```json
{
  "frames": 142,
  "rubric": [
    { "rubric": "title-card-opening", "passed": true, "needles": ["ATRIO", "MILAN AI WEEK"] },
    { "rubric": "stage-2-self-second-blocked", "passed": true, "needles": ["Self-second BLOCKED", "audit recorded"] }
  ],
  "pass_rate": 1.0
}
```
