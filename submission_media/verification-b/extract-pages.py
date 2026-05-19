"""
extract-pages.py — render every page of a PDF to a PNG via PyMuPDF.

Mirrors `demovideo/verification-b/extract-frames.py` (which uses ffmpeg on
video frames). For PDFs we go straight to PyMuPDF — no ffmpeg needed.

Default render zoom: 1.5x (= 144 DPI for 96 DPI source) for readable OCR.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    import fitz  # PyMuPDF
except ImportError:
    print("[verify-b] missing PyMuPDF. Run:  python -m pip install PyMuPDF")
    sys.exit(2)


def extract(pdf_path: Path, out_dir: Path, zoom: float = 1.5) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    # Clear any previous run
    for f in out_dir.glob("page_*.png"):
        f.unlink()

    doc = fitz.open(pdf_path)
    matrix = fitz.Matrix(zoom, zoom)
    pages: list[Path] = []
    for i, page in enumerate(doc, 1):
        pix = page.get_pixmap(matrix=matrix)
        out_png = out_dir / f"page_{i:02d}.png"
        pix.save(str(out_png))
        pages.append(out_png)
    doc.close()
    return pages


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", required=True, help="Path to input PDF")
    ap.add_argument("--out", required=True, help="Directory to write page_NN.png files into")
    ap.add_argument("--zoom", type=float, default=1.5)
    args = ap.parse_args()

    pdf = Path(args.pdf)
    if not pdf.exists():
        print(f"[verify-b] pdf not found: {pdf}")
        sys.exit(1)

    pages = extract(pdf, Path(args.out), args.zoom)
    print(f"[verify-b] extracted {len(pages)} pages to {args.out}")
