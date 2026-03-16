"""Helpers for emitted config file naming."""

from __future__ import annotations

from pathlib import Path


def normalize_emit_segment(raw: str, arg_name: str) -> str:
    """Validate and normalize a naming segment used in file names."""
    value = raw.strip()
    if not value:
        raise ValueError(f"{arg_name} 不能为空")
    if "/" in value or "\\" in value:
        raise ValueError(f"{arg_name} 不能包含路径分隔符")
    return value


def normalize_emit_separator(raw: str, arg_name: str) -> str:
    """Validate and normalize separator used between naming segments."""
    value = raw.strip()
    if not value:
        raise ValueError(f"{arg_name} 不能为空")
    if "/" in value or "\\" in value:
        raise ValueError(f"{arg_name} 不能包含路径分隔符")
    return value


def validate_emit_template(raw: str, arg_name: str = "--emit-template") -> str:
    """Validate template and ensure required placeholders exist."""
    value = normalize_emit_segment(raw, arg_name)
    if "{symbol}" not in value:
        raise ValueError(f"{arg_name} 必须包含 {{symbol}} 占位符")
    if "{ts}" not in value:
        raise ValueError(f"{arg_name} 必须包含 {{ts}} 占位符")
    return value


def build_emit_filename(
    *,
    symbol: str,
    timestamp_token: str = "{ts}",
    separator: str = "_",
    prefix: str | None = None,
    tag: str | None = None,
    template: str | None = None,
) -> str:
    """Build emitted config file name with template or structured tokens."""
    if template is not None:
        name = template.replace("{symbol}", symbol)
        if not name.endswith(".json"):
            name = f"{name}.json"
        return name

    tokens = ["score", "vs", "macd", symbol, timestamp_token]
    name = separator.join(tokens) + ".json"
    if prefix:
        name = f"{prefix}{separator}{name}"
    if tag:
        path = Path(name)
        name = f"{path.stem}{separator}{tag}{path.suffix}"
    return name
