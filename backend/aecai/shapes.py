"""Fixture symbol detection using OpenCV contour analysis.

Provides two detectors:
- find_ovals(): calibrated oval detector (original, strict circularity)
- find_symbols(): general enclosed-shape detector (circles, rectangles, etc.)

The pipeline tries find_ovals() first and falls back to find_symbols()
when no ovals are found, supporting a wider variety of drawing styles.
"""

from __future__ import annotations

import logging

import cv2
import numpy as np

from .config import (
    OVAL_CIRCULARITY_THRESH,
    OVAL_MAX_AREA,
    OVAL_MAX_ASPECT,
    OVAL_MIN_AREA,
    OVAL_MIN_ASPECT,
)

logger = logging.getLogger(__name__)

# Maximum symbols to keep from the general detector.
# Prevents the OCR stage from hanging on busy drawings.
MAX_GENERAL_DETECTIONS = 300


def _binarize(image: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Convert to grayscale and produce a binary image for contour detection."""
    if len(image.shape) == 3:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    else:
        gray = image

    binary = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 15, 8
    )

    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel, iterations=2)

    return gray, binary


def _contour_to_dict(cnt, area: float, circularity: float) -> dict:
    """Convert an OpenCV contour to our standard detection dict."""
    x, y, w, h = cv2.boundingRect(cnt)
    return {
        "x": int(x),
        "y": int(y),
        "w": int(w),
        "h": int(h),
        "cx": int(x + w // 2),
        "cy": int(y + h // 2),
        "area": float(area),
        "circularity": float(circularity),
    }


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

    Parameters are calibrated — do not change the detection thresholds
    without re-testing against real drawings.
    """
    _, binary = _binarize(image)
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

        ovals.append(_contour_to_dict(cnt, area, circularity))

    return ovals


def find_symbols(
    image: np.ndarray,
    *,
    min_area: int = 400,
    max_area: int = 20000,
    min_aspect: float = 0.2,
    max_aspect: float = 5.0,
    min_circularity: float = 0.15,
) -> list[dict]:
    """Detect general enclosed shapes (circles, rectangles, hexagons, etc.).

    This is a broader detector than find_ovals(). It accepts any small enclosed
    contour that could plausibly be a fixture symbol, including rectangles and
    other non-circular shapes.

    Returns the same dict format as find_ovals().
    """
    _, binary = _binarize(image)

    # Use RETR_TREE to catch nested contours (symbols inside title blocks, etc.)
    contours, hierarchy = cv2.findContours(binary, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)

    symbols: list[dict] = []
    for i, cnt in enumerate(contours):
        area = cv2.contourArea(cnt)
        if area < min_area or area > max_area:
            continue

        perimeter = cv2.arcLength(cnt, True)
        if perimeter == 0:
            continue

        circularity = 4 * np.pi * area / (perimeter * perimeter)
        if circularity < min_circularity:
            continue

        x, y, w, h = cv2.boundingRect(cnt)
        aspect = w / h if h > 0 else 0
        if aspect < min_aspect or aspect > max_aspect:
            continue

        # Skip very large contours that are likely room outlines or title blocks
        if w > 300 or h > 300:
            continue

        symbols.append(_contour_to_dict(cnt, area, circularity))

    # De-duplicate overlapping detections: keep the smaller (inner) one
    symbols = _deduplicate(symbols)

    # Cap to prevent OCR stage from hanging on very busy drawings
    if len(symbols) > MAX_GENERAL_DETECTIONS:
        logger.warning(
            "  General detector found %d shapes, capping to %d. "
            "Consider raising min_area or min_circularity.",
            len(symbols), MAX_GENERAL_DETECTIONS,
        )
        # Keep detections with highest circularity (most likely to be symbols)
        symbols.sort(key=lambda d: d["circularity"], reverse=True)
        symbols = symbols[:MAX_GENERAL_DETECTIONS]

    return symbols


def _deduplicate(detections: list[dict], iou_thresh: float = 0.5) -> list[dict]:
    """Remove overlapping detections, keeping the smaller bounding box."""
    if len(detections) <= 1:
        return detections

    # Sort by area ascending so smaller detections are preferred
    detections.sort(key=lambda d: d["area"])
    keep: list[dict] = []

    for det in detections:
        overlaps = False
        for kept in keep:
            # Compute IoU of bounding boxes
            x1 = max(det["x"], kept["x"])
            y1 = max(det["y"], kept["y"])
            x2 = min(det["x"] + det["w"], kept["x"] + kept["w"])
            y2 = min(det["y"] + det["h"], kept["y"] + kept["h"])

            if x2 > x1 and y2 > y1:
                inter = (x2 - x1) * (y2 - y1)
                area_det = det["w"] * det["h"]
                area_kept = kept["w"] * kept["h"]
                iou = inter / min(area_det, area_kept)
                if iou > iou_thresh:
                    overlaps = True
                    break

        if not overlaps:
            keep.append(det)

    return keep
