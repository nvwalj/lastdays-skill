"""Reddit via the public search.json endpoint (keyless).

Note: Reddit increasingly returns HTTP 403 to the public .json endpoints from
datacenter IPs. This fetcher tolerates that (returns []); when it comes back
thin, the agent supplements Reddit via WebSearch `site:reddit.com` and labels it
web-sourced. A keyless RSS + shreddit fallback is a planned fast-follow.
"""

from __future__ import annotations

import datetime
from urllib.parse import quote_plus

from .. import http, registry
from ..dates import Window
from ..schema import Item
from .base import strip_html, to_int

DEPTH = {"quick": 10, "default": 25, "deep": 40}


def _t_param(days: int) -> str:
    if days <= 1:
        return "day"
    if days <= 7:
        return "week"
    if days <= 31:
        return "month"
    if days <= 366:
        return "year"
    return "all"


def fetch(query: str, window: Window, *, env: dict, depth: str = "default") -> list[Item]:
    limit = DEPTH.get(depth, 25)
    url = (
        f"https://www.reddit.com/search.json?q={quote_plus(query)}"
        f"&sort=relevance&t={_t_param(window.days)}&limit={limit}&raw_json=1"
    )
    try:
        data = http.get(url, headers={"Accept": "application/json"}, timeout=15, retries=2)
    except http.HTTPError:
        return []
    children = (data or {}).get("data", {}).get("children", [])
    items: list[Item] = []
    for ch in children:
        if ch.get("kind") != "t3":
            continue
        p = ch.get("data", {})
        permalink = str(p.get("permalink", "")).strip()
        if "/comments/" not in permalink:
            continue
        created = p.get("created_utc")
        ts = float(created) if created else None
        date = (
            datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc).strftime("%Y-%m-%d")
            if ts
            else None
        )
        author = p.get("author")
        items.append(
            Item(
                source="reddit",
                lang="en",
                title=str(p.get("title", "")).strip(),
                url=f"https://www.reddit.com{permalink}",
                author=author if author not in ("[deleted]", "[removed]") else None,
                container=f"r/{p.get('subreddit', '')}",
                date=date,
                ts=ts,
                engagement={
                    "score": to_int(p.get("score")),
                    "comments": to_int(p.get("num_comments")),
                    "upvote_ratio": p.get("upvote_ratio"),
                },
                snippet=strip_html(str(p.get("selftext", ""))[:240]),
                relevance=0.6,
                item_id=f"rd{p.get('id', '')}",
            )
        )
    return items


registry.register(registry.Source("reddit", "en", fetch, aliases=("r", "subreddit")))
