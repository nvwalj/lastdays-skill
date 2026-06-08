"""Stack Exchange source: window param, engagement parse, HTML-entity decode,
tag-aware on-topic gate, paging, and graceful degradation on throttle."""

from datetime import datetime, timezone

from lib.dates import Window
from lib.sources import stackexchange


def _q(qid, title, tags, *, score=10, answers=2, views=500, day=1):
    ts = int(datetime(2026, 6, day, tzinfo=timezone.utc).timestamp())
    return {
        "question_id": qid,
        "title": title,
        "link": f"https://stackoverflow.com/questions/{qid}/x",
        "score": score,
        "answer_count": answers,
        "view_count": views,
        "creation_date": ts,
        "tags": tags,
        "owner": {"display_name": "alice"},
        "is_answered": True,
    }


def _win():
    return Window(days=30, now=datetime(2026, 6, 8, tzinfo=timezone.utc))


def test_se_window_param_and_engagement_parse(monkeypatch):
    captured = {}

    def fake_get(url, **kw):
        captured["url"] = url
        # &quot; in the title must come back decoded to a real quote.
        return {"items": [_q(111, "Bypass Cloudflare while &quot;web scraping&quot;",
                             ["web-scraping", "python"], score=42, answers=3, views=1500)],
                "has_more": False, "quota_remaining": 290}

    monkeypatch.setattr(stackexchange.http, "get", fake_get)
    items = stackexchange.fetch("web scraping", _win(), env={})

    w = _win()
    assert f"fromdate={w.cutoff_day_ts}" in captured["url"]   # day-quantized window bound
    assert "todate" not in captured["url"]                    # omitted -> stable URL, caches
    assert "site=stackoverflow" in captured["url"]
    assert len(items) == 1
    it = items[0]
    assert it.title == 'Bypass Cloudflare while "web scraping"'  # &quot; decoded
    assert it.source == "stackexchange"
    assert it.engagement == {"score": 42, "answers": 3, "views": 1500}
    assert it.author == "alice"
    assert it.date == "2026-06-01"
    assert it.ts == float(int(datetime(2026, 6, 1, tzinfo=timezone.utc).timestamp()))
    assert it.item_id == "so111"
    assert it.metadata["tags"] == ["web-scraping", "python"]
    assert it.relevance > 0.5                                 # title has both query words


def test_se_tag_passes_gate_when_title_is_terse(monkeypatch):
    # Title alone doesn't contain "web"; the curated tag `web-scraping` carries
    # both tokens, so the title-OR-tags gate must keep it.
    monkeypatch.setattr(stackexchange.http, "get",
                        lambda url, **kw: {"items": [_q(1, "Cloudflare 403 on requests",
                                                        ["web-scraping", "python"])],
                                           "has_more": False})
    items = stackexchange.fetch("web scraping", _win(), env={})
    assert len(items) == 1 and items[0].item_id == "so1"


def test_se_offtopic_body_match_dropped(monkeypatch):
    # SE `q=` matches body text, so an unrelated question can come back. With
    # neither title nor tags matching both query tokens, the gate drops it.
    monkeypatch.setattr(stackexchange.http, "get",
                        lambda url, **kw: {"items": [
                            _q(1, "Cloudflare 403 on requests", ["web-scraping", "python"]),
                            _q(2, "How to add two numbers in C", ["c", "math"]),
                        ], "has_more": False})
    items = stackexchange.fetch("web scraping", _win(), env={})
    assert [it.item_id for it in items] == ["so1"]            # numbers question dropped


def test_se_http_error_degrades_to_empty(monkeypatch):
    def boom(*a, **k):
        raise stackexchange.http.HTTPError("throttled", status_code=429)
    monkeypatch.setattr(stackexchange.http, "get", boom)
    assert stackexchange.fetch("web scraping", _win(), env={}) == []  # no crash


def test_se_walks_pages_on_long_window_and_dedups(monkeypatch):
    calls = []

    def fake_get(url, **kw):
        calls.append(url)
        page = int(dict(p.split("=") for p in url.split("?")[1].split("&")).get("page", "1"))
        if page == 1:
            return {"items": [_q(1, "scraping with web proxies", ["web-scraping"]),
                              _q(2, "web scraping rate limits", ["web-scraping"])],
                    "has_more": True}
        return {"items": [_q(2, "web scraping rate limits", ["web-scraping"]),  # dup id 2
                          _q(3, "web scraping headless browser", ["web-scraping"])],
                "has_more": True}

    monkeypatch.setattr(stackexchange.http, "get", fake_get)
    w = Window(days=90, now=datetime(2026, 6, 8, tzinfo=timezone.utc))
    items = stackexchange.fetch("web scraping", w, env={})
    assert len(calls) == 2                                    # MAX_PAGES caps the walk at 2
    assert [it.item_id for it in items] == ["so1", "so2", "so3"]  # dup so2 dropped


def test_se_stops_paging_when_no_more(monkeypatch):
    calls = []
    monkeypatch.setattr(stackexchange.http, "get",
                        lambda url, **kw: calls.append(url) or {
                            "items": [_q(1, "web scraping basics", ["web-scraping"])],
                            "has_more": False})
    w = Window(days=90, now=datetime(2026, 6, 8, tzinfo=timezone.utc))
    stackexchange.fetch("web scraping", w, env={})
    assert len(calls) == 1                                    # has_more=False -> stop after page 1
