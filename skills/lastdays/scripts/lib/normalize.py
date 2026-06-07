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


_TITLE_NORM_RE = re.compile(r"[^a-z0-9一-鿿]+")


def norm_title(title: str) -> str:
    """Normalize a title for cross-source matching: lowercase, strip punctuation/
    whitespace, keep ASCII alnum + CJK. So 'OpenAI releases GPT-6' and
    'openai releases gpt-6' (HN original vs a Reddit discussion of it) collapse
    to one key even when their URLs differ."""
    return _TITLE_NORM_RE.sub(" ", (title or "").lower()).strip()


def dedupe_keys(item: Item) -> tuple:
    """The keys that identify an item across sources: its canonical URL AND its
    normalized title. Two items collide if EITHER matches — the same story shared
    to two platforms usually keeps the title but not the URL."""
    cu = canonical_url(item.url)
    nt = norm_title(item.title)
    return (cu or None, nt or None)


def dedupe(items: list[Item]) -> list[Item]:
    """Drop duplicates by canonical URL OR normalized title, keeping the
    higher-scored / higher-engagement copy. Process highest-score-first so the
    survivor is the strongest copy (e.g. HN original over a low-score reshare)."""
    seen_url: set = set()
    seen_title: set = set()
    out: list[Item] = []
    for it in sorted(items, key=lambda i: (i.score, i.engagement_total()), reverse=True):
        cu, nt = dedupe_keys(it)
        if (cu and cu in seen_url) or (nt and nt in seen_title):
            continue  # a stronger copy already kept
        if cu:
            seen_url.add(cu)
        if nt:
            seen_title.add(nt)
        out.append(it)
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
