"""FastAPI route definitions for the AECAI takeoff API."""

from __future__ import annotations

import base64
import io
import json
import tempfile
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import PlainTextResponse
from pdf2image import convert_from_path
from pydantic import BaseModel

from aecai.config import POPPLER_PATH
from .jobs import JobStatus, create_job, get_job

router = APIRouter(prefix="/api")

# ---------------------------------------------------------------------------
# Temp file store for previewed PDFs (maps preview_id → path)
# ---------------------------------------------------------------------------
_preview_files: dict[str, str] = {}


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class TakeoffRequest(BaseModel):
    pages: list[int] | None = None
    sheet_map: dict[int, str] | None = None
    multipliers: dict[str, int] | None = None


class JobResponse(BaseModel):
    id: str
    status: str
    created_at: str
    current_page: int
    total_pages: int
    current_floor: str
    results: dict[str, Any] | None = None
    error: str | None = None


class PagePreview(BaseModel):
    page_number: int
    thumbnail: str  # base64 JPEG
    is_legend: bool


class PreviewResponse(BaseModel):
    preview_id: str
    total_pages: int
    pages: list[PagePreview]


class HealthResponse(BaseModel):
    status: str
    service: str


# ---------------------------------------------------------------------------
# Helpers – legend detection
# ---------------------------------------------------------------------------

def _detect_legend_page(pil_images: list) -> int | None:
    """Try to identify which page is the symbol legend.

    Checks for the word 'LEGEND' or 'SYMBOL' in large text regions.
    Returns 1-based page number or None.
    """
    import pytesseract
    from aecai.config import TESSERACT_CMD
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD

    for idx, pil_img in enumerate(pil_images):
        # Use a low-res version for speed
        small = pil_img.resize((800, int(800 * pil_img.height / pil_img.width)))
        try:
            text = pytesseract.image_to_string(small, config="--psm 3")
            upper = text.upper()
            if "LEGEND" in upper or "SYMBOL SCHEDULE" in upper or "LUMINAIRE SCHEDULE" in upper:
                return idx + 1  # 1-based
        except Exception:
            continue
    return None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/health", response_model=HealthResponse)
async def health_check():
    return HealthResponse(status="ok", service="aecai-api")


@router.post("/takeoff/preview", response_model=PreviewResponse)
async def preview_pdf(file: UploadFile):
    """Upload a PDF and get page thumbnails + legend detection.

    Returns low-res thumbnails and identifies which page is the legend.
    The PDF is kept on disk so the user can start processing later
    using the returned preview_id.
    """
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="File must be a PDF")

    suffix = Path(file.filename).suffix
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix, prefix="aecai_prev_") as tmp:
        content = await file.read()
        if len(content) == 0:
            raise HTTPException(status_code=400, detail="Empty file")
        tmp.write(content)
        tmp_path = tmp.name

    # Render at low DPI for thumbnails
    kwargs: dict[str, Any] = {"dpi": 72}
    if POPPLER_PATH:
        kwargs["poppler_path"] = POPPLER_PATH

    try:
        pil_images = convert_from_path(tmp_path, **kwargs)
    except Exception as e:
        Path(tmp_path).unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=f"Failed to read PDF: {e}")

    # Detect legend page
    legend_page = _detect_legend_page(pil_images)

    # Build thumbnails
    import uuid
    preview_id = uuid.uuid4().hex[:12]
    _preview_files[preview_id] = tmp_path

    pages: list[PagePreview] = []
    for idx, pil_img in enumerate(pil_images):
        # Resize to max 400px wide
        max_w = 400
        ratio = max_w / pil_img.width
        thumb = pil_img.resize((max_w, int(pil_img.height * ratio)))

        buf = io.BytesIO()
        thumb.save(buf, format="JPEG", quality=60)
        b64 = base64.b64encode(buf.getvalue()).decode("ascii")

        pages.append(PagePreview(
            page_number=idx + 1,
            thumbnail=b64,
            is_legend=(idx + 1 == legend_page),
        ))

    return PreviewResponse(
        preview_id=preview_id,
        total_pages=len(pil_images),
        pages=pages,
    )


@router.post("/takeoff", response_model=JobResponse)
async def start_takeoff(request: Request):
    """Start a takeoff job.

    Either upload a new PDF (file) or reference a previously previewed one
    (preview_id). Optionally upload a legend_image (PNG/JPG snapshot of the
    lighting fixture legend table). Poll GET /api/takeoff/{job_id} for status.

    Uses manual form parsing to reliably handle optional file uploads.
    """
    import logging
    _log = logging.getLogger(__name__)

    form = await request.form()

    # Extract form fields
    preview_id = form.get("preview_id")
    pages = form.get("pages")
    sheet_map = form.get("sheet_map")
    multipliers = form.get("multipliers")
    legend_page = form.get("legend_page")
    file = form.get("file")
    legend_image = form.get("legend_image")
    fixture_prefix = form.get("fixture_prefix")

    _log.info("Takeoff request: preview_id=%s, fixture_prefix=%s, legend_image=%s (type=%s)",
              preview_id, fixture_prefix, legend_image, type(legend_image).__name__)

    tmp_path: str | None = None

    if preview_id and str(preview_id) in _preview_files:
        tmp_path = _preview_files.pop(str(preview_id))
    elif file and hasattr(file, "read"):
        filename = getattr(file, "filename", "") or ""
        if not filename.lower().endswith(".pdf"):
            raise HTTPException(status_code=400, detail="File must be a PDF")
        suffix = Path(filename).suffix
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix, prefix="aecai_") as tmp:
            content = await file.read()
            if len(content) == 0:
                raise HTTPException(status_code=400, detail="Empty file")
            tmp.write(content)
            tmp_path = tmp.name
    else:
        raise HTTPException(status_code=400, detail="Provide either a file or preview_id")

    # Save legend image — supports both file upload and base64 text field
    legend_image_path: str | None = None

    # Method 1: base64-encoded image (most reliable across all environments)
    legend_image_b64 = form.get("legend_image_b64")
    if legend_image_b64:
        b64_str = str(legend_image_b64)
        # Strip data URL prefix (e.g. "data:image/png;base64,...")
        if "," in b64_str:
            b64_str = b64_str.split(",", 1)[1]
        img_data = base64.b64decode(b64_str)
        _log.info("Legend image received via base64: %d bytes", len(img_data))
        if len(img_data) > 0:
            with tempfile.NamedTemporaryFile(
                delete=False, suffix=".png", prefix="aecai_legend_"
            ) as tmp:
                tmp.write(img_data)
                legend_image_path = tmp.name
            _log.info("Saved legend image to %s", legend_image_path)

    # Method 2: multipart file upload (fallback)
    if not legend_image_path and legend_image and hasattr(legend_image, "read"):
        img_content = await legend_image.read()
        _log.info("Legend image received via file upload: %d bytes", len(img_content))
        if img_content and len(img_content) > 0:
            with tempfile.NamedTemporaryFile(
                delete=False, suffix=".png", prefix="aecai_legend_"
            ) as tmp:
                tmp.write(img_content)
                legend_image_path = tmp.name
            _log.info("Saved legend image to %s", legend_image_path)

    if not legend_image_path:
        _log.info("No legend image received")

    # Parse optional JSON parameters from form fields (cast to str first)
    pages_str = str(pages) if pages else None
    sheet_map_str = str(sheet_map) if sheet_map else None
    multipliers_str = str(multipliers) if multipliers else None
    legend_page_str = str(legend_page) if legend_page else None

    parsed_pages = None
    parsed_sheet_map = None
    parsed_multipliers = None

    if pages_str:
        try:
            parsed_pages = json.loads(pages_str)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Invalid pages JSON")

    if sheet_map_str:
        try:
            raw = json.loads(sheet_map_str)
            parsed_sheet_map = {int(k): v for k, v in raw.items()}
        except (json.JSONDecodeError, ValueError):
            raise HTTPException(status_code=400, detail="Invalid sheet_map JSON")

    if multipliers_str:
        try:
            raw = json.loads(multipliers_str)
            parsed_multipliers = {str(k): int(v) for k, v in raw.items()}
        except (json.JSONDecodeError, ValueError):
            raise HTTPException(status_code=400, detail="Invalid multipliers JSON")

    parsed_legend_page = None
    if legend_page_str:
        try:
            parsed_legend_page = int(legend_page_str)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid legend_page value")

    parsed_fixture_prefix = str(fixture_prefix).strip().upper() if fixture_prefix else None
    if parsed_fixture_prefix == "":
        parsed_fixture_prefix = None

    job = create_job(
        pdf_path=tmp_path,
        pages=parsed_pages,
        sheet_map=parsed_sheet_map,
        multipliers=parsed_multipliers,
        legend_page=parsed_legend_page,
        legend_image_path=legend_image_path,
        fixture_prefix=parsed_fixture_prefix,
    )

    return _job_to_response(job)


@router.get("/takeoff/{job_id}", response_model=JobResponse)
async def get_takeoff_status(job_id: str):
    """Poll the status of a takeoff job."""
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return _job_to_response(job)


@router.get("/takeoff/{job_id}/report")
async def download_report(job_id: str):
    """Download the TXT report for a completed job."""
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != JobStatus.COMPLETED:
        raise HTTPException(status_code=400, detail="Job not yet completed")
    if not job.results or "txt_report" not in job.results:
        raise HTTPException(status_code=500, detail="Report not available")

    return PlainTextResponse(
        content=job.results["txt_report"],
        media_type="text/plain",
        headers={"Content-Disposition": f"attachment; filename=aecai_report_{job_id}.txt"},
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _job_to_response(job) -> JobResponse:
    return JobResponse(
        id=job.id,
        status=job.status.value,
        created_at=job.created_at,
        current_page=job.current_page,
        total_pages=job.total_pages,
        current_floor=job.current_floor,
        results=job.results if job.status == JobStatus.COMPLETED else None,
        error=job.error,
    )
