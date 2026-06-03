"""Reddit search (keyless), two-tier via the registry tier framework.

Tier "json" (quality 100): public ``search.json`` — carries real engagement
(score, comments, upvote_ratio) but returns HTTP 403 from datacenter IPs.
Tier "rss" (quality 40, degraded): ``search.rss`` — reachable where ``.json`` is
403, but RSS only carries title/link/author/date, NOT engagement. Because it has
no engagement to rank by, this tier additionally drops titles that don't actually
match the query (otherwise "Flea market find" leaks in for query "Nvidia" just
because both contain "market"). Items are flagged degraded so scoring/rendering
never fake upvotes. If both tiers fail the source yields nothing and the agent
supplements via WebSearch ``site:reddit.com``.
"""

from __future__ import annotations

import datetime
import re
from urllib.parse import quote_plus

from .. import http, registry
from ..dates import Window
from ..schema import Item
from .base import strip_html, title_relevance, to_int

DEPTH = {"quick": 10, "default": 25, "deep": 40}
# Min title relevance for the engagement-less RSS tier (tuned on real data:
# keeps "Nvidia hits new high", drops "Flea market find" for query "Nvidia").
RSS_MIN_RELEVANCE = 0.3


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


def _from_json(query: str, window: Window, *, env: dict, depth: str = "default") -> list[Item]:
    """Tier 'json' (quality 100): real engagement; 403 from datacenter IPs."""
    limit = DEPTH.get(depth, 25)
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


def _from_rss(query: str, window: Window, *, env: dict, depth: str = "default") -> list[Item]:
    """Tier 'rss' (quality 40, degraded): reachable on 403, but no engagement."""
    limit = DEPTH.get(depth, 25)
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
        # RSS has no engagement to rank by, so a relevance gate is the only
        # defense against off-topic noise (e.g. "Flea market find" for "Nvidia").
        if title_relevance(query, title) < RSS_MIN_RELEVANCE:
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
        # removeprefix, NOT lstrip: lstrip("/u/") strips any leading / u / chars
        # and would corrupt "/u/user123" -> "ser123". Guard against a missing
        # <author> tag (_tag can return "") so one odd entry can't sink the tier.
        author = (_tag(raw, "name") or "").removeprefix("/u/") or None
        sub = re.search(r"/r/([^/]+)/comments/", href)
        cid = re.search(r"/comments/([a-z0-9]+)", href)  # compute once
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
                item_id=f"rd{cid.group(1)}" if cid else "",
            )
        )
        if len(items) >= limit:
            break
    return items


registry.register(
    registry.Source(
        "reddit",
        "en",
        tiers=(
            registry.Tier(_from_json, quality=100, degraded=False, label="json"),
            registry.Tier(_from_rss, quality=40, degraded=True, label="rss"),
        ),
        aliases=("r", "subreddit"),
    )
)
