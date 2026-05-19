# ATRIO Pitch Deck — verification-a · Structural review

Re-runs over the generated PDF with **hard assertions** at every page gate.
No OCR — text is extracted directly from the PDF via PyMuPDF, which is much
faster and more accurate than vision when the source is a "born-digital"
PDF (i.e. one made by `pptx -> pdf` rather than a scan).

If every assertion passes, the PDF is structurally correct: right page
count, right page size, right text on every page.

## What it asserts (52 assertions across 2 stages)

### Stage A — PDF-level (4 assertions)
- A0.1 PDF opens cleanly (PyMuPDF `is_pdf=True`)
- A0.2 Page count == 12
- A0.3 Page 1 width ≈ 960 pts (16:9 widescreen, ±1.5 pts)
- A0.4 Page 1 height ≈ 540 pts (±1.5 pts)

### Stage B — Per-page content (~48 assertions across 12 pages)
Each EXPECTED_SLIDES row in `structural-review.py` asserts that every needle
appears verbatim (case-insensitive) on its target page. Examples:
- B1.1   page 1 contains 'atrio'
- B1.2   page 1 contains 'milan ai week'
- B5.3   page 5 contains 'two-party'
- B5.4   page 5 contains 'proposed'
- B5.5   page 5 contains 'first_authorised'
- B5.6   page 5 contains 'executed'
- B7.1   page 7 contains 'proof'
- B7.2   page 7 contains '381'
- B7.3   page 7 contains '90.68'
- B7.4   page 7 contains '24 / 24'
- B7.5   page 7 contains '14 / 14'

Full list in `EXPECTED_SLIDES` near the top of `structural-review.py`.

## Run

```powershell
pwsh ./submission_media/verification-a/run-verify-a.ps1
```

Requirements:
- Python 3.10+ on PATH (or at the hardcoded fallback `C:\Users\v_sen\AppData\Local\Programs\Python\Python312\python.exe`)
- PyMuPDF (auto-installed by the run-script if missing)
- A pdf at `submission_media/atrio-pitch-deck-*.pdf`

## Output

- TXT report: `verification-a/reports/structural-review-{stamp}.txt`
- JSON sidecar: `verification-a/reports/structural-review-{stamp}.json` (machine-readable)
- Exit code: 0 if all assertions pass, 1 otherwise

## How to extend in a new project

1. Edit `EXPECTED_SLIDES` (list of `(page_number, [needles])`)
2. Edit `EXPECTED_PAGE_COUNT` (derived from list length, change only the list)
3. Adjust `EXPECTED_WIDTH_POINTS` / `EXPECTED_HEIGHT_POINTS` if non-widescreen

Everything else is project-agnostic. The total assertion count is `4 + sum(len(needles) for _, needles in EXPECTED_SLIDES)`.

## Why this exists (not just trust the deck)

A AI-generated artefact needs an automated counter-signature before we put
it in front of judges. `build_pitch_deck.py` reads from doc files — a single
content drift in a doc could silently change a slide. verification-a catches
"page missing" or "wrong page count" failures cheaply (~0.5s). verification-b
(sibling folder) catches "right page, wrong rendering" failures via OCR.
