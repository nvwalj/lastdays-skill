"""Xiaohongshu / RED (小红书) via a LOCAL xiaohongshu-mcp bridge (optional).

Zero-key keyword search of XHS is not possible (verified 2026-06: the
`search/notes` API hard-gates on a logged-in `web_session` cookie with code
-104; the X-s signing scheme rotates ~monthly; RSSHub has no search route and
no working public instance; free anonymous aggregators don't exist). The
pragmatic path — already proven by two last30days CN forks — is
github.com/xpzouying/xiaohongshu-mcp: the user installs the binary, scans a
login QR once, and it exposes a plain REST API on localhost (default :18060)
backed by a logged-in headless browser.

This source self-activates: when the bridge answers `GET /api/v1/login/status`
with is_logged_in=true (see `probe`), the orchestrator promotes xiaohongshu to
an engine source; otherwise it stays in the agent's WebSearch layer exactly as
before. No bridge, no behavior change.

Dates: bridge SEARCH results carry no timestamp — only the per-note DETAIL
call returns `note.time` (epoch ms). Each bridge call spawns a headless
Chromium server-side (~5-15s), so this source ranks search hits by likes and
details only the top few, with `LASTDAYS_XHS_BUDGET` seconds (default 25)
capping the WHOLE source — search and detail calls' timeouts are all clamped
to the time remaining. Notes whose real timestamp came back are emitted with
real UTC dates; an un-detailed note is dropped, never guessed — strict-window
honesty over volume.

Filter gotcha (upstream filterOptionsMap): publish_time accepts only
不限/一天内/一周内/半年内 — there is NO 一个月内 (a known CN-fork bug was
sending it). Windows over 7 days use 半年内 + the engine's own window filter.
"""

from __future__ import annotations

import datetime
import json
import re
import time

from .. import http, registry
from ..dates import Window
from ..schema import Item
from .base import is_on_topic, strip_html, title_relevance

BASE_ENV = "XIAOHONGSHU_API_BASE"  # same env name the CN forks use
DEFAULT_BASE = "http://localhost:18060"
BUDGET_ENV = "LASTDAYS_XHS_BUDGET"
DETAIL_BUDGET_S = 25.0
# Each item costs a detail call (a fresh server-side browser), so caps are far
# tighter than API-only sources.
DEPTH = {"quick": 3, "default": 5, "deep": 8}
NO_MATCH_FLOOR = 0.3

# Trailing "+" covers XHS's truncated counts ("10万+", "1000+").
_ZH_NUM_RE = re.compile(r"^([\d.]+)\s*(万|亿)?\s*\+?$")


def _base(env: dict) -> str:
    return str(env.get(BASE_ENV) or DEFAULT_BASE).rstrip("/")


def _budget(env: dict) -> float:
    try:
        return float(env.get(BUDGET_ENV) or DETAIL_BUDGET_S)
    except (TypeError, ValueError):
        return DETAIL_BUDGET_S


def probe(env: dict) -> bool:
    """True only when the local bridge is up AND holds a logged-in session.

    raw=True bypasses the day-TTL GET cache — bridge state changes within a day
    (user starts it, session expires) and a cached probe would lie about it.
    """
    try:
        text = http.request(
            "GET", f"{_base(env)}/api/v1/login/status", raw=True, timeout=3, retries=1
        )
        data = json.loads(text)
    except Exception:  # noqa: BLE001  unreachable/non-JSON/refused -> just not available
        return False
    if not isinstance(data, dict):
        return False
    inner = data.get("data")
    # isinstance guard, not `or {}`: a drifted API returning data="ok" must
    # read as "not available", not raise AttributeError mid-promotion.
    return isinstance(inner, dict) and bool(inner.get("is_logged_in"))


def _zh_count(v) -> int:
    """'1.2万' -> 12000, '3亿' -> 300000000, '156' -> 156, junk/None -> 0."""
    if isinstance(v, (int, float)):
        return max(0, int(v))
    m = _ZH_NUM_RE.match(str(v or "").strip())
    if not m:
        return 0
    try:
        n = float(m.group(1))
    except ValueError:
        return 0
    return int(n * {"万": 10_000, "亿": 100_000_000}.get(m.group(2) or "", 1))


def _publish_time(days: int) -> str:
    if days <= 1:
        return "一天内"
    if days <= 7:
        return "一周内"
    return "半年内"  # no 一个月内 upstream; engine's filter_window narrows the rest


def fetch(query: str, window: Window, *, env: dict, depth: str = "default") -> list[Item]:
    base = _base(env)
    cap = DEPTH.get(depth, 5)
    # The budget caps the WHOLE source — search AND detail calls — so a slow
    # bridge can never hold the engine far past LASTDAYS_XHS_BUDGET seconds:
    # the clock starts before search, and every call's timeout is clamped to
    # the time remaining.
    budget = _budget(env)
    start = time.monotonic()
    try:
        resp = http.post(
            f"{base}/api/v1/feeds/search",
            {
                "keyword": query,
                # ≤7d: the platform's publish_time filter already guarantees
                # in-window results, so relevance sort (综合) is safe. Beyond
                # 7d the coarsest filter is 半年内 (no 一个月内 upstream) and
                # dates are unknown until the detail call — sort by 最新 so the
                # scarce detail slots land on notes likely inside the window
                # instead of popular-but-months-old ones.
                "filters": {
                    "sort_by": "综合" if window.days <= 7 else "最新",
                    "publish_time": _publish_time(window.days),
                },
            },
            timeout=max(2, min(30, int(budget))),
            retries=1,
        )
    except http.HTTPError:
        return []
    feeds = ((resp or {}).get("data") or {}).get("feeds") or []
    if not isinstance(feeds, list):
        return []

    # Rank candidates by likes, then spend the detail budget on the top ones.
    cands = []
    for f in feeds:
        if not isinstance(f, dict):
            continue
        fid = f.get("id")
        card = f.get("noteCard") or {}
        title = strip_html(str(card.get("displayTitle") or ""))
        if not fid or not title:
            continue
        if not is_on_topic(query, title):
            continue
        info = card.get("interactInfo") or {}
        cands.append((_zh_count(info.get("likedCount")), str(fid), f, card, info))
    cands.sort(key=lambda c: c[0], reverse=True)

    items: list[Item] = []
    for likes, fid, f, card, info in cands[: cap * 2]:
        remaining = budget - (time.monotonic() - start)
        if len(items) >= cap or remaining < 2:
            break
        try:
            d = http.post(
                f"{base}/api/v1/feeds/detail",
                {"feed_id": fid, "xsec_token": str(f.get("xsecToken") or "")},
                timeout=max(2, min(20, int(remaining))),
                retries=1,
            )
        except http.HTTPError:
            continue
        # Upstream envelope nests twice: {data: {data: {note: ...}}}.
        note = (((d or {}).get("data") or {}).get("data") or {}).get("note") or {}
        t_ms = note.get("time")
        try:
            ts = float(t_ms)
        except (TypeError, ValueError):
            continue  # no real timestamp -> drop, never guess
        # Upstream Go sends epoch MILLISECONDS; tolerate a seconds-emitting
        # bridge build (>1e11 can only be ms — that's year 5138 in seconds).
        if ts > 1e11:
            ts /= 1000.0
        if ts <= 0:
            continue
        date = datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc).strftime("%Y-%m-%d")
        title = strip_html(str(note.get("title") or card.get("displayTitle") or ""))
        items.append(
            Item(
                source="xiaohongshu",
                lang="zh",
                title=title,
                url=f"https://www.xiaohongshu.com/explore/{fid}",
                author=(card.get("user") or {}).get("nickname"),
                date=date,
                ts=ts,
                engagement={
                    "likes": likes,
                    "comments": _zh_count(info.get("commentCount")),
                    "collects": _zh_count(info.get("collectedCount")),
                },
                snippet=strip_html(str(note.get("desc") or ""))[:240],
                relevance=max(NO_MATCH_FLOOR, title_relevance(query, title)),
                item_id=f"xhs{fid}",
                metadata={"bridge": "xiaohongshu-mcp"},
            )
        )
    return items


registry.register(
    registry.Source(
        "xiaohongshu",
        "zh",
        fetch,
        requires_key=True,  # needs the local logged-in bridge, not a baked-in key
        implemented=True,
        aliases=("xhs", "rednote", "小红书"),
        bridge_probe=probe,
    )
)
