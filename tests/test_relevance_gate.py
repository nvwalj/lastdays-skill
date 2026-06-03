"""Regression tests for title_relevance (the RSS/Douyin noise gate).

Locks in the counterexamples a reviewer (codex) flagged: substring matching let
off-topic ASCII titles through ("AI" in "stainless", "market" in "Flea market
find"). The gate now uses whole-word matching + category stopwords + coverage.
"""

from lib.sources.base import title_relevance as tr

GATE = 0.3  # the RSS tier's RSS_MIN_RELEVANCE


def _passes(q, t):
    return tr(q, t) >= GATE


def test_codex_counterexamples_are_dropped():
    assert not _passes("AI", "stainless steel review")      # substring "ai" must NOT match
    assert not _passes("US stock market", "Flea market find")  # "market" alone insufficient
    assert not _passes("Nvidia", "Flea market find")


def test_on_topic_titles_pass():
    assert _passes("Nvidia", "Nvidia hits new high")
    assert _passes("AI", "New AI model released")           # whole word "AI" present
    assert _passes("US stock market", "US stock market hits record")
    assert _passes("US stock market", "stock market crash today")
    assert _passes("Tesla stock", "Tesla stock soars 10%")
    assert _passes("Claude Code", "Claude Code v2 ships")


def test_specific_token_required_not_category_word():
    # "stock" query qualified only by the specific entity, not the category word.
    assert _passes("Tesla stock", "Tesla earnings beat")    # tesla is specific
    assert not _passes("Tesla stock", "Ford stock dips")    # only category "stock" matches


def test_cjk_substring_path():
    assert _passes("人工智能", "人工智能写高考作文")
    assert not _passes("人工智能", "完全无关的体育新闻")
    assert tr("人工智能", "人工智能大爆发") >= 0.75


def test_empty_inputs():
    assert tr("", "anything") == 0.0
    assert tr("query", "") == 0.0
