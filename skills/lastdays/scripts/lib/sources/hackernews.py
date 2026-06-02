"""Hacker News via the Algolia API (free, no key).

hn.algolia.com/api/v1/search_by_date with a created_at_i lower bound gives a
strict, recency-first window with real points + comment counts.
"""

from __future__ import annotations

import datetime
from urllib.parse import urlencode

from .. import http, registry
from ..dates import Window
from ..schema import Item
from .base import strip_html, to_int

ALGOLIA = "https://hn.algolia.com/api/v1/search_by_date"
DEPTH = {"quick": 15, "default": 30, "deep": 50}


def fetch(query: str, window: Window, *, env: dict, depth: str = "default") -> list[Item]:
    count = DEPTH.get(depth, 30)
    from_ts = int(window.cutoff.timestamp())
    params = {
        "query": query,
        "tags": "story",
        "numericFilters": f"created_at_i>{from_ts},points>1",
        "hitsPerPage": str(count),
    }
    # Algolia ANDs query tokens by default, so a multi-word phrase like
    # "US stock market" matches only titles containing all three words -> often 0.
    # Mark every token after the first as optional: Algolia then ranks by how many
    # tokens match instead of requiring all of them.
    tokens = query.split()
    if len(tokens) > 1:
        params["optionalWords"] = " ".join(tokens[1:])
    resp = http.get(f"{ALGOLIA}?{urlencode(params)}", timeout=20, retries=2)
    items: list[Item] = []
    for hit in resp.get("hits", []):
        title = hit.get("title") or hit.get("story_title") or ""
        if not title:
            continue
        oid = hit.get("objectID", "")
        created = hit.get("created_at_i")
        ts = float(created) if created else None
        date = (
            datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc).strftime("%Y-%m-%d")
            if ts
            else None
        )
        items.append(
            Item(
                source="hackernews",
                lang="en",
                title=title,
                url=hit.get("url") or f"https://news.ycombinator.com/item?id={oid}",
                author=hit.get("author"),
                date=date,
                ts=ts,
                engagement={"points": to_int(hit.get("points")), "comments": to_int(hit.get("num_comments"))},
                snippet=strip_html(hit.get("story_text") or "")[:240],
                relevance=0.6,
                item_id=f"hn{oid}",
                metadata={"hn_url": f"https://news.ycombinator.com/item?id={oid}"},
            )
        )
    return items


registry.register(registry.Source("hackernews", "en", fetch, aliases=("hn",)))
