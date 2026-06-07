"""Topic gating (is_on_topic) and ranking score (title_relevance).

Locks in counterexamples reviewers/usage flagged:
- substring matching let "AI" match "stainless", "market" match "Flea market find"
- a 2-word query scored 0.575 on one weak token ("rate" of "rate limiting" in
  "Nasdaq Rate-Hike Fears"), masquerading as a real match
The gate is now a boolean is_on_topic (whole-word, coverage-based); the
continuous title_relevance is for ranking only.
"""

from lib.sources.base import is_on_topic, title_relevance as tr


def test_codex_counterexamples_dropped():
    assert not is_on_topic("AI", "stainless steel review")        # substring "ai" must NOT match
    assert not is_on_topic("US stock market", "Flea market find")  # only "market" -> 1/3
    assert not is_on_topic("Nvidia", "Flea market find")


def test_rate_word_noise_dropped():
    # The round-2 finding: "rate" alone (1 of 2 tokens) must not qualify.
    assert not is_on_topic("rate limiting", "Nasdaq Sinks over Rate-Hike Fears")
    assert not is_on_topic("rate limiting", "US cigarette smoking rate hits low")
    assert not is_on_topic("rate limiting", "Token bucket limiting explained")  # only "limiting"


def test_on_topic_titles_pass():
    assert is_on_topic("Nvidia", "Nvidia hits new high")
    assert is_on_topic("AI", "New AI model released")
    assert is_on_topic("US stock market", "US stock market hits record")
    assert is_on_topic("US stock market", "stock market crash today")   # 2 of 3
    assert is_on_topic("Tesla stock", "Tesla stock soars 10%")          # both tokens
    assert is_on_topic("rate limiting", "Nginx rate limiting tutorial") # both tokens
    assert is_on_topic("Claude Code", "Claude Code v2 ships")


def test_two_word_query_needs_both_tokens():
    assert not is_on_topic("Tesla stock", "Ford stock dips")    # only "stock"
    assert not is_on_topic("Tesla stock", "Tesla earnings beat")  # only "tesla"
    assert is_on_topic("Tesla stock", "Tesla stock dips")        # both


def test_cjk_substring_path():
    assert is_on_topic("人工智能", "人工智能写高考作文")
    assert not is_on_topic("人工智能", "完全无关的体育新闻")


def test_ranking_score_full_above_partial():
    # title_relevance is for ordering: a full match outranks a partial one.
    full = tr("rate limiting", "Nginx rate limiting guide")
    partial = tr("web scraping anti-bot", "fast web scraping framework")  # 2 of 3
    assert full == 0.9
    assert 0.3 <= partial < full
    assert tr("人工智能", "人工智能大爆发") >= 0.75


def test_empty_inputs():
    assert not is_on_topic("", "anything")
    assert not is_on_topic("query", "")
    assert tr("", "anything") == 0.0
