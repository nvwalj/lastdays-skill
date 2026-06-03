"""Tier fallback runner.

Tries a source's tiers from highest quality to lowest and uses the first that
returns results - the firecrawl engine-fallback pattern, scoped to our keyless
sources. Each returned item is stamped with the tier that produced it
(metadata.tier) and whether that tier is degraded (metadata.degraded), so
scoring and rendering can stay honest about thin evidence.

A tier that raises is recorded and skipped; the next tier still runs (one tier
failing must never sink the source). Returns ([], None) when tiers completed but
none had results (graceful "no hits"); raises TierError only when EVERY tier
errored (a real outage, none completed).
"""

from __future__ import annotations

from .dates import Window
from .registry import Source, Tier


def run_tiers(source: Source, query: str, window: Window, *, env: dict, depth: str = "default"):
    """Run a source's tiers in quality order. Returns (items, used_tier_or_None).

    A tier that errors is isolated and the next is tried. A tier that completes
    but returns nothing (e.g. RSS reachable but all results relevance-filtered)
    counts as a successful empty result - the source simply has no hits, NOT a
    failure. TierError is raised ONLY when every tier errored (none completed),
    so a real outage is still surfaced while normal "no results" degrades to
    ([], None) just like a single-fetch source would.
    """
    errors: list[str] = []
    any_completed = False
    for tier in source.ordered_tiers():
        try:
            items = tier.fetch(query, window, env=env, depth=depth) or []
        except Exception as e:  # noqa: BLE001  isolate a tier failure, try the next
            errors.append(f"{tier.label}: {type(e).__name__}: {e}")
            continue
        any_completed = True
        if items:
            _stamp(items, tier)
            return items, tier
    # Every tier errored (none completed) -> surface the outage. Otherwise some
    # tier ran fine and just had no hits -> graceful empty, like any other source.
    if errors and not any_completed:
        raise TierError(f"{source.name}: " + "; ".join(errors))
    return [], None


def _stamp(items: list, tier: Tier) -> None:
    for it in items:
        # Don't clobber a label a source set deliberately; record tier provenance.
        it.metadata.setdefault("tier", tier.label)
        if tier.degraded:
            it.metadata["degraded"] = True


class TierError(Exception):
    """All tiers errored (none returned results). Carries the joined messages."""
