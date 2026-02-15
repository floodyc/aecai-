"""Launch script for local development on Windows.

Usage: python run.py
"""
import os
import sys
from pathlib import Path

# Set PYTHONPATH as env var so uvicorn's reload subprocess inherits it
backend_dir = str(Path(__file__).parent)
os.environ["PYTHONPATH"] = backend_dir
sys.path.insert(0, backend_dir)

import uvicorn

if __name__ == "__main__":
    uvicorn.run("api.main:app", host="127.0.0.1", port=8000, reload=True)
