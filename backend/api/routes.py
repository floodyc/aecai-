"""FastAPI route definitions for the AECAI takeoff API."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, UploadFile
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from .jobs import JobStatus, create_job, get_job

router = APIRouter(prefix="/api")


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


class HealthResponse(BaseModel):
    status: str
    service: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/health", response_model=HealthResponse)
async def health_check():
    return HealthResponse(status="ok", service="aecai-api")


@router.post("/takeoff", response_model=JobResponse)
async def start_takeoff(
    file: UploadFile,
    pages: str | None = None,
    sheet_map: str | None = None,
    multipliers: str | None = None,
):
    """Upload a PDF and start a takeoff job.

    The PDF is saved to a temp file and processed in a background thread.
    Poll GET /api/takeoff/{job_id} for status updates.
    """
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="File must be a PDF")

    # Save uploaded file to temp location
    suffix = Path(file.filename).suffix
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix, prefix="aecai_") as tmp:
        content = await file.read()
        if len(content) == 0:
            raise HTTPException(status_code=400, detail="Empty file")
        tmp.write(content)
        tmp_path = tmp.name

    # Parse optional JSON parameters from form fields
    parsed_pages = None
    parsed_sheet_map = None
    parsed_multipliers = None

    if pages:
        try:
            parsed_pages = json.loads(pages)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Invalid pages JSON")

    if sheet_map:
        try:
            raw = json.loads(sheet_map)
            parsed_sheet_map = {int(k): v for k, v in raw.items()}
        except (json.JSONDecodeError, ValueError):
            raise HTTPException(status_code=400, detail="Invalid sheet_map JSON")

    if multipliers:
        try:
            raw = json.loads(multipliers)
            parsed_multipliers = {str(k): int(v) for k, v in raw.items()}
        except (json.JSONDecodeError, ValueError):
            raise HTTPException(status_code=400, detail="Invalid multipliers JSON")

    job = create_job(
        pdf_path=tmp_path,
        pages=parsed_pages,
        sheet_map=parsed_sheet_map,
        multipliers=parsed_multipliers,
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
