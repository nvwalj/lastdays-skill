"""Tests for the tier fallback runner (lib/tiers.py) and registry tier model."""

import pytest

from lib import registry, tiers
from lib.dates import Window
from lib.schema import Item


def _item(title="t"):
    return Item(source="x", lang="en", title=title, url="https://e.com/" + title)


def _src(*tier_specs):
    return registry.Source(
        "x", "en", tiers=tuple(registry.Tier(fn, q, deg, lbl) for fn, q, deg, lbl in tier_specs)
    )


def _w():
    from datetime import datetime, timezone

    return Window(days=7, now=datetime(2026, 6, 2, tzinfo=timezone.utc))


def test_single_fetch_source_becomes_one_tier():
    src = registry.Source("x", "en", fetch=lambda q, w, *, env, depth="default": [_item()])
    ts = src.ordered_tiers()
    assert len(ts) == 1 and ts[0].label == "default" and ts[0].degraded is False


def test_tiers_ordered_by_quality_desc():
    src = _src(
        (lambda *a, **k: [], 40, True, "low"),
        (lambda *a, **k: [], 100, False, "high"),
    )
    assert [t.label for t in src.ordered_tiers()] == ["high", "low"]


def test_high_quality_tier_wins_and_low_not_tried():
    calls = []
    src = _src(
        (lambda *a, **k: calls.append("high") or [_item("a")], 100, False, "high"),
        (lambda *a, **k: calls.append("low") or [_item("b")], 40, True, "low"),
    )
    items, used = tiers.run_tiers(src, "q", _w(), env={})
    assert used.label == "high" and calls == ["high"]   # low tier never ran
    assert items[0].metadata["tier"] == "high"
    assert not items[0].metadata.get("degraded")


def test_falls_through_empty_high_to_low():
    src = _src(
        (lambda *a, **k: [], 100, False, "high"),       # empty -> skip
        (lambda *a, **k: [_item("b")], 40, True, "low"),
    )
    items, used = tiers.run_tiers(src, "q", _w(), env={})
    assert used.label == "low"
    assert items[0].metadata["tier"] == "low"
    assert items[0].metadata["degraded"] is True        # degraded stamped


def test_tier_error_skips_to_next():
    def boom(*a, **k):
        raise RuntimeError("kaboom")

    src = _src(
        (boom, 100, False, "high"),
        (lambda *a, **k: [_item("b")], 40, True, "low"),
    )
    items, used = tiers.run_tiers(src, "q", _w(), env={})
    assert used.label == "low" and len(items) == 1      # high errored, low rescued


def test_all_empty_returns_none():
    src = _src(
        (lambda *a, **k: [], 100, False, "high"),
        (lambda *a, **k: [], 40, True, "low"),
    )
    items, used = tiers.run_tiers(src, "q", _w(), env={})
    assert items == [] and used is None


def test_all_error_raises_tiererror():
    def boom(*a, **k):
        raise RuntimeError("x")

    src = _src((boom, 100, False, "high"), (boom, 40, True, "low"))
    with pytest.raises(tiers.TierError):
        tiers.run_tiers(src, "q", _w(), env={})
