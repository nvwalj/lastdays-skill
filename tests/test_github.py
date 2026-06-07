"""GitHub relevance: was flat 0.6 (last flat-relevance source), so the round-10
relevance gate did nothing for it — unrelated CI/RAG issues that GitHub search
loosely recalled looked as relevant as a real match. Now scored by title+repo."""

from datetime import datetime, timezone

from lib.dates import Window
from lib.sources import github
from lib.sources.github import NO_MATCH_FLOOR


def _resp(*pairs):  # (title, repo)
    return {"items": [
        {"title": t, "html_url": f"https://github.com/{r}/issues/{i}",
         "repository_url": f"https://api.github.com/repos/{r}",
         "created_at": "2026-06-07T00:00:00Z", "number": i,
         "comments": 3, "reactions": {"total_count": 2}, "user": {"login": "u"}}
        for i, (t, r) in enumerate(pairs)
    ]}


def _fetch(query, resp, monkeypatch):
    monkeypatch.setattr(github.http, "get", lambda *a, **k: resp)
    w = Window(days=30, now=datetime(2026, 6, 7, tzinfo=timezone.utc))
    return github.fetch(query, w, env={})


def test_relevance_not_flat(monkeypatch):
    items = _fetch("scraper",
                   _resp(("fix scrape results", "x/airbnb-scraper"),
                         ("Phase 2 Monitoring & CI/CD", "y/eventrelay")), monkeypatch)
    rels = {round(i.relevance, 2) for i in items}
    assert len(rels) > 1                          # no longer all 0.6


def test_matched_title_scores_high(monkeypatch):
    items = _fetch("scraper", _resp(("airbnb scraper persist", "x/y")), monkeypatch)
    assert items[0].relevance > NO_MATCH_FLOOR


def test_matched_via_repo_name(monkeypatch):
    # Title omits the term but the repo name carries it.
    items = _fetch("fredy", _resp(("persist results honestly", "orangecoding/fredy")), monkeypatch)
    assert items[0].relevance > NO_MATCH_FLOOR


def test_unrelated_gets_floor(monkeypatch):
    items = _fetch("scraper", _resp(("Phase 2 Monitoring CI/CD", "y/eventrelay")), monkeypatch)
    assert items[0].relevance == NO_MATCH_FLOOR
