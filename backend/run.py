"""Launch script for local development on Windows.

Usage: python run.py
"""
import sys
from pathlib import Path

# Ensure the backend directory is on Python's path
sys.path.insert(0, str(Path(__file__).parent))

import uvicorn

if __name__ == "__main__":
    uvicorn.run("api.main:app", host="127.0.0.1", port=8000, reload=True)
