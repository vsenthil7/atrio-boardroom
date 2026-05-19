"""
Grade BOTH founder + ceo videos and produce a combined report.

The demo spec records two browser contexts (founder + ceo). Stage 3 (CEO
second-authorise) is only in the CEO recording. Vision verification grades
each video, then unions the OCR text across both before checking the rubric.
"""
import json
import sys
import subprocess
from pathlib import Path

ROOT = Path(__file__).parent
DEMO = Path(r'C:\Users\v_sen\Documents\Projects\0010_AT_Hack0021_ATRIO_MilanAIWeek\atrio\demo')
FRAMES_BASE = ROOT / 'frames'
REPORTS = ROOT / 'reports'
REPORTS.mkdir(exist_ok=True)


def extract_frames(video, out_dir, every_seconds=2):
    if out_dir.exists():
        for f in out_dir.glob('*.png'):
            f.unlink()
    else:
        out_dir.mkdir(parents=True, exist_ok=True)
    rate = f"1/{every_seconds}"
    cmd = ['ffmpeg', '-y', '-i', str(video), '-vf', f'fps={rate}', str(out_dir / 'frame_%04d.png')]
    rc = subprocess.run(cmd, capture_output=True).returncode
    return rc, sorted(out_dir.glob('frame_*.png'))


from grade_frames_lib import ocr_text, RUBRIC  # see helper below


def main():
    videos = sorted(DEMO.glob('atrio-walkthrough-*.mp4'))
    if not videos:
        print('[verify-b combined] no mp4s found')
        return 1
    print(f'[verify-b combined] grading {len(videos)} videos:')
    for v in videos:
        print(f'  - {v.name}  ({v.stat().st_size // 1024} KB)')

    all_text = []
    for v in videos:
        sub_frames = FRAMES_BASE / v.stem
        rc, frames = extract_frames(v, sub_frames)
        print(f'  [{v.stem}] {len(frames)} frames extracted (ffmpeg rc={rc})')
        for fr in frames:
            all_text.append(ocr_text(fr))
    combined_lower = '\n'.join(all_text).lower()

    results = []
    for label, needles in RUBRIC:
        def needle_ok(n):
            base = n.lower()
            variants = [base, base.replace('i', 'l'), base.replace('l', 'i')]
            return any(v in combined_lower for v in variants)
        passed = all(needle_ok(n) for n in needles)
        results.append({'rubric': label, 'passed': passed, 'needles': needles})
        flag = 'PASS' if passed else 'FAIL'
        print(f'  [{flag}] {label}')

    summary = {
        'videos': [v.name for v in videos],
        'frames_total': len(all_text),
        'rubric': results,
        'pass_rate': sum(r['passed'] for r in results) / len(results),
    }
    import datetime
    stamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    out = REPORTS / f'vision-review-combined-{stamp}.json'
    out.write_text(json.dumps(summary, indent=2))
    print(f'\n[verify-b combined] report -> {out}')
    print(f'[verify-b combined] pass rate: {summary["pass_rate"]:.0%}')
    return 0 if summary['pass_rate'] == 1.0 else 1


if __name__ == '__main__':
    sys.exit(main())
