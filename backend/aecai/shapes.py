"""Fixture symbol detection using OpenCV contour analysis.

Detects oval/elliptical fixture symbols on electrical floor plans.
Uses RETR_LIST to find ALL contours (not just outermost), which is
critical for floor plans where fixture ovals are nested inside room
outlines.
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


MAX_OVALS = 500  # safety cap to prevent Tesseract from hanging


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

    Uses RETR_LIST to find ALL contours regardless of nesting depth.
    This is essential for floor plans where fixture ovals sit inside
    room outlines and other enclosing shapes.

    Returns a list of dicts with keys:
        x, y, w, h  – bounding rectangle
        cx, cy       – centre point
        area         – contour area
        circularity  – 4*pi*area / perimeter^2
    """
    _, binary = _binarize(image)

    # RETR_LIST finds ALL contours (not just outermost). Critical for floor
    # plans where small fixture ovals are nested inside room boundaries.
    contours, _ = cv2.findContours(binary, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)

    logger.info("  Total contours found: %d", len(contours))

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

        # Skip shapes too small in either dimension — text characters
        # at 300 DPI are typically <20px wide, fixture ovals are >25px
        if w < 25 or h < 15:
            continue

        aspect = w / h if h > 0 else 0
        if aspect < min_aspect or aspect > max_aspect:
            continue

        # Skip very large shapes (room outlines, title blocks)
        if w > 200 or h > 200:
            continue

        ovals.append(_contour_to_dict(cnt, area, circularity))

    # De-duplicate overlapping detections (nested contours can produce
    # near-identical bounding boxes)
    ovals = _deduplicate(ovals)

    # Cap to prevent OCR stage from hanging on very busy drawings
    if len(ovals) > MAX_OVALS:
        logger.warning("  Found %d ovals, capping to %d (sorted by circularity)",
                        len(ovals), MAX_OVALS)
        ovals.sort(key=lambda d: d["circularity"], reverse=True)
        ovals = ovals[:MAX_OVALS]

    logger.info("  Ovals after filtering: %d", len(ovals))
    return ovals


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
