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

    # Three entries: one matches "Nvidia"; one is off-topic noise that only
    # shares the word "market" (must be relevance-filtered); one is a subreddit
    # card (no /comments/, must be skipped). The matching post's author starts
    # with 'u' to lock in the removeprefix (not lstrip) username fix.
    sample_rss = """<feed>
    <entry><title>Nvidia hits new high</title>
      <link href="https://www.reddit.com/r/stocks/comments/abc123/nvidia_hits_new_high/" />
      <updated>2026-06-02T10:00:00+00:00</updated>
      <author><name>/u/ultradev</name></author></entry>
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
    assert it.author == "ultradev"               # /u/ prefix stripped, leading 'u' intact
    assert it.metadata.get("tier") == "rss"
    assert it.metadata.get("degraded") is True   # framework stamps degraded tier
    assert it.engagement == {}                    # RSS carries no engagement; must not be faked
    assert it.item_id == "rdabc123"


def test_reddit_rss_entry_without_author_does_not_crash(monkeypatch):
    # An entry missing <author> must not raise (would otherwise sink the tier).
    def boom(*a, **k):
        raise reddit.http.HTTPError("403", status_code=403)

    rss = """<feed>
    <entry><title>Nvidia ships chip</title>
      <link href="https://www.reddit.com/r/hardware/comments/zzz999/nvidia_ships_chip/" />
      <updated>2026-06-02T08:00:00+00:00</updated></entry>
    </feed>"""
    monkeypatch.setattr(reddit.http, "get", boom)
    monkeypatch.setattr(reddit.http, "get_text", lambda *a, **k: rss)
    w = Window(days=7, now=datetime(2026, 6, 2, tzinfo=timezone.utc))
    items, used = tiers.run_tiers(registry.get("reddit"), "Nvidia", w, env={})
    assert used.label == "rss" and len(items) == 1
    assert items[0].author is None               # absent author -> None, no crash


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


def test_hn_pages_long_window_dedups(monkeypatch):
    """Long windows page-walk past the single-response cap; dups across pages drop."""
    from datetime import datetime, timezone
    calls = []
    def fake_get(url, **k):
        calls.append(url)
        page = int(dict(p.split("=") for p in url.split("?")[1].split("&")).get("page", "0"))
        ts = int(datetime(2026, 6, 6, tzinfo=timezone.utc).timestamp())
        if page <= 1:  # full pages 0,1 -> keep going
            base = page * 30
            return {"hits": [{"objectID": str(base + i), "title": f"AI {base+i}",
                              "points": 5, "num_comments": 1, "created_at_i": ts} for i in range(30)]}
        return {"hits": [{"objectID": "5", "title": "AI 5 dup", "points": 5,
                          "num_comments": 1, "created_at_i": ts}]}  # short page (dup id) -> stop
    monkeypatch.setattr(hackernews.http, "get", fake_get)
    w = Window(days=90, now=datetime(2026, 6, 7, tzinfo=timezone.utc))
    items = hackernews.fetch("AI", w, env={})
    assert len(calls) == 3                       # 90d -> 3 pages walked
    assert len(items) == 60                       # 30+30, the dup id "5" on p2 dropped
    assert len({it.item_id for it in items}) == 60  # all unique


def test_hn_short_window_single_page(monkeypatch):
    calls = []
    monkeypatch.setattr(hackernews.http, "get",
                        lambda url, **k: calls.append(url) or {"hits": []})
    from datetime import datetime, timezone
    w = Window(days=7, now=datetime(2026, 6, 7, tzinfo=timezone.utc))
    hackernews.fetch("AI", w, env={})
    assert len(calls) == 1                        # short window: one request only


# --- oldweb tier (2026-06-10): old.reddit HTML with real engagement ----------

_OLD_HTML = """<div class="contents">
<div class=" search-result search-result-link has-thumbnail " data-fullname="t3_1tva44g">
<header class="search-result-header"><a href="https://old.reddit.com/r/ClaudeCode/comments/1tva44g/i_live_by_sfo/" class="search-title may-blank" >I built a projection &amp; mapping rig</a></header>
<div class="search-result-meta"><span class="search-score">3,822 points</span>&#32;<a href="https://old.reddit.com/r/ClaudeCode/comments/1tva44g/i_live_by_sfo/" class="search-comments may-blank" >156 comments</a>&#32;<span class="search-time">submitted&#32;<time title="Wed Jun 3 01:04:03 2026 UTC" datetime="2026-06-03T01:04:03+00:00">7 days ago</time></span>&#32;<span class="search-author">by&#32;<a href="https://old.reddit.com/user/I_am_Root01" class="author may-blank id-t2_oyaxwi3" >I_am_Root01</a></span>&#32;<span>to&#32;<a href="https://old.reddit.com/r/ClaudeCode/" class="search-subreddit-link may-blank" >r/ClaudeCode</a></span></div></div>
<div class=" search-result search-result-link " data-fullname="t3_broken1">
<div class="search-result-meta"><span class="search-score">10 points</span></div></div>
</div>"""


def test_reddit_falls_back_to_oldweb_on_403(monkeypatch):
    def boom(*a, **k):
        raise reddit.http.HTTPError("403", status_code=403)

    monkeypatch.setattr(reddit.http, "get", boom)
    monkeypatch.setattr(reddit.http, "get_text", lambda *a, **k: _OLD_HTML)
    w = Window(days=7, now=datetime(2026, 6, 9, tzinfo=timezone.utc))
    items, used = tiers.run_tiers(registry.get("reddit"), "claude code", w, env={})

    assert used.label == "oldweb"                # json 403 -> oldweb, NOT rss
    assert len(items) == 1                        # block without a title link skipped
    it = items[0]
    assert it.title == "I built a projection & mapping rig"   # entities unescaped
    assert it.url == "https://www.reddit.com/r/ClaudeCode/comments/1tva44g/i_live_by_sfo/"
    assert it.engagement == {"score": 3822, "comments": 156}  # commas stripped, real numbers
    assert it.date == "2026-06-03" and it.ts is not None
    assert it.author == "I_am_Root01"
    assert it.container == "r/ClaudeCode"
    assert it.item_id == "rd1tva44g"
    assert it.metadata.get("tier") == "oldweb"
    assert "degraded" not in it.metadata          # real engagement -> not degraded


def test_reddit_oldweb_empty_html_falls_to_rss(monkeypatch):
    def boom(*a, **k):
        raise reddit.http.HTTPError("403", status_code=403)

    rss = """<feed><entry><title>Nvidia hits new high</title>
      <link href="https://www.reddit.com/r/stocks/comments/abc123/x/" />
      <updated>2026-06-02T10:00:00+00:00</updated></entry></feed>"""
    monkeypatch.setattr(reddit.http, "get", boom)
    # get_text serves BOTH oldweb (html, no posts) and rss tiers here
    monkeypatch.setattr(reddit.http, "get_text", lambda *a, **k: rss)
    w = Window(days=7, now=datetime(2026, 6, 2, tzinfo=timezone.utc))
    items, used = tiers.run_tiers(registry.get("reddit"), "Nvidia", w, env={})
    assert used.label == "rss" and len(items) == 1
