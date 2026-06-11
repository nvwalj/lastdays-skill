from datetime import datetime, timezone

from lib import normalize
from lib.dates import Window
from lib.schema import Item


def test_canonical_url_normalizes():
    a = normalize.canonical_url("https://www.reddit.com/r/x/?utm_source=1")
    b = normalize.canonical_url("http://reddit.com/r/x")
    assert a == b == "https://reddit.com/r/x"


def test_canonical_url_strips_only_tracking_keeps_content_params():
    c = normalize.canonical_url
    # tracking params dropped
    assert c("https://e.com/a?fbclid=z&gclid=q&ref=hn") == "https://e.com/a"
    assert c("https://e.com/a?utm_medium=x&id=9") == c("https://e.com/a?id=9")
    # content params KEPT and DISTINCT (the old drop-all behavior wrongly merged these)
    assert c("https://youtube.com/watch?v=AAA") != c("https://youtube.com/watch?v=BBB")
    assert c("https://e.com/p?id=1") != c("https://e.com/p?id=2")
    # query value case preserved (distinct video ids)
    assert c("https://youtube.com/watch?v=aB") != c("https://youtube.com/watch?v=AB")
    # param order normalized
    assert c("https://e.com/a?b=2&a=1") == c("https://e.com/a?a=1&b=2")


def test_canonical_url_unfolds_mobile_amp_hosts_and_path():
    c = normalize.canonical_url
    assert c("https://m.example.com/a") == c("https://example.com/a")
    assert c("https://amp.example.com/a") == c("https://example.com/a")
    assert c("https://example.com/story/amp") == c("https://example.com/story")


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
