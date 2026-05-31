"""GitHub via the public search API (keyless; optional GITHUB_TOKEN lifts the limit).

Searches issues + PRs created inside the window, ranked by reactions. Unauthed
calls are capped at ~10 search req/min, so 403/429 degrades to [] gracefully; set
GITHUB_TOKEN (or GH_TOKEN) to raise the ceiling.
"""

from __future__ import annotations

from urllib.parse import urlencode

from .. import http, registry
from ..dates import Window
from ..schema import Item
from .base import strip_html, to_int

SEARCH_ISSUES = "https://api.github.com/search/issues"
DEPTH = {"quick": 10, "default": 20, "deep": 40}


def fetch(query: str, window: Window, *, env: dict, depth: str = "default") -> list[Item]:
    per = DEPTH.get(depth, 20)
    params = {
        "q": f"{query} created:>={window.from_date}",
        "sort": "reactions",
        "order": "desc",
        "per_page": str(per),
    }
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = (env or {}).get("GITHUB_TOKEN") or (env or {}).get("GH_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        resp = http.get(f"{SEARCH_ISSUES}?{urlencode(params)}", headers=headers, timeout=20, retries=2, max_429_retries=1)
    except http.HTTPError:
        return []
    items: list[Item] = []
    for it in resp.get("items", []):
        repo = ""
        ru = it.get("repository_url", "")
        if ru:
            repo = "/".join(ru.split("/")[-2:])
        created = it.get("created_at")
        reactions = (it.get("reactions") or {}).get("total_count", 0)
        items.append(
            Item(
                source="github",
                lang="en",
                title=it.get("title", ""),
                url=it.get("html_url", ""),
                author=(it.get("user") or {}).get("login"),
                container=repo,
                date=created[:10] if created else None,
                ts=None,
                engagement={"comments": to_int(it.get("comments")), "reactions": to_int(reactions)},
                snippet=strip_html((it.get("body") or "")[:240]),
                relevance=0.6,
                item_id=f"gh{it.get('number', '')}",
                metadata={"state": it.get("state"), "is_pr": "pull_request" in it},
            )
        )
    return items


registry.register(registry.Source("github", "en", fetch, aliases=("gh",)))
