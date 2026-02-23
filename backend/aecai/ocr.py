"""OCR module – reads fixture codes from detected ovals on floor plans.

Strategy: crop each detected oval INWARD (15% horiz / 20% vert) to remove
the drawn oval border, upscale, Tesseract PSM-8 (single word), then apply
prefix normalization and suffix fixes.
"""

from __future__ import annotations

import logging
import os
import re
import tempfile

import cv2
import numpy as np
import pytesseract

from thefuzz import fuzz

from .config import (
    CROP_MARGIN_H,
    CROP_MARGIN_V,
    TESSERACT_CMD,
)

# Debug crop saving — set AECAI_DEBUG_CROPS=1 to save OCR crop images
_DEBUG_CROPS = os.environ.get("AECAI_DEBUG_CROPS", "0") == "1"
_DEBUG_CROP_DIR: str | None = None

pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD
logger = logging.getLogger(__name__)

# Log Tesseract version on module load — helps diagnose OCR issues
try:
    _tess_version = pytesseract.get_tesseract_version()
    logger.info("Tesseract version: %s (cmd: %s)", _tess_version, TESSERACT_CMD)
except Exception as _e:
    logger.warning("Could not detect Tesseract version: %s", _e)


def _init_debug_crop_dir() -> str:
    """Create a temp directory for debug crop images."""
    global _DEBUG_CROP_DIR
    if _DEBUG_CROP_DIR is None:
        _DEBUG_CROP_DIR = tempfile.mkdtemp(prefix="aecai_crops_")
        logger.info("Debug crop images will be saved to: %s", _DEBUG_CROP_DIR)
    return _DEBUG_CROP_DIR


def save_debug_crop(
    crop: np.ndarray,
    processed: np.ndarray | None,
    label: str,
    raw_text: str,
) -> None:
    """Save a crop image to the debug directory for inspection.

    Only active when AECAI_DEBUG_CROPS=1.
    Saves the raw crop and the preprocessed version side by side.
    """
    if not _DEBUG_CROPS:
        return
    crop_dir = _init_debug_crop_dir()
    safe_label = re.sub(r"[^A-Za-z0-9_-]", "_", label)
    safe_text = re.sub(r"[^A-Za-z0-9_-]", "_", raw_text) if raw_text else "empty"

    path = os.path.join(crop_dir, f"{safe_label}_raw_{safe_text}.png")
    cv2.imwrite(path, crop)

    if processed is not None:
        path_proc = os.path.join(crop_dir, f"{safe_label}_proc_{safe_text}.png")
        cv2.imwrite(path_proc, processed)


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
# Alternative preprocessing (adaptive threshold + CLAHE)
# ---------------------------------------------------------------------------

def preprocess_adaptive(crop: np.ndarray, scale: int = 3) -> np.ndarray:
    """Alternative preprocessing using adaptive thresholding + CLAHE.

    Better than Otsu when the global threshold merges text with the
    oval border (producing garbled reads like "GD" instead of "LT04").
    CLAHE enhances local contrast so thin text stands out from the background.
    """
    if len(crop.shape) == 3:
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    else:
        gray = crop

    gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)

    # CLAHE contrast enhancement — makes text ink darker relative to background
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    gray = clahe.apply(gray)

    # Adaptive threshold — handles uneven illumination and avoids merging
    # text with nearby border lines (which Otsu sometimes does)
    binary = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 15, 4
    )

    # Add white border
    binary = cv2.copyMakeBorder(binary, 10, 10, 10, 10, cv2.BORDER_CONSTANT, value=255)

    return binary


def ocr_crop_adaptive(crop: np.ndarray, scale: int = 3, psm: int = 8) -> str:
    """Run Tesseract using adaptive preprocessing (fallback for Otsu failures)."""
    processed = preprocess_adaptive(crop, scale=scale)
    whitelist = "-c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    text = pytesseract.image_to_string(processed, config=f"--psm {psm} {whitelist}").strip()
    return text


# ---------------------------------------------------------------------------
# Tesseract OCR
# ---------------------------------------------------------------------------

def ocr_crop(crop: np.ndarray, scale: int = 3, psm: int = 8) -> str:
    """Run Tesseract on a preprocessed crop.

    Args:
        crop: the cropped oval image
        scale: upscale factor before OCR
        psm: Tesseract page segmentation mode
             8 = single word (default), 7 = single line, 13 = raw line

    Whitelist restricts to A-Z 0-9.

    Tries adaptive preprocessing first (CLAHE + adaptive threshold) which
    handles oval border bleed much better than Otsu — avoids garbled reads
    like "GD" when the border merges with text.  Falls back to Otsu if
    adaptive produces fewer than 3 alphanumeric characters.

    If PSM 8 still produces a very short result (< 3 alphanumeric chars),
    automatically retries with PSM 7 (single text line) which works
    better on some Tesseract installations (especially Windows 5.x).
    """
    whitelist = "-c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"

    # Try adaptive preprocessing first — handles oval border bleed that
    # causes Otsu to merge text with borders (producing "GD", "G0D", etc.)
    processed_adap = preprocess_adaptive(crop, scale=scale)
    text = pytesseract.image_to_string(
        processed_adap, config=f"--psm {psm} {whitelist}"
    ).strip()
    alpha_count = sum(1 for c in text if c.isalnum())

    # Fallback to Otsu if adaptive produced a poor result
    if alpha_count < 3:
        processed_otsu = preprocess_for_ocr(crop, scale=scale)
        text_otsu = pytesseract.image_to_string(
            processed_otsu, config=f"--psm {psm} {whitelist}"
        ).strip()
        otsu_alpha = sum(1 for c in text_otsu if c.isalnum())
        if otsu_alpha > alpha_count:
            text = text_otsu
            alpha_count = otsu_alpha

    # Auto-retry with PSM 7 if PSM 8 produced a short/garbled result
    if psm == 8 and alpha_count < 3:
        alt = pytesseract.image_to_string(
            processed_adap, config=f"--psm 7 {whitelist}"
        ).strip()
        alt_alpha = sum(1 for c in alt if c.isalnum())
        if alt_alpha > alpha_count:
            logger.debug("PSM 7 improved OCR: %r → %r", text, alt)
            text = alt

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
    "71":  "LT",     # L misread as 7, T misread as 1
    "7T":  "LT",     # L misread as 7
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


def _normalize_digits(text: str) -> str:
    """Fix OCR letter/digit confusion in the numeric portion of a code.

    After the leading letter prefix, 'I' and 'l' should be '1',
    and 'O' should be '0'.  E.g. "LTII" → "LT11", "LTO4" → "LT04".
    """
    # Find where the digit portion starts (first digit or misread digit)
    m = re.match(r"^([A-Z]+)", text)
    if not m:
        return text
    prefix_end = m.end()
    prefix_part = text[:prefix_end]
    digit_part = text[prefix_end:]

    # In the digit portion, fix common OCR confusion
    digit_part = digit_part.replace("I", "1").replace("O", "0")

    return prefix_part + digit_part


# Pattern for a valid fixture code: 1-3 letters, 1-3 digits, optional suffix letter
_FIXTURE_CODE_RE = re.compile(r"^[A-Z]{1,3}\d{1,3}[A-Z]?$")


def _clean_and_normalize(raw: str) -> str | None:
    """Strip non-alphanumeric chars, uppercase, normalize, and validate.

    Returns None if the result doesn't look like a fixture code.
    """
    cleaned = re.sub(r"[^A-Za-z0-9]", "", raw).upper()
    if not cleaned or len(cleaned) < 2:
        return None
    cleaned = _normalize_prefix(cleaned)
    cleaned = _normalize_digits(cleaned)
    cleaned = _normalize_suffix(cleaned)

    # Only accept text that looks like a fixture code
    if _FIXTURE_CODE_RE.match(cleaned):
        return cleaned

    # Strip 1-2 leading noise characters and retry normalization.
    # OCR often prepends border artifacts: "CLT11" → "LT11", "GLT04" → "LT04"
    for offset in range(1, min(3, len(cleaned) - 1)):
        candidate = cleaned[offset:]
        if len(candidate) < 3:
            break
        candidate = _normalize_prefix(candidate)
        candidate = _normalize_digits(candidate)
        candidate = _normalize_suffix(candidate)
        if _FIXTURE_CODE_RE.match(candidate):
            return candidate

    return None


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


def _has_text_content(crop: np.ndarray, dark_pct_range: tuple[float, float] = (0.02, 0.90)) -> bool:
    """Quick check whether a crop contains text-like content.

    A fixture oval crop should have SOME dark pixels (text) on a light
    background — roughly 5-85% dark.  Empty white regions, solid black
    blobs, and near-uniform crops are rejected without calling Tesseract.
    """
    if crop.size == 0:
        return False
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if len(crop.shape) == 3 else crop
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    dark_fraction = 1.0 - np.count_nonzero(binary) / binary.size
    return dark_pct_range[0] <= dark_fraction <= dark_pct_range[1]


def _ocr_with_retries(
    image: np.ndarray,
    oval: dict,
    prefix: str,
) -> tuple[str, str | None]:
    """Try multiple crop/scale strategies until one produces a prefix match.

    Returns (raw_text, cleaned_fixture_or_None).
    The first attempt uses default settings; subsequent attempts use
    _RETRY_STRATEGIES.  Stops as soon as a prefix match is found.
    Skips OCR entirely for crops with no visible text content, and
    skips retries when the first pass produced no alphanumeric text.
    """
    # First attempt: default crop + scale
    crop = crop_oval(image, oval)
    if crop.size == 0:
        return ("", None)

    # Quick visual pre-check — skip Tesseract for empty/solid crops
    if not _has_text_content(crop):
        return ("", None)

    raw = ocr_crop(crop)
    cleaned = _clean_and_normalize(raw)
    if cleaned and _is_valid_prefix_match(cleaned, prefix):
        return (raw, cleaned)

    # Only retry if first pass produced at least 2 alphanumeric chars —
    # otherwise there's no text here and retries are wasted.
    alpha_count = sum(1 for c in raw if c.isalnum())
    if alpha_count < 2:
        return (raw, None)

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
# Fuzzy matching against known fixture codes
# ---------------------------------------------------------------------------

_FUZZY_THRESHOLD = 70  # minimum fuzz ratio to accept a match


def _fuzzy_match(text: str, known_codes: list[str]) -> str | None:
    """Try to fuzzy-match OCR text against a list of known fixture codes.

    Returns the best matching code if the score meets the threshold,
    otherwise None.
    """
    if not text or not known_codes:
        return None

    best_score = 0
    best_code = None
    for code in known_codes:
        score = fuzz.ratio(text.upper(), code.upper())
        if score > best_score:
            best_score = score
            best_code = code

    if best_score >= _FUZZY_THRESHOLD and best_code:
        logger.debug("Fuzzy matched %r → %s (score=%d)", text, best_code, best_score)
        return best_code

    return None


# Retry strategies for the no-prefix path (same idea as _RETRY_STRATEGIES
# but also includes adaptive preprocessing variants).
_NOPREFIX_RETRY_STRATEGIES = [
    {"margin_h": 0.10, "margin_v": 0.15, "scale": 4, "adaptive": True},
    {"margin_h": 0.05, "margin_v": 0.10, "scale": 4, "adaptive": True},
    {"margin_h": 0.10, "margin_v": 0.15, "scale": 4},
    {"margin_h": 0.05, "margin_v": 0.10, "scale": 4},
    {"margin_h": 0.20, "margin_v": 0.25, "scale": 5},
]


# ---------------------------------------------------------------------------
# Main recognition
# ---------------------------------------------------------------------------

def recognize_fixtures(
    image: np.ndarray,
    ovals: list[dict],
    *,
    prefix: str | None = None,
    known_codes: list[str] | None = None,
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
        known_codes: optional list of known fixture codes for fuzzy matching
                     (e.g. from legend parsing).

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
            # Fuzzy match fallback
            if not fixture and known_codes and raw:
                fixture = _fuzzy_match(raw, known_codes)
            results.append({"oval": oval, "raw_text": raw, "fixture": fixture})
            continue

        # No prefix — multi-strategy OCR with retries
        crop = crop_oval(image, oval)
        if crop.size == 0:
            continue

        if not _has_text_content(crop):
            continue

        raw = ocr_crop(crop)

        if _is_false_positive(raw):
            results.append({"oval": oval, "raw_text": raw, "fixture": None})
            continue

        cleaned = _clean_and_normalize(raw)
        if cleaned:
            results.append({"oval": oval, "raw_text": raw, "fixture": cleaned})
            continue

        # First pass failed — retry with alternative strategies
        alpha_count = sum(1 for c in raw if c.isalnum())
        best_raw = raw
        fixture = None

        if alpha_count >= 2:
            for strat in _NOPREFIX_RETRY_STRATEGIES:
                retry_crop = crop_oval(
                    image, oval,
                    margin_h=strat["margin_h"],
                    margin_v=strat["margin_v"],
                )
                if retry_crop.size == 0:
                    continue
                if strat.get("adaptive"):
                    retry_raw = ocr_crop_adaptive(retry_crop, scale=strat["scale"])
                else:
                    retry_raw = ocr_crop(retry_crop, scale=strat["scale"])
                retry_cleaned = _clean_and_normalize(retry_raw)
                if retry_cleaned:
                    best_raw = retry_raw
                    fixture = retry_cleaned
                    break

        # Fuzzy match fallback
        if not fixture and known_codes and best_raw:
            fixture = _fuzzy_match(best_raw, known_codes)

        results.append({"oval": oval, "raw_text": best_raw, "fixture": fixture})
    return results
