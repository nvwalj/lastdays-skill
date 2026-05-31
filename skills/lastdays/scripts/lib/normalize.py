"""Dedupe + strict date-window filtering."""

from __future__ import annotations

import re
from urllib.parse import urlsplit, urlunsplit

from .dates import Window
from .schema import Item


def canonical_url(u: str) -> str:
    """Normalize a URL for dedup keying: https, no www, no query/fragment, no trailing slash."""
    if not u:
        return ""
    try:
        parts = urlsplit(u.strip())
    except ValueError:
        return u.strip().lower()
    netloc = parts.netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    path = re.sub(r"/+$", "", parts.path)
    return urlunsplit(("https", netloc, path, "", "")).lower()


def dedupe(items: list[Item]) -> list[Item]:
    """Drop duplicate URLs, keeping the higher-scored / higher-engagement copy."""
    seen: dict[str, Item] = {}
    out: list[Item] = []
    for it in items:
        key = canonical_url(it.url) or f"{it.source}|{it.title.lower()}"
        prev = seen.get(key)
        if prev is None:
            seen[key] = it
            out.append(it)
            continue
        if (it.score, it.engagement_total()) > (prev.score, prev.engagement_total()):
            out[out.index(prev)] = it
            seen[key] = it
    return out


def filter_window(items: list[Item], window: Window, *, allow_undated: bool = False) -> list[Item]:
    """Keep items whose date falls inside the window.

    Out-of-window dated items are always dropped. Undated items are dropped by
    default (strict) and kept only when allow_undated=True.
    """
    out: list[Item] = []
    for it in items:
        stamp = it.ts if it.ts is not None else it.date
        if window.contains(stamp):
            out.append(it)
        elif allow_undated and it.ts is None and not it.date:
            out.append(it)
    return out
