"""Lobsters (lobste.rs) source for lastdays.

Keyless: lobste.rs exposes a public hottest.json with real score / comment_count
/ created_at / tags. Its search endpoint is HTML-only (search.json -> 400), so —
like the Douyin hot board — this reads the front-page hot list and keeps entries
whose title/tags match the query via is_on_topic. That makes it a high-signal
"what's hot in the dev community right now" source for technical topics, with
genuine engagement, rather than an arbitrary-query search.
"""

from __future__ import annotations

from .. import http, registry
from ..dates import Window, to_datetime
from ..schema import Item
from .base import is_on_topic, strip_html, to_int

HOTTEST_URL = "https://lobste.rs/hottest.json"


def _matches(query: str, story: dict) -> bool:
    """On-topic if the query matches the title OR any tag (tags carry the topic,
    e.g. 'ai'/'databases', which a terse title may omit)."""
    if is_on_topic(query, story.get("title", "")):
        return True
    return is_on_topic(query, " ".join(story.get("tags", []) or []))


def fetch(query: str, window: Window, *, env: dict, depth: str = "default") -> list[Item]:
    try:
        stories = http.get(HOTTEST_URL, timeout=15, retries=2)
    except http.HTTPError:
        return []
    if not isinstance(stories, list):
        return []
    items: list[Item] = []
    for s in stories:
        if not isinstance(s, dict) or not _matches(query, s):
            continue
        title = strip_html(s.get("title", ""))
        if not title:
            continue
        # ISO 8601 with the site's OWN offset (e.g. ...-05:00) — convert to UTC
        # before taking the date; a bare [:10] slice would keep the local date
        # and disagree with the engine's UTC window convention at day edges.
        created_dt = to_datetime(s.get("created_at"))
        date = created_dt.strftime("%Y-%m-%d") if created_dt else None
        sid = s.get("short_id", "")
        items.append(
            Item(
                source="lobsters",
                lang="en",
                title=title,
                url=s.get("url") or s.get("comments_url") or "",
                author=(s.get("submitter_user") or {}).get("username")
                if isinstance(s.get("submitter_user"), dict)
                else s.get("submitter_user"),
                date=date,
                ts=None,
                engagement={"score": to_int(s.get("score")), "comments": to_int(s.get("comment_count"))},
                snippet=strip_html(s.get("description_plain") or s.get("description") or "")[:240],
                relevance=0.6,  # matched via is_on_topic gate; engine ranks by engagement+recency
                item_id=f"lo{sid}",
                metadata={"tags": s.get("tags", []), "comments_url": s.get("comments_url")},
            )
        )
    return items


registry.register(registry.Source("lobsters", "en", fetch, aliases=("lob", "lobste")))
