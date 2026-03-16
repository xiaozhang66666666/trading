#!/usr/bin/env python3
"""Bootstrap local Python environment for this project."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python <3.11 fallback
    import tomli as tomllib  # type: ignore[no-redef]


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
    parser.add_argument("--check-sync", action="store_true", help="Check pyproject/requirements dependency sync and exit")
    return parser


def _extract_req_name(spec: str) -> str:
    token = spec.strip()
    if not token:
        return ""
    token = token.split(";", 1)[0].strip()
    token = token.split("[", 1)[0].strip()
    parts = re.split(r"[<>=!~ ]", token, maxsplit=1)
    return parts[0].strip().lower()


def _parse_requirements(path: Path, seen: set[Path] | None = None) -> set[str]:
    if seen is None:
        seen = set()
    resolved = path.resolve()
    if resolved in seen or not path.exists():
        return set()
    seen.add(resolved)

    names: set[str] = set()
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("-r ") or line.startswith("--requirement "):
            _, rel = line.split(maxsplit=1)
            names.update(_parse_requirements(path.parent / rel.strip(), seen))
            continue
        name = _extract_req_name(line)
        if name:
            names.add(name)
    return names


def _parse_pyproject_dependencies(pyproject_path: Path) -> tuple[set[str], set[str]]:
    if not pyproject_path.exists():
        return set(), set()
    payload = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    project = payload.get("project", {})
    deps = {_extract_req_name(str(item)) for item in project.get("dependencies", [])}
    optional = project.get("optional-dependencies", {})
    dev = {_extract_req_name(str(item)) for item in optional.get("dev", [])}
    return {d for d in deps if d}, {d for d in dev if d}


def _check_dependency_sync(root: Path) -> tuple[bool, list[str]]:
    req_core = _parse_requirements(root / "requirements.txt")
    req_dev = _parse_requirements(root / "requirements-dev.txt")
    py_core, py_dev = _parse_pyproject_dependencies(root / "pyproject.toml")

    issues: list[str] = []
    if req_core != py_core:
        issues.append(
            "核心依赖不一致: "
            f"requirements-only={sorted(req_core - py_core)}, "
            f"pyproject-only={sorted(py_core - req_core)}"
        )
    # requirements-dev 通常包含 -r requirements.txt，因此仅比较 dev 增量
    req_dev_extra = req_dev - req_core
    if req_dev_extra != py_dev:
        issues.append(
            "开发依赖不一致: "
            f"requirements-dev-only={sorted(req_dev_extra - py_dev)}, "
            f"pyproject-dev-only={sorted(py_dev - req_dev_extra)}"
        )
    return len(issues) == 0, issues


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    root = Path(__file__).resolve().parents[1]
    if args.check_sync:
        ok, issues = _check_dependency_sync(root)
        if ok:
            print("Dependency sync check passed (pyproject == requirements).")
            return 0
        print("Dependency sync check failed:")
        for issue in issues:
            print(f"- {issue}")
        return 2

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
