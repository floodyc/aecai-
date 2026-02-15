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
#   1-4 uppercase letters, optionally followed by a dash/space,
#   then 1-3 digits, optionally followed by a suffix letter.
# Examples: LT04, LT04A, A1, RL-2, EF12B, HP1
_CODE_PATTERN = re.compile(
    r"\b([A-Z]{1,4}[-\s]?\d{1,3}[A-Z]?)\b"
)

# Codes to ignore – common drawing text that matches the pattern but isn't a fixture
_IGNORE = {
    "A1", "A2", "A3", "A4", "B1", "B2",  # paper sizes
    "P1", "P2", "P3",  # parking levels (context-dependent, but safe default)
    "DWG", "REV", "NO",
}


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
        if code not in _IGNORE and len(code) >= 2:
            codes.add(code)

    return sorted(codes)
