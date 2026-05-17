"""Utility functions for pixel-square-daily."""

from __future__ import annotations

import html
import os
import re
from typing import Any


def env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def mask_key(api_key: str) -> str:
    api_key = api_key.strip()
    if len(api_key) <= 10:
        return "***"
    return f"{api_key[:5]}...{api_key[-4:]}"


def clean_html(value: str) -> str:
    value = html.unescape(value)
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def compact_usd(value: float | None) -> str:
    if value is None:
        return "N/A"
    if value >= 1_000_000_000:
        return f"${value / 1_000_000_000:.2f}B"
    if value >= 1_000_000:
        return f"${value / 1_000_000:.2f}M"
    if value >= 1_000:
        return f"${value / 1_000:.2f}K"
    return f"${value:.2f}"
