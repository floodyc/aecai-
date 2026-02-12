"""OCR module – crops each detected oval, runs Tesseract, and fuzzy-corrects.

The pipeline:
1. Centre-crop around each oval to remove border artefacts
2. Pre-process (resize, threshold) for better Tesseract accuracy
3. Run Tesseract in single-word mode (PSM 8)
4. Fuzzy-match raw text against known luminaire codes
"""

from __future__ import annotations

import re

import cv2
import numpy as np
import pytesseract
from thefuzz import fuzz

from .config import CROP_PADDING, FUZZY_THRESHOLD, KNOWN_LUMINAIRES, TESSERACT_CMD

pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD


def crop_oval(image: np.ndarray, oval: dict, padding: int = CROP_PADDING) -> np.ndarray:
    """Centre-crop around an oval detection, removing outer border pixels."""
    h_img, w_img = image.shape[:2]
    x = max(oval["x"] + padding, 0)
    y = max(oval["y"] + padding, 0)
    x2 = min(oval["x"] + oval["w"] - padding, w_img)
    y2 = min(oval["y"] + oval["h"] - padding, h_img)

    if x2 <= x or y2 <= y:
        # Fallback: use full bounding box
        x, y = oval["x"], oval["y"]
        x2, y2 = x + oval["w"], y + oval["h"]

    return image[y:y2, x:x2]


def preprocess_for_ocr(crop: np.ndarray) -> np.ndarray:
    """Resize and threshold a crop for better Tesseract accuracy."""
    if len(crop.shape) == 3:
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    else:
        gray = crop

    # Scale up small crops
    h, w = gray.shape
    if max(h, w) < 80:
        scale = 80 / max(h, w)
        gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)

    # Otsu binarisation
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    # Invert if background is dark (text should be dark-on-light for Tesseract)
    if np.mean(binary) < 128:
        binary = cv2.bitwise_not(binary)

    return binary


def ocr_crop(crop: np.ndarray) -> str:
    """Run Tesseract on a preprocessed crop and return raw text."""
    processed = preprocess_for_ocr(crop)
    text = pytesseract.image_to_string(
        processed,
        config="--psm 8 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789",
    )
    return text.strip()


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


def recognize_fixtures(image: np.ndarray, ovals: list[dict]) -> list[dict]:
    """OCR all detected ovals and return fixture identifications.

    Returns a list of dicts:
        oval     – original oval dict
        raw_text – Tesseract output before correction
        fixture  – corrected luminaire code (or None)
    """
    results = []
    for oval in ovals:
        crop = crop_oval(image, oval)
        if crop.size == 0:
            continue

        raw = ocr_crop(crop)
        fixture = fuzzy_correct(raw)

        results.append(
            {
                "oval": oval,
                "raw_text": raw,
                "fixture": fixture,
            }
        )
    return results
