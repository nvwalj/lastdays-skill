"""Edge/boundary behavior locked in by a round-15 audit (no bug found — these
guard the verified-good behavior against future regressions): symbol/short
language names, special characters, and empty queries."""

from lib.sources.base import is_on_topic, title_relevance as tr


def test_symbol_language_names_match_whole_word():
    # "Go" must match "Go 1.30" but NOT "Going to the store" (whole-word, not prefix).
    assert is_on_topic("Go", "Go 1.30 released")
    assert not is_on_topic("Go", "Going to the store")
    assert tr("Go", "Go 1.30 released") == 0.9


def test_cpp_and_csharp_match_via_letter_token():
    # "C++"/"C#" reduce to the token "c"; a title literally containing "C++"
    # tokenizes to "c" and matches, while an unrelated "Cython" does not.
    assert is_on_topic("C++", "C++ documentary")
    assert tr("C++", "C++ documentary") == 0.9
    assert not is_on_topic("C++", "Cython tutorial")
    assert not is_on_topic("C#", "Python is great")


def test_nodejs_dotted_name():
    assert is_on_topic("Node.js", "Node.js 24 ships")     # node/js tokens present
    assert not is_on_topic("Node.js", "a quiet morning")


def test_empty_and_whitespace_query():
    assert not is_on_topic("", "anything")
    assert not is_on_topic("   ", "anything")
    assert tr("", "anything") == 0.0


def test_query_all_special_chars_is_safe():
    # Pure punctuation query must not crash or match everything.
    assert tr("+++", "anything at all") == 0.0
    assert not is_on_topic("&&&", "some title")
