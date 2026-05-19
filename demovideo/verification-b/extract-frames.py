"""
extract-frames.py — extract still frames from a video file at a fixed cadence.

Used by verification-b to feed OCR. Default: 1 frame every 2 seconds.
"""
import argparse
import subprocess
import sys
from pathlib import Path


def extract(video, out_dir, every_seconds=2):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    rate = f"1/{every_seconds}"
    cmd = ["ffmpeg", "-y", "-i", str(video), "-vf", f"fps={rate}", str(out_dir / "frame_%04d.png")]
    print("[verify-b] running:", " ".join(cmd))
    rc = subprocess.run(cmd, capture_output=True).returncode
    return rc, sorted(out_dir.glob("frame_*.png"))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True, help="Path to input .mp4/.webm video")
    ap.add_argument("--out", required=True, help="Directory to write frame_NNNN.png files into")
    ap.add_argument("--every", type=float, default=2.0, help="Seconds between frames (default 2.0)")
    args = ap.parse_args()
    rc, frames = extract(args.video, args.out, args.every)
    print(f"[verify-b] ffmpeg rc={rc}, extracted {len(frames)} frames")
    sys.exit(rc)
