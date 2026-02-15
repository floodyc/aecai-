"""End-to-end takeoff pipeline – converts a PDF into structured fixture counts.

This is the main orchestrator that ties together PDF rendering, symbol detection,
OCR, and report generation.  The web API calls this module.

Detection strategies (tried in order):
1. Template matching – if a legend image is provided, extract symbol templates
   from the legend and use OpenCV matchTemplate to find them on floor plans.
2. Oval detection – calibrated contour detector for oval-symbol drawings.
3. Text search – full-page OCR filtered by legend codes.
"""

from __future__ import annotations

import logging
from collections import Counter
from pathlib import Path
from typing import Any, Callable

import cv2
import numpy as np
from pdf2image import convert_from_path

from .config import DEFAULT_SHEET_MAP, DEFAULT_TYPICAL_MULTIPLIERS, DPI, KNOWN_LUMINAIRES, POPPLER_PATH
from .legend import extract_symbol_templates, parse_legend_page
from .ocr import recognize_fixtures, scan_page_for_codes
from .report import build_results_json, generate_txt_report
from .shapes import find_ovals
from .symbol_match import match_templates_on_page

logger = logging.getLogger(__name__)


def pdf_to_images(
    pdf_path: str | Path,
    dpi: int = DPI,
    pages: list[int] | None = None,
) -> list[np.ndarray]:
    """Convert PDF pages to OpenCV images.

    Args:
        pdf_path: path to the PDF file
        dpi: rendering resolution (300 recommended for fixture detection)
        pages: 1-based page numbers to process, or None for all

    Returns:
        list of BGR numpy arrays, one per page
    """
    kwargs: dict[str, Any] = {"dpi": dpi}
    if POPPLER_PATH:
        kwargs["poppler_path"] = POPPLER_PATH
    if pages:
        # pdf2image uses 1-based page numbering
        kwargs["first_page"] = min(pages)
        kwargs["last_page"] = max(pages)

    pil_images = convert_from_path(str(pdf_path), **kwargs)

    cv_images = []
    for pil_img in pil_images:
        arr = np.array(pil_img)
        bgr = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
        cv_images.append(bgr)

    return cv_images


def run_takeoff(
    pdf_path: str | Path,
    pages: list[int] | None = None,
    sheet_map: dict[int, str] | None = None,
    multipliers: dict[str, int] | None = None,
    legend_page: int | None = None,
    legend_image_path: str | Path | None = None,
    progress_callback: Callable[[int, int, str], None] | None = None,
) -> dict[str, Any]:
    """Run the full takeoff pipeline on a PDF.

    Args:
        pdf_path: path to the uploaded PDF
        pages: specific 1-based page numbers to process (None = all)
        sheet_map: page_number → floor_name mapping
        multipliers: floor_name → multiplier for typical floors
        legend_page: 1-based page number of the symbol legend sheet.
        legend_image_path: path to a user-uploaded image (PNG/JPG) of the
                          lighting fixture legend table. Takes priority over
                          legend_page when both are provided.
        progress_callback: called with (current_page, total_pages, floor_name)

    Returns:
        Full results dict from build_results_json, plus "txt_report" key.
    """
    sheet_map = sheet_map or DEFAULT_SHEET_MAP
    multipliers = multipliers if multipliers is not None else DEFAULT_TYPICAL_MULTIPLIERS

    # Diagnostics: collect debug info about each pipeline stage
    diagnostics: dict[str, Any] = {
        "legend_page": legend_page,
        "legend_image": bool(legend_image_path),
        "legend_codes": [],
        "used_default_codes": False,
        "pages": {},
    }

    # --- Parse legend: extract symbol templates AND fixture codes ---
    symbol_templates: list[dict] = []
    known_codes: list[str] | None = None

    # Priority 1: user-uploaded legend image
    if legend_image_path:
        logger.info("Parsing uploaded legend image...")
        if progress_callback:
            progress_callback(0, 0, "Learning symbols from legend...")
        legend_img = cv2.imread(str(legend_image_path))
        if legend_img is not None:
            # Extract graphical templates + codes
            symbol_templates = extract_symbol_templates(legend_img)
            if symbol_templates:
                known_codes = [t["code"] for t in symbol_templates]
                diagnostics["legend_codes"] = known_codes
                diagnostics["legend_source"] = "uploaded_image"
                diagnostics["templates_extracted"] = len(symbol_templates)
                logger.info("  Extracted %d symbol templates: %s",
                            len(symbol_templates), known_codes)
            else:
                # Template extraction failed — fall back to code extraction
                logger.warning("  No symbol templates found, trying code-only extraction...")
                known_codes = parse_legend_page(legend_img)
                if known_codes:
                    diagnostics["legend_codes"] = known_codes
                    diagnostics["legend_source"] = "uploaded_image"
                    logger.info("  Extracted %d codes (no templates): %s",
                                len(known_codes), known_codes)

        if not known_codes:
            logger.warning("  Legend image produced no codes, trying legend page...")

    # Priority 2: legend page from the PDF
    if not known_codes and legend_page:
        logger.info("Parsing legend page %d...", legend_page)
        if progress_callback:
            progress_callback(0, 0, "Reading symbol legend...")
        legend_images = pdf_to_images(pdf_path, pages=[legend_page])
        if legend_images:
            # Try template extraction from PDF legend page too
            if not symbol_templates:
                symbol_templates = extract_symbol_templates(legend_images[0])
                if symbol_templates:
                    known_codes = [t["code"] for t in symbol_templates]
                    diagnostics["legend_codes"] = known_codes
                    diagnostics["legend_source"] = "pdf_page"
                    diagnostics["templates_extracted"] = len(symbol_templates)

            if not known_codes:
                known_codes = parse_legend_page(legend_images[0])
                diagnostics["legend_codes"] = known_codes or []
                diagnostics["legend_source"] = "pdf_page"

        if not known_codes:
            logger.warning("  No codes found on legend page, falling back to defaults")

    # Fall back to built-in list if nothing worked
    if not known_codes:
        known_codes = KNOWN_LUMINAIRES
        diagnostics["used_default_codes"] = True
        diagnostics["legend_source"] = "defaults"

    diagnostics["active_codes"] = known_codes

    logger.info("Rendering PDF to images at %d DPI...", DPI)
    images = pdf_to_images(pdf_path, pages=pages)

    # Build page number list
    if pages:
        page_numbers = sorted(pages)
    else:
        page_numbers = list(range(1, len(images) + 1))

    # Ensure we have the right count
    if len(images) != len(page_numbers):
        page_numbers = list(range(min(page_numbers), min(page_numbers) + len(images)))

    page_results: dict[str, list[dict]] = {}
    total_pages = len(images)

    for idx, (page_num, image) in enumerate(zip(page_numbers, images)):
        floor_name = sheet_map.get(page_num, f"Page {page_num}")

        # Skip non-plan pages ONLY when processing all pages (no explicit selection).
        # If the user explicitly selected pages, process everything they chose.
        if not pages and floor_name in ("Cover", "Legend", "Site Plan"):
            logger.info("Skipping %s (page %d)", floor_name, page_num)
            diagnostics["pages"][floor_name] = {"status": "skipped"}
            if progress_callback:
                progress_callback(idx + 1, total_pages, f"Skipped {floor_name}")
            continue

        logger.info("Processing %s (page %d/%d)...", floor_name, idx + 1, total_pages)
        if progress_callback:
            progress_callback(idx + 1, total_pages, f"Processing {floor_name}")

        # --- Strategy 1: Template matching (when we have templates from legend) ---
        if symbol_templates:
            detection_method = "template_match"
            logger.info("  Using template matching (%d templates) on %s",
                        len(symbol_templates), floor_name)
            detections = match_templates_on_page(image, symbol_templates)

            raw_samples = [f"{d['code']}@({d['x']},{d['y']}) s={d['score']:.2f}"
                           for d in detections][:15]
            diagnostics["pages"][floor_name] = {
                "status": "processed",
                "detection_method": detection_method,
                "template_matches": len(detections),
                "raw_ocr_samples": raw_samples,
            }
            page_results[floor_name] = detections
            continue

        # --- Strategy 2: Oval detection (calibrated for oval-symbol drawings) ---
        ovals = find_ovals(image)
        if ovals:
            detection_method = "ovals"
            logger.info("  Found %d ovals on %s", len(ovals), floor_name)
            detections = recognize_fixtures(image, ovals, known=known_codes)
            recognised = [d for d in detections if d["fixture"] is not None]
            logger.info("  Recognised %d/%d fixtures", len(recognised), len(ovals))

            raw_samples = [d["raw_text"] for d in detections if d["raw_text"]][:15]
            diagnostics["pages"][floor_name] = {
                "status": "processed",
                "detection_method": detection_method,
                "shapes_found": len(ovals),
                "shapes_matched": len(recognised),
                "raw_ocr_samples": raw_samples,
            }
            page_results[floor_name] = detections
            continue

        # --- Strategy 3: Full-page text search ---
        detection_method = "text_search"
        logger.info("  No ovals found on %s, using full-page text search", floor_name)
        detections = scan_page_for_codes(image, known_codes)

        raw_samples = [d["raw_text"] for d in detections][:15]
        diagnostics["pages"][floor_name] = {
            "status": "processed",
            "detection_method": detection_method,
            "text_matches": len(detections),
            "raw_ocr_samples": raw_samples,
        }
        page_results[floor_name] = detections

    # Aggregate counts
    floor_counts: dict[str, Counter] = {}
    for floor_name, detections in page_results.items():
        counter: Counter = Counter()
        for det in detections:
            code = det.get("fixture") or det.get("code")
            if code:
                counter[code] += 1
        if counter:
            floor_counts[floor_name] = counter

    # Build output
    results = build_results_json(floor_counts, multipliers)
    results["txt_report"] = generate_txt_report(floor_counts, multipliers)
    results["diagnostics"] = diagnostics
    if known_codes and known_codes is not KNOWN_LUMINAIRES:
        results["legend_codes"] = known_codes

    if progress_callback:
        progress_callback(total_pages, total_pages, "Complete")

    return results
