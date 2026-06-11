"""arXiv search (keyless), primary-research coverage.

`export.arxiv.org/api/query?search_query=all:<q>&sortBy=submittedDate` returns
the newest papers matching the query as an Atom feed. This is the primary-source
layer that news/social/forum sources miss — fresh CS/ML/physics/stat papers for
research-shaped topics. It is a **degraded** source: papers carry no engagement
(citations aren't in the feed), so items are scored on relevance + recency only,
flagged `metadata.degraded`, and `is_on_topic`-gated (title or abstract) to drop
the looser `all:`-field matches.

Etiquette: arXiv asks for <=1 request / 3s on a single connection; the engine
makes one request per run here and already backs off on 429 (sporadic since
~Feb 2026). For non-research topics the feed is legitimately empty — say so in
the brief rather than implying arXiv had nothing relevant.
"""

from __future__ import annotations

import datetime
import xml.etree.ElementTree as ET
from urllib.parse import quote

from .. import http, registry
from ..dates import Window
from ..schema import Item
from .base import is_on_topic, strip_html, title_relevance

API = "https://export.arxiv.org/api/query"
DEPTH = {"quick": 15, "default": 30, "deep": 50}
NO_MATCH_FLOOR = 0.3
_NS = {"a": "http://www.w3.org/2005/Atom"}


def _parsed_dt(raw: str):
    """arXiv ISO 'YYYY-MM-DDTHH:MM:SSZ' -> (ts, 'YYYY-MM-DD') in UTC, or (None, None)."""
    try:
        dt = datetime.datetime.fromisoformat((raw or "").replace("Z", "+00:00"))
    except ValueError:
        return None, None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    dt = dt.astimezone(datetime.timezone.utc)
    return dt.timestamp(), dt.strftime("%Y-%m-%d")


def _authors(entry) -> str | None:
    names = [n.text.strip() for n in entry.findall("a:author/a:name", _NS) if (n.text or "").strip()]
    if not names:
        return None
    return names[0] if len(names) == 1 else f"{names[0]} et al."


def fetch(query: str, window: Window, *, env: dict, depth: str = "default") -> list[Item]:
    count = DEPTH.get(depth, 30)
    # Quote the phrase so a multi-word topic is a phrase match (precision); the
    # is_on_topic gate below still trims any loose all:-field hits.
    q = quote(f'all:"{query}"')
    url = f"{API}?search_query={q}&sortBy=submittedDate&sortOrder=descending&max_results={count}"
    text = http.get_text(url, timeout=20, accept="application/atom+xml, application/xml, */*")
    if not text:
        return []
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return []
    items: list[Item] = []
    for e in root.findall("a:entry", _NS):
        title = strip_html(" ".join((e.findtext("a:title", "", _NS) or "").split()))
        if not title:
            continue
        summary = strip_html(" ".join((e.findtext("a:summary", "", _NS) or "").split()))
        # No engagement to rank by -> gate on title OR abstract (capped) so loose
        # all:-field matches drop, but a topic stated only in the abstract passes.
        if not (is_on_topic(query, title) or is_on_topic(query, summary[:400])):
            continue
        ts, date = _parsed_dt(e.findtext("a:published", "", _NS))
        if ts is not None and not window.contains(ts):
            continue
        abs_url = (e.findtext("a:id", "", _NS) or "").strip().replace("http://", "https://", 1)
        aid = abs_url.rsplit("/abs/", 1)[-1] if "/abs/" in abs_url else abs_url.rsplit("/", 1)[-1]
        items.append(
            Item(
                source="arxiv",
                lang="en",
                title=title,
                url=abs_url,
                author=_authors(e),
                container="arXiv",
                date=date,
                ts=ts,
                engagement={},  # citations not in the feed — never fake engagement
                snippet=summary[:240],
                relevance=max(NO_MATCH_FLOOR, title_relevance(query, title)),
                item_id=f"arxiv{aid}",
                metadata={"arxiv_id": aid},
            )
        )
        if len(items) >= count:
            break
    return items


registry.register(
    registry.Source(
        "arxiv",
        "en",
        tiers=(
            registry.Tier(
                fetch, quality=100, degraded=True, label="atom",
                note="research papers: no engagement; relevance+recency only",
            ),
        ),
        aliases=("arx", "papers"),
    )
)
