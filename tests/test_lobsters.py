"""Lobsters source: hot-list + is_on_topic gate (search.json is HTML-only), with
real score/comment_count, matched on title OR tags."""

from datetime import datetime, timezone

from lib import registry
from lib import sources  # noqa: F401  registers sources
from lib.dates import Window
from lib.sources import lobsters


def _story(title, tags, score=10, cmt=2, sid="x", day="2026-06-07"):
    return {"title": title, "tags": tags, "score": score, "comment_count": cmt,
            "short_id": sid, "url": f"https://e/{sid}", "comments_url": f"https://lobste.rs/s/{sid}",
            "created_at": f"{day}T10:00:00.000-07:00", "submitter_user": "alice"}


def _fetch(query, stories, monkeypatch, days=30):
    monkeypatch.setattr(lobsters.http, "get", lambda *a, **k: stories)
    w = Window(days=days, now=datetime(2026, 6, 7, tzinfo=timezone.utc))
    return lobsters.fetch(query, w, env={})


def test_is_engine_source():
    assert "lobsters" in registry.ENGINE_SOURCES
    assert registry.get("lob").name == "lobsters"
    assert registry.get("lobsters").implemented is True


def test_matches_title(monkeypatch):
    items = _fetch("terminal", [_story("Life is too short for a slow terminal", ["linux"])], monkeypatch)
    assert len(items) == 1
    it = items[0]
    assert it.source == "lobsters" and it.engagement == {"score": 10, "comments": 2}
    assert it.date == "2026-06-07"


def test_matches_via_tag_when_title_misses(monkeypatch):
    # Title has no query word, but the tag does -> still on-topic.
    items = _fetch("databases", [_story("UUIDs considered harmful", ["databases", "sqlite"])], monkeypatch)
    assert len(items) == 1


def test_off_topic_dropped(monkeypatch):
    items = _fetch("kubernetes", [_story("Getting silly with C", ["c", "satire"])], monkeypatch)
    assert items == []


def test_dates_parsed_for_window_filtering(monkeypatch):
    # fetch() maps dates; the engine's normalize.filter_window does the actual
    # window cut. Verify the date is parsed so that filter can act on it.
    from lib import normalize
    old = _story("Old linux post", ["linux"], day="2026-01-01")
    new = _story("New linux post", ["linux"], sid="y", day="2026-06-06")
    items = _fetch("linux", [old, new], monkeypatch, days=7)
    assert {i.date for i in items} == {"2026-01-01", "2026-06-06"}  # both fetched, dated
    w = Window(days=7, now=datetime(2026, 6, 7, tzinfo=timezone.utc))
    kept = [i.title for i in normalize.filter_window(items, w)]
    assert kept == ["New linux post"]  # window filter drops the old one
