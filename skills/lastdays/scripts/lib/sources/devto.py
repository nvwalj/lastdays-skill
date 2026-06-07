"""Dev.to source for lastdays.

Keyless: dev.to's public API (/api/articles) returns real public_reactions_count,
comments_count, published_at, and tags. It searches by TAG, not arbitrary text,
so the query is normalized to a tag (lowercased, spaces removed: "web scraping"
-> "webscraping") and, as a fallback, recent articles are pulled and filtered by
is_on_topic on title+tags. Adds developer-blog coverage (tutorials, write-ups)
that HN/Lobsters headlines miss — strong for technical how-to topics.
"""

from __future__ import annotations

import re
from urllib.parse import urlencode

from .. import http, registry
from ..dates import Window
from ..schema import Item
from .base import is_on_topic, strip_html, title_relevance, to_int

API = "https://dev.to/api/articles"
DEPTH = {"quick": 15, "default": 30, "deep": 60}


def _query_tag(query: str) -> str:
    """dev.to tags are lowercase, alphanumeric, no spaces."""
    return re.sub(r"[^a-z0-9]", "", (query or "").lower())


def _to_items(articles: list, query: str) -> list[Item]:
    items: list[Item] = []
    for a in articles or []:
        if not isinstance(a, dict):
            continue
        title = strip_html(a.get("title", ""))
        if not title:
            continue
        tags = a.get("tag_list") or a.get("tags") or []
        if isinstance(tags, str):
            tags = [t.strip() for t in tags.split(",")]
        # Tag-endpoint hits are already on-topic; latest-endpoint hits must pass
        # the gate on title OR tags.
        if not (is_on_topic(query, title) or is_on_topic(query, " ".join(tags))):
            continue
        pub = a.get("published_at", "")  # ISO 8601 Z
        items.append(
            Item(
                source="devto",
                lang="en",
                title=title,
                url=a.get("url") or a.get("canonical_url") or "",
                author=(a.get("user") or {}).get("username") if isinstance(a.get("user"), dict) else None,
                date=pub[:10] if pub else None,
                ts=None,
                engagement={
                    "reactions": to_int(a.get("public_reactions_count") or a.get("positive_reactions_count")),
                    "comments": to_int(a.get("comments_count")),
                },
                snippet=strip_html(a.get("description") or "")[:240],
                relevance=max(0.3, title_relevance(query, f"{title} {' '.join(tags)}")),
                item_id=f"dt{a.get('id', '')}",
                metadata={"tags": tags, "reading_minutes": a.get("reading_time_minutes")},
            )
        )
    return items


def fetch(query: str, window: Window, *, env: dict, depth: str = "default") -> list[Item]:
    per = DEPTH.get(depth, 30)
    tag = _query_tag(query)
    items: list[Item] = []
    # Tier 1: tag search (precise) when the query maps to a usable tag.
    if tag:
        try:
            resp = http.get(f"{API}?{urlencode({'tag': tag, 'per_page': per})}", timeout=15, retries=2)
            items = _to_items(resp if isinstance(resp, list) else [], query)
        except http.HTTPError:
            items = []
    # Tier 2: fall back to latest + on-topic filter if the tag found nothing.
    if not items:
        try:
            resp = http.get(f"{API}/latest?{urlencode({'per_page': per})}", timeout=15, retries=2)
            items = _to_items(resp if isinstance(resp, list) else [], query)
        except http.HTTPError:
            return []
    return items


registry.register(registry.Source("devto", "en", fetch, aliases=("dev", "dev.to")))
