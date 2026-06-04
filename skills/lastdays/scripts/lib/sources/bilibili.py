"""Bilibili (B站) video search source for lastdays.

Keyless: fetches an anonymous buvid3 (spi endpoint) and the wbi keys (nav
endpoint), signs the request with B站's public `wbi` algorithm (plain md5), and
queries the desktop video search. Engagement = views / danmaku / favorites.
Results are window-filtered and engagement-ranked by the engine.

A logged-in cookie (env BILI_COOKIE) is optional and only helps if the anonymous
path hits 风控 (-412). The wbi algorithm is documented at
github.com/SocialSisterYi/bilibili-API-collect (docs/misc/sign/wbi.md).
"""

from __future__ import annotations

import datetime
import hashlib
import re
import time
import urllib.parse

from .. import http, registry
from ..dates import Window
from ..schema import Item
from .base import strip_html, to_int

SPI_URL = "https://api.bilibili.com/x/frontend/finger/spi"
NAV_URL = "https://api.bilibili.com/x/web-interface/nav"
SEARCH_URL = "https://api.bilibili.com/x/web-interface/search/type"
WBI_SEARCH_URL = "https://api.bilibili.com/x/web-interface/wbi/search/type"
REFERER = "https://www.bilibili.com/"

DEPTH = {"quick": 10, "default": 30, "deep": 50}

# Fixed permutation table for the wbi mixin key (public, stable).
MIXIN_KEY_ENC_TAB = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35,
    27, 43, 5, 49, 33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13,
    37, 48, 7, 16, 24, 55, 40, 61, 26, 17, 0, 1, 60, 51, 30, 4,
    22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11, 36, 20, 34, 44, 52,
]

_EM_RE = re.compile(r"</?em[^>]*>", re.IGNORECASE)
_CACHE: dict = {}  # process-level cache for buvid3 + wbi keys


def _mixin_key(orig: str) -> str:
    return "".join(orig[i] for i in MIXIN_KEY_ENC_TAB)[:32]


def _key_from_url(url: str) -> str:
    return url.rsplit("/", 1)[-1].split(".")[0] if url else ""


def _clean_title(t: str) -> str:
    # Drop B站's <em class="keyword"> highlight tags WITHOUT inserting spaces, so
    # CJK keywords stay contiguous (工具盘点, not 工具 盘点), then strip the rest.
    return strip_html(_EM_RE.sub("", t or ""))


def sign_wbi(params: dict, img_key: str, sub_key: str, wts: int | None = None) -> dict:
    """Add wts + w_rid (wbi signature) to params. wts injectable for tests."""
    mixin = _mixin_key(img_key + sub_key)
    out = dict(params)
    out["wts"] = str(wts if wts is not None else int(time.time()))
    # Drop !'()* from values, then sort by key and urlencode for the digest.
    cleaned = {k: "".join(c for c in str(v) if c not in "!'()*") for k, v in out.items()}
    query = urllib.parse.urlencode(sorted(cleaned.items()))
    out["w_rid"] = hashlib.md5((query + mixin).encode("utf-8")).hexdigest()
    return out


def _get_buvid3(env: dict) -> str:
    cookie = (env or {}).get("BILI_COOKIE")
    if cookie:
        return cookie if "=" in cookie else f"buvid3={cookie}"
    if "buvid3" not in _CACHE:
        r = http.get(SPI_URL, headers={"Referer": REFERER}, timeout=15, retries=2)
        _CACHE["buvid3"] = f"buvid3={(r.get('data') or {}).get('b_3', '')}"
    return _CACHE["buvid3"]


def _get_wbi_keys() -> tuple[str, str]:
    if "wbi" not in _CACHE:
        # nav returns code -101 when logged out, but data.wbi_img is present anyway.
        r = http.get(NAV_URL, headers={"Referer": REFERER}, timeout=15, retries=2)
        w = (r.get("data") or {}).get("wbi_img") or {}
        _CACHE["wbi"] = (_key_from_url(w.get("img_url", "")), _key_from_url(w.get("sub_url", "")))
    return _CACHE["wbi"]


def _parse(results: list) -> list[Item]:
    items: list[Item] = []
    for v in results or []:
        if v.get("type") != "video":
            continue
        title = _clean_title(v.get("title", ""))
        if not title:
            continue
        bvid = v.get("bvid", "")
        pub = v.get("pubdate")
        ts = float(pub) if pub else None
        date = (
            datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc).strftime("%Y-%m-%d")
            if ts
            else None
        )
        items.append(
            Item(
                source="bilibili",
                lang="zh",
                title=title,
                url=f"https://www.bilibili.com/video/{bvid}" if bvid else (v.get("arcurl") or ""),
                author=v.get("author"),
                date=date,
                ts=ts,
                engagement={
                    "views": to_int(v.get("play")),
                    "danmaku": to_int(v.get("video_review")),
                    "favorites": to_int(v.get("favorites")),
                },
                snippet=_clean_title(v.get("description", ""))[:240],
                relevance=0.6,
                item_id=f"bv{bvid}",
                metadata={"duration": v.get("duration")},
            )
        )
    return items


def _search(endpoint: str, query: str, depth: str, env: dict) -> list[Item]:
    """Shared search call against one endpoint. Raises on non-zero code so the
    tier runner can record the failure and fall through to the next tier."""
    cookie = _get_buvid3(env)
    img_key, sub_key = _get_wbi_keys()
    # Comprehensive (default) ordering returns results reliably; the engine then
    # window-filters and ranks by recency + engagement. (order=pubdate on the wbi
    # endpoint was observed to return an empty result set / risk-control voucher.)
    params = {
        "search_type": "video",
        "keyword": query,
        "page": "1",
        "page_size": str(DEPTH.get(depth, 30)),
        "web_location": "1430654",
    }
    signed = sign_wbi(params, img_key, sub_key)
    url = f"{endpoint}?{urllib.parse.urlencode(signed)}"
    resp = http.get(url, headers={"Referer": REFERER, "Cookie": cookie}, timeout=20, retries=2)
    code = resp.get("code")
    if code != 0:
        raise http.HTTPError(f"bilibili code {code}: {resp.get('message')}")
    return _parse((resp.get("data") or {}).get("result") or [])


def _from_search_type(query: str, window: Window, *, env: dict, depth: str = "default") -> list[Item]:
    """Tier 'search' (quality 100): the plain search/type endpoint - observed the
    most reliable anonymously (the wbi/ variant sometimes answers with an empty
    risk-control voucher instead of results)."""
    return _search(SEARCH_URL, query, depth, env)


def _from_wbi_search_type(query: str, window: Window, *, env: dict, depth: str = "default") -> list[Item]:
    """Tier 'wbi-search' (quality 60): the wbi/search/type variant as fallback.
    Same data shape and full engagement when it answers - NOT degraded, just a
    second route if the primary endpoint errors or comes back empty."""
    return _search(WBI_SEARCH_URL, query, depth, env)


registry.register(
    registry.Source(
        "bilibili",
        "zh",
        tiers=(
            registry.Tier(_from_search_type, quality=100, degraded=False, label="search"),
            registry.Tier(_from_wbi_search_type, quality=60, degraded=False, label="wbi-search"),
        ),
        requires_key=False,
        implemented=True,
        aliases=("bili", "b站"),
    )
)
