"""Oval (lighting fixture symbol) detection using OpenCV contour analysis.

Finds oval contours on electrical floor-plan images and returns their
bounding boxes for downstream OCR.  Parameters are calibrated — do not
change the detection thresholds without re-testing against real drawings.
"""

from __future__ import annotations

import cv2
import numpy as np

from .config import (
    OVAL_CIRCULARITY_THRESH,
    OVAL_MAX_AREA,
    OVAL_MAX_ASPECT,
    OVAL_MIN_AREA,
    OVAL_MIN_ASPECT,
)


def find_ovals(
    image: np.ndarray,
    *,
    min_area: int = OVAL_MIN_AREA,
    max_area: int = OVAL_MAX_AREA,
    min_aspect: float = OVAL_MIN_ASPECT,
    max_aspect: float = OVAL_MAX_ASPECT,
    circularity_thresh: float = OVAL_CIRCULARITY_THRESH,
) -> list[dict]:
    """Detect oval contours in a grayscale or BGR image.

    Returns a list of dicts with keys:
        x, y, w, h  – bounding rectangle
        cx, cy       – centre point
        area         – contour area
        circularity  – 4π·area / perimeter²
    """
    if len(image.shape) == 3:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    else:
        gray = image

    # Adaptive threshold to handle varying background brightness
    binary = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 15, 8
    )

    # Morphological close to merge broken oval outlines
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel, iterations=2)

    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    ovals: list[dict] = []
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < min_area or area > max_area:
            continue

        perimeter = cv2.arcLength(cnt, True)
        if perimeter == 0:
            continue

        circularity = 4 * np.pi * area / (perimeter * perimeter)
        if circularity < circularity_thresh:
            continue

        x, y, w, h = cv2.boundingRect(cnt)
        aspect = w / h if h > 0 else 0
        if aspect < min_aspect or aspect > max_aspect:
            continue

        ovals.append(
            {
                "x": int(x),
                "y": int(y),
                "w": int(w),
                "h": int(h),
                "cx": int(x + w // 2),
                "cy": int(y + h // 2),
                "area": float(area),
                "circularity": float(circularity),
            }
        )

    return ovals
