"""
grade-frames.py — grade OCR-extracted frames against an expected-text RUBRIC.

Single-video grader. For the multi-context demo (founder + ceo recordings),
use grade-combined.py instead.

Each rubric entry is (label, list_of_required_substrings). A rubric entry is
satisfied if the COMBINED text across all frames contains all its substrings
(case-insensitive, OCR-tolerant).

Output: JSON report at --report.
"""
import argparse
import json
import sys
from pathlib import Path

# Allow `from grade_frames_lib import ...` regardless of cwd
sys.path.insert(0, str(Path(__file__).parent))
from grade_frames_lib import ocr_text, RUBRIC  # noqa: E402


def grade(frames_dir, report_path):
    frames = sorted(Path(frames_dir).glob("frame_*.png"))
    if not frames:
        print("[verify-b] no frames in", frames_dir)
        return 1
    print(f"[verify-b] OCRing {len(frames)} frames...")
    all_text = []
    for fr in frames:
        all_text.append(ocr_text(fr))
    combined_lower = ("\n".join(all_text)).lower()

    results = []
    for label, needles in RUBRIC:
        def needle_ok(n: str) -> bool:
            base = n.lower()
            variants = [base, base.replace("i", "l"), base.replace("l", "i")]
            return any(v in combined_lower for v in variants)
        passed = all(needle_ok(n) for n in needles)
        results.append({"rubric": label, "passed": passed, "needles": needles})
        flag = "PASS" if passed else "FAIL"
        print(f"  [{flag}] {label}")

    summary = {
        "frames": len(frames),
        "rubric": results,
        "pass_rate": sum(r["passed"] for r in results) / len(results),
    }
    Path(report_path).write_text(json.dumps(summary, indent=2))
    print(f"[verify-b] report -> {report_path} (pass rate: {summary['pass_rate']:.0%})")
    return 0 if summary["pass_rate"] == 1.0 else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames", required=True)
    ap.add_argument("--report", required=True)
    args = ap.parse_args()
    sys.exit(grade(args.frames, args.report))
