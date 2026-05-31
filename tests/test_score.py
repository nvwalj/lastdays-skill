from datetime import datetime, timezone

from lib import score
from lib.dates import Window
from lib.schema import Item


def _ts(y, m, d):
    return datetime(y, m, d, tzinfo=timezone.utc).timestamp()


def test_score_and_rank_orders_by_signal():
    w = Window(days=30, now=datetime(2026, 5, 30, tzinfo=timezone.utc))
    hot = Item(
        source="hackernews", lang="en", title="hot", url="u1",
        date="2026-05-29", ts=_ts(2026, 5, 29),
        engagement={"points": 500, "comments": 200}, relevance=0.8,
    )
    cold = Item(
        source="hackernews", lang="en", title="cold", url="u2",
        date="2026-05-05", ts=_ts(2026, 5, 5),
        engagement={"points": 2, "comments": 0}, relevance=0.5,
    )
    items = [cold, hot]
    score.score_items(items, w)
    ranked = score.rank(items)
    assert ranked[0].url == "u1"
    assert ranked[0].score > ranked[1].score


def test_engagement_raw_unknown_is_none():
    assert score.engagement_raw("hackernews", {}) is None
    assert score.engagement_raw("github", {"comments": 3}) is not None
