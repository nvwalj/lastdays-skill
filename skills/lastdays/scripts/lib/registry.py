"""Source registry - the extension point for adding (Chinese) media sources.

A source is any module exposing:

    fetch(query: str, window: Window, *, env: dict, depth: str = "default") -> list[Item]

and registering itself at import time:

    from .. import registry
    registry.register(registry.Source("weibo", "zh", fetch, requires_key=True))

A source may instead declare multiple `tiers` (ordered fallback strategies, e.g.
Reddit's `.json` then `.rss`). The tier runner (lib/tiers.py) tries them by
quality, highest first, and uses the first that returns results - mirroring
firecrawl's engine fallback list. A degraded tier (no engagement signal) is
flagged so scoring/rendering stay honest.

Adding a new source = one module + one register() call + one import line in
sources/__init__.py. The engine orchestration never changes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

# Sources the Python engine actually executes itself (zero-key, real engagement).
# Everything else (web, x, and the zh stubs) is routed to the agent's WebSearch.
ENGINE_SOURCES = frozenset({"reddit", "hackernews", "github", "polymarket", "bilibili", "douyin"})


@dataclass(frozen=True)
class Tier:
    """One fallback strategy for a source.

    fetch: same contract as a source fetch -> fetch(query, window, *, env, depth).
    quality: higher is tried first; negatives are last-resort tiers (firecrawl
             convention). degraded tiers should sit below their richer siblings.
    degraded: True when this tier cannot return a full signal (e.g. no
              engagement). Surfaced on each item's metadata so scoring/rendering
              treat it honestly and never fake numbers.
    label: short id (e.g. "json"/"rss") recorded in item metadata for diagnosis.
    """

    fetch: Callable
    quality: int = 100
    degraded: bool = False
    label: str = "default"


@dataclass(frozen=True)
class Source:
    name: str
    lang: str                                   # "en" | "zh"
    fetch: Optional[Callable] = None            # single-strategy source (back-compat)
    tiers: tuple = field(default_factory=tuple) # multi-tier source; overrides fetch
    requires_key: bool = False                  # needs cookies/token not yet wired
    implemented: bool = True                    # False for stub placeholders
    aliases: tuple = field(default_factory=tuple)

    def ordered_tiers(self) -> list:
        """Tiers highest-quality first. A single-fetch source becomes one tier."""
        if self.tiers:
            return sorted(self.tiers, key=lambda t: t.quality, reverse=True)
        return [Tier(fetch=self.fetch, quality=100, degraded=False, label="default")]


_REGISTRY: dict[str, Source] = {}
_ALIASES: dict[str, str] = {}


def register(src: Source) -> None:
    _REGISTRY[src.name] = src
    for alias in src.aliases:
        _ALIASES[alias] = src.name


def get(name: str) -> Optional[Source]:
    key = name.strip().lower()
    key = _ALIASES.get(key, key)
    return _REGISTRY.get(key)


def all_sources() -> list[Source]:
    return list(_REGISTRY.values())


def by_lang(lang: Optional[str]) -> list[Source]:
    """Sources for a language. lang=None or 'both' returns everything."""
    if not lang or lang == "both":
        return all_sources()
    return [s for s in _REGISTRY.values() if s.lang == lang]


def resolve_names(raw: Optional[str], lang: str) -> list[str]:
    """Resolve the requested source list.

    raw is a CSV from --sources (alias-normalized + validated). When raw is None,
    default to the language group's registered sources.
    """
    if raw:
        names: list[str] = []
        for tok in raw.split(","):
            tok = tok.strip().lower()
            if not tok:
                continue
            src = get(tok)
            if src is None:
                raise ValueError(f"unknown source: {tok!r}")
            if src.name not in names:
                names.append(src.name)
        return names
    return [s.name for s in by_lang(lang)]
