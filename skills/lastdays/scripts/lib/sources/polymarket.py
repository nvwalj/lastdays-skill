"""Polymarket via the Gamma public-search API (free, no key).

Each active event becomes one Item: title, top-market outcome odds, and monthly
volume as the engagement signal. Date is the event's updatedAt (prediction
markets are a "current odds" snapshot, so undated/active markets are expected).
"""

from __future__ import annotations

import json
from urllib.parse import urlencode

from .. import http, registry
from ..dates import Window
from ..schema import Item

GAMMA = "https://gamma-api.polymarket.com/public-search"
DEPTH = {"quick": 5, "default": 12, "deep": 20}


def _outcomes(market: dict) -> list[tuple]:
    out_raw = market.get("outcomes")
    pr_raw = market.get("outcomePrices")
    try:
        outs = json.loads(out_raw) if isinstance(out_raw, str) else (out_raw or [])
        prs = json.loads(pr_raw) if isinstance(pr_raw, str) else (pr_raw or [])
    except (json.JSONDecodeError, TypeError):
        return []
    res = []
    for i, p in enumerate(prs):
        try:
            pf = float(p)
        except (TypeError, ValueError):
            continue
        name = outs[i] if i < len(outs) else f"Outcome {i + 1}"
        res.append((name, pf))
    return res


def fetch(query: str, window: Window, *, env: dict, depth: str = "default") -> list[Item]:
    cap = DEPTH.get(depth, 12)
    params = {"q": query, "events_status": "active", "keep_closed_markets": "0"}
    try:
        resp = http.get(f"{GAMMA}?{urlencode(params)}", timeout=15, retries=2)
    except http.HTTPError:
        return []
    items: list[Item] = []
    for ev in resp.get("events", []):
        if ev.get("closed"):
            continue
        markets = ev.get("markets") or []
        if not markets:
            continue
        outs = _outcomes(markets[0])[:3]
        updated = ev.get("updatedAt", "")
        try:
            vol = float(ev.get("volume1mo") or ev.get("volume") or 0)
        except (TypeError, ValueError):
            vol = 0.0
        slug = ev.get("slug", "")
        items.append(
            Item(
                source="polymarket",
                lang="en",
                title=ev.get("title", ""),
                url=f"https://polymarket.com/event/{slug}" if slug else "https://polymarket.com",
                date=updated[:10] if updated else None,
                ts=None,
                engagement={"volume": round(vol)},
                snippet=", ".join(f"{n} {round(p * 100)}%" for n, p in outs),
                relevance=0.55,
                item_id=f"pm{ev.get('id', '')}",
                metadata={"outcomes": outs},
            )
        )
        if len(items) >= cap:
            break
    return items


registry.register(registry.Source("polymarket", "en", fetch, aliases=("pm", "market")))
