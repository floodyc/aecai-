"""In-memory job queue for takeoff processing.

For the MVP we use a simple dict-based store with threading.
Upgrade to Redis + RQ or Celery for production.
"""

from __future__ import annotations

import logging
import threading
import traceback
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from aecai.pipeline import run_takeoff

logger = logging.getLogger(__name__)


class JobStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class Job:
    id: str
    pdf_path: str
    status: JobStatus = JobStatus.PENDING
    created_at: str = ""
    current_page: int = 0
    total_pages: int = 0
    current_floor: str = ""
    results: dict[str, Any] | None = None
    error: str | None = None
    pages: list[int] | None = None
    sheet_map: dict[int, str] | None = None
    multipliers: dict[str, int] | None = None
    legend_page: int | None = None
    legend_image_path: str | None = None
    fixture_prefix: str | None = None
    exemplars: list[dict[str, Any]] | None = None

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()


# In-memory job store
_jobs: dict[str, Job] = {}
_lock = threading.Lock()


def create_job(
    pdf_path: str,
    pages: list[int] | None = None,
    sheet_map: dict[int, str] | None = None,
    multipliers: dict[str, int] | None = None,
    legend_page: int | None = None,
    legend_image_path: str | None = None,
    fixture_prefix: str | None = None,
    exemplars: list[dict] | None = None,
) -> Job:
    """Create a new takeoff job and start processing in a background thread."""
    job_id = uuid.uuid4().hex[:12]
    job = Job(
        id=job_id,
        pdf_path=pdf_path,
        pages=pages,
        sheet_map=sheet_map,
        multipliers=multipliers,
        legend_page=legend_page,
        legend_image_path=legend_image_path,
        fixture_prefix=fixture_prefix,
        exemplars=exemplars,
    )

    with _lock:
        _jobs[job_id] = job

    # Start processing in background thread
    thread = threading.Thread(target=_process_job, args=(job_id,), daemon=True)
    thread.start()

    return job


def get_job(job_id: str) -> Job | None:
    """Retrieve a job by ID."""
    with _lock:
        return _jobs.get(job_id)


def _process_job(job_id: str) -> None:
    """Background worker that runs the takeoff pipeline."""
    job = _jobs.get(job_id)
    if not job:
        return

    def progress_callback(current: int, total: int, floor_name: str) -> None:
        with _lock:
            job.current_page = current
            job.total_pages = total
            job.current_floor = floor_name

    try:
        with _lock:
            job.status = JobStatus.PROCESSING

        results = run_takeoff(
            pdf_path=job.pdf_path,
            pages=job.pages,
            sheet_map=job.sheet_map,
            multipliers=job.multipliers,
            legend_page=job.legend_page,
            legend_image_path=job.legend_image_path,
            fixture_prefix=job.fixture_prefix,
            exemplars=job.exemplars,
            progress_callback=progress_callback,
        )

        with _lock:
            job.status = JobStatus.COMPLETED
            job.results = results

        logger.info("Job %s completed successfully", job_id)

    except Exception as e:
        logger.error("Job %s failed: %s", job_id, e)
        logger.error(traceback.format_exc())
        with _lock:
            job.status = JobStatus.FAILED
            job.error = str(e)

    finally:
        # Clean up the uploaded files
        try:
            Path(job.pdf_path).unlink(missing_ok=True)
        except Exception:
            pass
        if job.legend_image_path:
            try:
                Path(job.legend_image_path).unlink(missing_ok=True)
            except Exception:
                pass


def cleanup_old_jobs(max_age_hours: int = 24) -> int:
    """Remove jobs older than max_age_hours. Returns count removed."""
    now = datetime.now(timezone.utc)
    to_remove = []

    with _lock:
        for job_id, job in _jobs.items():
            created = datetime.fromisoformat(job.created_at)
            age = (now - created).total_seconds() / 3600
            if age > max_age_hours:
                to_remove.append(job_id)

        for job_id in to_remove:
            del _jobs[job_id]

    return len(to_remove)
