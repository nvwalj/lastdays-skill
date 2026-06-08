from lib import registry
from lib import sources  # noqa: F401  registers sources
from lib.sources import bilibili


def test_mixin_key_matches_known_vector():
    # Reference vector from bilibili-API-collect docs/misc/sign/wbi.md.
    img = "7cd084941338484aae1ad9425b84077c"
    sub = "4932caff0ff746eab6f01bf08b70ac45"
    assert bilibili._mixin_key(img + sub) == "ea1db124af3c7062474693fa704f4ff8"


def test_sign_wbi_is_deterministic_and_adds_w_rid():
    img = "7cd084941338484aae1ad9425b84077c"
    sub = "4932caff0ff746eab6f01bf08b70ac45"
    a = bilibili.sign_wbi({"keyword": "AI", "page": "1"}, img, sub, wts=1716950400)
    b = bilibili.sign_wbi({"page": "1", "keyword": "AI"}, img, sub, wts=1716950400)
    assert a["wts"] == "1716950400"
    assert len(a["w_rid"]) == 32
    assert a["w_rid"] == b["w_rid"]  # order-independent (params are sorted)


def test_parse_maps_video_results():
    results = [
        {
            "type": "video",
            "bvid": "BV1xx",
            "title": 'AI <em class="keyword">工具</em>盘点',
            "author": "UP主",
            "pubdate": 1716950400,
            "play": 12345,
            "video_review": 678,
            "favorites": 90,
            "description": "desc",
        },
        {"type": "user", "uname": "ignored"},
    ]
    items = bilibili._parse(results, "工具盘点")
    assert len(items) == 1
    it = items[0]
    assert it.source == "bilibili" and it.lang == "zh"
    assert it.title == "AI 工具盘点"  # <em> stripped
    assert it.url == "https://www.bilibili.com/video/BV1xx"
    assert it.engagement == {"views": 12345, "danmaku": 678, "favorites": 90}
    assert it.date == "2024-05-29"
    assert it.relevance == 0.9  # real title_relevance (full CJK match), not a flat 0.6


def test_parse_gates_offtopic_fuzzy_match():
    # B站 search fuzzes the 2-bigram query 泰瑞达 (Teradyne) into "瑞达" game clips
    # and 瑞达利欧 (Ray Dalio) videos. The engine must drop them and keep only the
    # real Teradyne video. Regression for the 2026-06-08 --lang both finding.
    results = [
        {"type": "video", "bvid": "BV1on", "title": "泰瑞达 Q1 财报点评",
         "pubdate": 1716950400, "play": 100, "video_review": 1, "favorites": 1},
        {"type": "video", "bvid": "BV1off", "title": "【刺客信条】瑞达每日精选",
         "pubdate": 1716950400, "play": 9999, "video_review": 1, "favorites": 1},
        {"type": "video", "bvid": "BV1off2", "title": "瑞达利欧谈债务危机",
         "pubdate": 1716950400, "play": 8888, "video_review": 1, "favorites": 1},
    ]
    items = bilibili._parse(results, "泰瑞达")
    assert [it.item_id for it in items] == ["bvBV1on"]  # only the genuine match survives
    assert items[0].relevance == 0.9                    # full whole-word match


def test_bilibili_is_engine_source_with_two_tiers():
    assert "bilibili" in registry.ENGINE_SOURCES
    src = registry.get("bili")
    assert src.name == "bilibili" and src.implemented is True
    ts = src.ordered_tiers()
    assert [t.label for t in ts] == ["search", "wbi-search"]   # quality order
    # Both endpoints return full engagement when they answer - neither degraded.
    assert all(t.degraded is False for t in ts)


def test_search_url_stable_within_day_for_cache(monkeypatch):
    """The signed search URL must be identical across calls in the same day, or
    the HTTP cache can never hit (the wts-per-second bug)."""
    from lib.dates import Window
    from datetime import datetime, timezone
    seen = []
    monkeypatch.setattr(bilibili, "_get_buvid3", lambda env: "buvid3=x")
    monkeypatch.setattr(bilibili, "_get_wbi_keys", lambda: ("a" * 32, "b" * 32))
    def fake_get(url, **k):
        seen.append(url)
        return {"code": 0, "data": {"result": []}}
    monkeypatch.setattr(bilibili.http, "get", fake_get)
    w = Window.from_days(7)
    bilibili._search(bilibili.SEARCH_URL, "游戏", "default", {})
    bilibili._search(bilibili.SEARCH_URL, "游戏", "default", {})
    assert seen[0] == seen[1]              # same wts/w_rid -> cacheable
    assert "wts=" in seen[0]
