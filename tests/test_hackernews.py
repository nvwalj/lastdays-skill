"""HN relevance scoring: optionalWords pulls in off-topic stories; the relevance
floor must keep genuine matches ranked above 'we'-only noise."""

from datetime import datetime, timezone

from lib.dates import Window
from lib.sources import hackernews
from lib.sources.hackernews import _relevance, NO_MATCH_FLOOR


def test_relevance_floor_for_nonmatching_title():
    # "We Forget" only rode in on optionalWords; no query word matches -> floor.
    assert _relevance("web scraping anti-bot", "We Forget") == NO_MATCH_FLOOR


def test_relevance_high_for_matching_title():
    full = _relevance("web scraping", "A fast web scraping framework")  # both tokens
    assert full == 0.9                       # full match scores high
    partial = _relevance("web scraping anti-bot", "A fast web scraping framework")
    assert NO_MATCH_FLOOR < partial < full   # partial ranks above noise, below full


def test_optional_words_only_for_multiword(monkeypatch):
    seen = {}
    monkeypatch.setattr(hackernews.http, "get", lambda url, **k: seen.update(url=url) or {"hits": []})
    w = Window(days=7, now=datetime(2026, 6, 7, tzinfo=timezone.utc))
    hackernews.fetch("scraping", w, env={})
    assert "optionalWords" not in seen["url"]   # single token: no optionalWords
    hackernews.fetch("web scraping bypass", w, env={})
    assert "optionalWords" in seen["url"]        # multi token: optionalWords set


def test_fetch_scores_items_by_relevance(monkeypatch):
    hits = [
        {"objectID": "1", "title": "We Forget", "points": 200, "num_comments": 50,
         "created_at_i": int(datetime(2026, 6, 6, tzinfo=timezone.utc).timestamp())},
        {"objectID": "2", "title": "Show HN: a web scraping toolkit", "points": 20, "num_comments": 3,
         "created_at_i": int(datetime(2026, 6, 6, tzinfo=timezone.utc).timestamp())},
    ]
    monkeypatch.setattr(hackernews.http, "get", lambda *a, **k: {"hits": hits})
    w = Window(days=7, now=datetime(2026, 6, 7, tzinfo=timezone.utc))
    items = {it.title: it for it in hackernews.fetch("web scraping toolkit", w, env={})}
    # The on-topic story scores higher on relevance even with far fewer points.
    assert items["Show HN: a web scraping toolkit"].relevance > items["We Forget"].relevance
    assert items["We Forget"].relevance == NO_MATCH_FLOOR
