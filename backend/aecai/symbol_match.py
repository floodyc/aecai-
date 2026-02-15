"""Template-based symbol matching – finds fixture symbols on floor plans
by matching templates extracted from the legend.

Uses OpenCV matchTemplate with multi-scale search and non-maximum
suppression to avoid duplicate detections.
"""

from __future__ import annotations

import logging

import cv2
import numpy as np

logger = logging.getLogger(__name__)

# Scales to try when matching (legend symbols may differ slightly from plan)
_SCALES = [0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.4]

# Minimum match score (TM_CCOEFF_NORMED ranges from -1 to 1)
_MATCH_THRESHOLD = 0.65

# IoU threshold for non-maximum suppression
_NMS_IOU_THRESHOLD = 0.3


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
    page_gray: np.ndarray,
    template: np.ndarray,
    code: str,
    threshold: float = _MATCH_THRESHOLD,
) -> list[dict]:
    """Match one symbol template against a floor plan page at multiple scales.

    Returns list of detections: {code, x, y, w, h, score, scale}
    """
    page_h, page_w = page_gray.shape[:2]
    tmpl_h, tmpl_w = template.shape[:2]
    raw_detections: list[dict] = []

    for scale in _SCALES:
        new_w = int(tmpl_w * scale)
        new_h = int(tmpl_h * scale)

        if new_w < 8 or new_h < 8:
            continue
        if new_w >= page_w or new_h >= page_h:
            continue

        scaled_tmpl = cv2.resize(template, (new_w, new_h), interpolation=cv2.INTER_AREA)

        result = cv2.matchTemplate(page_gray, scaled_tmpl, cv2.TM_CCOEFF_NORMED)
        locations = np.where(result >= threshold)

        for pt_y, pt_x in zip(*locations):
            raw_detections.append({
                "code": code,
                "fixture": code,
                "x": int(pt_x),
                "y": int(pt_y),
                "w": new_w,
                "h": new_h,
                "score": float(result[pt_y, pt_x]),
                "scale": scale,
            })

    # NMS within this template's detections
    return _nms(raw_detections)


def match_templates_on_page(
    image: np.ndarray,
    templates: list[dict],
    threshold: float = _MATCH_THRESHOLD,
) -> list[dict]:
    """Find all fixture symbol matches on a floor plan page.

    Args:
        image: the floor plan image (BGR or grayscale)
        templates: list of {code: str, template: np.ndarray} from legend extraction
        threshold: minimum matchTemplate score

    Returns:
        list of detections: {code, fixture, x, y, w, h, score, scale}
    """
    if len(image.shape) == 3:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    else:
        gray = image

    all_detections: list[dict] = []

    for tmpl_info in templates:
        code = tmpl_info["code"]
        template = tmpl_info["template"]

        detections = match_single_template(gray, template, code, threshold)
        logger.info("    Template %s: %d matches", code, len(detections))
        all_detections.extend(detections)

    # Final NMS across all templates (in case different symbols overlap)
    all_detections = _nms(all_detections)

    logger.info("  Template matching total: %d detections after NMS", len(all_detections))
    return all_detections
