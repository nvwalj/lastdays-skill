from datetime import datetime, timezone

from lib import registry
from lib import sources  # noqa: F401  registers sources
from lib.dates import Window
from lib.sources import douyin


def test_douyin_is_engine_source():
    assert "douyin" in registry.ENGINE_SOURCES
    assert registry.get("dy").name == "douyin"
    assert registry.get("douyin").implemented is True


def test_relevance_cjk_containment():
    # token_overlap misses CJK substrings; the containment boost must catch it.
    assert douyin._relevance("人工智能", "人工智能大爆发") >= 0.75
    assert douyin._relevance("AI", "完全无关的热搜") < 0.4


def test_fetch_filters_and_maps(monkeypatch):
    board = [
        {"word": "人工智能写高考作文", "hot_value": 9000000, "position": 1,
         "event_time": int(datetime(2026, 5, 28, tzinfo=timezone.utc).timestamp()), "sentence_id": "111"},
        {"word": "完全无关的体育新闻", "hot_value": 8000000, "position": 2, "sentence_id": "222"},
    ]
    monkeypatch.setattr(douyin, "_word_list", lambda env: board)
    w = Window(days=30, now=datetime(2026, 5, 31, tzinfo=timezone.utc))
    items = douyin.fetch("人工智能", w, env={})
    assert len(items) == 1                      # off-topic entry dropped
    it = items[0]
    assert it.source == "douyin" and it.lang == "zh"
    assert it.title == "人工智能写高考作文"
    assert it.date == "2026-05-28"
    assert it.engagement == {"hot_value": 9000000, "rank": 1}
    assert it.url == "https://www.douyin.com/hot/111"
