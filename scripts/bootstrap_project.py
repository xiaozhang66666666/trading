#!/usr/bin/env python3
"""Bootstrap local Python environment for this project."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def _venv_python_path(venv_dir: Path) -> Path:
    if sys.platform.startswith("win"):
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def _run(cmd: list[str], *, cwd: Path) -> None:
    result = subprocess.run(cmd, cwd=str(cwd), check=False)
    if result.returncode != 0:
        joined = " ".join(cmd)
        raise RuntimeError(f"Command failed ({result.returncode}): {joined}")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create venv and install dependencies for market-signal-system")
    parser.add_argument("--venv", default=".venv", help="Virtualenv directory, default .venv")
    parser.add_argument(
        "--mode",
        choices=["pyproject", "requirements", "hybrid"],
        default="hybrid",
        help="Install mode: pyproject / requirements / hybrid",
    )
    parser.add_argument("--dev", action="store_true", help="Install development dependencies")
    parser.add_argument("--no-upgrade-pip", action="store_true", help="Skip pip upgrade")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    root = Path(__file__).resolve().parents[1]
    venv_dir = root / args.venv

    _run([sys.executable, "-m", "venv", str(venv_dir)], cwd=root)
    py = _venv_python_path(venv_dir)

    if not py.exists():
        raise FileNotFoundError(f"Venv python not found: {py}")

    if not args.no_upgrade_pip:
        _run([str(py), "-m", "pip", "install", "--upgrade", "pip"], cwd=root)

    mode = str(args.mode)
    if mode in {"requirements", "hybrid"}:
        req = root / "requirements.txt"
        if req.exists():
            _run([str(py), "-m", "pip", "install", "-r", str(req)], cwd=root)
        if args.dev:
            req_dev = root / "requirements-dev.txt"
            if req_dev.exists():
                _run([str(py), "-m", "pip", "install", "-r", str(req_dev)], cwd=root)

    if mode in {"pyproject", "hybrid"}:
        if (root / "pyproject.toml").exists():
            target = ".[dev]" if args.dev else "."
            _run([str(py), "-m", "pip", "install", "-e", target], cwd=root)

    print(f"Bootstrap complete. Activate with: source {venv_dir}/bin/activate")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
