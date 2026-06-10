"""Kalshi via its public search API (free, no key, no login).

The CFTC-regulated US prediction market — the regulated counterpart to the
Polymarket source, so the two exchanges' odds can cross-check each other on the
same event. Each open event becomes one Item: event title, the top-volume
markets' odds in the snippet (Kalshi prices are cents, i.e. probability %), and
contract volume as the engagement signal.

Dating: the search response carries no per-event "updated" timestamp (the trade
API's `updated_time` is a config-edit time that sits stale on actively-traded
markets, and `open_ts` can be months old — both would wrongly drop live markets
from short windows). An open market's odds ARE a live quote at fetch time, so
items are dated `window.to_date` — the same "current odds snapshot" semantics
the Polymarket source gets from its always-fresh `updatedAt`. This equals fetch
day because engine windows always end at now; a hypothetical past-ending window
would mis-stamp live odds. The item metadata records the basis so rendering/
synthesis stay honest about what the date means.

The web frontend has no per-event slug in this API; `kalshi.com/markets/<series
ticker>` resolves through Kalshi's router.
"""

from __future__ import annotations

from urllib.parse import urlencode

from .. import http, registry
from ..dates import Window
from ..schema import Item
from .base import is_on_topic, title_relevance

SEARCH = "https://api.elections.kalshi.com/v1/search/series"
# Single page only (50 rows; next_cursor unused): with the hard gate below, a
# deep query whose page 1 is mostly padding can return fewer than the cap —
# accepted recall ceiling in exchange for exactly one request per run.
DEPTH = {"quick": 5, "default": 12, "deep": 20}
# Kalshi's search pads thin result sets with trending sports/esports rows
# (measured: "Rust async runtime" returned CS2 and MLB markets), so unlike the
# Polymarket source this one HARD-gates each event with is_on_topic over the
# event's full searchable text — title, series title, tags, topic keywords, and
# market subtitles (a ladder like "Which companies IPO this year?" carries
# "SpaceX" only in its market subtitles). The floor below is then only for
# gate-passing events whose TITLE alone doesn't match (e.g. matched via a tag):
# present, ranked by volume, but below events whose title matches outright.
NO_MATCH_FLOOR = 0.3


def _vol(x) -> float:
    try:
        return max(0.0, float(x or 0))
    except (TypeError, ValueError):
        return 0.0


def _open_markets(ev: dict) -> list[dict]:
    """Unsettled markets of one event, highest contract volume first."""
    out = [
        m
        for m in (ev.get("markets") or [])
        if isinstance(m, dict) and not m.get("result")
    ]
    out.sort(key=lambda m: _vol(m.get("volume")), reverse=True)
    return out


def _odds(market: dict) -> tuple[str, int]:
    """(outcome name, price in cents == implied %). last trade, else best bid."""
    name = market.get("yes_subtitle") or market.get("title") or market.get("ticker") or "Yes"
    price = market.get("last_price") or market.get("yes_bid") or 0
    try:
        cents = int(round(float(price)))
    except (TypeError, ValueError):
        cents = 0
    return str(name), cents


def fetch(query: str, window: Window, *, env: dict, depth: str = "default") -> list[Item]:
    cap = DEPTH.get(depth, 12)
    try:
        resp = http.get(f"{SEARCH}?{urlencode({'query': query})}", timeout=15, retries=2)
    except http.HTTPError:
        return []
    if not isinstance(resp, dict):
        return []
    items: list[Item] = []
    for ev in resp.get("current_page") or []:
        if not isinstance(ev, dict):
            continue
        # Search mixes result types; only "contract" rows carry an event+markets.
        if ev.get("type") not in (None, "contract"):
            continue
        # 0 means Kalshi says every market is closed; absent/None stays in (the
        # settled-market filter below still applies).
        if ev.get("active_market_count") == 0:
            continue
        markets = _open_markets(ev)
        if not markets:
            continue
        title = ev.get("event_title") or ev.get("series_title") or ""
        if not title:
            continue
        gate_text = " ".join(
            str(part)
            for part in (
                title,
                ev.get("series_title") or "",
                *(ev.get("tags") or []),
                *(ev.get("topic_keywords") or []),
                *(m.get("yes_subtitle") or "" for m in markets),
            )
            if part
        )
        if not is_on_topic(query, gate_text):
            continue
        series = ev.get("series_ticker") or ev.get("event_ticker") or ""
        vol = _vol(ev.get("total_volume"))
        if not vol:
            vol = sum(_vol(m.get("volume")) for m in markets)
        outs = [_odds(m) for m in markets[:3]]
        items.append(
            Item(
                source="kalshi",
                lang="en",
                title=title,
                url=f"https://kalshi.com/markets/{series}" if series else "https://kalshi.com",
                date=window.to_date,  # live-odds snapshot; see module docstring
                ts=None,
                engagement={"volume": round(vol)},
                snippet=", ".join(f"{n} {p}%" for n, p in outs),
                relevance=max(NO_MATCH_FLOOR, title_relevance(query, title)),
                item_id=f"ks{ev.get('event_ticker') or series}",
                metadata={"outcomes": outs, "date_basis": "live-odds snapshot at fetch time"},
            )
        )
        if len(items) >= cap:
            break
    return items


registry.register(registry.Source("kalshi", "en", fetch, aliases=("ks",)))
