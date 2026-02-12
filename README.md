# AECAI – Automated Lighting Fixture Takeoff

A full-stack web application that performs automated lighting fixture takeoff from electrical drawing PDFs using computer vision.

## How It Works

1. **Upload** an electrical drawing PDF
2. The backend renders each page at 300 DPI, detects oval fixture symbols using OpenCV, reads fixture codes via Tesseract OCR, and fuzzy-corrects misreads
3. **View results** – per-floor fixture counts with building totals
4. **Download** reports in TXT or JSON format

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | Next.js 14, TypeScript, Tailwind CSS, SWR |
| Backend | FastAPI, Python 3.12, OpenCV, Tesseract OCR |
| Deploy | Vercel (frontend), Render (backend, Docker) |

## Quick Start

### Backend

```bash
cd backend
pip install -r requirements.txt
uvicorn api.main:app --reload --port 8000
```

Requires system packages: `tesseract-ocr` and `poppler-utils`.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Set `NEXT_PUBLIC_API_URL=http://localhost:8000` in `.env.local`.

### Docker

```bash
cd backend
docker build -t aecai-api .
docker run -p 8000:8000 aecai-api
```

## API Endpoints

| Method | Path | Description |
|---|---|---|
| POST | `/api/takeoff` | Upload PDF, start processing |
| GET | `/api/takeoff/{id}` | Poll job status |
| GET | `/api/takeoff/{id}/report` | Download TXT report |
| GET | `/api/health` | Health check |

## Deployment

- **Render**: Uses `render.yaml` with Docker. Set `CORS_ORIGINS` to your Vercel URL.
- **Vercel**: Point to `frontend/` directory. Set `NEXT_PUBLIC_API_URL` to your Render backend URL.

## License

Proprietary
