"""Reddit search (keyless), two-tier.

Tier 0: public ``search.json`` — carries real engagement (score, comments,
upvote_ratio) but returns HTTP 403 from datacenter IPs.
Tier 1 (fallback): ``search.rss`` — reachable where ``.json`` is 403, but RSS
only carries title/link/author/date, NOT engagement. Items from this tier are
marked ``metadata.via = "rss"`` and carry empty engagement, so scoring and the
brief can treat them honestly (no invented upvotes). When both tiers fail the
fetcher returns [] and the agent supplements via WebSearch ``site:reddit.com``.
"""

from __future__ import annotations

import datetime
import re
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


def _from_json(query: str, window: Window, limit: int) -> list[Item]:
    url = (
        f"https://www.reddit.com/search.json?q={quote_plus(query)}"
        f"&sort=relevance&t={_t_param(window.days)}&limit={limit}&raw_json=1"
    )
    data = http.get(url, headers={"Accept": "application/json"}, timeout=15, retries=2)
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


_ENTRY_RE = re.compile(r"<entry>(.*?)</entry>", re.S)


def _tag(entry: str, name: str) -> str:
    m = re.search(rf"<{name}[^>]*>(.*?)</{name}>", entry, re.S)
    return strip_html(m.group(1)).strip() if m else ""


def _from_rss(query: str, window: Window, limit: int) -> list[Item]:
    url = f"https://www.reddit.com/search.rss?q={quote_plus(query)}&sort=new&t={_t_param(window.days)}"
    text = http.get_text(url, timeout=15, accept="application/atom+xml, application/rss+xml, */*")
    if not text:
        return []
    items: list[Item] = []
    for raw in _ENTRY_RE.findall(text):
        link = re.search(r'<link[^>]*href="([^"]+)"', raw)
        href = link.group(1) if link else ""
        if "/comments/" not in href:  # skip subreddit/user cards, keep only posts
            continue
        title = _tag(raw, "title")
        if not title:
            continue
        updated = _tag(raw, "updated") or _tag(raw, "published")
        ts = None
        date = None
        try:
            dt = datetime.datetime.fromisoformat(updated.replace("Z", "+00:00"))
            ts = dt.timestamp()
            date = dt.strftime("%Y-%m-%d")
        except (ValueError, AttributeError):
            pass
        author = _tag(raw, "name").lstrip("/u/") or None
        sub = re.search(r"/r/([^/]+)/comments/", href)
        items.append(
            Item(
                source="reddit",
                lang="en",
                title=title,
                url=href,
                author=author,
                container=f"r/{sub.group(1)}" if sub else None,
                date=date,
                ts=ts,
                engagement={},  # RSS carries no score/comments — leave empty, do not fake
                snippet="",
                relevance=0.55,
                item_id=f"rd{re.search(r'/comments/([a-z0-9]+)', href).group(1)}" if re.search(r'/comments/([a-z0-9]+)', href) else "",
                metadata={"via": "rss", "no_engagement": True},
            )
        )
        if len(items) >= limit:
            break
    return items


def fetch(query: str, window: Window, *, env: dict, depth: str = "default") -> list[Item]:
    limit = DEPTH.get(depth, 25)
    try:
        items = _from_json(query, window, limit)
        if items:
            return items
    except http.HTTPError:
        pass  # 403 from datacenter IPs — fall through to RSS
    return _from_rss(query, window, limit)


registry.register(registry.Source("reddit", "en", fetch, aliases=("r", "subreddit")))
