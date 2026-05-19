"""
ATRIO Pitch Deck — Verification-A: structural review

Re-runs over the generated PDF with HARD ASSERTIONS at each page gate.
No OCR — this is structural checking via PyMuPDF text extraction. If every
assertion passes, the PDF is structurally correct (page count, page sizes,
page-title text on every page).

Mirrors `atrio/demovideo/verification-a/structural-review.spec.ts` so the
two artefacts (video + pdf) follow the same proof pattern.

Output: a TXT report at --report listing per-assertion pass/fail.
"""
from __future__ import annotations

import argparse
import datetime
import json
import sys
from dataclasses import dataclass
from pathlib import Path

try:
    import fitz  # PyMuPDF
except ImportError:
    print("[verify-a] missing PyMuPDF. Run:  python -m pip install PyMuPDF")
    sys.exit(2)


# ---------- The expected deck ----------
# (page_index, must_contain_substring_lower)
# Page index is 1-based to match human counting.
EXPECTED_SLIDES: list[tuple[int, list[str]]] = [
    (1,  ["atrio", "milan ai week"]),
    (2,  ["the problem", "founders"]),
    (3,  ["the solution", "debate", "enforce", "audit"]),
    (4,  ["six specialists", "cfo", "cto", "cmo", "coo", "counsel", "facilitator"]),
    (5,  ["treasury", "mandate", "two-party", "proposed", "first_authorised", "executed"]),
    (6,  ["live demo", "boardroom debate", "second human", "boardpack", "audit export"]),
    (7,  ["proof", "381", "90.68", "24 / 24", "14 / 14"]),
    (8,  ["architecture", "frontend", "api", "infra"]),
    (9,  ["sponsor pools", "vultr", "gemini", "featherless", "speechmatics", "kraken"]),
    (10, ["beyond the mvp", "v1.1", "v1.2"]),
    (11, ["team", "ask", "vultr credits"]),
    (12, ["mandate-enforced", "github.com/vsenthil7/atrio-boardroom", "apache 2.0"]),
]

EXPECTED_PAGE_COUNT = len(EXPECTED_SLIDES)
# 16:9 widescreen at 13.333"x7.5" — PowerPoint default after we set slide dims.
# Pdf points: 72 per inch -> 960 x 540, ±1pt tolerance.
EXPECTED_WIDTH_POINTS = 960
EXPECTED_HEIGHT_POINTS = 540
DIM_TOLERANCE = 1.5


@dataclass
class AssertResult:
    id: str
    label: str
    passed: bool
    detail: str = ""


def soft_assert(results: list[AssertResult], aid: str, label: str, condition: bool, detail: str = "") -> None:
    results.append(AssertResult(id=aid, label=label, passed=bool(condition), detail=detail))


def find_pdf(out_dir: Path) -> Path | None:
    """Locate the most recent atrio-pitch-deck-*.pdf in submission_media/."""
    pdfs = sorted(out_dir.glob("atrio-pitch-deck-*.pdf"), key=lambda p: p.stat().st_mtime, reverse=True)
    return pdfs[0] if pdfs else None


def verify(pdf_path: Path) -> tuple[list[AssertResult], dict]:
    results: list[AssertResult] = []
    doc = fitz.open(pdf_path)
    summary: dict = {
        "pdf": str(pdf_path),
        "pdf_size_kb": round(pdf_path.stat().st_size / 1024, 1),
        "page_count": doc.page_count,
    }

    # ---------- Stage A: PDF-level ----------
    soft_assert(
        results, "A0.1", "pdf opens cleanly", doc.is_pdf, detail=f"is_pdf={doc.is_pdf}"
    )
    soft_assert(
        results, "A0.2", f"page count == {EXPECTED_PAGE_COUNT}",
        doc.page_count == EXPECTED_PAGE_COUNT,
        detail=f"got {doc.page_count}, want {EXPECTED_PAGE_COUNT}",
    )
    if doc.page_count == 0:
        return results, summary

    page0 = doc[0]
    w, h = page0.rect.width, page0.rect.height
    soft_assert(
        results, "A0.3",
        f"page 1 width ~= {EXPECTED_WIDTH_POINTS} pts (16:9 widescreen)",
        abs(w - EXPECTED_WIDTH_POINTS) <= DIM_TOLERANCE,
        detail=f"got {w:.2f}",
    )
    soft_assert(
        results, "A0.4",
        f"page 1 height ~= {EXPECTED_HEIGHT_POINTS} pts",
        abs(h - EXPECTED_HEIGHT_POINTS) <= DIM_TOLERANCE,
        detail=f"got {h:.2f}",
    )

    # ---------- Stage B: per-page content ----------
    page_texts: dict[int, str] = {}
    for page_num, needles in EXPECTED_SLIDES:
        if page_num > doc.page_count:
            soft_assert(
                results, f"B{page_num}.0",
                f"page {page_num} exists",
                False,
                detail=f"only {doc.page_count} pages",
            )
            continue
        text = doc[page_num - 1].get_text("text").lower()
        page_texts[page_num] = text
        for i, needle in enumerate(needles, 1):
            soft_assert(
                results, f"B{page_num}.{i}",
                f"page {page_num} contains '{needle}'",
                needle.lower() in text,
                detail="" if needle.lower() in text else f"page {page_num} text len={len(text)}",
            )

    summary["page_texts_preview"] = {
        pn: (txt[:160] + ("..." if len(txt) > 160 else "")).replace("\n", " | ")
        for pn, txt in page_texts.items()
    }
    doc.close()
    return results, summary


def render_report(results: list[AssertResult], summary: dict) -> str:
    lines: list[str] = []
    lines.append("[verify-a] === ATRIO Pitch Deck · Structural review ===")
    lines.append("")
    lines.append(f"pdf      : {summary['pdf']}")
    lines.append(f"size     : {summary['pdf_size_kb']} KB")
    lines.append(f"pages    : {summary['page_count']}")
    lines.append("")
    passed = sum(1 for r in results if r.passed)
    total = len(results)
    pct = 100 * passed // max(total, 1)
    lines.append(f"assertions: {passed}/{total} PASS ({pct} %)")
    lines.append("")
    for r in results:
        flag = "PASS" if r.passed else "FAIL"
        detail = f"  — {r.detail}" if r.detail and not r.passed else ""
        lines.append(f"  [{flag}] {r.id}  {r.label}{detail}")
    lines.append("")
    if passed != total:
        lines.append("FAILED — review the FAIL rows above. Likely causes:")
        lines.append("  - build_pitch_deck.py changed and a needle no longer appears verbatim")
        lines.append("  - pptx_to_pdf.ps1 conversion dropped a page (PowerPoint complaint?)")
        lines.append("  - slide dimensions changed (16:9 widescreen vs 4:3 default)")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", help="Path to a specific pdf (default: most recent in submission_media/)")
    ap.add_argument("--report", help="Output report path (default: reports/structural-review-{stamp}.txt)")
    args = ap.parse_args()

    here = Path(__file__).resolve().parent
    submission_media = here.parent

    pdf_path = Path(args.pdf) if args.pdf else find_pdf(submission_media)
    if not pdf_path or not pdf_path.exists():
        print(f"[verify-a] no pdf found in {submission_media}")
        return 1

    results, summary = verify(pdf_path)

    reports_dir = here / "reports"
    reports_dir.mkdir(exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = Path(args.report) if args.report else reports_dir / f"structural-review-{stamp}.txt"
    txt = render_report(results, summary)
    report_path.write_text(txt, encoding="utf-8")
    print(txt)
    print()
    print(f"[verify-a] report -> {report_path}")

    # JSON sidecar (machine-readable)
    json_path = report_path.with_suffix(".json")
    json_path.write_text(
        json.dumps(
            {
                "summary": summary,
                "results": [r.__dict__ for r in results],
                "passed": sum(1 for r in results if r.passed),
                "total": len(results),
                "pass_rate": (sum(1 for r in results if r.passed) / max(len(results), 1)),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"[verify-a] json   -> {json_path}")

    return 0 if all(r.passed for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
