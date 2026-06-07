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


def test_relevance_gate_keeps_offtopic_viral_below_relevant():
    # A high-engagement off-topic item must NOT outrank a genuinely relevant one.
    w = Window(days=7, now=datetime(2026, 6, 7, tzinfo=timezone.utc))
    viral_noise = Item(
        source="hackernews", lang="en", title="viral but off topic", url="n",
        date="2026-06-06", ts=_ts(2026, 6, 6),
        engagement={"points": 400, "comments": 200}, relevance=0.25,
    )
    quiet_relevant = Item(
        source="hackernews", lang="en", title="exactly what you searched", url="r",
        date="2026-06-06", ts=_ts(2026, 6, 6),
        engagement={"points": 40, "comments": 15}, relevance=0.90,
    )
    items = [viral_noise, quiet_relevant]
    score.score_items(items, w)
    ranked = score.rank(items)
    assert ranked[0].url == "r"                  # relevant wins despite 10x less engagement
    assert ranked[0].score > ranked[1].score


def test_engagement_raw_unknown_is_none():
    assert score.engagement_raw("hackernews", {}) is None
    assert score.engagement_raw("github", {"comments": 3}) is not None
