"""Legend/symbol sheet parser – extracts luminaire type codes from a legend page.

Supports two code styles:
- LT-prefixed codes: LT04, LT04A, LT12  (e.g. "LT" prefix projects)
- Number-only types: 30, 31, 32A          (e.g. "TYPE 30" projects)

OCRs the legend and extracts whatever fixture codes are present.
These are used by the pipeline for fuzzy-matching OCR text inside ovals.
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

# Pattern for LT-prefixed codes: LT04, LT04A, LT12
_LT_CODE_PATTERN = re.compile(r"\bLT\d{1,3}[A-Z]?\b")

# Pattern for general letter+digit fixture codes: A1, LT04, FX12A
_GENERAL_CODE_PATTERN = re.compile(
    r"(?<![A-Z])([A-Z]{1,3}\d{1,3}[A-Z]?)(?![A-Z0-9])"
)

# Pattern for number-only luminaire types: "TYPE 30", "TYPE 31A"
# Matches standalone 1-3 digit numbers (optionally with suffix letter)
_TYPE_NUMBER_PATTERN = re.compile(
    r"(?:TYPE\s*)?(\d{1,3}[A-Z]?)\b"
)

# Section headers for lighting fixture table
_LIGHTING_HEADERS = re.compile(
    r"(LIGHT(?:ING)?|LUMINAIRE|FIXTURE)\s*(SCHEDULE|LEGEND|TABLE|LIST|TYPE)?",
    re.IGNORECASE,
)

# "LUMINAIRE TYPE" indicator (signals number-based type scheme)
_LUMINAIRE_TYPE_INDICATOR = re.compile(
    r"LUMINAIRE\s+TYPE|DENOTES\s+LUMINAIRE|LUM[\.\s]*SCHEDULE",
    re.IGNORECASE,
)


def parse_legend_page(image: np.ndarray) -> list[str]:
    """Extract luminaire type codes from a legend/symbol sheet image.

    Strategy:
    1. OCR the full page/image
    2. Look for LT-prefixed codes first (highest confidence)
    3. Look for "LUMINAIRE TYPE" indicator → extract number-only types
    4. Look for general letter+digit codes in a lighting section
    5. Fall back to any general codes on the page

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

    # Strategy 1: LT-prefixed codes (highest confidence)
    lt_codes = sorted(set(_LT_CODE_PATTERN.findall(upper_text)))
    if lt_codes:
        logger.info("  Found %d LT codes: %s", len(lt_codes), lt_codes)
        return lt_codes

    # Strategy 2: "LUMINAIRE TYPE" indicator → number-based types
    # e.g. "DENOTES LUMINAIRE TYPE - THIS EX: 'TYPE 30'"
    type_match = _LUMINAIRE_TYPE_INDICATOR.search(upper_text)
    if type_match:
        logger.info("  Found luminaire type indicator, extracting number codes...")
        # Look for "TYPE XX" patterns near the indicator
        section = upper_text[max(0, type_match.start() - 100):]
        type_numbers = re.findall(r"TYPE\s+['\"]?(\d{1,3}[A-Z]?)", section)
        if type_numbers:
            codes = sorted(set(type_numbers))
            logger.info("  Found TYPE references: %s", codes)
            # These are example codes; the actual types are on the floor plan
            # Return them so fuzzy matching can correct OCR

    # Strategy 3: Lighting section with general codes
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

    # Strategy 4: Any general codes on the page
    all_codes = sorted(set(
        m.group(1) for m in _GENERAL_CODE_PATTERN.finditer(upper_text)
        if len(m.group(1)) >= 2
    ))
    if all_codes:
        logger.info("  Extracted %d general codes from full page: %s", len(all_codes), all_codes)
        return all_codes

    logger.warning("  No fixture codes found in legend")
    return []
