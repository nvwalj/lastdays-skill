"""Tier fallback runner.

Tries a source's tiers from highest quality to lowest and uses the first that
returns results - the firecrawl engine-fallback pattern, scoped to our keyless
sources. Each returned item is stamped with the tier that produced it
(metadata.tier) and whether that tier is degraded (metadata.degraded), so
scoring and rendering can stay honest about thin evidence.

A tier that raises is recorded and skipped; the next tier still runs (one tier
failing must never sink the source). Returns ([], None) only if every tier
errors or comes back empty.
"""

from __future__ import annotations

from .dates import Window
from .registry import Source, Tier


def run_tiers(source: Source, query: str, window: Window, *, env: dict, depth: str = "default"):
    """Run a source's tiers in quality order. Returns (items, used_tier_or_None)."""
    errors: list[str] = []
    for tier in source.ordered_tiers():
        try:
            items = tier.fetch(query, window, env=env, depth=depth) or []
        except Exception as e:  # noqa: BLE001  isolate a tier failure, try the next
            errors.append(f"{tier.label}: {type(e).__name__}: {e}")
            continue
        if items:
            _stamp(items, tier)
            return items, tier
    # Nothing produced results. Surface tier errors (if any) so the caller can log.
    if errors:
        raise TierError("; ".join(errors))
    return [], None


def _stamp(items: list, tier: Tier) -> None:
    for it in items:
        # Don't clobber a label a source set deliberately; record tier provenance.
        it.metadata.setdefault("tier", tier.label)
        if tier.degraded:
            it.metadata["degraded"] = True


class TierError(Exception):
    """All tiers errored (none returned results). Carries the joined messages."""
