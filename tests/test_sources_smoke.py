from lib import registry
from lib import sources  # noqa: F401  registers all sources
from lib.dates import Window


def test_zh_stubs_return_empty_and_are_marked():
    w = Window.from_days(30)
    for name in ("weibo", "zhihu"):
        src = registry.get(name)
        assert src is not None
        assert src.lang == "zh"
        assert src.implemented is False
        assert src.fetch("anything", w, env={}) == []


def test_xiaohongshu_is_bridge_gated_not_stub():
    # Implemented now, but engine-run ONLY when its local-bridge probe passes.
    src = registry.get("xiaohongshu")
    assert src.implemented is True
    assert src.bridge_probe is not None
    assert "xiaohongshu" not in registry.ENGINE_SOURCES   # static set stays honest


def test_en_sources_registered_and_callable():
    for name in ("hackernews", "reddit", "github", "polymarket"):
        src = registry.get(name)
        assert src is not None
        assert src.implemented is True
        # Works for both single-fetch sources and multi-tier sources (reddit).
        tiers = src.ordered_tiers()
        assert tiers and all(callable(t.fetch) for t in tiers)
