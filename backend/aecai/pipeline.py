"""End-to-end takeoff pipeline – converts a PDF into structured fixture counts.

This is the main orchestrator that ties together PDF rendering, oval detection,
OCR, and report generation.  The web API calls this module.
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
from .legend import parse_legend_page
from .ocr import recognize_fixtures
from .report import build_results_json, generate_txt_report
from .shapes import find_ovals

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
    progress_callback: Callable[[int, int, str], None] | None = None,
) -> dict[str, Any]:
    """Run the full takeoff pipeline on a PDF.

    Args:
        pdf_path: path to the uploaded PDF
        pages: specific 1-based page numbers to process (None = all)
        sheet_map: page_number → floor_name mapping
        multipliers: floor_name → multiplier for typical floors
        legend_page: 1-based page number of the symbol legend sheet.
                     If provided, that page is OCR'd first to extract
                     project-specific fixture codes for fuzzy matching.
        progress_callback: called with (current_page, total_pages, floor_name)

    Returns:
        Full results dict from build_results_json, plus "txt_report" key.
    """
    sheet_map = sheet_map or DEFAULT_SHEET_MAP
    multipliers = multipliers if multipliers is not None else DEFAULT_TYPICAL_MULTIPLIERS

    # --- Parse legend page for project-specific fixture codes ---
    known_codes: list[str] | None = None
    if legend_page:
        logger.info("Parsing legend page %d for fixture codes...", legend_page)
        if progress_callback:
            progress_callback(0, 0, "Reading symbol legend...")
        legend_images = pdf_to_images(pdf_path, pages=[legend_page])
        if legend_images:
            known_codes = parse_legend_page(legend_images[0])
            logger.info("  Extracted %d fixture codes from legend: %s", len(known_codes), known_codes)
        if not known_codes:
            logger.warning("  No codes found on legend page, falling back to defaults")
            known_codes = None

    # Fall back to built-in list if no legend provided or parsing found nothing
    if known_codes is None:
        known_codes = KNOWN_LUMINAIRES

    logger.info("Rendering PDF to images at %d DPI...", DPI)
    images = pdf_to_images(pdf_path, pages=pages)

    # Build page number list
    if pages:
        page_numbers = sorted(pages)
    else:
        page_numbers = list(range(1, len(images) + 1))

    # Ensure we have the right count
    if len(images) != len(page_numbers):
        # When specifying a range, pdf2image returns all pages in range
        page_numbers = list(range(min(page_numbers), min(page_numbers) + len(images)))

    page_results: dict[str, list[dict]] = {}
    total_pages = len(images)

    for idx, (page_num, image) in enumerate(zip(page_numbers, images)):
        floor_name = sheet_map.get(page_num, f"Page {page_num}")

        # Skip non-plan pages (Cover, Legend, Site Plan, etc.)
        if floor_name in ("Cover", "Legend", "Site Plan"):
            logger.info("Skipping %s (page %d)", floor_name, page_num)
            if progress_callback:
                progress_callback(idx + 1, total_pages, f"Skipped {floor_name}")
            continue

        logger.info("Processing %s (page %d/%d)...", floor_name, idx + 1, total_pages)
        if progress_callback:
            progress_callback(idx + 1, total_pages, f"Processing {floor_name}")

        # Detect ovals
        ovals = find_ovals(image)
        logger.info("  Found %d ovals on %s", len(ovals), floor_name)

        # OCR each oval using project-specific codes
        detections = recognize_fixtures(image, ovals, known=known_codes)
        recognised = [d for d in detections if d["fixture"] is not None]
        logger.info("  Recognised %d/%d fixtures", len(recognised), len(ovals))

        page_results[floor_name] = detections

    # Aggregate counts
    floor_counts: dict[str, Counter] = {}
    for floor_name, detections in page_results.items():
        counter: Counter = Counter()
        for det in detections:
            if det["fixture"]:
                counter[det["fixture"]] += 1
        if counter:
            floor_counts[floor_name] = counter

    # Build output
    results = build_results_json(floor_counts, multipliers)
    results["txt_report"] = generate_txt_report(floor_counts, multipliers)
    if known_codes and known_codes is not KNOWN_LUMINAIRES:
        results["legend_codes"] = known_codes

    if progress_callback:
        progress_callback(total_pages, total_pages, "Complete")

    return results
