"""Cross-source dedupe: the same story shared to two platforms (same title,
different URL — HN original vs Reddit discussion) must collapse to one, keeping
the higher-scored copy. Round-6 loop finding: dedupe was URL-only."""

from lib import normalize
from lib.schema import Item


def _i(source, title, url, score=0):
    return Item(source=source, lang="en", title=title, url=url, score=score)


def test_same_title_different_url_collapses_keeping_high_score():
    items = [
        _i("hackernews", "OpenAI releases GPT-6", "https://openai.com/gpt6", 90),
        _i("github", "openai releases gpt-6", "https://github.com/x/y/issues/1", 50),
    ]
    out = normalize.dedupe(items)
    assert len(out) == 1
    assert out[0].source == "hackernews" and out[0].score == 90  # stronger copy wins


def test_same_url_different_title_collapses():
    items = [
        _i("reddit", "A", "https://example.com/p", 10),
        _i("reddit", "B totally different headline", "https://www.example.com/p/", 20),
    ]
    out = normalize.dedupe(items)
    assert len(out) == 1
    assert out[0].score == 20  # canonical_url match, higher score kept


def test_distinct_stories_all_kept():
    items = [
        _i("hackernews", "Story one", "https://a.com/1", 30),
        _i("reddit", "Story two", "https://b.com/2", 40),
        _i("github", "Story three", "https://c.com/3", 20),
    ]
    assert len(normalize.dedupe(items)) == 3


def test_norm_title_handles_punctuation_and_cjk():
    assert normalize.norm_title("OpenAI releases GPT-6!") == normalize.norm_title("openai releases gpt 6")
    assert normalize.norm_title("国产大模型 横评") == "国产大模型 横评"
    assert normalize.norm_title("") == ""


def test_empty_url_falls_back_to_title():
    # No URL on either -> title still dedupes them.
    items = [_i("x", "same thing", "", 5), _i("y", "same thing", "", 9)]
    out = normalize.dedupe(items)
    assert len(out) == 1 and out[0].score == 9
