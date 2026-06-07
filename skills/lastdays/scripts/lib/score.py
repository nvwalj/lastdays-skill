"""Cross-source ranking.

Engagement is normalized WITHIN each source to 0..1 first (an upvote and a
GitHub star are not the same unit), then blended with relevance and recency into
a shared 0..100 score so the merged ranking is fair.
"""

from __future__ import annotations

import math

from .dates import Window
from .schema import Item

WEIGHTS = {"relevance": 0.45, "recency": 0.25, "engagement": 0.30}
UNKNOWN_ENGAGEMENT_PENALTY = 10.0


def _log(x) -> float:
    try:
        return math.log1p(max(0.0, float(x or 0)))
    except (TypeError, ValueError):
        return 0.0


def engagement_raw(source: str, eng: dict) -> float | None:
    """Per-source raw engagement signal (pre-normalization). None if unknown."""
    if not eng:
        return None
    if source == "reddit":
        return 0.55 * _log(eng.get("score")) + 0.40 * _log(eng.get("comments")) + 0.05 * (
            float(eng.get("upvote_ratio") or 0) * 10
        )
    if source == "hackernews":
        return 0.60 * _log(eng.get("points")) + 0.40 * _log(eng.get("comments"))
    if source == "lobsters":
        return 0.60 * _log(eng.get("score")) + 0.40 * _log(eng.get("comments"))
    if source == "github":
        return 0.60 * _log(eng.get("comments")) + 0.40 * _log(eng.get("reactions"))
    if source == "polymarket":
        return _log(eng.get("volume"))
    if source == "bilibili":
        return 0.5 * _log(eng.get("views")) + 0.3 * _log(eng.get("danmaku")) + 0.2 * _log(eng.get("favorites"))
    if source == "douyin":
        return _log(eng.get("hot_value"))
    total = sum(float(v or 0) for v in eng.values() if isinstance(v, (int, float)))
    return _log(total) if total else None


def score_items(items: list[Item], window: Window) -> None:
    """Compute item.score in place (0..100)."""
    by_src: dict[str, list[Item]] = {}
    for it in items:
        by_src.setdefault(it.source, []).append(it)

    for src, group in by_src.items():
        raws = [engagement_raw(src, it.engagement) for it in group]
        present = [r for r in raws if r is not None]
        lo = min(present) if present else 0.0
        hi = max(present) if present else 0.0
        span = (hi - lo) or 1.0
        for it, r in zip(group, raws):
            eng_norm = 0.0 if r is None else (r - lo) / span
            rec = window.recency(it.ts if it.ts is not None else it.date)
            base = 100.0 * (
                WEIGHTS["relevance"] * max(0.0, min(1.0, it.relevance))
                + WEIGHTS["recency"] * rec
                + WEIGHTS["engagement"] * eng_norm
            )
            if r is None:
                base -= UNKNOWN_ENGAGEMENT_PENALTY
            it.score = max(0.0, min(100.0, base))


def rank(items: list[Item]) -> list[Item]:
    return sorted(
        items,
        key=lambda it: (it.score, it.date or "", it.engagement_total()),
        reverse=True,
    )
