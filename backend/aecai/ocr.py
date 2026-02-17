"""OCR module – reads fixture codes from detected ovals on floor plans.

Strategy: crop each detected oval INWARD (15% horiz / 20% vert) to remove
the drawn oval border, upscale, Tesseract PSM-8 (single word), then apply
prefix normalization and suffix fixes.
"""

from __future__ import annotations

import logging
import re

import cv2
import numpy as np
import pytesseract

from .config import (
    CROP_MARGIN_H,
    CROP_MARGIN_V,
    TESSERACT_CMD,
)

pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Cropping
# ---------------------------------------------------------------------------

def crop_oval(
    image: np.ndarray,
    oval: dict,
    margin_h: float = CROP_MARGIN_H,
    margin_v: float = CROP_MARGIN_V,
) -> np.ndarray:
    """Centre-crop an oval detection INWARD to remove the oval border.

    Margins are percentages of the oval's width/height:
      - 15% horizontal → removes left/right oval line
      - 20% vertical   → removes top/bottom oval line

    This ensures Tesseract sees only the text (e.g. "LT04"), not the
    surrounding drawn oval which confuses OCR.
    """
    h_img, w_img = image.shape[:2]
    ox, oy, ow, oh = oval["x"], oval["y"], oval["w"], oval["h"]

    margin_x = int(ow * margin_h)
    margin_y = int(oh * margin_v)

    x1 = max(ox + margin_x, 0)
    y1 = max(oy + margin_y, 0)
    x2 = min(ox + ow - margin_x, w_img)
    y2 = min(oy + oh - margin_y, h_img)

    # If margins ate the whole crop, fall back to full bbox
    if x2 <= x1 or y2 <= y1:
        x1, y1 = ox, oy
        x2, y2 = ox + ow, oy + oh

    return image[y1:y2, x1:x2]


# ---------------------------------------------------------------------------
# Preprocessing
# ---------------------------------------------------------------------------

def preprocess_for_ocr(crop: np.ndarray, scale: int = 3) -> np.ndarray:
    """Resize and threshold a crop for better Tesseract accuracy.

    Upscales by *scale* factor (default 3x), then Otsu binarises.
    Adds a white border so edge characters aren't clipped.
    """
    if len(crop.shape) == 3:
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    else:
        gray = crop

    # Upscale — small fixture-code crops need magnification
    gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)

    # Otsu binarisation
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    # Invert if background is dark (text should be dark-on-light for Tesseract)
    if np.mean(binary) < 128:
        binary = cv2.bitwise_not(binary)

    # Add white border — Tesseract needs some margin around characters
    binary = cv2.copyMakeBorder(binary, 10, 10, 10, 10, cv2.BORDER_CONSTANT, value=255)

    return binary


# ---------------------------------------------------------------------------
# Tesseract OCR
# ---------------------------------------------------------------------------

def ocr_crop(crop: np.ndarray, scale: int = 3) -> str:
    """Run Tesseract PSM-8 (single word) on a preprocessed crop.

    PSM-8 is the right mode for short fixture codes like "LT04A".
    Whitelist restricts to A-Z 0-9.
    """
    processed = preprocess_for_ocr(crop, scale=scale)
    whitelist = "-c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"

    text = pytesseract.image_to_string(processed, config=f"--psm 8 {whitelist}").strip()
    return text


# ---------------------------------------------------------------------------
# OCR correction
# ---------------------------------------------------------------------------

# Common OCR misreads for the "LT" prefix
_PREFIX_FIXES = {
    "LTO": "LT0",   # O misread as zero
    "L7":  "LT",     # T misread as 7
    "IT":  "LT",     # L misread as I
    "1T":  "LT",     # L misread as 1
    "L1":  "LT",     # T misread as 1 (when followed by digits)
}

# Common OCR suffix misreads
_SUFFIX_FIXES = {
    "8": "B",   # B misread as 8 (LT048 → LT04B)
}


def _normalize_prefix(text: str) -> str:
    """Fix common OCR misreads of the LT prefix."""
    upper = text.upper()
    for bad, good in _PREFIX_FIXES.items():
        if upper.startswith(bad):
            upper = good + upper[len(bad):]
            break
    return upper


def _normalize_suffix(text: str) -> str:
    """Fix trailing character misreads (e.g. 8 → B)."""
    if len(text) >= 3 and text[-1] in _SUFFIX_FIXES:
        # Only fix if the rest looks like a fixture code (has digits before the suffix)
        body = text[:-1]
        if any(c.isdigit() for c in body):
            text = body + _SUFFIX_FIXES[text[-1]]
    return text


def _clean_and_normalize(raw: str) -> str | None:
    """Strip non-alphanumeric chars, uppercase, apply prefix/suffix fixes."""
    cleaned = re.sub(r"[^A-Za-z0-9]", "", raw).upper()
    if not cleaned or len(cleaned) < 2:
        return None
    cleaned = _normalize_prefix(cleaned)
    cleaned = _normalize_suffix(cleaned)
    return cleaned


# ---------------------------------------------------------------------------
# Multi-strategy OCR retry (used when a prefix hint is available)
# ---------------------------------------------------------------------------

# Each strategy tries a different crop margin + scale factor to give
# Tesseract a different view of the text.  Ordered from moderate to
# aggressive changes.
_RETRY_STRATEGIES = [
    {"margin_h": 0.10, "margin_v": 0.15, "scale": 4},   # looser crop, bigger scale
    {"margin_h": 0.05, "margin_v": 0.10, "scale": 4},   # much looser crop
    {"margin_h": 0.20, "margin_v": 0.25, "scale": 5},   # tighter crop, much bigger
    {"margin_h": 0.12, "margin_v": 0.18, "scale": 2},   # slightly looser, smaller scale
]


def _is_valid_prefix_match(text: str, prefix: str) -> bool:
    """Check that text starts with prefix AND has at least one char after it."""
    return (
        text.startswith(prefix)
        and len(text) > len(prefix)
    )


def _ocr_with_retries(
    image: np.ndarray,
    oval: dict,
    prefix: str,
) -> tuple[str, str | None]:
    """Try multiple crop/scale strategies until one produces a prefix match.

    Returns (raw_text, cleaned_fixture_or_None).
    The first attempt uses default settings; subsequent attempts use
    _RETRY_STRATEGIES.  Stops as soon as a prefix match is found.
    """
    # First attempt: default crop + scale
    crop = crop_oval(image, oval)
    if crop.size == 0:
        return ("", None)

    raw = ocr_crop(crop)
    cleaned = _clean_and_normalize(raw)
    if cleaned and _is_valid_prefix_match(cleaned, prefix):
        return (raw, cleaned)

    # Retry with alternative strategies
    best_raw = raw
    for strat in _RETRY_STRATEGIES:
        retry_crop = crop_oval(
            image, oval,
            margin_h=strat["margin_h"],
            margin_v=strat["margin_v"],
        )
        if retry_crop.size == 0:
            continue

        retry_raw = ocr_crop(retry_crop, scale=strat["scale"])
        retry_cleaned = _clean_and_normalize(retry_raw)

        if retry_cleaned and _is_valid_prefix_match(retry_cleaned, prefix):
            logger.debug(
                "  Retry matched: %r → %s (strategy: %s)",
                retry_raw, retry_cleaned, strat,
            )
            return (retry_raw, retry_cleaned)

    # No strategy matched — return original attempt
    return (best_raw, None)


# ---------------------------------------------------------------------------
# False-positive filter
# ---------------------------------------------------------------------------

def _is_false_positive(text: str) -> bool:
    """Filter out OCR results that are clearly not fixture codes.

    Common false positives:
    - Single characters (noise)
    - Pure whitespace
    - Common drawing annotations (N, S, E, W, UP, DN, etc.)
    """
    if not text or len(text) < 2:
        return True

    cleaned = re.sub(r"[^A-Za-z0-9]", "", text).upper()
    if len(cleaned) < 2:
        return True

    # Common non-fixture annotations found inside oval-like shapes
    _noise_words = {"UP", "DN", "EX", "NIC", "TYP", "SIM", "REF", "NTS", "EQ"}
    if cleaned in _noise_words:
        return True

    return False


# ---------------------------------------------------------------------------
# Main recognition
# ---------------------------------------------------------------------------

def recognize_fixtures(
    image: np.ndarray,
    ovals: list[dict],
    *,
    prefix: str | None = None,
) -> list[dict]:
    """OCR all detected ovals and return fixture identifications.

    Every oval with readable alphanumeric text is captured as a fixture.
    OCR error corrections (prefix/suffix normalization) are always applied.
    If *prefix* is provided it acts as a filter — only codes starting with
    that prefix are kept, with multi-strategy retries for better recall.

    Args:
        image: the page image (BGR or grayscale)
        ovals: list of oval detection dicts from find_ovals()
        prefix: if set, only keep ovals whose corrected text starts with
                this string (e.g. "LT").

    Returns a list of dicts:
        oval     – original oval dict
        raw_text – Tesseract output before correction
        fixture  – corrected code, or None if not a fixture
    """
    upper_prefix = prefix.upper() if prefix else None
    results = []
    for oval in ovals:
        # When a prefix is specified, use multi-strategy retry to give
        # Tesseract several chances at reading the text correctly.
        if upper_prefix:
            raw, fixture = _ocr_with_retries(image, oval, upper_prefix)
            if _is_false_positive(raw):
                fixture = None
            results.append({"oval": oval, "raw_text": raw, "fixture": fixture})
            continue

        # No prefix — single-pass OCR, capture everything
        crop = crop_oval(image, oval)
        if crop.size == 0:
            continue

        raw = ocr_crop(crop)

        # Filter obvious noise
        if _is_false_positive(raw):
            results.append({"oval": oval, "raw_text": raw, "fixture": None})
            continue

        cleaned = _clean_and_normalize(raw)
        if not cleaned:
            results.append({"oval": oval, "raw_text": raw, "fixture": None})
            continue

        results.append(
            {
                "oval": oval,
                "raw_text": raw,
                "fixture": cleaned,
            }
        )
    return results
