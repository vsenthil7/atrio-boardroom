"""
Shared OCR helpers + RUBRIC. Imported by both:
  - grade-frames.py  (single video)
  - grade-combined.py (founder + ceo videos combined)
"""
import sys
from pathlib import Path

try:
    import pytesseract
    from PIL import Image, ImageOps
except ImportError as e:
    print("[verify-b] missing dep:", e)
    print("  pip install -r demovideo/verification-b/requirements.txt")
    sys.exit(2)

# ATRIO demo rubric — matches the captions emitted by full-walkthrough.spec.ts.
# Each row: (id, [substrings that must ALL appear across all frames OCR text]).
#
# Note: rubric items target the SHORTEST, most-distinctive phrase from each
# caption. OCR is imperfect on the 100-200ms pill display, so we don't insist
# on every phrase — just one or two unique identifiers per scene.
RUBRIC = [
    ("title-card-opening",          ["ATRIO", "MILAN"]),
    ("stage-1-scene-card",          ["STAGE 1", "BOARDROOM DEBATE", "GIVEN", "WHEN", "THEN"]),
    ("stage-1-six-agents-pill",     ["six agents", "streaming"]),
    ("stage-1-consensus-pill",      ["Consensus", "action list"]),
    ("stage-2-scene-card",          ["STAGE 2", "TREASURY", "MANDATE", "TWO-PARTY"]),
    ("stage-2-propose-pill",        ["Proposed", "SHV-xStock"]),
    ("stage-2-self-second-blocked", ["Self-second BLOCKED", "audit recorded"]),
    ("stage-3-scene-card",          ["STAGE 3", "SECOND HUMAN", "AUTHORISE"]),
    # Stage 3.2 pill: "CEO sees the proposal in first_authorised state"
    ("stage-3-ceo-sees-proposal",   ["CEO sees", "first"]),
    ("stage-3-trade-executed",      ["EXECUTED", "Kraken paper"]),
    ("stage-4-scene-card",          ["STAGE 4", "BOARDPACK", "AUDIT EXPORT"]),
    ("stage-4-session-closed",      ["Session closed"]),
    ("stage-4-audit-export",        ["Audit", "JSONL"]),
    ("title-card-closing",          ["ATRIO", "Mandate-enforced", "Apache 2.0"]),
]


def ocr_text(frame_path: Path) -> str:
    """Two-pass OCR: original + inverted (for dark-background captions)."""
    try:
        img = Image.open(frame_path).convert("RGB")
        text_normal = pytesseract.image_to_string(img)
        gray = img.convert("L")
        mean = sum(gray.getdata()) / (gray.width * gray.height)
        if mean < 100:
            inverted = ImageOps.invert(gray)
            text_inverted = pytesseract.image_to_string(inverted)
            return text_normal + "\n" + text_inverted
        text_inverted = pytesseract.image_to_string(ImageOps.invert(gray))
        return text_normal + "\n" + text_inverted
    except Exception:
        return ""
