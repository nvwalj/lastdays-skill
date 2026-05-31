from lib import registry
from lib import sources  # noqa: F401  registers all sources
from lib.dates import Window


def test_zh_stubs_return_empty_and_are_marked():
    w = Window.from_days(30)
    for name in ("weibo", "xiaohongshu", "douyin", "zhihu"):
        src = registry.get(name)
        assert src is not None
        assert src.lang == "zh"
        assert src.implemented is False
        assert src.fetch("anything", w, env={}) == []


def test_en_sources_registered_and_callable():
    for name in ("hackernews", "reddit", "github", "polymarket"):
        src = registry.get(name)
        assert src is not None
        assert src.implemented is True
        assert callable(src.fetch)
