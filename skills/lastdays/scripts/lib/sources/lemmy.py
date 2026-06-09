"""Lemmy (federated Reddit alternative) via the public API (keyless).

lemmy.world/api/v3/search returns real engagement (score, comments) and a
published date, no key. Lemmy is the zero-key complement to the Reddit source,
which frequently 403s from datacenter IPs -- and its technology communities
actively discuss scraping / data-access topics (e.g. "Reddit blocks JSON API").

There is no server-side date filter, so the sort is picked to bracket the
window (TopWeek/Month/Year) to fetch recent-window heat; the engine then strictly
window-filters (normalize.filter_window) and engagement-ranks. The instance is
overridable via env LEMMY_INSTANCE (default lemmy.world, the largest instance).
"""

from __future__ import annotations

from urllib.parse import urlencode

from .. import http, registry
from ..dates import Window
from ..schema import Item
from .base import is_on_topic, strip_html, title_relevance, to_int

DEFAULT_INSTANCE = "lemmy.world"
DEPTH = {"quick": 10, "default": 20, "deep": 40}
# Floor for a hit that passed the on-topic gate but shows no literal title match.
NO_MATCH_FLOOR = 0.3


def _sort_for_window(days: int) -> str:
    """Smallest Top period that brackets the window, so we fetch recent-window
    heat and the engine then strictly window-filters. Finer buckets than
    Week/Month/Year tighten the bracket and lift recall for mid-length windows
    (lemmy.world supports TopThreeMonths/TopSixMonths). A sort an older instance
    rejects just errors out, and fetch() degrades to []."""
    if days <= 7:
        return "TopWeek"
    if days <= 31:
        return "TopMonth"
    if days <= 93:
        return "TopThreeMonths"
    if days <= 186:
        return "TopSixMonths"
    return "TopYear"


def fetch(query: str, window: Window, *, env: dict, depth: str = "default") -> list[Item]:
    instance = (env or {}).get("LEMMY_INSTANCE") or DEFAULT_INSTANCE
    per = DEPTH.get(depth, 20)
    params = {
        "q": query,
        "type_": "Posts",
        "sort": _sort_for_window(window.days),
        "limit": str(per),
    }
    url = f"https://{instance}/api/v3/search?{urlencode(params)}"
    try:
        resp = http.get(url, timeout=20, retries=2)
    except http.HTTPError:
        return []  # instance down / rate-limited -> degrade gracefully
    items: list[Item] = []
    seen: set = set()
    for entry in (resp.get("posts") or []) if isinstance(resp, dict) else []:
        if not isinstance(entry, dict):
            continue
        post = entry.get("post") or {}
        title = strip_html(post.get("name", ""))
        if not title:
            continue
        # Lemmy search recalls loosely (body/community matches); gate on the
        # engine's own relevance so off-topic posts drop.
        if not is_on_topic(query, title):
            continue
        pid = post.get("id")
        if pid is None or pid in seen:  # skip id-less malformed posts (would collide on "lmNone")
            continue
        seen.add(pid)
        counts = entry.get("counts") or {}
        published = post.get("published")  # ISO 8601; engine filters the window
        community = (entry.get("community") or {}).get("name")
        creator = (entry.get("creator") or {}).get("name")
        items.append(
            Item(
                source="lemmy",
                lang="en",
                title=title,
                url=post.get("url") or post.get("ap_id") or "",
                author=creator,
                container=f"c/{community}" if community else None,
                date=published[:10] if published else None,
                ts=None,
                engagement={"score": to_int(counts.get("score")), "comments": to_int(counts.get("comments"))},
                snippet=strip_html((post.get("body") or "")[:240]),
                relevance=max(NO_MATCH_FLOOR, title_relevance(query, title)),
                item_id=f"lm{pid}",
                metadata={"community": community, "ap_id": post.get("ap_id")},
            )
        )
    return items


registry.register(registry.Source("lemmy", "en", fetch, aliases=("lem",)))
