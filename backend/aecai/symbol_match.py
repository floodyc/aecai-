"""Edge-based template matching – finds fixture symbols on floor plans
by matching the SHAPE (oval border) regardless of the text inside.

Converts templates and pages to Canny edges before matchTemplate so
that an "LT04" exemplar matches all ovals — LT04, LT07, LT09, etc.
Each match is then OCR'd to read the actual fixture code.
"""

from __future__ import annotations

import logging

import cv2
import numpy as np

logger = logging.getLogger(__name__)

# Scales to try when matching (symbols may vary slightly across pages)
_SCALES = [0.8, 0.9, 1.0, 1.1, 1.2]

# Lower threshold for edge matching (edges are sparser than grayscale)
_MATCH_THRESHOLD = 0.40

# IoU threshold for non-maximum suppression
_NMS_IOU_THRESHOLD = 0.3


def _to_edges(img: np.ndarray) -> np.ndarray:
    """Convert a grayscale image to Canny edges.

    Uses Otsu's method to set adaptive thresholds.
    """
    if len(img.shape) == 3:
        img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # Slight blur to reduce noise
    blurred = cv2.GaussianBlur(img, (3, 3), 0)

    # Otsu threshold for adaptive Canny
    otsu_thresh, _ = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    low = max(10, int(otsu_thresh * 0.5))
    high = max(30, int(otsu_thresh))

    edges = cv2.Canny(blurred, low, high)

    # Dilate slightly so thin edges have more overlap during correlation
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
    edges = cv2.dilate(edges, kernel, iterations=1)

    return edges


def _nms(detections: list[dict], iou_threshold: float = _NMS_IOU_THRESHOLD) -> list[dict]:
    """Non-maximum suppression – remove overlapping detections, keep highest score."""
    if not detections:
        return []

    # Sort by score descending
    detections.sort(key=lambda d: d["score"], reverse=True)

    keep: list[dict] = []
    for det in detections:
        overlaps = False
        for kept in keep:
            # Compute IoU
            x1 = max(det["x"], kept["x"])
            y1 = max(det["y"], kept["y"])
            x2 = min(det["x"] + det["w"], kept["x"] + kept["w"])
            y2 = min(det["y"] + det["h"], kept["y"] + kept["h"])

            if x1 < x2 and y1 < y2:
                intersection = (x2 - x1) * (y2 - y1)
                area1 = det["w"] * det["h"]
                area2 = kept["w"] * kept["h"]
                union = area1 + area2 - intersection
                iou = intersection / union if union > 0 else 0.0

                if iou > iou_threshold:
                    overlaps = True
                    break

        if not overlaps:
            keep.append(det)

    return keep


def match_single_template(
    page_edges: np.ndarray,
    template_edges: np.ndarray,
    threshold: float = _MATCH_THRESHOLD,
) -> list[dict]:
    """Match one edge template against a floor plan page at multiple scales.

    Both inputs should already be edge images (from _to_edges).
    Returns list of detections: {x, y, w, h, score, scale}
    """
    page_h, page_w = page_edges.shape[:2]
    tmpl_h, tmpl_w = template_edges.shape[:2]
    raw_detections: list[dict] = []

    for scale in _SCALES:
        new_w = int(tmpl_w * scale)
        new_h = int(tmpl_h * scale)

        if new_w < 8 or new_h < 8:
            continue
        if new_w >= page_w or new_h >= page_h:
            continue

        scaled_tmpl = cv2.resize(template_edges, (new_w, new_h), interpolation=cv2.INTER_AREA)

        result = cv2.matchTemplate(page_edges, scaled_tmpl, cv2.TM_CCOEFF_NORMED)
        locations = np.where(result >= threshold)

        for pt_y, pt_x in zip(*locations):
            raw_detections.append({
                "x": int(pt_x),
                "y": int(pt_y),
                "w": new_w,
                "h": new_h,
                "score": float(result[pt_y, pt_x]),
                "scale": scale,
            })

    return _nms(raw_detections)


def match_templates_on_page(
    image: np.ndarray,
    templates: list[dict],
    threshold: float = _MATCH_THRESHOLD,
) -> list[dict]:
    """Find all fixture symbol shapes on a floor plan page.

    Uses edge-based matching: the oval BORDER is matched, not the text
    inside.  This means an exemplar of "LT04" will find all ovals
    regardless of whether they contain LT04, LT07, LT09, etc.

    Each detection has fixture=None — the caller should OCR each match
    to determine the actual fixture code.

    Args:
        image: the floor plan image (BGR or grayscale)
        templates: list of {code: str, template: np.ndarray} — grayscale crops
        threshold: minimum edge correlation score

    Returns:
        list of detections: {x, y, w, h, score, scale}
        (no 'code' or 'fixture' — OCR determines these)
    """
    # Convert page to edges once (reused for all templates)
    page_edges = _to_edges(image)

    all_detections: list[dict] = []

    for tmpl_info in templates:
        label = tmpl_info["code"]
        template = tmpl_info["template"]

        # Convert template to edges
        tmpl_edges = _to_edges(template)

        detections = match_single_template(page_edges, tmpl_edges, threshold)
        logger.info("    Template %s: %d edge matches", label, len(detections))
        all_detections.extend(detections)

    # NMS across all templates (different orientations of the same symbol
    # will produce overlapping detections — keep the best one)
    all_detections = _nms(all_detections)

    logger.info("  Edge matching total: %d detections after NMS", len(all_detections))
    return all_detections
