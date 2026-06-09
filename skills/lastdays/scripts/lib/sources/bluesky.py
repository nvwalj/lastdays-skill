"""Bluesky (AT Protocol) post search via the public AppView (keyless).

app.bsky.feed.searchPosts returns real engagement (likes, reposts, replies),
a timestamp, and server-side `since` date filtering -- no key. Bluesky is the
engine's structured-engagement answer to the X/Twitter layer (which is otherwise
an engagement-less WebSearch layer): an open, API-accessible social feed whose
tech/policy communities actively discuss scraping & data topics.

Two hosts via the tier framework: the documented public AppView
(public.api.bsky.app) first, then api.bsky.app as fallback -- the public host
403s from some datacenter IPs (same class as Reddit's .json), so the second tier
keeps the source alive there. Both carry full engagement (neither degraded).
"""

from __future__ import annotations

from urllib.parse import urlencode

from .. import dates, http, registry
from ..dates import Window
from ..schema import Item
from .base import is_on_topic, title_relevance, to_int

PUBLIC_HOST = "public.api.bsky.app"
APPVIEW_HOST = "api.bsky.app"
PATH = "/xrpc/app.bsky.feed.searchPosts"
DEPTH = {"quick": 15, "default": 25, "deep": 50}
NO_MATCH_FLOOR = 0.3


def _web_url(handle: str, uri: str) -> str:
    rkey = uri.rsplit("/", 1)[-1] if uri else ""
    if handle and rkey:
        return f"https://bsky.app/profile/{handle}/post/{rkey}"
    return uri or ""


def _ident(uri: str) -> str:
    """Globally-unique id from an AT URI (at://<did>/app.bsky.feed.post/<rkey>).
    rkey alone is only per-repo; pair it with the FULL did (keep the method, so a
    path-style did:web:host:x can't collapse onto a did:plc:x with the same rkey)."""
    rkey = uri.rsplit("/", 1)[-1]
    parts = uri.split("/")
    did = parts[2] if uri.startswith("at://") and len(parts) > 2 else ""
    return f"{did}_{rkey}" if did else rkey


def _parse(posts: list, query: str) -> list[Item]:
    items: list[Item] = []
    seen: set = set()
    for p in posts or []:
        if not isinstance(p, dict):
            continue
        uri = p.get("uri", "")
        if not isinstance(uri, str) or not uri or uri in seen:  # globally unique; guard non-str
            continue
        record = p.get("record")
        if not isinstance(record, dict):  # malformed entry -> skip (no AttributeError)
            continue
        # AT-Proto post text is PLAINTEXT, not HTML: just collapse whitespace.
        # strip_html would delete "<...>" spans (code, "a<b") and could flip the
        # on-topic gate or corrupt the title.
        text = " ".join((record.get("text") or "").split())
        if not text:
            continue
        # Gate AND score on the FULL post (<=300 chars); only the title is
        # truncated, so query terms past char 200 still count.
        if not is_on_topic(query, text):
            continue
        seen.add(uri)
        author_obj = p.get("author")
        author = author_obj.get("handle") if isinstance(author_obj, dict) else None
        # indexedAt is the server-authoritative timestamp the API's `since`
        # filters on; record.createdAt is client-settable (spoofable), so prefer
        # indexedAt for the window filter + recency.
        dt = dates.to_datetime(p.get("indexedAt") or record.get("createdAt"))
        items.append(
            Item(
                source="bluesky",
                lang="en",
                title=text[:200],
                url=_web_url(author, uri),
                author=author,
                date=dt.strftime("%Y-%m-%d") if dt else None,
                ts=dt.timestamp() if dt else None,
                engagement={
                    "likes": to_int(p.get("likeCount")),
                    "reposts": to_int(p.get("repostCount")),
                    "replies": to_int(p.get("replyCount")),
                },
                snippet=text[:240],
                relevance=max(NO_MATCH_FLOOR, title_relevance(query, text)),
                item_id=f"bs{_ident(uri)}",
                metadata={"uri": uri, "cid": p.get("cid")},
            )
        )
    return items


def _search(host: str, query: str, window: Window, depth: str) -> list[Item]:
    # Day-quantized `since` (start of the cutoff day) so the URL is stable within
    # a day and the HTTP cache can hit; the server filters the lower bound and the
    # engine's filter_window enforces the exact window afterward.
    since = f"{window.from_date}T00:00:00Z"
    params = {
        "q": query,
        "limit": str(DEPTH.get(depth, 25)),
        "sort": "top",
        "since": since,
    }
    resp = http.get(f"https://{host}{PATH}?{urlencode(params)}", timeout=20, retries=2)
    posts = resp.get("posts", []) if isinstance(resp, dict) else []
    return _parse(posts, query)


def _from_public(query: str, window: Window, *, env: dict, depth: str = "default") -> list[Item]:
    return _search(PUBLIC_HOST, query, window, depth)


def _from_appview(query: str, window: Window, *, env: dict, depth: str = "default") -> list[Item]:
    return _search(APPVIEW_HOST, query, window, depth)


registry.register(
    registry.Source(
        "bluesky",
        "en",
        tiers=(
            registry.Tier(_from_public, quality=100, degraded=False, label="public"),
            registry.Tier(_from_appview, quality=80, degraded=False, label="appview"),
        ),
        aliases=("bsky",),
    )
)
