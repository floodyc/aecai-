"""End-to-end takeoff pipeline – converts a PDF into structured fixture counts.

This is the main orchestrator that ties together PDF rendering, oval detection,
OCR, and report generation.  The web API calls this module.

Detection approach:
1. Find ovals on each floor plan page
2. OCR text inside each oval — every oval with alphanumeric text is captured
3. Optionally filter by a user-supplied prefix
4. Aggregate counts per floor
"""

from __future__ import annotations

import gc
import logging
from collections import Counter
from pathlib import Path
from typing import Any, Callable

import cv2
import numpy as np
from pdf2image import convert_from_path

from .config import DPI, POPPLER_PATH
from .ocr import (
    _clean_and_normalize,
    _has_text_content,
    _is_false_positive,
    _ocr_with_retries,
    crop_oval,
    ocr_crop,
    recognize_fixtures,
)
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


def _render_single_page(
    pdf_path: str | Path,
    page_num: int,
    dpi: int = DPI,
) -> np.ndarray | None:
    """Render a single PDF page to a BGR OpenCV image.

    Memory-optimised: frees the PIL image and intermediate RGB array
    before returning, so peak usage is ~2× the final image size instead
    of 3× (which matters for 113-million-pixel architectural drawings).

    Returns None if the page cannot be rendered.
    """
    import PIL.Image
    # Large architectural drawings at 300 DPI easily exceed PIL's default
    # decompression bomb limit (89 megapixels).  These are legitimate
    # engineering documents, not attacks.
    PIL.Image.MAX_IMAGE_PIXELS = 250_000_000

    kwargs: dict[str, Any] = {
        "dpi": dpi,
        "first_page": page_num,
        "last_page": page_num,
    }
    if POPPLER_PATH:
        kwargs["poppler_path"] = POPPLER_PATH

    try:
        pil_images = convert_from_path(str(pdf_path), **kwargs)
    except Exception as e:
        logger.warning("Failed to render page %d: %s", page_num, e)
        return None

    if not pil_images:
        return None

    # Convert PIL→numpy→BGR with minimal concurrent copies.
    # A 113M-pixel page is ~340 MB per copy, so keeping 3 copies
    # simultaneously (PIL + RGB + BGR) = 1020 MB — too much.
    arr = np.array(pil_images[0])
    del pil_images                    # free PIL image (~340 MB)
    bgr = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
    del arr                           # free RGB array (~340 MB)
    # Now only bgr (~340 MB) is alive
    return bgr


def _get_page_count(pdf_path: str | Path) -> int:
    """Get total page count without rendering."""
    from pdf2image import pdfinfo_from_path
    kwargs: dict[str, Any] = {}
    if POPPLER_PATH:
        kwargs["poppler_path"] = POPPLER_PATH
    info = pdfinfo_from_path(str(pdf_path), **kwargs)
    return info.get("Pages", 0)


def _extract_exemplar_templates(
    pdf_path: str | Path,
    exemplars: list[dict],
    target_dpi: int = DPI,
) -> list[dict]:
    """Render exemplar source pages and crop templates at target DPI.

    Each exemplar dict has: {label, page, x, y, w, h, source_dpi}.
    Coordinates are in source_dpi image-pixel space.  We render at
    target_dpi and scale the crop coordinates accordingly.

    Returns list of {code: str, template: np.ndarray} for symbol_match.
    """
    # Group exemplars by source page to avoid re-rendering
    from collections import defaultdict
    by_page: dict[int, list[dict]] = defaultdict(list)
    for ex in exemplars:
        by_page[ex["page"]].append(ex)

    templates: list[dict] = []
    for page_num, page_exemplars in by_page.items():
        # Render just this page at target DPI
        img = _render_single_page(pdf_path, page_num, dpi=target_dpi)
        if img is None:
            logger.warning("Could not render page %d for exemplar extraction", page_num)
            continue

        for ex in page_exemplars:
            source_dpi = ex.get("source_dpi", 150)
            scale = target_dpi / source_dpi

            x = int(ex["x"] * scale)
            y = int(ex["y"] * scale)
            w = int(ex["w"] * scale)
            h = int(ex["h"] * scale)

            # Clamp to image bounds
            h_img, w_img = img.shape[:2]
            x = max(0, min(x, w_img - 1))
            y = max(0, min(y, h_img - 1))
            w = min(w, w_img - x)
            h = min(h, h_img - y)

            if w < 5 or h < 5:
                logger.warning("Exemplar crop too small: %s (%dx%d)", ex["label"], w, h)
                continue

            crop = img[y:y + h, x:x + w]

            # Convert to grayscale for template matching
            if len(crop.shape) == 3:
                crop = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)

            templates.append({"code": ex["label"], "template": crop.copy()})
            logger.info("Extracted exemplar template: %s (%dx%d from page %d)",
                        ex["label"], w, h, page_num)

        # Free the full-page image before processing the next page
        del img
        gc.collect()

    return templates


def run_takeoff(
    pdf_path: str | Path,
    pages: list[int] | None = None,
    sheet_map: dict[int, str] | None = None,
    multipliers: dict[str, int] | None = None,
    legend_page: int | None = None,
    legend_image_path: str | Path | None = None,
    fixture_prefix: str | None = None,
    exemplars: list[dict] | None = None,
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
                          lighting fixture legend table.
        exemplars: user-drawn bounding boxes for visual template matching.
                   List of {label, page, x, y, w, h, source_dpi}.
        progress_callback: called with (current_page, total_pages, floor_name)

    Returns:
        Full results dict from build_results_json, plus "txt_report" key.
    """
    # Only use default sheet map if explicitly provided; otherwise use generic
    # page names so we never accidentally skip floor plan pages on other PDFs.
    user_provided_map = sheet_map is not None
    sheet_map = sheet_map or {}
    multipliers = multipliers if multipliers is not None else {}

    # Diagnostics: collect debug info about each pipeline stage
    diagnostics: dict[str, Any] = {
        "legend_page": legend_page,
        "legend_image": bool(legend_image_path),
        "legend_codes": [],
        "used_default_codes": False,
        "fixture_prefix": fixture_prefix,
        "pages": {},
    }

    # Extract exemplar templates (user-drawn bounding boxes).
    # Templates are cropped at their source DPI (default 150) — NO upscaling
    # to 300 DPI.  Processing pages are also rendered at the template DPI,
    # so template matching runs at 150 DPI.  This uses 25% of the memory
    # compared to 300 DPI (85 MB vs 340 MB per 113-megapixel page).
    templates: list[dict] = []
    template_dpi: int = 150  # source DPI from the exemplar drawing canvas
    if exemplars:
        logger.info("Extracting %d exemplar templates...", len(exemplars))
        # Extract at source DPI — no scaling needed
        template_dpi = exemplars[0].get("source_dpi", 150)
        templates = _extract_exemplar_templates(pdf_path, exemplars, target_dpi=template_dpi)
        logger.info("Extracted %d templates at %d DPI", len(templates), template_dpi)
        diagnostics["exemplars_provided"] = len(exemplars)
        diagnostics["templates_extracted"] = len(templates)

    use_template_matching = len(templates) > 0

    # Extract the letter prefix from exemplar labels (e.g. "LT" from "LT04").
    # Used to validate OCR results on template-matched shapes.
    tmpl_prefix = ""
    if templates:
        import re as _re
        _m = _re.match(r"^[A-Z]+", templates[0]["code"].upper())
        tmpl_prefix = _m.group() if _m else ""

    if use_template_matching:
        logger.info("Using template matching (%d templates, OCR prefix=%r)",
                    len(templates), tmpl_prefix)
        diagnostics["legend_source"] = "exemplars"
        diagnostics["active_codes"] = list({t["code"] for t in templates})
    elif fixture_prefix:
        logger.info("Using oval detection with prefix filter: '%s'", fixture_prefix)
        diagnostics["legend_source"] = "prefix"
        diagnostics["active_codes"] = [f"{fixture_prefix}*"]
    else:
        logger.info("Using oval detection — capturing all ovals with text")
        diagnostics["legend_source"] = "all_ovals"
        diagnostics["active_codes"] = []
    # Build page number list — render one page at a time to stay under
    # the 2 GB memory limit on Render (15 pages × 25 MB/page = 375 MB
    # all at once, plus OpenCV intermediates easily exceeds the cap).
    if pages:
        page_numbers = sorted(pages)
    else:
        total_count = _get_page_count(pdf_path)
        page_numbers = list(range(1, total_count + 1))

    page_results: dict[str, list[dict]] = {}
    total_pages = len(page_numbers)

    for idx, page_num in enumerate(page_numbers):
        floor_name = sheet_map.get(page_num, f"Page {page_num}")

        # Skip non-plan pages ONLY when the user explicitly provided a sheet map
        # that labels them as Cover/Legend/Site Plan.  Never skip with generic names.
        if not pages and user_provided_map and floor_name in ("Cover", "Legend", "Site Plan"):
            logger.info("Skipping %s (page %d)", floor_name, page_num)
            diagnostics["pages"][floor_name] = {"status": "skipped"}
            if progress_callback:
                progress_callback(idx + 1, total_pages, f"Skipped {floor_name}")
            continue

        logger.info("Processing %s (page %d/%d)...", floor_name, idx + 1, total_pages)
        if progress_callback:
            progress_callback(idx + 1, total_pages, f"Processing {floor_name}")

        # Render at 150 DPI for template matching (25% memory), 300 DPI for ovals
        render_dpi = template_dpi if use_template_matching else DPI
        image = _render_single_page(pdf_path, page_num, dpi=render_dpi)
        if image is None:
            logger.warning("Skipping %s — failed to render", floor_name)
            diagnostics["pages"][floor_name] = {"status": "render_failed"}
            continue

        if use_template_matching:
            # ---- Template matching (user-provided exemplars) ----
            # Two-pass approach:
            #   Pass 1: edge matching at 150 DPI (low memory, shape detection)
            #   Pass 2: re-render at 300 DPI for OCR (text needs resolution)

            # Pass 1 — shape matching at 150 DPI
            tmpl_detections = match_templates_on_page(image, templates)
            logger.info("  Template matching: %d shape detections on %s",
                        len(tmpl_detections), floor_name)

            # Free the 150 DPI image before rendering at 300 DPI
            del image
            gc.collect()

            # Pass 2 — re-render at 300 DPI for OCR
            image_hires = _render_single_page(pdf_path, page_num, dpi=DPI)
            if image_hires is None:
                logger.warning("  Could not re-render %s at %d DPI for OCR",
                               floor_name, DPI)
                diagnostics["pages"][floor_name] = {
                    "status": "processed",
                    "detection_method": "template",
                    "template_matches": len(tmpl_detections),
                    "ocr_recognised": 0,
                }
                page_results[floor_name] = []
                continue

            # Scale detection coordinates from 150 DPI → 300 DPI
            dpi_scale = DPI / template_dpi

            # OCR each matched region at 300 DPI
            detections = []
            for td in tmpl_detections:
                oval = {
                    "x": int(td["x"] * dpi_scale),
                    "y": int(td["y"] * dpi_scale),
                    "w": int(td["w"] * dpi_scale),
                    "h": int(td["h"] * dpi_scale),
                }

                if tmpl_prefix:
                    raw, fixture = _ocr_with_retries(image_hires, oval, tmpl_prefix)
                else:
                    crop = crop_oval(image_hires, oval)
                    if crop.size == 0:
                        detections.append({
                            "oval": oval, "raw_text": "", "fixture": None,
                            "score": td["score"], "detection_method": "template",
                        })
                        continue
                    if not _has_text_content(crop):
                        detections.append({
                            "oval": oval, "raw_text": "", "fixture": None,
                            "score": td["score"], "detection_method": "template",
                        })
                        continue
                    raw = ocr_crop(crop)
                    fixture = _clean_and_normalize(raw) if not _is_false_positive(raw) else None

                detections.append({
                    "oval": oval, "raw_text": raw, "fixture": fixture,
                    "score": td["score"], "detection_method": "template",
                })

            # Free the 300 DPI image
            del image_hires
            gc.collect()

            recognised = [d for d in detections if d["fixture"] is not None]
            logger.info("  OCR recognised %d/%d template matches at %d DPI",
                        len(recognised), len(tmpl_detections), DPI)

            raw_samples = [d["raw_text"] for d in detections if d["raw_text"]][:15]

            diagnostics["pages"][floor_name] = {
                "status": "processed",
                "detection_method": "template",
                "template_matches": len(tmpl_detections),
                "ocr_recognised": len(recognised),
                "raw_ocr_samples": raw_samples,
            }

            page_results[floor_name] = detections

            # Already freed both images above; skip the del at end of loop
            continue
        else:
            # ---- Oval detection + OCR (default pipeline) ----
            ovals = find_ovals(image)
            logger.info("  Found %d ovals on %s", len(ovals), floor_name)

            detections = recognize_fixtures(image, ovals, prefix=fixture_prefix)
            recognised = [d for d in detections if d["fixture"] is not None]
            logger.info("  Recognised %d/%d fixtures", len(recognised), len(ovals))

            raw_samples = [d["raw_text"] for d in detections if d["raw_text"]][:15]

            diagnostics["pages"][floor_name] = {
                "status": "processed",
                "detection_method": "ovals",
                "shapes_found": len(ovals),
                "shapes_matched": len(recognised),
                "raw_ocr_samples": raw_samples,
            }

        page_results[floor_name] = detections

        # Free the page image and force garbage collection.  A single
        # 113-megapixel page at 300 DPI is ~340 MB; OpenCV intermediates
        # add another 200-300 MB.  Without explicit gc.collect() Python
        # may not reclaim these before the next page renders.
        del image
        gc.collect()

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
    results["diagnostics"] = diagnostics

    if progress_callback:
        progress_callback(total_pages, total_pages, "Complete")

    return results
