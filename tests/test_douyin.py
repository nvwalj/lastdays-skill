from datetime import datetime, timezone

from lib import registry, tiers
from lib import sources  # noqa: F401  registers sources
from lib.dates import Window
from lib.sources import douyin

BOARD = [
    {"word": "人工智能写高考作文", "hot_value": 9000000, "position": 1,
     "event_time": int(datetime(2026, 5, 28, tzinfo=timezone.utc).timestamp()), "sentence_id": "111"},
    {"word": "完全无关的体育新闻", "hot_value": 8000000, "position": 2, "sentence_id": "222"},
]


def _w():
    return Window(days=30, now=datetime(2026, 5, 31, tzinfo=timezone.utc))


def test_douyin_is_engine_source_with_two_tiers():
    assert "douyin" in registry.ENGINE_SOURCES
    src = registry.get("dy")
    assert src.name == "douyin" and src.implemented is True
    labels = [t.label for t in src.ordered_tiers()]
    assert labels == ["aweme", "v2"]            # quality order
    assert src.ordered_tiers()[1].degraded is True


def test_relevance_cjk_containment():
    # token_overlap misses CJK substrings; the containment boost must catch it.
    assert douyin._relevance("人工智能", "人工智能大爆发") >= 0.75
    assert douyin._relevance("AI", "完全无关的热搜") < 0.4


def test_aweme_tier_filters_and_maps(monkeypatch):
    monkeypatch.setattr(douyin, "_board", lambda url, env: BOARD)
    items, used = tiers.run_tiers(registry.get("douyin"), "人工智能", _w(), env={})
    assert used.label == "aweme"
    assert len(items) == 1                      # off-topic entry dropped
    it = items[0]
    assert it.source == "douyin" and it.lang == "zh"
    assert it.title == "人工智能写高考作文"
    assert it.date == "2026-05-28"
    assert it.engagement == {"hot_value": 9000000, "rank": 1}
    assert it.url == "https://www.douyin.com/hot/111"
    assert not it.metadata.get("degraded")      # primary tier is full-signal


def test_v2_fallback_marks_degraded(monkeypatch):
    def board(url, env):
        if url == douyin.PRIMARY_URL:
            raise douyin.http.HTTPError("boom", status_code=500)
        return BOARD
    monkeypatch.setattr(douyin, "_board", board)
    items, used = tiers.run_tiers(registry.get("douyin"), "人工智能", _w(), env={})
    assert used.label == "v2"
    assert items[0].metadata.get("degraded") is True
    assert "timestamps" in items[0].metadata.get("degraded_note", "")
