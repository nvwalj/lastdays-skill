"""Shared parse helpers for source modules."""

from __future__ import annotations

import html as _html
import re


def to_int(v, default: int = 0) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        try:
            return int(float(v))
        except (TypeError, ValueError):
            return default


def strip_html(text: str) -> str:
    if not text:
        return ""
    text = _html.unescape(text)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()
