"""No-strongly-relevant-results signal in the compact evidence block: a source
whose items are all at the no-match floor is flagged, and when the WHOLE pool is
weak a global NOTE tells the agent to lean on web layers + lower confidence."""

from lib import render
from lib.schema import Item, Report


def _report(items_by_source, topic="web scraping anti-bot"):
    r = Report(topic=topic, days=30, from_date="2026-05-12", to_date="2026-06-11",
               generated_at="2026-06-11T00:00:00Z")
    r.items_by_source = items_by_source
    return r


def _i(source, title, rel):
    return Item(source=source, lang="en", title=title, url=f"https://e/{abs(hash(title))%10**9}",
                date="2026-06-01", relevance=rel, score=10.0)


def test_weak_source_flagged():
    rep = _report({"hackernews": [_i("hackernews", "We forget", 0.25), _i("hackernews", "Random AMA", 0.3)]})
    out = render.render_compact(rep)
    assert "## hackernews (2)" in out
    assert "no strongly-relevant results in-window" in out


def test_strong_source_not_flagged():
    rep = _report({"hackernews": [_i("hackernews", "A web scraping anti-bot toolkit", 0.9),
                                  _i("hackernews", "noise", 0.25)]})
    out = render.render_compact(rep)
    # the source has a strong item -> no per-source weak flag, no global note
    assert "no strongly-relevant results" not in out


def test_partial_match_is_not_weak():
    # 2-of-4-token partial == 0.4 == ceiling -> NOT flagged (it's a real partial).
    rep = _report({"hackernews": [_i("hackernews", "web scraping news", 0.4)]})
    assert "no strongly-relevant results" not in render.render_compact(rep)


def test_global_note_when_entire_pool_weak():
    rep = _report({
        "hackernews": [_i("hackernews", "We forget", 0.25)],
        "github": [_i("github", "unrelated/repo", 0.3)],
    })
    out = render.render_compact(rep)
    assert "NOTE: no strongly-relevant engine results" in out
    assert 'for "web scraping anti-bot"' in out


def test_no_global_note_when_any_strong():
    rep = _report({
        "hackernews": [_i("hackernews", "We forget", 0.25)],
        "reddit": [_i("reddit", "web scraping anti-bot guide", 0.6)],
    })
    out = render.render_compact(rep)
    assert "NOTE: no strongly-relevant engine results" not in out  # reddit is strong
    assert "## hackernews (1)" in out and "no strongly-relevant results in-window" in out  # HN still flagged
