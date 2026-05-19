"""
Shared OCR helpers + RUBRIC for ATRIO pitch-deck vision review.

Imported by:
  - grade-pages.py  (single deck PDF)

The RUBRIC is intentionally LESS strict than verification-a's text assertions:
because OCR is imperfect, we only require the SHORTEST, most-distinctive
phrase per slide. verification-a (PDF text extraction) catches text drift;
verification-b (OCR over rendered pixels) catches "renders blank" or
"font not embedded so glyphs are wrong".
"""
import sys
from pathlib import Path

try:
    import pytesseract
    from PIL import Image, ImageOps
except ImportError as e:
    print("[verify-b] missing dep:", e)
    print("  pip install -r submission_media/verification-b/requirements.txt")
    sys.exit(2)

# ATRIO pitch-deck rubric — matches the 12 slides built by atrio/scripts/build_pitch_deck.py.
# Each row: (id, [substrings that must ALL appear across all rendered pages]).
RUBRIC = [
    ("slide-1-title",            ["ATRIO", "Your AI boardroom"]),
    ("slide-2-problem",          ["The problem", "Founders"]),
    ("slide-3-solution",         ["DEBATE", "ENFORCE", "AUDIT"]),
    ("slide-4-six-agents",       ["CFO", "CTO", "Facilitator"]),
    ("slide-5-treasury",         ["TREASURY", "proposed", "executed"]),
    ("slide-6-demo",             ["Live demo", "BOARDPACK"]),
    ("slide-7-proof",            ["381", "90.68"]),
    ("slide-8-architecture",     ["FRONTEND", "API", "INFRA"]),
    ("slide-9-sponsors",         ["Vultr", "Gemini", "Kraken"]),
    ("slide-10-roadmap",         ["v1.1", "v1.2"]),
    ("slide-11-team",            ["Verixa", "Vultr credits"]),
    ("slide-12-closing",         ["Mandate-enforced", "Apache 2.0"]),
]


def ocr_text(page_image_path: Path) -> str:
    """Two-pass OCR: original + inverted (in case theme is dark)."""
    try:
        img = Image.open(page_image_path).convert("RGB")
        text_normal = pytesseract.image_to_string(img)
        gray = img.convert("L")
        mean = sum(gray.getdata()) / (gray.width * gray.height)
        if mean < 100:
            inverted = ImageOps.invert(gray)
            return text_normal + "\n" + pytesseract.image_to_string(inverted)
        # Light backgrounds: also try inverted as a fallback for low-contrast captions
        return text_normal + "\n" + pytesseract.image_to_string(ImageOps.invert(gray))
    except Exception:
        return ""
