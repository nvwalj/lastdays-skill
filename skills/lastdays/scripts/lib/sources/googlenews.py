"""Google News RSS search (keyless), mainstream-news coverage.

`news.google.com/rss/search?q=<q>+when:{N}d` returns a recency-bounded RSS feed
of news articles — the layer Hacker News / Reddit / Lobsters miss (press, trade
press, regional outlets). It is a **degraded** source: RSS carries no engagement
(no upvotes/comments), so items are scored on relevance + recency only, flagged
`metadata.degraded`, and gated by `is_on_topic` (the only defense against noise
when there is no engagement to rank by).

Caveats handled here:
- `when:{N}d` ties recency to the engine window server-side; we still re-check
  each pubDate against the window so a stale item can't slip in.
- Item links are Google redirect URLs (`/rss/articles/CBMi…`). They resolve to
  the publisher in a browser; the post-2024 encoding is not trivially decodable
  keyless, so we keep the working redirect URL and surface the real publisher via
  `author`/`container` (and strip the " - Publisher" suffix Google appends to
  titles). The synthesizer cites the outlet by name, not the opaque URL.
"""

from __future__ import annotations

import datetime
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from urllib.parse import quote_plus

from .. import http, registry
from ..dates import Window
from ..schema import Item
from .base import is_on_topic, strip_html, title_relevance

DEPTH = {"quick": 15, "default": 30, "deep": 50}
FEED = "https://news.google.com/rss/search"


def _when(days: int) -> str:
    """Google News recency operator. Clamp to its useful range (1..365 days)."""
    return f"{max(1, min(days, 365))}d"


def _parsed_dt(raw: str):
    """RFC-822 pubDate -> aware UTC datetime, or (None, None)."""
    if not raw:
        return None, None
    try:
        dt = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return None, None
    if dt is None:
        return None, None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    dt = dt.astimezone(datetime.timezone.utc)
    return dt.timestamp(), dt.strftime("%Y-%m-%d")


def _strip_suffix(title: str, source: str) -> str:
    """Google appends ' - Publisher' to every title; drop it when it matches."""
    if source and title.endswith(f" - {source}"):
        return title[: -(len(source) + 3)].strip()
    return title


def _article_id(link: str) -> str:
    """Stable per-article id from the redirect URL's opaque token."""
    tail = link.rstrip("/").rsplit("/", 1)[-1]
    return "gn" + (tail[:32] or str(abs(hash(link))))


def fetch(query: str, window: Window, *, env: dict, depth: str = "default") -> list[Item]:
    limit = DEPTH.get(depth, 30)
    q = quote_plus(f"{query} when:{_when(window.days)}")
    url = f"{FEED}?q={q}&hl=en-US&gl=US&ceid=US:en"
    text = http.get_text(url, timeout=15, accept="application/rss+xml, application/xml, */*")
    if not text:
        return []
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return []
    channel = root.find("channel")
    if channel is None:
        return []
    items: list[Item] = []
    for el in channel.findall("item"):
        link = (el.findtext("link") or "").strip()
        if not link:
            continue
        src_el = el.find("source")
        source_name = (src_el.text or "").strip() if src_el is not None else ""
        title = _strip_suffix(strip_html(el.findtext("title") or ""), source_name)
        if not title:
            continue
        # No engagement to rank by -> a hard topic gate is the only noise defense.
        if not is_on_topic(query, title):
            continue
        ts, date = _parsed_dt(el.findtext("pubDate") or "")
        if ts is not None and not window.contains(ts):
            continue  # when:Nd is approximate; enforce the exact window
        items.append(
            Item(
                source="googlenews",
                lang="en",
                title=title,
                url=link,
                author=source_name or None,
                container=source_name or None,
                date=date,
                ts=ts,
                engagement={},  # RSS has no engagement — never fake it
                snippet=strip_html(el.findtext("description") or "")[:240],
                relevance=title_relevance(query, title),
                item_id=_article_id(link),
                metadata={"publisher": source_name} if source_name else {},
            )
        )
        if len(items) >= limit:
            break
    return items


registry.register(
    registry.Source(
        "googlenews",
        "en",
        tiers=(
            registry.Tier(
                fetch, quality=100, degraded=True, label="rss",
                note="news RSS: no engagement; relevance+recency only",
            ),
        ),
        aliases=("gn", "news"),
    )
)
