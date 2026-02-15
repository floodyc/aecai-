"""Legend/symbol sheet parser – extracts fixture codes AND graphical symbol
templates from a project's legend image or page.

Two outputs:
1. Fixture codes (list[str]) – for text-search fallback
2. Symbol templates (list[dict]) – for template matching on floor plans
   Each dict: {code: str, template: np.ndarray}
"""

from __future__ import annotations

import logging
import re

import cv2
import numpy as np
import pytesseract

from .config import TESSERACT_CMD

pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD
logger = logging.getLogger(__name__)

# Pattern that matches typical electrical fixture codes:
#   1-3 uppercase letters followed by 1-3 digits, optional suffix letter.
# Examples: LT04, LT04A, A1, RL2, EF12B, HP1, C3, C10
_CODE_PATTERN = re.compile(
    r"(?<![A-Z])([A-Z]{1,3}\d{1,3}[A-Z]?)(?![A-Z0-9])"
)

# Minimal ignore list – only things that are NEVER fixture codes
_IGNORE = {"A0"}

# Single-letter prefixes that are OCR noise
_NOISE_PREFIXES = {"O", "I", "OO", "OE", "MN", "MNO"}


def _extract_codes(text: str) -> list[str]:
    """Extract fixture codes from a block of text."""
    codes: set[str] = set()
    for match in _CODE_PATTERN.finditer(text.upper()):
        code = match.group(1).replace(" ", "").replace("-", "")
        if code in _IGNORE:
            continue
        if len(code) < 2:
            continue
        prefix = re.match(r"[A-Z]+", code)
        if prefix and prefix.group() in _NOISE_PREFIXES:
            continue
        codes.add(code)
    return sorted(codes)


def _find_table_rows(gray: np.ndarray) -> list[tuple[int, int]]:
    """Detect horizontal row boundaries in a legend table.

    Returns list of (y_start, y_end) tuples for each row.
    """
    h, w = gray.shape

    # Create horizontal projection (sum of dark pixels per row)
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    row_sums = np.sum(binary, axis=1) / 255

    # Threshold: rows with very little content are gaps/dividers
    threshold = w * 0.02  # at least 2% of width has ink
    is_content = row_sums > threshold

    # Find contiguous runs of content
    rows: list[tuple[int, int]] = []
    in_row = False
    row_start = 0
    for y in range(h):
        if is_content[y] and not in_row:
            row_start = y
            in_row = True
        elif not is_content[y] and in_row:
            if y - row_start > 10:  # minimum row height
                rows.append((row_start, y))
            in_row = False
    if in_row and h - row_start > 10:
        rows.append((row_start, h))

    return rows


def extract_symbol_templates(image: np.ndarray) -> list[dict]:
    """Extract symbol templates and their codes from a legend table image.

    Strategy:
    1. OCR the legend to find all text with bounding boxes
    2. Identify fixture codes from the text
    3. For each code, find the graphical symbol to its left (same row)
    4. Extract the symbol region as a template for matching

    Args:
        image: BGR or grayscale image of the legend table.

    Returns:
        list of {code: str, template: np.ndarray, bbox: (x,y,w,h)}
    """
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image
    h_img, w_img = gray.shape

    # Step 1: OCR with bounding boxes
    data = pytesseract.image_to_data(
        gray, config="--psm 6", output_type=pytesseract.Output.DICT
    )

    # Step 2: Find text that looks like fixture codes + their positions
    codes_with_pos: list[dict] = []
    seen_codes: set[str] = set()
    for i in range(len(data["text"])):
        text = data["text"][i].strip()
        if not text:
            continue
        cleaned = re.sub(r"[^A-Za-z0-9]", "", text).upper()
        if not cleaned or len(cleaned) < 2:
            continue
        m = _CODE_PATTERN.fullmatch(cleaned)
        if m and cleaned not in _IGNORE and cleaned not in seen_codes:
            prefix = re.match(r"[A-Z]+", cleaned)
            if prefix and prefix.group() in _NOISE_PREFIXES:
                continue
            codes_with_pos.append({
                "code": cleaned,
                "x": data["left"][i],
                "y": data["top"][i],
                "w": data["width"][i],
                "h": data["height"][i],
                "cy": data["top"][i] + data["height"][i] // 2,
            })
            seen_codes.add(cleaned)

    logger.info("  Legend OCR found %d potential codes: %s",
                len(codes_with_pos), [c["code"] for c in codes_with_pos])

    if not codes_with_pos:
        return []

    # Step 3: Find contours that could be symbols
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    # Morphological close to connect symbol parts
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    closed = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel, iterations=2)

    contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    # Filter to reasonable symbol sizes
    symbol_regions: list[dict] = []
    for cnt in contours:
        x, y, w, h = cv2.boundingRect(cnt)
        area = w * h
        # Symbols are typically 15-150px in each dimension
        if area < 100 or area > 40000:
            continue
        if w < 8 or h < 8:
            continue
        if w > w_img * 0.4 or h > h_img * 0.3:
            continue  # too big, probably table border
        aspect = w / h if h > 0 else 0
        if aspect < 0.15 or aspect > 7.0:
            continue  # too elongated, probably a line

        symbol_regions.append({
            "x": x, "y": y, "w": w, "h": h,
            "cx": x + w // 2, "cy": y + h // 2,
        })

    logger.info("  Found %d potential symbol regions", len(symbol_regions))

    # Step 4: Match each code to the nearest symbol on its left (same row)
    templates: list[dict] = []
    used_symbols: set[int] = set()

    for code_info in codes_with_pos:
        best_sym = None
        best_dist = float("inf")
        best_idx = -1

        for idx, sym in enumerate(symbol_regions):
            if idx in used_symbols:
                continue
            # Symbol should be to the LEFT of the code text
            if sym["x"] + sym["w"] > code_info["x"] + code_info["w"] * 0.5:
                continue
            # Same vertical band (within 40px of each other's centre)
            dy = abs(sym["cy"] - code_info["cy"])
            if dy > 40:
                continue
            # Prefer closest horizontally
            dx = code_info["x"] - (sym["x"] + sym["w"])
            if 0 <= dx < best_dist:
                best_dist = dx
                best_sym = sym
                best_idx = idx

        if best_sym is not None:
            used_symbols.add(best_idx)
            # Extract template with padding
            pad = 4
            x1 = max(0, best_sym["x"] - pad)
            y1 = max(0, best_sym["y"] - pad)
            x2 = min(w_img, best_sym["x"] + best_sym["w"] + pad)
            y2 = min(h_img, best_sym["y"] + best_sym["h"] + pad)
            template = gray[y1:y2, x1:x2].copy()

            if template.size > 0:
                templates.append({
                    "code": code_info["code"],
                    "template": template,
                    "bbox": (x1, y1, x2 - x1, y2 - y1),
                })
                logger.info("    Extracted template for %s: %dx%d px",
                            code_info["code"], template.shape[1], template.shape[0])
        else:
            logger.warning("    No symbol found for code %s", code_info["code"])

    return templates


def parse_legend_page(image: np.ndarray) -> list[str]:
    """Extract just the fixture codes (no templates) from a legend image.

    Backward-compatible function for text-search fallback.
    """
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image
    text = pytesseract.image_to_string(gray, config="--psm 6")

    logger.info("  Legend OCR full text (first 500 chars): %s", text[:500])

    codes = _extract_codes(text)
    if codes:
        logger.info("  Extracted %d codes from legend: %s", len(codes), codes)
    else:
        logger.warning("  No codes found in legend text")
    return codes
