"""Configuration for AECAI pipeline.

Paths switch between Windows (local dev) and Linux (Docker container).
Sheet-to-floor mapping is project-specific; for the web app, users can
configure this after upload or rely on auto-detection.
"""

import os
import platform
import shutil

# ---------------------------------------------------------------------------
# Tesseract / Poppler paths
# ---------------------------------------------------------------------------

if platform.system() == "Windows":
    TESSERACT_CMD = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    POPPLER_PATH = r"C:\poppler\Library\bin"
else:
    # Linux / Docker – Tesseract and Poppler installed via apt
    TESSERACT_CMD = shutil.which("tesseract") or "/usr/bin/tesseract"
    POPPLER_PATH = None  # poppler-utils in PATH on Linux

# Override via environment variables
TESSERACT_CMD = os.environ.get("TESSERACT_CMD", TESSERACT_CMD)
POPPLER_PATH = os.environ.get("POPPLER_PATH", POPPLER_PATH)

# ---------------------------------------------------------------------------
# PDF rendering
# ---------------------------------------------------------------------------

DPI = int(os.environ.get("AECAI_DPI", "300"))

# ---------------------------------------------------------------------------
# Oval detection parameters (calibrated – do not change)
# ---------------------------------------------------------------------------

OVAL_MIN_AREA = 400
OVAL_MAX_AREA = 8000
OVAL_MIN_ASPECT = 1.2
OVAL_MAX_ASPECT = 3.5
OVAL_ELLIPSE_FIT_MIN = 0.6
OVAL_ELLIPSE_FIT_MAX = 1.4

# ---------------------------------------------------------------------------
# OCR crop settings
# ---------------------------------------------------------------------------

# Center-crop margins (fraction of oval size) — crops INWARD to remove
# the drawn oval border before OCR.  Asymmetric because ovals are wider
# than tall and the code text is centred.
CROP_MARGIN_H = 0.15  # 15% horizontal margin
CROP_MARGIN_V = 0.20  # 20% vertical margin

# ---------------------------------------------------------------------------
# Default sheet → floor mapping (UBC Lot 4 IFC project-specific)
# For the web app this is configurable per job.
# ---------------------------------------------------------------------------

DEFAULT_SHEET_MAP: dict[int, str] = {
    1: "Cover",
    2: "Legend",
    3: "Site Plan",
    4: "Level 1",
    5: "Level 2",
    6: "Level 3",
    7: "Level 4",
    8: "Level 5",
    9: "Level 6",
    10: "Level 7",
    11: "Level 8",
    12: "Penthouse",
    13: "Roof",
    14: "Parking P1",
    15: "Parking P2",
}

# Typical-floor multiplier: some floors are identical and counted N times
DEFAULT_TYPICAL_MULTIPLIERS: dict[str, int] = {
    "Level 2": 1,
    "Level 3": 1,
    "Level 4": 1,
    "Level 5": 1,
    "Level 6": 1,
    "Level 7": 1,
    "Level 8": 1,
}
