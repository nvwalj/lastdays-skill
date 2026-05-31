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
    items = bilibili._parse(results)
    assert len(items) == 1
    it = items[0]
    assert it.source == "bilibili" and it.lang == "zh"
    assert it.title == "AI 工具盘点"  # <em> stripped
    assert it.url == "https://www.bilibili.com/video/BV1xx"
    assert it.engagement == {"views": 12345, "danmaku": 678, "favorites": 90}
    assert it.date == "2024-05-29"


def test_bilibili_is_engine_source_now():
    assert "bilibili" in registry.ENGINE_SOURCES
    assert registry.get("bili").name == "bilibili"
    assert registry.get("bilibili").implemented is True
