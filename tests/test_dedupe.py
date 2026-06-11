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


# --- near-duplicate clustering (reworded/reordered headlines, distinct URLs) ---

def test_reordered_headline_merges_keeping_high_score():
    # Same story, words reordered + a synonym; exact-title pass can't catch it.
    items = [
        _i("googlenews", "OpenAI files paperwork for an IPO", "https://news.google.com/rss/articles/AbC", 40),
        _i("reddit", "OpenAI confidentially files IPO paperwork", "https://reddit.com/r/x/comments/1", 70),
    ]
    out = normalize.dedupe(items)
    assert len(out) == 1
    assert out[0].source == "reddit" and out[0].score == 70  # stronger copy survives


def test_same_article_googlenews_and_hn_merges():
    # The article on Google News (redirect URL) and as an HN link (publisher URL):
    # different URLs, near-identical titles -> one survivor.
    items = [
        _i("hackernews", "Model routing is a fix for AI overspending", "https://thepub.com/routing", 55),
        _i("googlenews", "Model routing is a fix for AI overspending today", "https://news.google.com/rss/articles/XyZ", 12),
    ]
    out = normalize.dedupe(items)
    assert len(out) == 1 and out[0].source == "hackernews"


def test_distinct_stories_sharing_words_not_merged():
    # Same template, different subject -> must stay separate (no false merge).
    items = [
        _i("hackernews", "Apple unveils iPhone 18 Pro model", "https://a.com/1", 30),
        _i("reddit", "Apple unveils iPad Air tablet model", "https://b.com/2", 20),
    ]
    assert len(normalize.dedupe(items)) == 2


def test_short_titles_dedupe_exact_only_not_near():
    # Short titles are Jaccard-unstable -> exact-only; "Rust 2.0" vs "Rust 3.0"
    # must both survive.
    items = [_i("hackernews", "Rust 2.0", "https://a/1", 10), _i("lobsters", "Rust 3.0", "https://b/2", 9)]
    assert len(normalize.dedupe(items)) == 2


def test_cjk_near_dup_merges_when_trailing_token_differs():
    # Same Chinese headline, one source appends a year (digits dropped from the
    # CJK shingle) -> exact pass misses it, trigram Jaccard catches it.
    items = [
        _i("bilibili", "国产大模型横评对比测评", "https://b/1", 30),
        _i("weibo", "国产大模型横评对比测评 2026", "https://w/2", 10),
    ]
    out = normalize.dedupe(items)
    assert len(out) == 1 and out[0].score == 30


def test_distinct_cjk_titles_not_merged():
    items = [
        _i("bilibili", "苹果发布新款手机评测", "https://b/1", 30),
        _i("bilibili", "英伟达显卡深度性能解析", "https://b/2", 20),
    ]
    assert len(normalize.dedupe(items)) == 2
