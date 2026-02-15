"""FastAPI application entry point for AECAI."""

from __future__ import annotations

import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routes import router

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="AECAI API",
    description="Automated lighting fixture takeoff from electrical drawing PDFs",
    version="1.0.0",
)

# ---------------------------------------------------------------------------
# CORS – allow the Vercel frontend (production + preview URLs)
# ---------------------------------------------------------------------------

ALLOWED_ORIGINS = [
    o.strip()
    for o in os.environ.get(
        "CORS_ORIGINS",
        "http://localhost:3000,https://aecai.vercel.app",
    ).split(",")
    if "*" not in o
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_origin_regex=r"https://aecai(-[a-z0-9]+)?\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

app.include_router(router)


@app.get("/")
async def root():
    return {"message": "AECAI API", "docs": "/docs"}
