"""Hacker News via the Algolia API (free, no key).

hn.algolia.com/api/v1/search_by_date with a created_at_i lower bound gives a
strict, recency-first window with real points + comment counts.
"""

from __future__ import annotations

import datetime
from urllib.parse import urlencode

from .. import dates, http, registry
from ..dates import Window
from ..schema import Item
from .base import strip_html, title_relevance, to_int

ALGOLIA = "https://hn.algolia.com/api/v1/search_by_date"
DEPTH = {"quick": 15, "default": 30, "deep": 50}
# Relevance floor for an Algolia hit whose title shows no literal query-word
# match. optionalWords lets single weak tokens ("we", "ai") pull in off-topic
# stories; this floor keeps them present (HN engagement may still matter) but
# well below titles that actually match, so noise sinks instead of riding
# upvotes to the top. A real word match scores higher via title_relevance.
NO_MATCH_FLOOR = 0.25


def _relevance(query: str, title: str) -> float:
    """Blend literal title match with a floor. A title that matches query words
    scores by coverage (up to ~0.9); one that matches none (only pulled in by
    optionalWords) gets NO_MATCH_FLOOR so it ranks below genuine matches."""
    return max(NO_MATCH_FLOOR, title_relevance(query, title))


def fetch(query: str, window: Window, *, env: dict, depth: str = "default") -> list[Item]:
    count = DEPTH.get(depth, 30)
    # Day-quantized so the URL is stable within a day -> HTTP cache can hit.
    # (A second-precise cutoff made every request unique and defeated caching.)
    from_ts = window.cutoff_day_ts
    base = {
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
        base["optionalWords"] = " ".join(tokens[1:])
    # Page-walk for longer windows: one response is capped at hitsPerPage, so a
    # 180-day window needs several pages to surface more than a 7-day one.
    hits: list = []
    for page in range(dates.pages_for_window(window.days)):
        params = dict(base, page=str(page))
        resp = http.get(f"{ALGOLIA}?{urlencode(params)}", timeout=20, retries=2)
        page_hits = resp.get("hits", [])
        hits.extend(page_hits)
        if len(page_hits) < count:  # last page reached, stop early
            break
    items: list[Item] = []
    seen_ids: set = set()
    for hit in hits:
        title = hit.get("title") or hit.get("story_title") or ""
        if not title:
            continue
        oid = hit.get("objectID", "")
        if oid in seen_ids:  # de-dup across pages
            continue
        seen_ids.add(oid)
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
                relevance=_relevance(query, title),
                item_id=f"hn{oid}",
                metadata={"hn_url": f"https://news.ycombinator.com/item?id={oid}"},
            )
        )
    return items


registry.register(registry.Source("hackernews", "en", fetch, aliases=("hn",)))
