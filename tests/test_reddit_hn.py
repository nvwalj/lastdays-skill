"""Regression tests for the two bugs found 2026-06-02:
- HN: multi-word queries returned 0 (Algolia ANDs tokens) -> need optionalWords.
- Reddit: .json is 403 from datacenter IPs -> need the search.rss fallback.
"""

from datetime import datetime, timezone

from lib import registry, tiers
from lib.dates import Window
from lib.sources import hackernews, reddit


def test_hn_multiword_sets_optional_words(monkeypatch):
    captured = {}

    def fake_get(url, **kw):
        captured["url"] = url
        return {"hits": []}

    monkeypatch.setattr(hackernews.http, "get", fake_get)
    w = Window(days=7, now=datetime(2026, 6, 2, tzinfo=timezone.utc))
    hackernews.fetch("US stock market", w, env={})
    # tokens after the first become optional so Algolia stops requiring all of them
    assert "optionalWords=stock+market" in captured["url"]


def test_hn_singleword_no_optional(monkeypatch):
    captured = {}
    monkeypatch.setattr(hackernews.http, "get", lambda url, **kw: captured.update(url=url) or {"hits": []})
    w = Window(days=7, now=datetime(2026, 6, 2, tzinfo=timezone.utc))
    hackernews.fetch("stocks", w, env={})
    assert "optionalWords" not in captured["url"]


def test_reddit_falls_back_to_rss_on_403(monkeypatch):
    def boom(*a, **k):
        raise reddit.http.HTTPError("403", status_code=403)

    # Two posts: one matches "Nvidia", one is off-topic noise that only shares
    # the word "market" — the RSS tier's relevance gate must drop the latter.
    sample_rss = """<feed>
    <entry><title>Nvidia hits new high</title>
      <link href="https://www.reddit.com/r/stocks/comments/abc123/nvidia_hits_new_high/" />
      <updated>2026-06-02T10:00:00+00:00</updated>
      <author><name>/u/trader</name></author></entry>
    <entry><title>Flea market find</title>
      <link href="https://www.reddit.com/r/flashlight/comments/def456/flea_market_find/" />
      <updated>2026-06-02T09:00:00+00:00</updated>
      <author><name>/u/collector</name></author></entry>
    <entry><title>The stocks Subreddit</title>
      <link href="https://www.reddit.com/r/stocks/" />
      <updated>2010-01-01T00:00:00+00:00</updated></entry>
    </feed>"""

    monkeypatch.setattr(reddit.http, "get", boom)
    monkeypatch.setattr(reddit.http, "get_text", lambda *a, **k: sample_rss)
    w = Window(days=7, now=datetime(2026, 6, 2, tzinfo=timezone.utc))
    items, used = tiers.run_tiers(registry.get("reddit"), "Nvidia", w, env={})

    assert used.label == "rss"                   # json 403 -> fell back to rss tier
    assert len(items) == 1                        # subreddit card + off-topic noise dropped
    it = items[0]
    assert it.title == "Nvidia hits new high"
    assert it.container == "r/stocks"
    assert it.date == "2026-06-02"
    assert it.metadata.get("tier") == "rss"
    assert it.metadata.get("degraded") is True   # framework stamps degraded tier
    assert it.engagement == {}                    # RSS carries no engagement; must not be faked
    assert it.item_id == "rdabc123"


def test_reddit_prefers_json_when_available(monkeypatch):
    json_payload = {
        "data": {"children": [
            {"kind": "t3", "data": {
                "title": "Real post", "permalink": "/r/stocks/comments/xyz/real_post/",
                "score": 500, "num_comments": 120, "created_utc": 1780000000,
                "subreddit": "stocks", "author": "u1", "id": "xyz",
            }},
        ]}
    }
    called = {"rss": False}
    monkeypatch.setattr(reddit.http, "get", lambda *a, **k: json_payload)
    monkeypatch.setattr(reddit.http, "get_text", lambda *a, **k: called.update(rss=True) or "")
    w = Window(days=3650, now=datetime(2026, 6, 2, tzinfo=timezone.utc))
    items, used = tiers.run_tiers(registry.get("reddit"), "stocks", w, env={})

    assert called["rss"] is False                # json worked, RSS never touched
    assert used.label == "json"
    assert items[0].engagement["score"] == 500   # json keeps real engagement
    assert not items[0].metadata.get("degraded")  # json tier is not degraded
