"""Fixture symbol detection using OpenCV contour analysis.

Detects oval/elliptical fixture symbols on electrical floor plans.
Uses ellipse fitting (not circularity) to distinguish true ovals from
circles, squares, and other shapes.  Aspect ratio >= 1.2 ensures only
elongated ovals (wider than tall) are selected — fixture label ovals,
not junction-box circles or switch symbols.
"""

from __future__ import annotations

import logging

import cv2
import numpy as np

from .config import (
    OVAL_ELLIPSE_FIT_MAX,
    OVAL_ELLIPSE_FIT_MIN,
    OVAL_MAX_AREA,
    OVAL_MAX_ASPECT,
    OVAL_MIN_AREA,
    OVAL_MIN_ASPECT,
)

logger = logging.getLogger(__name__)


def _binarize(image: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Convert to grayscale and produce a binary image for contour detection.

    Uses a two-stage morphological close:
    1. Small kernel (3x3) to close tiny gaps in line work
    2. Larger kernel (7x7) to merge text glyphs INTO the oval boundary,
       turning a text-filled oval into a single solid blob whose contour
       is roughly elliptical.
    """
    if len(image.shape) == 3:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    else:
        gray = image

    binary = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 15, 8
    )

    # Stage 1: close tiny gaps in contour lines
    k_small = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, k_small, iterations=2)

    # Stage 2: merge text inside ovals into a solid blob
    # 7x7 ellipse bridges gaps between characters and the oval wall
    k_large = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, k_large, iterations=1)

    return gray, binary


def _ellipse_fit_ratio(cnt) -> float:
    """Compute how well a contour matches a fitted ellipse.

    Returns the ratio of contour area to fitted-ellipse area.
    A perfect ellipse returns ~1.0.  Values 0.6–1.4 indicate a good
    oval shape.  Very low (<0.4) means irregular; very high (>1.6)
    means the contour encloses much more than the ellipse.
    """
    if len(cnt) < 5:
        return 0.0

    contour_area = cv2.contourArea(cnt)
    if contour_area < 1:
        return 0.0

    ellipse = cv2.fitEllipse(cnt)
    (_, (ma, MA), _) = ellipse
    ellipse_area = np.pi * (ma / 2) * (MA / 2)

    if ellipse_area < 1:
        return 0.0

    return contour_area / ellipse_area


def _contour_to_dict(cnt, area: float, ellipse_fit: float) -> dict:
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
        "ellipse_fit": float(ellipse_fit),
    }


MAX_OVALS = 500  # safety cap to prevent Tesseract from hanging


def find_ovals(
    image: np.ndarray,
    *,
    min_area: int = OVAL_MIN_AREA,
    max_area: int = OVAL_MAX_AREA,
    min_aspect: float = OVAL_MIN_ASPECT,
    max_aspect: float = OVAL_MAX_ASPECT,
    fit_min: float = OVAL_ELLIPSE_FIT_MIN,
    fit_max: float = OVAL_ELLIPSE_FIT_MAX,
) -> list[dict]:
    """Detect oval contours in a grayscale or BGR image.

    Filtering pipeline:
    1. Area 400–8000 px² (at 300 DPI)
    2. Aspect ratio 1.2–3.5 (wider than tall — eliminates circles)
    3. Ellipse fit 0.6–1.4 (contour matches an ellipse shape)
    4. Minimum dimension (w>=25, h>=12) to skip stray text fragments

    Uses RETR_LIST to find ALL contours regardless of nesting depth.
    This is essential for floor plans where fixture ovals sit inside
    room outlines and other enclosing shapes.

    Returns a list of dicts with keys:
        x, y, w, h   – bounding rectangle
        cx, cy        – centre point
        area          – contour area
        ellipse_fit   – ratio of contour area to fitted ellipse area
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

        # Need >=5 points to fit an ellipse
        if len(cnt) < 5:
            continue

        x, y, w, h = cv2.boundingRect(cnt)

        # Skip shapes too small in either dimension — text characters
        # at 300 DPI are typically <20px wide, fixture ovals are >25px
        if w < 25 or h < 12:
            continue

        # Aspect ratio filter: fixture ovals are wider than tall (1.2+)
        # This eliminates circles (aspect ~1.0) like switches and outlets
        aspect = w / h if h > 0 else 0
        if aspect < min_aspect or aspect > max_aspect:
            continue

        # Skip very large shapes (room outlines, title blocks)
        if w > 200 or h > 100:
            continue

        # Ellipse fit: how closely does the contour match an ellipse?
        fit = _ellipse_fit_ratio(cnt)
        if fit < fit_min or fit > fit_max:
            continue

        ovals.append(_contour_to_dict(cnt, area, fit))

    # De-duplicate overlapping detections (nested contours can produce
    # near-identical bounding boxes)
    ovals = _deduplicate(ovals)

    # Cap to prevent OCR stage from hanging on very busy drawings
    if len(ovals) > MAX_OVALS:
        logger.warning("  Found %d ovals, capping to %d (sorted by ellipse_fit)",
                        len(ovals), MAX_OVALS)
        ovals.sort(key=lambda d: abs(1.0 - d["ellipse_fit"]))
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
