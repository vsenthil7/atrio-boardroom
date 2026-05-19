"""
grade-pages.py — OCR every rendered page and grade against the RUBRIC.

Output: JSON report listing per-rubric pass/fail + overall pass rate.

Mirrors `demovideo/verification-b/grade-frames.py` so the pattern is
identical across the video + deck verifications.
"""
from __future__ import annotations

import argparse
import datetime
import json
import sys
from pathlib import Path

# Allow `from grade_pages_lib import ...` regardless of cwd
sys.path.insert(0, str(Path(__file__).parent))
from grade_pages_lib import RUBRIC, ocr_text  # noqa: E402


def grade(pages_dir: Path, report_path: Path) -> int:
    pages = sorted(pages_dir.glob("page_*.png"))
    if not pages:
        print(f"[verify-b] no rendered pages in {pages_dir}")
        return 1
    print(f"[verify-b] OCRing {len(pages)} pages...")
    all_text: list[str] = []
    for p in pages:
        all_text.append(ocr_text(p))
    combined_lower = "\n".join(all_text).lower()

    results = []
    for label, needles in RUBRIC:
        def needle_ok(n: str) -> bool:
            base = n.lower()
            # OCR-tolerant: try i<->l swap (common Tesseract confusion)
            variants = [base, base.replace("i", "l"), base.replace("l", "i")]
            return any(v in combined_lower for v in variants)

        passed = all(needle_ok(n) for n in needles)
        results.append({"rubric": label, "passed": passed, "needles": needles})
        flag = "PASS" if passed else "FAIL"
        print(f"  [{flag}] {label}")

    summary = {
        "pages": len(pages),
        "rubric": results,
        "pass_rate": sum(r["passed"] for r in results) / len(results),
    }
    report_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"[verify-b] report -> {report_path} (pass rate: {summary['pass_rate']:.0%})")
    return 0 if summary["pass_rate"] == 1.0 else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--pages", required=True)
    ap.add_argument("--report", help="Output report path (default: reports/vision-review-{stamp}.json)")
    args = ap.parse_args()

    pages_dir = Path(args.pages)
    if args.report:
        report = Path(args.report)
    else:
        reports = Path(__file__).parent / "reports"
        reports.mkdir(exist_ok=True)
        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        report = reports / f"vision-review-{stamp}.json"

    sys.exit(grade(pages_dir, report))
