"""Google News RSS source: degraded (no engagement) tier with a hard topic gate,
RFC-822 date parsing in UTC, ' - Publisher' suffix stripping, strict window."""

from datetime import datetime, timezone

from lib import registry, tiers
from lib import sources  # noqa: F401  registers sources
from lib.dates import Window
from lib.sources import googlenews


def _rss(items: list[str]) -> str:
    body = "".join(items)
    return (
        '<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel>'
        "<title>News</title>" + body + "</channel></rss>"
    )


def _item(title, pubdate, source="TechRadar", link=None, desc="snippet here"):
    link = link or f"https://news.google.com/rss/articles/{abs(hash(title)) % 10**12}"
    return (
        f"<item><title>{title}</title><link>{link}</link>"
        f"<pubDate>{pubdate}</pubDate>"
        f'<description>&lt;a href="x"&gt;{desc}&lt;/a&gt;</description>'
        f'<source url="https://t.co">{source}</source></item>'
    )


def _fetch(query, rss, monkeypatch, days=30, now=None):
    monkeypatch.setattr(googlenews.http, "get_text", lambda *a, **k: rss)
    w = Window(days=days, now=now or datetime(2026, 6, 11, tzinfo=timezone.utc))
    return googlenews.fetch(query, w, env={})


def test_is_engine_source():
    assert "googlenews" in registry.ENGINE_SOURCES
    assert registry.get("gn").name == "googlenews"
    assert registry.get("news").name == "googlenews"
    assert registry.get("googlenews").implemented is True


def test_parses_strips_suffix_and_no_fake_engagement(monkeypatch):
    rss = _rss([_item("How to achieve low latency when web scraping - TechRadar",
                      "Sat, 30 May 2026 12:56:22 GMT")])
    items = _fetch("web scraping", rss, monkeypatch)
    assert len(items) == 1
    it = items[0]
    assert it.source == "googlenews" and it.lang == "en"
    assert it.title == "How to achieve low latency when web scraping"  # suffix stripped
    assert it.author == "TechRadar" and it.container == "TechRadar"
    assert it.engagement == {}            # degraded: never fake engagement
    assert it.date == "2026-05-30"
    assert it.url.startswith("https://news.google.com/rss/articles/")


def test_off_topic_dropped(monkeypatch):
    # No engagement to rank by -> off-topic items must be dropped outright.
    rss = _rss([_item("Best slow-cooker pasta recipe - FoodBlog", "Sat, 30 May 2026 12:00:00 GMT")])
    assert _fetch("web scraping anti-bot", rss, monkeypatch) == []


def test_out_of_window_dropped(monkeypatch):
    # when:Nd is approximate; an item dated before the cutoff is dropped.
    rss = _rss([
        _item("Web scraping in 2026 - Wired", "Mon, 08 Jun 2026 09:00:00 GMT"),
        _item("Web scraping history - OldSite", "Mon, 01 Jan 2024 09:00:00 GMT"),
    ])
    items = _fetch("web scraping", rss, monkeypatch, days=14)
    assert [i.date for i in items] == ["2026-06-08"]


def test_pubdate_normalized_to_utc(monkeypatch):
    # A non-UTC offset must resolve to the UTC date (next day here), matching the
    # engine's UTC window — same invariant the lobsters source guards.
    rss = _rss([_item("Web scraping news - Outlet", "Sat, 30 May 2026 23:30:00 -0500")])
    items = _fetch("web scraping", rss, monkeypatch)
    assert items and items[0].date == "2026-05-31"


def test_degraded_flag_stamped_by_tier(monkeypatch):
    rss = _rss([_item("New web scraping tool - Outlet", "Sat, 30 May 2026 12:00:00 GMT")])
    monkeypatch.setattr(googlenews.http, "get_text", lambda *a, **k: rss)
    w = Window(days=30, now=datetime(2026, 6, 11, tzinfo=timezone.utc))
    items, used = tiers.run_tiers(registry.get("googlenews"), "web scraping", w, env={})
    assert used is not None and used.degraded is True
    assert items[0].metadata.get("degraded") is True
    assert items[0].metadata.get("tier") == "rss"
    assert "no engagement" in items[0].metadata.get("degraded_note", "")


def test_empty_or_malformed_feed_is_safe(monkeypatch):
    assert _fetch("web scraping", "", monkeypatch) == []
    assert _fetch("web scraping", "<not xml", monkeypatch) == []
