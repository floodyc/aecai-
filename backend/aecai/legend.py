"""Legend/symbol sheet parser – extracts luminaire type codes from a legend page.

OCRs the legend and looks for LT-prefixed fixture codes (e.g. LT04, LT04A).
These codes are used by the pipeline for fuzzy-matching OCR text inside ovals.
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

# Pattern for luminaire type codes:
#   LT prefix followed by 1-3 digits, optional suffix letter.
# Examples: LT04, LT04A, LT04B, LT12, LT16
_LT_CODE_PATTERN = re.compile(
    r"\bLT\d{1,3}[A-Z]?\b"
)

# Broader pattern for general fixture codes (1-3 letters + 1-3 digits + optional suffix)
_GENERAL_CODE_PATTERN = re.compile(
    r"(?<![A-Z])([A-Z]{1,3}\d{1,3}[A-Z]?)(?![A-Z0-9])"
)

# Section headers that indicate the lighting fixture table
_LIGHTING_HEADERS = re.compile(
    r"(LIGHT(?:ING)?|LUMINAIRE|FIXTURE)\s*(SCHEDULE|LEGEND|TABLE|LIST|TYPE)?",
    re.IGNORECASE,
)


def parse_legend_page(image: np.ndarray) -> list[str]:
    """Extract luminaire type codes from a legend/symbol sheet image.

    Strategy:
    1. OCR the full page/image
    2. Look for LT-prefixed codes first (most reliable)
    3. If no LT codes found, look for a lighting section header and
       extract general codes from that section

    Args:
        image: BGR or grayscale image of the legend page.

    Returns:
        Sorted list of unique fixture codes found, or empty list.
    """
    if len(image.shape) == 3:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    else:
        gray = image

    # Full-page OCR
    text = pytesseract.image_to_string(gray, config="--psm 6")
    upper_text = text.upper()

    logger.info("  Legend OCR text (first 500 chars): %s", text[:500].replace("\n", " | "))

    # Strategy 1: Look for LT-prefixed codes (highest confidence)
    lt_codes = sorted(set(_LT_CODE_PATTERN.findall(upper_text)))
    if lt_codes:
        logger.info("  Found %d LT codes: %s", len(lt_codes), lt_codes)
        return lt_codes

    # Strategy 2: Look for a lighting section, extract general codes from it
    lighting_match = _LIGHTING_HEADERS.search(upper_text)
    if lighting_match:
        section_text = upper_text[lighting_match.start():]
        logger.info("  Found lighting section header at char %d", lighting_match.start())

        codes = sorted(set(
            m.group(1) for m in _GENERAL_CODE_PATTERN.finditer(section_text)
            if len(m.group(1)) >= 2
        ))
        if codes:
            logger.info("  Extracted %d codes from lighting section: %s", len(codes), codes)
            return codes

    # Strategy 3: Any general codes on the page (least confident)
    all_codes = sorted(set(
        m.group(1) for m in _GENERAL_CODE_PATTERN.finditer(upper_text)
        if len(m.group(1)) >= 2
    ))
    if all_codes:
        logger.info("  Extracted %d general codes from full page: %s", len(all_codes), all_codes)
        return all_codes

    logger.warning("  No fixture codes found in legend")
    return []
