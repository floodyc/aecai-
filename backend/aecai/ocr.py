"""OCR module – reads fixture codes from detected ovals on floor plans.

Strategy: crop each detected oval INWARD (15% horiz / 20% vert) to remove
the drawn oval border, upscale 3x, Tesseract PSM-8 (single word), then
fuzzy-correct against known codes with prefix normalization and suffix fixes.
"""

from __future__ import annotations

import logging
import re

import cv2
import numpy as np
import pytesseract
from thefuzz import fuzz

from .config import (
    CROP_MARGIN_H,
    CROP_MARGIN_V,
    FUZZY_THRESHOLD,
    KNOWN_LUMINAIRES,
    TESSERACT_CMD,
)

pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Cropping
# ---------------------------------------------------------------------------

def crop_oval(image: np.ndarray, oval: dict) -> np.ndarray:
    """Centre-crop an oval detection INWARD to remove the oval border.

    Margins are percentages of the oval's width/height:
      - 15% horizontal → removes left/right oval line
      - 20% vertical   → removes top/bottom oval line

    This ensures Tesseract sees only the text (e.g. "LT04"), not the
    surrounding drawn oval which confuses OCR.
    """
    h_img, w_img = image.shape[:2]
    ox, oy, ow, oh = oval["x"], oval["y"], oval["w"], oval["h"]

    margin_x = int(ow * CROP_MARGIN_H)
    margin_y = int(oh * CROP_MARGIN_V)

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

def preprocess_for_ocr(crop: np.ndarray) -> np.ndarray:
    """Resize and threshold a crop for better Tesseract accuracy.

    Upscales 3x (matches the working version's approach), then Otsu
    binarises.  Adds a white border so edge characters aren't clipped.
    """
    if len(crop.shape) == 3:
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    else:
        gray = crop

    # 3x upscale — small fixture-code crops need magnification
    gray = cv2.resize(gray, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)

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

def ocr_crop(crop: np.ndarray) -> str:
    """Run Tesseract PSM-8 (single word) on a preprocessed crop.

    PSM-8 is the right mode for short fixture codes like "LT04A".
    Whitelist restricts to A-Z 0-9.
    """
    processed = preprocess_for_ocr(crop)
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


def fuzzy_correct(raw_text: str, known: list[str] | None = None, threshold: int = FUZZY_THRESHOLD) -> str | None:
    """Fuzzy-match OCR text against known luminaire codes.

    Applies prefix/suffix normalization before matching.
    Returns the best match if the score is above threshold, else None.
    """
    if not raw_text:
        return None

    known = known or KNOWN_LUMINAIRES

    # Clean: strip non-alphanumeric, uppercase
    cleaned = re.sub(r"[^A-Za-z0-9]", "", raw_text).upper()
    if not cleaned:
        return None

    # Apply OCR error corrections
    cleaned = _normalize_prefix(cleaned)
    cleaned = _normalize_suffix(cleaned)

    # If cleaned text exactly matches a known code, return immediately
    if cleaned in known:
        return cleaned

    # Fuzzy match
    best_match = None
    best_score = 0

    for code in known:
        score = fuzz.ratio(cleaned, code)
        if score > best_score:
            best_score = score
            best_match = code

    if best_score >= threshold:
        return best_match
    return None


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
    known: list[str] | None = None,
    prefix: str | None = None,
) -> list[dict]:
    """OCR all detected ovals and return fixture identifications.

    Two modes:
    - **Prefix mode** (when prefix is set): accept any oval text starting
      with the user-supplied prefix (e.g. "LT" matches "LT04", "LT12A").
    - **Fuzzy mode** (default): fuzzy-match against known code list.

    Args:
        image: the page image (BGR or grayscale)
        ovals: list of oval detection dicts from find_ovals()
        known: optional project-specific luminaire codes for fuzzy matching.
        prefix: if set, match ovals whose OCR text starts with this string.

    Returns a list of dicts:
        oval     – original oval dict
        raw_text – Tesseract output before correction
        fixture  – matched code, or None if not a fixture
    """
    results = []
    for oval in ovals:
        crop = crop_oval(image, oval)
        if crop.size == 0:
            continue

        raw = ocr_crop(crop)

        # Filter obvious noise
        if _is_false_positive(raw):
            results.append({"oval": oval, "raw_text": raw, "fixture": None})
            continue

        cleaned = re.sub(r"[^A-Za-z0-9]", "", raw).upper()

        fixture = None

        if prefix:
            # Prefix mode: apply the same OCR error corrections as fuzzy mode,
            # then check if text starts with the prefix.
            # This catches common misreads: LTO4→LT04, L704→LT04, LT048→LT04B
            cleaned = _normalize_prefix(cleaned)
            cleaned = _normalize_suffix(cleaned)
            if cleaned.startswith(prefix.upper()):
                fixture = cleaned
        else:
            # Fuzzy mode: match against known codes
            fixture = fuzzy_correct(raw, known=known)

            # Fallback: use cleaned text if it looks like a code
            if fixture is None and cleaned:
                cleaned = _normalize_prefix(cleaned)
                cleaned = _normalize_suffix(cleaned)
                has_letter = any(c.isalpha() for c in cleaned)
                has_digit = any(c.isdigit() for c in cleaned)
                if has_letter and has_digit and len(cleaned) >= 3:
                    fixture = cleaned

        results.append(
            {
                "oval": oval,
                "raw_text": raw,
                "fixture": fixture,
            }
        )
    return results


def scan_page_for_codes(
    image: np.ndarray,
    known_codes: list[str],
    threshold: int = FUZZY_THRESHOLD,
) -> list[dict]:
    """Full-page OCR: find all text on the page that matches known fixture codes.

    Instead of detecting shapes first, this scans the entire page for text and
    keeps only words that fuzzy-match a code from the legend. The legend drives
    what counts as a fixture.

    Args:
        image: the full page image (BGR or grayscale)
        known_codes: fixture codes extracted from the legend
        threshold: minimum fuzz ratio to accept a match

    Returns a list of dicts:
        raw_text – the OCR'd word
        fixture  – matched fixture code
        x, y, w, h – bounding box of the word on the page
    """
    if len(image.shape) == 3:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    else:
        gray = image

    # Get word-level bounding boxes from Tesseract (PSM 6 = block of text)
    data = pytesseract.image_to_data(
        gray,
        config="--psm 6 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789- ",
        output_type=pytesseract.Output.DICT,
    )

    results: list[dict] = []
    n_words = len(data["text"])

    for i in range(n_words):
        raw = data["text"][i].strip()
        if not raw or len(raw) < 2:
            continue

        # Clean: strip non-alphanumeric, uppercase
        cleaned = re.sub(r"[^A-Za-z0-9]", "", raw).upper()
        if not cleaned or len(cleaned) < 2:
            continue

        # Fuzzy-match against every known code
        best_match = None
        best_score = 0
        for code in known_codes:
            score = fuzz.ratio(cleaned, code)
            if score > best_score:
                best_score = score
                best_match = code

        if best_score >= threshold and best_match is not None:
            results.append(
                {
                    "raw_text": raw,
                    "fixture": best_match,
                    "x": data["left"][i],
                    "y": data["top"][i],
                    "w": data["width"][i],
                    "h": data["height"][i],
                    "score": best_score,
                }
            )

    logger.info("  Text search found %d code matches on page", len(results))
    return results
