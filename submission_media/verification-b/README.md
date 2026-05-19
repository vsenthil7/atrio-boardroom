# ATRIO Pitch Deck — verification-b · Vision review

Genuinely re-reads the produced PDF page-by-page. Uses **PyMuPDF** to render
each page to a high-DPI PNG, **Tesseract OCR** to read the visible text, and
grades against a rubric.

Sibling to `demovideo/verification-b/` (same shape: extract-pages.py +
grade-pages.py + grade_pages_lib.py + run script + reports). Differs only in
the extractor: PDF pages via PyMuPDF, not video frames via ffmpeg.

## Why both verifications

| | verification-a (structural) | verification-b (vision) |
|---|---|---|
| **Checks** | PDF page count + size + per-page text (PyMuPDF text extraction) | OCR on rendered pixels matches rubric needles |
| **Method** | `fitz.Document.get_text("text")` | Tesseract on `page.get_pixmap()` images |
| **Catches** | Wrong page count · missing page · text drift after a doc edit | Font not embedded · invisible text · pptx-to-pdf rendering bug |
| **Speed** | ~0.5 s | ~10 s |
| **Strict?** | Strict (52 needles, every one must hit) | Loose (1-3 distinctive needles per slide) |
| **Stand-alone evidence** | "If A passes, the doc-driven content is correct" | "If B passes, the renderer didn't lose anything" |

Both passing together is the by-construction proof. A passes but B fails ->
likely a font-embedding issue. A fails but B passes -> doc drift, e.g. a
needle phrase was renamed in the source doc.

## Modular pieces

- `extract-pages.py` — PyMuPDF wrapper, renders every page at zoom 1.5x
- `grade_pages_lib.py` — shared `RUBRIC` + `ocr_text` (so other graders can import)
- `grade-pages.py` — single-PDF grader using the lib
- `run-verify-b.ps1` — pre-flight + render + grade + report
- `requirements.txt` — `pillow + pytesseract + PyMuPDF`

## One-time prerequisites

```powershell
winget install UB-Mannheim.TesseractOCR
python -m pip install -r submission_media/verification-b/requirements.txt
```

## Run

```powershell
pwsh ./submission_media/verification-b/run-verify-b.ps1
```

Reads the latest `atrio-pitch-deck-*.pdf` from `submission_media/`.

## Rubric (12 items, mirrors the deck's slide order)

| Rubric item | Required substrings |
|---|---|
| slide-1-title          | ATRIO · Your AI boardroom |
| slide-2-problem        | The problem · Founders |
| slide-3-solution       | DEBATE · ENFORCE · AUDIT |
| slide-4-six-agents     | CFO · CTO · Facilitator |
| slide-5-treasury       | TREASURY · proposed · executed |
| slide-6-demo           | Live demo · BOARDPACK |
| slide-7-proof          | 381 · 90.68 |
| slide-8-architecture   | FRONTEND · API · INFRA |
| slide-9-sponsors       | Vultr · Gemini · Kraken |
| slide-10-roadmap       | v1.1 · v1.2 |
| slide-11-team          | Verixa · Vultr credits |
| slide-12-closing       | Mandate-enforced · Apache 2.0 |

To extend or fork for a new project, edit `RUBRIC` in `grade_pages_lib.py`.

## Output

`verification-b/reports/vision-review-{timestamp}.json` — per-rubric pass/fail + overall pass rate.

Example:
```json
{
  "pages": 12,
  "rubric": [
    { "rubric": "slide-1-title", "passed": true, "needles": ["ATRIO", "Your AI boardroom"] },
    { "rubric": "slide-7-proof", "passed": true, "needles": ["381", "90.68"] }
  ],
  "pass_rate": 1.0
}
```
