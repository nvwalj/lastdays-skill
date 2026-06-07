"""Polymarket relevance: was flat 0.55 (HN's old bug, never propagated here).
Now scored by title match with a floor so loosely-related markets sink."""

from datetime import datetime, timezone

from lib.dates import Window
from lib.sources import polymarket
from lib.sources.polymarket import NO_MATCH_FLOOR


def _resp(*titles):
    return {"events": [
        {"id": str(i), "title": t, "slug": f"s{i}", "active": True,
         "updatedAt": "2026-06-07", "volume1mo": 1000,
         "markets": [{"outcomes": '["Yes","No"]', "outcomePrices": '["0.5","0.5"]'}]}
        for i, t in enumerate(titles)
    ]}


def _fetch(query, resp, monkeypatch):
    monkeypatch.setattr(polymarket.http, "get", lambda *a, **k: resp)
    w = Window(days=30, now=datetime(2026, 6, 7, tzinfo=timezone.utc))
    return polymarket.fetch(query, w, env={})


def test_matching_market_scores_above_floor(monkeypatch):
    items = _fetch("Tesla robotaxi", _resp("Will Tesla launch robotaxi by June?"), monkeypatch)
    assert items[0].relevance > NO_MATCH_FLOOR        # real match scores high


def test_unrelated_market_gets_floor(monkeypatch):
    # A market sharing NO query word -> floor (not the old flat 0.55).
    items = _fetch("AI regulation", _resp("Will the Lakers win the title?"), monkeypatch)
    assert items[0].relevance == NO_MATCH_FLOOR


def test_partial_match_between_floor_and_full(monkeypatch):
    # "AI regulation" but title only has "AI" -> partial (weak), above floor,
    # below a full match. This is the intended round-2 curve, not noise=floor.
    items = _fetch("AI regulation", _resp("Which company has best AI model?"), monkeypatch)
    assert NO_MATCH_FLOOR < items[0].relevance < 0.9


def test_relevance_varies_not_flat(monkeypatch):
    items = _fetch("Tesla deliveries",
                   _resp("Tesla deliveries in Q2?", "Random unrelated market"), monkeypatch)
    rels = {round(it.relevance, 2) for it in items}
    assert len(rels) > 1                              # no longer a single flat value
