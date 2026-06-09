"""Lemmy source: field mapping, on-topic gate, window-aware sort, graceful degrade."""

from datetime import datetime, timezone

from lib import registry
from lib import sources  # noqa: F401  registers sources
from lib.dates import Window
from lib.sources import lemmy


def _win(days=30):
    return Window(days=days, now=datetime(2026, 6, 8, tzinfo=timezone.utc))


def _post(pid, name, *, score=10, comments=2, published="2026-05-29T12:00:00Z",
          community="technology", creator="alice", url=None):
    return {
        "post": {"id": pid, "name": name, "url": url or f"https://x/{pid}",
                 "ap_id": f"https://lemmy.world/post/{pid}", "published": published,
                 "body": "body text"},
        "counts": {"score": score, "comments": comments},
        "community": {"name": community},
        "creator": {"name": creator},
    }


def test_fetch_maps_fields(monkeypatch):
    captured = {}

    def fake_get(url, **kw):
        captured["url"] = url
        return {"posts": [_post(1, "Reddit blocks JSON API scraping", score=270, comments=30)]}

    monkeypatch.setattr(lemmy.http, "get", fake_get)
    items = lemmy.fetch("scraping", _win(), env={})
    assert "type_=Posts" in captured["url"]
    assert "sort=TopMonth" in captured["url"]            # 30d window -> TopMonth
    assert len(items) == 1
    it = items[0]
    assert it.source == "lemmy" and it.lang == "en"
    assert it.title == "Reddit blocks JSON API scraping"
    assert it.engagement == {"score": 270, "comments": 30}
    assert it.author == "alice"
    assert it.container == "c/technology"
    assert it.date == "2026-05-29"
    assert it.item_id == "lm1"
    assert it.relevance == 0.9                            # title contains the query word


def test_offtopic_dropped(monkeypatch):
    # Lemmy search recalls loosely; an off-topic high-score post must be gated out.
    monkeypatch.setattr(lemmy.http, "get", lambda url, **kw: {"posts": [
        _post(1, "Best web scraping tools", score=100),
        _post(2, "My cat photos", score=999),            # off-topic despite huge score
    ]})
    items = lemmy.fetch("web scraping", _win(), env={})
    assert [it.item_id for it in items] == ["lm1"]


def test_sort_brackets_window():
    assert lemmy._sort_for_window(7) == "TopWeek"
    assert lemmy._sort_for_window(8) == "TopMonth"
    assert lemmy._sort_for_window(31) == "TopMonth"
    assert lemmy._sort_for_window(90) == "TopThreeMonths"
    assert lemmy._sort_for_window(93) == "TopThreeMonths"
    assert lemmy._sort_for_window(180) == "TopSixMonths"
    assert lemmy._sort_for_window(365) == "TopYear"


def test_skips_idless_post(monkeypatch):
    # A malformed entry with no post.id must be skipped, not collapsed into "lmNone".
    good = _post(1, "scraping ok")
    idless = {"post": {"name": "scraping but no id"}, "counts": {}, "community": {}, "creator": {}}
    monkeypatch.setattr(lemmy.http, "get", lambda url, **kw: {"posts": [idless, good]})
    items = lemmy.fetch("scraping", _win(), env={})
    assert [it.item_id for it in items] == ["lm1"]


def test_http_error_degrades(monkeypatch):
    def boom(*a, **k):
        raise lemmy.http.HTTPError("503", status_code=503)
    monkeypatch.setattr(lemmy.http, "get", boom)
    assert lemmy.fetch("scraping", _win(), env={}) == []  # instance down -> []


def test_dedups_by_id(monkeypatch):
    monkeypatch.setattr(lemmy.http, "get", lambda url, **kw: {"posts": [
        _post(1, "scraping guide"),
        _post(1, "scraping guide"),                       # dup id across the page
    ]})
    items = lemmy.fetch("scraping", _win(), env={})
    assert len(items) == 1


def test_instance_override(monkeypatch):
    captured = {}
    monkeypatch.setattr(lemmy.http, "get",
                        lambda url, **kw: captured.update(url=url) or {"posts": []})
    lemmy.fetch("scraping", _win(), env={"LEMMY_INSTANCE": "lemmy.ml"})
    assert "https://lemmy.ml/api/v3/search" in captured["url"]


def test_lemmy_is_engine_source():
    assert "lemmy" in registry.ENGINE_SOURCES
    assert registry.get("lem").name == "lemmy"
