"""Render the most recent pitch-deck PDF to PNG previews so we can verify visually."""
from pathlib import Path
import fitz  # PyMuPDF

# atrio/submission_media/ relative to this script (atrio/scripts/render_deck_previews.py)
out_dir = Path(__file__).resolve().parent.parent / 'submission_media'
preview_dir = out_dir / 'previews'
preview_dir.mkdir(exist_ok=True)

pdfs = sorted(out_dir.glob('atrio-pitch-deck-*.pdf'), key=lambda p: p.stat().st_mtime, reverse=True)
if not pdfs:
    print(f'no pdf found in {out_dir}')
    raise SystemExit(1)
pdf = pdfs[0]
print(f'rendering: {pdf.name}')

doc = fitz.open(pdf)
print(f'pages: {doc.page_count}')

# Render every slide at 1.5x zoom (high enough to read)
matrix = fitz.Matrix(1.5, 1.5)
for i, page in enumerate(doc, 1):
    pix = page.get_pixmap(matrix=matrix)
    out_png = preview_dir / f'slide_{i:02d}.png'
    pix.save(str(out_png))
    print(f'  slide_{i:02d}: {out_png.stat().st_size // 1024} KB ({pix.width}x{pix.height})')

doc.close()
print(f'previews -> {preview_dir}')
