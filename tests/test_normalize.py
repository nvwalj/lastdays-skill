from datetime import datetime, timezone

from lib import normalize
from lib.dates import Window
from lib.schema import Item


def test_canonical_url_normalizes():
    a = normalize.canonical_url("https://www.reddit.com/r/x/?utm_source=1")
    b = normalize.canonical_url("http://reddit.com/r/x")
    assert a == b == "https://reddit.com/r/x"


def test_dedupe_keeps_higher_score():
    a = Item(source="reddit", lang="en", title="t", url="https://x.com/a", score=10)
    b = Item(source="reddit", lang="en", title="t", url="https://www.x.com/a/", score=20)
    out = normalize.dedupe([a, b])
    assert len(out) == 1
    assert out[0].score == 20


def test_filter_window_strict_and_undated():
    w = Window(days=7, now=datetime(2026, 5, 30, tzinfo=timezone.utc))
    inw = Item(source="reddit", lang="en", title="t", url="u1", date="2026-05-28")
    outw = Item(source="reddit", lang="en", title="t", url="u2", date="2026-01-01")
    undated = Item(source="reddit", lang="en", title="t", url="u3")
    assert normalize.filter_window([inw, outw, undated], w) == [inw]
    kept = {i.url for i in normalize.filter_window([inw, outw, undated], w, allow_undated=True)}
    assert kept == {"u1", "u3"}
