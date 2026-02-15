"""Legend/symbol sheet parser – extracts fixture codes from a project's legend page.

OCRs the legend page and extracts fixture code patterns (e.g. LT04, A1, RL-2)
so the pipeline can fuzzy-match against project-specific codes instead of a
hardcoded list.
"""

from __future__ import annotations

import re

import cv2
import numpy as np
import pytesseract

from .config import TESSERACT_CMD

pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD

# Pattern that matches typical electrical fixture codes:
#   1-3 uppercase letters followed by 1-2 digits, optional suffix letter.
# Examples: LT04, LT04A, A1, RL2, EF12B, HP1, C3A
# Requires the match to be "standalone" — not embedded in a longer word.
_CODE_PATTERN = re.compile(
    r"(?<![A-Z])([A-Z]{1,3}\d{1,2}[A-Z]?)(?![A-Z0-9])"
)

# Codes to ignore – common drawing text that matches the pattern
_IGNORE = {
    # Paper sizes
    "A0", "A1", "A2", "A3", "A4", "B1", "B2", "B3", "B4",
    # Parking / floor references
    "P1", "P2", "P3", "L1", "L2", "L3", "L4", "L5",
    # Common drawing abbreviations
    "E1", "E2", "E3", "N1", "S1",
    # Section/detail references
    "D1", "D2", "D3", "D4",
}

# Single-letter prefixes that are almost always OCR noise, not fixture codes.
# Real fixture codes usually have 2+ letter prefixes (LT, RL, EF, HP, etc.)
# or are well-known single-letter types (C, F, etc.).
_NOISE_PREFIXES = {"O", "I", "OO", "OE", "MN", "MNO"}


def parse_legend_page(image: np.ndarray) -> list[str]:
    """Extract fixture codes from a legend/symbol sheet image.

    Args:
        image: BGR or grayscale image of the legend page (rendered at 300 DPI).

    Returns:
        Sorted list of unique fixture codes found on the page.
    """
    if len(image.shape) == 3:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    else:
        gray = image

    # Full-page OCR with layout analysis
    text = pytesseract.image_to_string(gray, config="--psm 6")

    codes: set[str] = set()
    for match in _CODE_PATTERN.finditer(text.upper()):
        code = match.group(1).replace(" ", "").replace("-", "")
        if code in _IGNORE:
            continue
        if len(code) < 2:
            continue
        # Extract letter prefix and check against noise list
        prefix = re.match(r"[A-Z]+", code)
        if prefix and prefix.group() in _NOISE_PREFIXES:
            continue
        codes.add(code)

    return sorted(codes)
