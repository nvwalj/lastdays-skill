"""Stack Overflow / Stack Exchange via the public API (keyless).

api.stackexchange.com/2.3/search/advanced returns real engagement (question
score, answer count, view count) with SERVER-SIDE date filtering via `fromdate`
(Unix) — the cleanest date window of any source here. Keyless calls draw on a
per-IP ~300/day quota (cached repeats are free); a throttle or quota-exhaustion
raises and degrades to [] gracefully.

Curated tags make precision high: a question tagged `web-scraping` tokenizes to
both "web" and "scraping", so the is_on_topic gate on title+tags keeps genuine
hits while dropping body-only matches (a "how to add numbers" question that just
mentions "scraping" in its body). Technical-leaning by nature — niche or
non-programming topics return little, which the brief should state rather than
implying silence.
"""

from __future__ import annotations

import datetime
from urllib.parse import urlencode

from .. import dates, http, registry
from ..dates import Window
from ..schema import Item
from .base import is_on_topic, strip_html, title_relevance, to_int

API = "https://api.stackexchange.com/2.3/search/advanced"
SITE = "stackoverflow"
DEPTH = {"quick": 15, "default": 30, "deep": 50}
# Floor for a hit that passed the gate (so a body/tag match without a literal
# title match still ranks, but below titles that match the query words).
NO_MATCH_FLOOR = 0.3
# Keyless quota is ~300/day per IP, so page-walk conservatively even on long
# windows. fromdate already widens recall server-side; a couple pages suffice.
MAX_PAGES = 2


def _to_items(raw: list, query: str) -> list[Item]:
    items: list[Item] = []
    for q in raw or []:
        if not isinstance(q, dict):
            continue
        title = strip_html(q.get("title", ""))  # unescapes &quot; etc.
        if not title:
            continue
        tags = q.get("tags") or []
        # Curated tags carry the topic word a terse title may omit: gate on title
        # OR tags so `web-scraping` (-> "web"+"scraping") passes, while an
        # off-topic question that only matched the query in its body is dropped.
        if not (is_on_topic(query, title) or is_on_topic(query, " ".join(tags))):
            continue
        created = q.get("creation_date")
        ts = float(created) if created else None
        date = (
            datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc).strftime("%Y-%m-%d")
            if ts
            else None
        )
        items.append(
            Item(
                source="stackexchange",
                lang="en",
                title=title,
                url=q.get("link", ""),
                author=(q.get("owner") or {}).get("display_name"),
                date=date,
                ts=ts,
                engagement={
                    "score": to_int(q.get("score")),
                    "answers": to_int(q.get("answer_count")),
                    "views": to_int(q.get("view_count")),
                },
                snippet=("tags: " + ", ".join(tags))[:240] if tags else "",
                relevance=max(NO_MATCH_FLOOR, title_relevance(query, f"{title} {' '.join(tags)}")),
                item_id=f"so{q.get('question_id', '')}",
                metadata={"tags": tags, "is_answered": q.get("is_answered"), "site": SITE},
            )
        )
    return items


def fetch(query: str, window: Window, *, env: dict, depth: str = "default") -> list[Item]:
    per = DEPTH.get(depth, 30)
    # No `todate`: omitting it defaults to "now" server-side AND keeps the URL
    # stable within a day so the HTTP cache can hit. `fromdate` is day-quantized
    # for the same reason (a second-precise bound made every URL unique).
    base = {
        "order": "desc",
        "sort": "votes",
        "q": query,
        "site": SITE,
        "fromdate": str(window.cutoff_day_ts),
        "pagesize": str(per),
        "filter": "default",
    }
    items: list[Item] = []
    seen: set = set()
    pages = min(MAX_PAGES, dates.pages_for_window(window.days))
    for page in range(1, pages + 1):
        params = dict(base, page=str(page))
        try:
            resp = http.get(f"{API}?{urlencode(params)}", timeout=20, retries=2, max_429_retries=1)
        except http.HTTPError:
            break  # throttled / quota exhausted -> use what we have
        page_items = resp.get("items", []) if isinstance(resp, dict) else []
        for it in _to_items(page_items, query):
            if it.item_id in seen:  # de-dup across pages
                continue
            seen.add(it.item_id)
            items.append(it)
        if not (isinstance(resp, dict) and resp.get("has_more")):  # server: no more pages
            break
    return items


registry.register(registry.Source("stackexchange", "en", fetch, aliases=("stackoverflow", "so", "se")))
