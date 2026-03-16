"""Bootstrap package for running `python -m market_signal_system` from repo root."""

from __future__ import annotations

import sys
from pathlib import Path
from pkgutil import extend_path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if SRC.is_dir() and str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

__path__ = extend_path(__path__, __name__)  # type: ignore[name-defined]

__all__ = ["__version__"]
__version__ = "0.1.0"
