"""OCR module – two detection strategies for fixture codes on floor plans.

Strategy 1 (shape-based): crops each detected oval, runs Tesseract PSM 8,
fuzzy-matches against known codes. Works for drawings with oval symbols.

Strategy 2 (text-search): full-page OCR with word bounding boxes, then
filters words that match known fixture codes. Works for any drawing style.
The legend drives what codes to keep.
"""

from __future__ import annotations

import logging
import re

import cv2
import numpy as np
import pytesseract
from thefuzz import fuzz

from .config import CROP_PADDING, FUZZY_THRESHOLD, KNOWN_LUMINAIRES, TESSERACT_CMD

pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD
logger = logging.getLogger(__name__)


def crop_oval(image: np.ndarray, oval: dict, padding: int = CROP_PADDING) -> np.ndarray:
    """Crop around an oval detection.

    padding > 0 shrinks inward, padding < 0 expands outward.
    Negative padding ensures the full text (e.g. "LT04") is captured
    even when letters are close to the oval boundary.
    """
    h_img, w_img = image.shape[:2]
    x = max(oval["x"] + padding, 0)
    y = max(oval["y"] + padding, 0)
    x2 = min(oval["x"] + oval["w"] - padding, w_img)
    y2 = min(oval["y"] + oval["h"] - padding, h_img)

    if x2 <= x or y2 <= y:
        x, y = oval["x"], oval["y"]
        x2, y2 = x + oval["w"], y + oval["h"]

    return image[y:y2, x:x2]


def preprocess_for_ocr(crop: np.ndarray) -> np.ndarray:
    """Resize and threshold a crop for better Tesseract accuracy.

    Scales small crops up to at least 120px on the longest side so
    Tesseract can read small fixture codes like "LT04A".  Adds a white
    border so characters at the edges aren't clipped.
    """
    if len(crop.shape) == 3:
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    else:
        gray = crop

    # Scale up so the longest side is at least 120px
    h, w = gray.shape
    target = 120
    if max(h, w) < target:
        scale = target / max(h, w)
        gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)

    # Otsu binarisation
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    # Invert if background is dark (text should be dark-on-light for Tesseract)
    if np.mean(binary) < 128:
        binary = cv2.bitwise_not(binary)

    # Add white border — Tesseract needs some margin around characters
    binary = cv2.copyMakeBorder(binary, 10, 10, 10, 10, cv2.BORDER_CONSTANT, value=255)

    return binary


def ocr_crop(crop: np.ndarray) -> str:
    """Run Tesseract on a preprocessed crop and return raw text.

    Tries PSM 7 (single text line) first, falls back to PSM 8 (single word).
    PSM 7 handles codes like "LT04A" better since it expects a full line
    rather than a single word/character.
    """
    processed = preprocess_for_ocr(crop)
    whitelist = "-c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"

    # Try PSM 7 (single text line) — better for multi-character codes
    text = pytesseract.image_to_string(processed, config=f"--psm 7 {whitelist}").strip()

    # If result is too short, try PSM 8 (single word) as fallback
    if len(text) < 3:
        text2 = pytesseract.image_to_string(processed, config=f"--psm 8 {whitelist}").strip()
        if len(text2) > len(text):
            text = text2

    return text


def fuzzy_correct(raw_text: str, known: list[str] | None = None, threshold: int = FUZZY_THRESHOLD) -> str | None:
    """Fuzzy-match OCR text against known luminaire codes.

    Returns the best match if the score is above threshold, else None.
    """
    if not raw_text:
        return None

    known = known or KNOWN_LUMINAIRES

    # Quick cleanup: strip non-alphanumeric, uppercase
    cleaned = re.sub(r"[^A-Za-z0-9]", "", raw_text).upper()
    if not cleaned:
        return None

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


def recognize_fixtures(
    image: np.ndarray,
    ovals: list[dict],
    known: list[str] | None = None,
) -> list[dict]:
    """OCR all detected ovals and return fixture identifications.

    Any oval with readable text is counted as a fixture. The text inside
    can be numbers only (e.g. "30"), letters+numbers (e.g. "LT04"), or
    any alphanumeric code. Fuzzy matching against known codes is used
    for OCR correction when available.

    Args:
        image: the page image (BGR or grayscale)
        ovals: list of oval detection dicts from find_ovals()
        known: optional project-specific luminaire codes for fuzzy matching.
               If None, uses the default KNOWN_LUMINAIRES from config.

    Returns a list of dicts:
        oval     – original oval dict
        raw_text – Tesseract output before correction
        fixture  – corrected/cleaned code, or None if oval had no text
    """
    results = []
    for oval in ovals:
        crop = crop_oval(image, oval)
        if crop.size == 0:
            continue

        raw = ocr_crop(crop)

        # Try fuzzy correction against known codes
        fixture = fuzzy_correct(raw, known=known)

        # If no fuzzy match, use the cleaned raw text directly
        # Accept any alphanumeric text (numbers like "30" or codes like "LT04")
        if fixture is None and raw:
            cleaned = re.sub(r"[^A-Za-z0-9]", "", raw).upper()
            if cleaned:
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
