"""Kalshi source: search parsing, settled-market filter, snapshot dating, odds snippet."""

from datetime import datetime, timezone

from lib.dates import Window
from lib.sources import kalshi
from lib.sources.kalshi import NO_MATCH_FLOOR


def _market(subtitle="Yes", last_price=50, yes_bid=45, volume=1000, result=""):
    return {
        "ticker": "KX-1",
        "yes_subtitle": subtitle,
        "last_price": last_price,
        "yes_bid": yes_bid,
        "volume": volume,
        "result": result,
    }


def _event(title, markets=None, **kw):
    ev = {
        "type": "contract",
        "event_ticker": "KXTEST",
        "series_ticker": "KXTEST",
        "event_title": title,
        "total_volume": 5000,
        "active_market_count": 1,
        "markets": markets if markets is not None else [_market()],
    }
    ev.update(kw)
    return ev


def _fetch(query, resp, monkeypatch, depth="default"):
    monkeypatch.setattr(kalshi.http, "get", lambda *a, **k: resp)
    w = Window(days=30, now=datetime(2026, 6, 9, tzinfo=timezone.utc))
    return kalshi.fetch(query, w, env={}, depth=depth)


def _page(*events):
    return {"current_page": list(events)}


def test_matching_event_scores_above_floor(monkeypatch):
    items = _fetch("SpaceX IPO", _page(_event("When will SpaceX officially announce an IPO?")), monkeypatch)
    assert len(items) == 1 and items[0].relevance > NO_MATCH_FLOOR


def test_unrelated_event_dropped(monkeypatch):
    # Kalshi search pads with trending sports rows -> hard-gated out entirely.
    resp = _page(
        _event("Will the Lakers win the title?", tags=["NBA"], topic_keywords=["Basketball"]),
        _event("brazylijski luz vs. SPARTA", tags=["Esports"], topic_keywords=["Counter-Strike 2"]),
    )
    assert _fetch("AI regulation", resp, monkeypatch) == []


def test_gate_passes_via_tags_title_floor(monkeypatch):
    # Title has no query token, but a tag carries it -> kept, at the title floor.
    ev = _event("Will the FOMC cut in June?", tags=["Fed"], topic_keywords=[])
    items = _fetch("Fed", _page(ev), monkeypatch)
    assert len(items) == 1 and items[0].relevance == NO_MATCH_FLOOR


def test_gate_passes_via_market_subtitle(monkeypatch):
    # Ladder events carry the entity only in market subtitles ("SpaceX 99%").
    ev = _event("Which companies will announce an IPO this year?",
                markets=[_market(subtitle="SpaceX"), _market(subtitle="OpenAI")])
    items = _fetch("SpaceX IPO", _page(ev), monkeypatch)
    assert len(items) == 1


def test_settled_markets_dropped_event_skipped(monkeypatch):
    # All markets settled -> nothing live to quote -> no item.
    ev = _event("Old market", markets=[_market(result="yes"), _market(result="no")])
    assert _fetch("old market", _page(ev), monkeypatch) == []


def test_active_count_zero_skipped_absent_kept(monkeypatch):
    closed = _event("Closed event", active_market_count=0)
    no_field = _event("Field-less event")
    del no_field["active_market_count"]
    items = _fetch("event", _page(closed, no_field), monkeypatch)
    assert [it.title for it in items] == ["Field-less event"]


def test_default_event_has_no_tags():
    # _event() must not smuggle tags that would satisfy the gate accidentally.
    assert "tags" not in _event("x") and "topic_keywords" not in _event("x")


def test_snippet_top_volume_first_price_in_percent(monkeypatch):
    ev = _event("Ladder", markets=[
        _market("Above 400B", last_price=12, volume=10),
        _market("Above 300B", last_price=61, volume=99999),
        _market("Above 350B", last_price=0, yes_bid=33, volume=500),  # no trades -> bid
    ])
    items = _fetch("ladder", _page(ev), monkeypatch)
    assert items[0].snippet == "Above 300B 61%, Above 350B 33%, Above 400B 12%"


def test_dated_as_fetch_time_snapshot(monkeypatch):
    items = _fetch("spacex", _page(_event("SpaceX")), monkeypatch)
    it = items[0]
    assert it.date == "2026-06-09" and it.ts is None
    assert "snapshot" in it.metadata["date_basis"]


def test_volume_engagement_with_market_fallback(monkeypatch):
    ev_total = _event("Report A", total_volume=7777)
    ev_sum = _event("Report B", total_volume=0, markets=[_market(volume=200), _market(volume=300)])
    items = _fetch("report", _page(ev_total, ev_sum), monkeypatch)
    vols = {it.title: it.engagement["volume"] for it in items}
    assert vols == {"Report A": 7777, "Report B": 500}


def test_depth_cap(monkeypatch):
    events = [_event(f"Event {i}", event_ticker=f"KX{i}") for i in range(10)]
    assert len(_fetch("event", _page(*events), monkeypatch, depth="quick")) == 5


def test_unknown_depth_defaults_to_12(monkeypatch):
    events = [_event(f"Event {i}", event_ticker=f"KX{i}") for i in range(15)]
    assert len(_fetch("event", _page(*events), monkeypatch, depth="nope")) == 12


def test_mixed_event_keeps_open_drops_settled_from_snippet(monkeypatch):
    ev = _event("Mixed", markets=[
        _market("Settled leg", volume=99999, result="yes"),
        _market("Open leg", last_price=40, volume=10),
    ])
    items = _fetch("mixed", _page(ev), monkeypatch)
    assert len(items) == 1 and items[0].snippet == "Open leg 40%"


def test_type_absent_kept(monkeypatch):
    ev = _event("Typeless event")
    del ev["type"]
    assert len(_fetch("typeless event", _page(ev), monkeypatch)) == 1


def test_non_numeric_volume_and_price_no_crash(monkeypatch):
    ev = _event("Weird data", total_volume="abc",
                markets=[_market("Leg", last_price="n/a", yes_bid=None, volume="x")])
    items = _fetch("weird data", _page(ev), monkeypatch)
    assert items[0].engagement["volume"] == 0
    assert items[0].snippet == "Leg 0%"


def test_malformed_rows_skipped(monkeypatch):
    resp = _page(
        "not a dict",
        _event("No markets", markets=[]),
        _event("", event_title=""),                       # missing title
        {"type": "series", "event_title": "nav row"},     # non-contract row
        _event("Good one"),
    )
    items = _fetch("good one", resp, monkeypatch)
    assert [it.title for it in items] == ["Good one"]


def test_http_error_and_bad_payload_empty(monkeypatch):
    def boom(*a, **k):
        raise kalshi.http.HTTPError("403")
    monkeypatch.setattr(kalshi.http, "get", boom)
    w = Window(days=30, now=datetime(2026, 6, 9, tzinfo=timezone.utc))
    assert kalshi.fetch("x", w, env={}) == []
    monkeypatch.setattr(kalshi.http, "get", lambda *a, **k: ["not", "a", "dict"])
    assert kalshi.fetch("x", w, env={}) == []
    monkeypatch.setattr(kalshi.http, "get", lambda *a, **k: {"current_page": None})
    assert kalshi.fetch("x", w, env={}) == []


def test_url_from_series_ticker(monkeypatch):
    items = _fetch("spacex", _page(_event("SpaceX")), monkeypatch)
    assert items[0].url == "https://kalshi.com/markets/KXTEST"
    assert items[0].item_id == "ksKXTEST"
