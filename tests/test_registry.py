import pytest

from lib import registry
from lib import sources  # noqa: F401  registers all sources on import


def test_lang_groups():
    assert set(registry.resolve_names(None, "en")) == {"hackernews", "reddit", "github", "polymarket", "kalshi", "lobsters", "devto", "stackexchange", "lemmy", "bluesky", "googlenews", "arxiv"}
    zh = registry.resolve_names(None, "zh")
    assert "weibo" in zh and len(zh) == 5


def test_both_includes_everything():
    assert len(registry.resolve_names(None, "both")) == 17  # 12 en + 5 zh


def test_aliases():
    assert registry.get("hn").name == "hackernews"
    assert registry.get("pm").name == "polymarket"
    assert registry.get("微博").name == "weibo"
    assert registry.get("xhs").name == "xiaohongshu"
    assert registry.get("so").name == "stackexchange"
    assert registry.get("stackoverflow").name == "stackexchange"
    assert registry.get("lem").name == "lemmy"
    assert registry.get("bsky").name == "bluesky"
    assert registry.get("ks").name == "kalshi"


def test_resolve_csv():
    assert registry.resolve_names("hn,gh", "en") == ["hackernews", "github"]


def test_unknown_source_raises():
    with pytest.raises(ValueError):
        registry.resolve_names("nope", "en")


def test_engine_sources_split():
    assert "hackernews" in registry.ENGINE_SOURCES
    assert "weibo" not in registry.ENGINE_SOURCES
