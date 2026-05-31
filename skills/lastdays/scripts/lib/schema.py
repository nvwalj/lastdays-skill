"""Canonical data model (stdlib-only).

One generic `Item` per result, plus a `Report` wrapping per-source lists. The
agent does synthesis, so we deliberately avoid the upstream fusion/cluster graph
- a single `Item` with a free-form `engagement` dict is all the engine needs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


def _clean(d: dict) -> dict:
    """Drop None / empty values so JSON output stays compact."""
    return {k: v for k, v in d.items() if v not in (None, "", [], {})}


@dataclass
class Item:
    source: str                       # "reddit" | "hackernews" | "github" | "polymarket" | ...
    lang: str                         # "en" | "zh"
    title: str
    url: str
    author: Optional[str] = None
    container: Optional[str] = None   # subreddit / repo / event slug
    date: Optional[str] = None        # YYYY-MM-DD
    ts: Optional[float] = None        # unix seconds
    engagement: dict = field(default_factory=dict)  # {"score","comments","points","stars","volume","likes"}
    snippet: str = ""
    relevance: float = 0.5            # 0..1, source-provided hint
    score: float = 0.0                # 0..100, computed by score.py
    item_id: str = ""
    metadata: dict = field(default_factory=dict)

    def engagement_total(self) -> float:
        """Single headline engagement number for cross-source normalization."""
        e = self.engagement or {}
        for key in ("score", "points", "likes", "volume", "comments", "stars"):
            if e.get(key):
                try:
                    return float(e[key])
                except (TypeError, ValueError):
                    continue
        return 0.0

    def to_dict(self) -> dict:
        return _clean(
            {
                "source": self.source,
                "lang": self.lang,
                "title": self.title,
                "url": self.url,
                "author": self.author,
                "container": self.container,
                "date": self.date,
                "engagement": {k: v for k, v in (self.engagement or {}).items() if v},
                "snippet": self.snippet,
                "relevance": round(self.relevance, 3),
                "score": round(self.score, 1),
                "item_id": self.item_id,
                "metadata": self.metadata or {},
            }
        )


@dataclass
class Report:
    topic: str
    days: int
    from_date: str
    to_date: str
    generated_at: str
    items_by_source: dict[str, list[Item]] = field(default_factory=dict)
    errors_by_source: dict[str, str] = field(default_factory=dict)
    web_layers_requested: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def all_items(self) -> list[Item]:
        out: list[Item] = []
        for items in self.items_by_source.values():
            out.extend(items)
        return out

    def to_dict(self) -> dict[str, Any]:
        return {
            "topic": self.topic,
            "window": {"days": self.days, "from": self.from_date, "to": self.to_date},
            "generated_at": self.generated_at,
            "counts": {s: len(i) for s, i in self.items_by_source.items()},
            "items_by_source": {
                s: [i.to_dict() for i in items] for s, items in self.items_by_source.items()
            },
            "errors_by_source": self.errors_by_source,
            "web_layers_requested": self.web_layers_requested,
            "warnings": self.warnings,
        }
