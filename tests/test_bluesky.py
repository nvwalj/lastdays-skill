"""Bluesky source: field mapping, full-text gate, server timestamp, unique id, tiers."""

from datetime import datetime, timezone

from lib import dates, registry, tiers
from lib import sources  # noqa: F401  registers sources
from lib.dates import Window
from lib.sources import bluesky


def _win(days=30):
    return Window(days=days, now=datetime(2026, 6, 8, tzinfo=timezone.utc))


def _post(rkey, text, *, likes=5, reposts=1, replies=0, created="2026-05-29T12:00:00Z",
          indexed=None, handle="alice.bsky.social", did="did:plc:abc"):
    p = {
        "uri": f"at://{did}/app.bsky.feed.post/{rkey}",
        "cid": f"cid{rkey}",
        "author": {"handle": handle, "did": did},
        "record": {"text": text, "createdAt": created},
        "likeCount": likes, "repostCount": reposts, "replyCount": replies,
    }
    if indexed:
        p["indexedAt"] = indexed
    return p


def test_parse_maps_fields():
    posts = [_post("aaa", "Web scraping with residential proxies", likes=22, reposts=20, replies=2)]
    items = bluesky._parse(posts, "web scraping")
    assert len(items) == 1
    it = items[0]
    assert it.source == "bluesky" and it.lang == "en"
    assert it.title == "Web scraping with residential proxies"
    assert it.url == "https://bsky.app/profile/alice.bsky.social/post/aaa"
    assert it.engagement == {"likes": 22, "reposts": 20, "replies": 2}
    assert it.author == "alice.bsky.social"
    assert it.date == "2026-05-29"
    assert it.ts == dates.to_datetime("2026-05-29T12:00:00Z").timestamp()   # precise ts kept
    assert it.item_id == "bsdid:plc:abc_aaa"    # full did + rkey -> globally unique
    assert it.relevance == 0.9


def test_prefers_indexedAt_over_createdAt():
    # createdAt is client-spoofable; the server-authoritative indexedAt wins.
    posts = [_post("aaa", "web scraping note", created="2020-01-01T00:00:00Z",
                   indexed="2026-05-29T12:00:00Z")]
    assert bluesky._parse(posts, "web scraping")[0].date == "2026-05-29"   # not the 2020 createdAt


def test_full_text_gating_not_truncated():
    # Query terms past char 200 must still count: gate on full text, not title[:200].
    filler = "x " * 130                          # ~260 chars before the topic words
    posts = [_post("aaa", filler + "web scraping")]
    items = bluesky._parse(posts, "web scraping")
    assert len(items) == 1                        # found despite terms sitting past char 200
    assert len(items[0].title) <= 200             # title still truncated for display


def test_offtopic_dropped():
    posts = [
        _post("on", "best web scraping framework"),
        _post("off", "my lunch was great today", likes=999),   # off-topic despite high likes
    ]
    items = bluesky._parse(posts, "web scraping")
    assert [it.item_id for it in items] == ["bsdid:plc:abc_on"]


def test_distinct_authors_same_rkey_not_deduped():
    # rkey is per-repo; two different authors sharing an rkey must NOT collide.
    posts = [
        _post("samekey", "scraping one", did="did:plc:aaa", handle="a.bsky.social"),
        _post("samekey", "scraping two", did="did:plc:bbb", handle="b.bsky.social"),
    ]
    items = bluesky._parse(posts, "scraping")
    assert len(items) == 2
    assert {it.item_id for it in items} == {"bsdid:plc:aaa_samekey", "bsdid:plc:bbb_samekey"}


def test_plaintext_angle_brackets_preserved():
    # AT-Proto text is plaintext; "<3" / "a<b" must survive (no strip_html).
    items = bluesky._parse([_post("aaa", "scraping with a<b comparison <3")], "scraping")
    assert "a<b" in items[0].title and "<3" in items[0].title


def test_empty_text_skipped():
    posts = [{"uri": "at://did:plc:x/app.bsky.feed.post/r1", "record": {"text": ""}, "author": {"handle": "a"}}]
    assert bluesky._parse(posts, "scraping") == []


def test_malformed_entries_skipped():
    posts = ["not a dict", {"uri": "at://did:plc:x/app.bsky.feed.post/r", "record": "notdict"}]
    assert bluesky._parse(posts, "scraping") == []        # no AttributeError


def test_search_sends_day_quantized_since(monkeypatch):
    captured = {}
    monkeypatch.setattr(bluesky.http, "get",
                        lambda url, **kw: captured.update(url=url) or {"posts": []})
    w = _win(30)
    bluesky._search(bluesky.APPVIEW_HOST, "scraping", w, "default")
    assert f"since={w.from_date}T00" in captured["url"]    # day-quantized -> cache-stable
    assert "sort=top" in captured["url"] and bluesky.APPVIEW_HOST in captured["url"]


def test_tier_fallback_public_to_appview(monkeypatch):
    # public host 403s from datacenter IPs; runner falls through to appview.
    calls = []

    def fake_get(url, **kw):
        calls.append(url)
        if bluesky.PUBLIC_HOST in url:
            raise bluesky.http.HTTPError("403", status_code=403)
        return {"posts": [_post("a", "scraping guide")]}

    monkeypatch.setattr(bluesky.http, "get", fake_get)
    items, used = tiers.run_tiers(registry.get("bluesky"), "scraping", _win(), env={})
    assert used.label == "appview" and len(items) == 1
    assert any(bluesky.PUBLIC_HOST in u for u in calls)
    assert any(bluesky.APPVIEW_HOST in u for u in calls)


def test_bluesky_is_engine_source_with_two_tiers():
    assert "bluesky" in registry.ENGINE_SOURCES
    assert registry.get("bsky").name == "bluesky"
    ts = registry.get("bluesky").ordered_tiers()
    assert [t.label for t in ts] == ["public", "appview"]
    assert all(t.degraded is False for t in ts)
