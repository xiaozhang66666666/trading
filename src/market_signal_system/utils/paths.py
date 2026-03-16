"""Path helpers for local data and runtime state."""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = PROJECT_ROOT / "data"
CACHE_DIR = DATA_DIR / "cache"
STATE_DIR = DATA_DIR / "state"
OUTPUT_DIR = PROJECT_ROOT / "outputs"


def ensure_runtime_dirs() -> None:
    """Create runtime directories when missing."""
    for path in (DATA_DIR, CACHE_DIR, STATE_DIR, OUTPUT_DIR):
        path.mkdir(parents=True, exist_ok=True)
