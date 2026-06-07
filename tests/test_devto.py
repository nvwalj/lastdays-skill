"""Dev.to source: tag search + is_on_topic gate, real reactions/comments."""
from datetime import datetime, timezone
from lib import registry
from lib import sources  # noqa: F401
from lib.dates import Window
from lib.sources import devto


def _art(title, tags, react=5, cmt=2, aid="1", day="2026-06-07"):
    return {"title": title, "tag_list": tags, "public_reactions_count": react,
            "comments_count": cmt, "id": aid, "url": f"https://dev.to/x/{aid}",
            "published_at": f"{day}T10:00:00Z", "user": {"username": "alice"},
            "description": "d"}


def _fetch(query, arts, monkeypatch):
    monkeypatch.setattr(devto.http, "get", lambda *a, **k: arts)
    w = Window(days=30, now=datetime(2026, 6, 7, tzinfo=timezone.utc))
    return devto.fetch(query, w, env={})


def test_is_engine_source():
    assert "devto" in registry.ENGINE_SOURCES
    assert registry.get("dev").name == "devto"


def test_query_tag_normalization():
    assert devto._query_tag("web scraping") == "webscraping"
    assert devto._query_tag("C++") == "c"
    assert devto._query_tag("Node.js") == "nodejs"


def test_tag_search_maps_fields(monkeypatch):
    items = _fetch("webscraping", [_art("Web Scraping Guide", ["webscraping", "python"])], monkeypatch)
    assert len(items) == 1
    it = items[0]
    assert it.source == "devto" and it.engagement == {"reactions": 5, "comments": 2}
    assert it.date == "2026-06-07" and it.author == "alice"


def test_offtopic_filtered(monkeypatch):
    items = _fetch("kubernetes", [_art("My morning routine", ["life", "health"])], monkeypatch)
    assert items == []


def test_matched_via_tag_when_title_misses(monkeypatch):
    items = _fetch("scraping", [_art("RepoHunter writeup", ["scraping", "python"])], monkeypatch)
    assert len(items) == 1
