"""arXiv source: degraded (no-engagement) Atom parse, title-OR-abstract topic
gate, UTC date parsing, strict window, author 'et al.' formatting."""

from datetime import datetime, timezone

from lib import registry, tiers
from lib import sources  # noqa: F401  registers sources
from lib.dates import Window
from lib.sources import arxiv


def _entry(title, summary, pub, authors=("Alice Smith",), aid="2606.12407v1"):
    auth = "".join(f"<author><name>{n}</name></author>" for n in authors)
    return (
        f"<entry><id>http://arxiv.org/abs/{aid}</id>"
        f"<title>{title}</title><published>{pub}</published>"
        f"<summary>{summary}</summary>{auth}</entry>"
    )


def _feed(entries):
    return ('<?xml version="1.0" encoding="UTF-8"?>'
            '<feed xmlns="http://www.w3.org/2005/Atom">' + "".join(entries) + "</feed>")


def _fetch(monkeypatch, query, feed, days=30, now=None):
    monkeypatch.setattr(arxiv.http, "get_text", lambda *a, **k: feed)
    w = Window(days=days, now=now or datetime(2026, 6, 11, tzinfo=timezone.utc))
    return arxiv.fetch(query, w, env={})


def test_is_engine_source():
    assert "arxiv" in registry.ENGINE_SOURCES
    assert registry.get("arx").name == "arxiv"
    assert registry.get("papers").name == "arxiv"


def test_parses_entry_no_fake_engagement(monkeypatch):
    feed = _feed([_entry("A survey of web scraping techniques",
                         "We study web scraping at scale.", "2026-06-05T10:00:00Z",
                         authors=("Alice Smith", "Bob Jones"))])
    items = _fetch(monkeypatch, "web scraping", feed)
    assert len(items) == 1
    it = items[0]
    assert it.source == "arxiv" and it.engagement == {}
    assert it.title == "A survey of web scraping techniques"
    assert it.author == "Alice Smith et al."          # multiple authors collapsed
    assert it.url == "https://arxiv.org/abs/2606.12407v1"
    assert it.item_id == "arxiv2606.12407v1"
    assert it.date == "2026-06-05"


def test_topic_in_abstract_only_is_kept(monkeypatch):
    # Title has no query word, abstract does -> the title-OR-abstract gate keeps it.
    feed = _feed([_entry("A novel approach to data extraction",
                         "Our method performs web scraping efficiently.", "2026-06-05T10:00:00Z")])
    assert len(_fetch(monkeypatch, "web scraping", feed)) == 1


def test_off_topic_dropped(monkeypatch):
    feed = _feed([_entry("Quantum entanglement in cold atoms",
                         "We measure quantum coherence in trapped ions.", "2026-06-05T10:00:00Z")])
    assert _fetch(monkeypatch, "web scraping", feed) == []


def test_out_of_window_dropped(monkeypatch):
    feed = _feed([
        _entry("Recent web scraping advances", "web scraping today", "2026-06-05T10:00:00Z", aid="1"),
        _entry("Old web scraping paper", "web scraping long ago", "2024-01-01T10:00:00Z", aid="2"),
    ])
    items = _fetch(monkeypatch, "web scraping", feed, days=14)
    assert [i.date for i in items] == ["2026-06-05"]


def test_degraded_flag_via_tier(monkeypatch):
    feed = _feed([_entry("Web scraping survey", "web scraping methods", "2026-06-05T10:00:00Z")])
    monkeypatch.setattr(arxiv.http, "get_text", lambda *a, **k: feed)
    w = Window(days=30, now=datetime(2026, 6, 11, tzinfo=timezone.utc))
    items, used = tiers.run_tiers(registry.get("arxiv"), "web scraping", w, env={})
    assert used.degraded is True and items[0].metadata.get("degraded") is True


def test_malformed_feed_is_safe(monkeypatch):
    assert _fetch(monkeypatch, "web scraping", "") == []
    assert _fetch(monkeypatch, "web scraping", "<not xml") == []
