"""Legend/symbol sheet parser – extracts fixture codes from a project's legend page.

OCRs the legend page and looks specifically for the "Lighting" section table,
then extracts fixture code patterns (e.g. LT04, A1, RL-2) so the pipeline can
fuzzy-match against project-specific codes instead of a hardcoded list.
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
#   1-3 uppercase letters followed by 1-2 digits, optional suffix letter.
# Examples: LT04, LT04A, A1, RL2, EF12B, HP1, C3A
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

# Single-letter prefixes that are almost always OCR noise
_NOISE_PREFIXES = {"O", "I", "OO", "OE", "MN", "MNO"}

# Section headers that indicate the lighting fixture table
_LIGHTING_HEADERS = re.compile(
    r"(LIGHT(?:ING)?|LUMINAIRE|FIXTURE)\s*(SCHEDULE|LEGEND|TABLE|LIST)?",
    re.IGNORECASE,
)

# Section headers for non-lighting tables that we should stop at
_OTHER_HEADERS = re.compile(
    r"(POWER|RECEPTACLE|PANEL|MECHANICAL|PLUMBING|FIRE ALARM|DEVICE|SWITCH"
    r"|COMMUNICATION|DATA|MOTOR|DISCONNECT)\s*(SCHEDULE|LEGEND|TABLE|LIST)?",
    re.IGNORECASE,
)


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


def parse_legend_page(image: np.ndarray) -> list[str]:
    """Extract fixture codes from a legend/symbol sheet image.

    Strategy:
    1. OCR the full page
    2. Look for a "Lighting" / "Luminaire" section header
    3. If found, extract codes only from that section (until the next
       section header or end of text)
    4. If no lighting header found, fall back to extracting codes from
       the entire page

    Args:
        image: BGR or grayscale image of the legend page (rendered at 300 DPI).

    Returns:
        Sorted list of unique fixture codes found.
    """
    if len(image.shape) == 3:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    else:
        gray = image

    # Full-page OCR with layout analysis
    text = pytesseract.image_to_string(gray, config="--psm 6")

    # Try to find the lighting section
    lighting_match = _LIGHTING_HEADERS.search(text)

    if lighting_match:
        # Extract text from the lighting section start onwards
        section_start = lighting_match.start()
        section_text = text[section_start:]

        # Look for the next non-lighting section header to bound the section
        other_match = _OTHER_HEADERS.search(section_text[len(lighting_match.group()):])
        if other_match:
            section_end = len(lighting_match.group()) + other_match.start()
            section_text = section_text[:section_end]

        logger.info("  Found lighting section starting at char %d (length %d chars)",
                     section_start, len(section_text))
        codes = _extract_codes(section_text)

        if codes:
            logger.info("  Extracted %d codes from lighting section: %s", len(codes), codes)
            return codes

        logger.warning("  Lighting section found but no codes extracted, falling back to full page")

    else:
        logger.info("  No lighting section header found, scanning full page")

    # Fallback: scan the entire page
    return _extract_codes(text)
