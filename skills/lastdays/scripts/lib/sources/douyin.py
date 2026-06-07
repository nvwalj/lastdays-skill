"""Douyin (抖音) hot-search source for lastdays.

Keyless: Douyin's content search needs an a_bogus signature, but the hot-search
billboard is public and unsigned. We read it as a "what's trending in Chinese
right now" signal - each entry is a hot topic with a real hot_value (engagement
proxy) and rank, not an individual video. Primary endpoint carries event_time
(unix), so entries can be window-filtered; the iesdouyin v2 fallback does not, so
its entries are stamped "today" (the board is a live snapshot).

Only entries whose topic word matches the query are kept, so this behaves like a
topic search over the trending board rather than dumping the whole top-50.
"""

from __future__ import annotations

import datetime

from .. import http, registry
from ..dates import Window
from ..schema import Item
from .base import is_on_topic, title_relevance, to_int

PRIMARY_URL = (
    "https://www.douyin.com/aweme/v1/web/hot/search/list/"
    "?device_platform=webapp&aid=6383&channel=channel_pc_web"
)
FALLBACK_URL = (
    "https://www.iesdouyin.com/web/api/v2/hotsearch/billboard/word/"
    "?device_platform=webapp&aid=6383"
)
REFERER = "https://www.douyin.com/"


def _relevance(query: str, word: str) -> float:
    """Topic match for a hot-search word (shared title_relevance helper)."""
    return title_relevance(query, word)


def _board(url: str, env: dict) -> list:
    r = http.get(url, headers={"Referer": REFERER}, timeout=15, retries=2)
    return r.get("word_list") or (r.get("data") or {}).get("word_list") or []


def _parse_board(word_list: list, query: str) -> list[Item]:
    today = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    items: list[Item] = []
    for i, row in enumerate(word_list):
        if not isinstance(row, dict):
            continue
        word = str(row.get("word") or row.get("sentence") or "").strip()
        if not word:
            continue
        if not is_on_topic(query, word):  # keep only entries on-topic for the query
            continue
        rel = _relevance(query, word)  # continuous score for ranking
        et = row.get("event_time")
        ts = float(et) if et else None
        date = (
            datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc).strftime("%Y-%m-%d")
            if ts
            else today  # v2 board has no timestamp; it's a live snapshot
        )
        sid = str(row.get("sentence_id") or "").strip()
        url = f"https://www.douyin.com/hot/{sid}" if sid else f"https://www.douyin.com/search/{word}"
        items.append(
            Item(
                source="douyin",
                lang="zh",
                title=word,
                url=url,
                date=date,
                ts=ts,
                engagement={"hot_value": to_int(row.get("hot_value")), "rank": to_int(row.get("position") or (i + 1))},
                snippet=str(row.get("word_cover", {}).get("desc", "") if isinstance(row.get("word_cover"), dict) else "")[:240],
                relevance=rel,
                item_id=f"dy{sid or i + 1}",
                metadata={"hot_search_rank": to_int(row.get("position") or (i + 1))},
            )
        )
    return items


def _from_aweme(query: str, window: Window, *, env: dict, depth: str = "default") -> list[Item]:
    """Tier 'aweme' (quality 100): rich board with event_time (real dates)."""
    return _parse_board(_board(PRIMARY_URL, env), query)


def _from_iesdouyin_v2(query: str, window: Window, *, env: dict, depth: str = "default") -> list[Item]:
    """Tier 'v2' (quality 40, degraded): board has NO timestamps - entries are
    stamped 'today' (live snapshot), so dates are synthesized, not observed."""
    return _parse_board(_board(FALLBACK_URL, env), query)


registry.register(
    registry.Source(
        "douyin",
        "zh",
        tiers=(
            registry.Tier(_from_aweme, quality=100, degraded=False, label="aweme"),
            registry.Tier(
                _from_iesdouyin_v2, quality=40, degraded=True, label="v2",
                note="board has no timestamps; dates synthesized as today",
            ),
        ),
        requires_key=False,
        implemented=True,
        aliases=("dy", "抖音"),
    )
)
