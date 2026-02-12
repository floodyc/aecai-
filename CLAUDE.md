# AECAI – Claude Code Technical Reference

## What This Is

AECAI (Automated Electrical Construction AI) is a full-stack web application that performs automated lighting fixture takeoff from electrical drawing PDFs. It uses computer vision (OpenCV) to find oval fixture symbols on floor plans, OCR (Tesseract) to read fixture codes, fuzzy matching to correct OCR errors, and aggregates counts per floor into reports.

## Repository Structure

```
aecai-/
  backend/
    aecai/              # Core CV/OCR pipeline modules
      config.py         # Paths, thresholds, known luminaires
      shapes.py         # Oval contour detection (OpenCV)
      ocr.py            # Tesseract OCR + fuzzy correction
      report.py         # Report generation (JSON + TXT)
      pipeline.py       # End-to-end orchestrator
    api/
      main.py           # FastAPI app entry point
      routes.py         # API endpoints
      jobs.py           # In-memory background job queue
    Dockerfile          # Python 3.12 + Tesseract + Poppler
    requirements.txt
  frontend/
    src/
      app/              # Next.js App Router pages
        page.tsx        # Upload page (/)
        takeoff/[id]/   # Processing + Results page
      components/       # UploadZone, ProgressView, ResultsView
      lib/api.ts        # API client + types
    package.json
    tailwind.config.js
  render.yaml           # Render deployment config
  CLAUDE.md             # This file
```

## Core Pipeline (DO NOT MODIFY thresholds)

The CV pipeline in `backend/aecai/` is calibrated against real electrical drawings:

1. **PDF → Images**: `pipeline.pdf_to_images()` – renders at 300 DPI via pdf2image/Poppler
2. **Oval Detection**: `shapes.find_ovals()` – adaptive threshold → morphological close → contour filtering by area, aspect ratio, circularity
3. **OCR**: `ocr.recognize_fixtures()` – centre-crop each oval, preprocess (resize, Otsu), Tesseract PSM 8, fuzzy-correct against `KNOWN_LUMINAIRES`
4. **Reporting**: `report.build_results_json()` / `generate_txt_report()` – per-floor counts with typical-floor multipliers

**Calibrated parameters** (in config.py): `OVAL_MIN_AREA`, `OVAL_MAX_AREA`, `OVAL_MIN_ASPECT`, `OVAL_MAX_ASPECT`, `OVAL_CIRCULARITY_THRESH`, `CROP_PADDING`, `FUZZY_THRESHOLD`. These are tuned and should not be changed.

## Backend API

- `POST /api/takeoff` – Upload PDF (multipart), returns job with ID
- `GET /api/takeoff/{job_id}` – Poll status (pending/processing/completed/failed)
- `GET /api/takeoff/{job_id}/report` – Download TXT report
- `GET /api/health` – Health check

## Running Locally

### Backend
```bash
cd backend
pip install -r requirements.txt
# Requires: tesseract-ocr, poppler-utils installed on system
uvicorn api.main:app --reload --port 8000
```

### Frontend
```bash
cd frontend
npm install
npm run dev   # http://localhost:3000
```

### Docker (backend)
```bash
cd backend
docker build -t aecai-api .
docker run -p 8000:8000 aecai-api
```

## System Dependencies

- **Tesseract OCR**: `apt install tesseract-ocr` (Linux) or Windows installer
- **Poppler**: `apt install poppler-utils` (Linux) or Windows binary

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `TESSERACT_CMD` | auto-detected | Path to tesseract binary |
| `POPPLER_PATH` | None (uses PATH) | Path to poppler bin directory |
| `AECAI_DPI` | 300 | PDF rendering DPI |
| `CORS_ORIGINS` | localhost:3000 | Comma-separated allowed origins |
| `NEXT_PUBLIC_API_URL` | http://localhost:8000 | Backend URL for frontend |

## Test Data

- Test PDF: "UBC Lot 4 IFC (electrical).pdf" – 15 pages
- Single page test: page 5 (Level 2)
- Expected page 5 output: LT04:18, LT04A:17, LT04B:12, LT07:8, LT09:10, LT11:12, LT12:7, LT16:3
- Processing speed: ~70s/page at 300 DPI
