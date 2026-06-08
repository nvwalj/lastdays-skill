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


def test_recency_gate_fresh_offtopic_below_stale_relevant():
    # Regression (2026-06-08): recency was NOT relevance-gated, so a brand-new
    # off-topic item (low rel, rec~1.0) banked a full recency contribution and
    # outranked an older but genuinely relevant item -- the "We Need VAT and UBI
    # crashes the top 10 of a web-scraping query" bug. Engagement is held equal
    # across both items so this test isolates the recency dimension.
    w = Window(days=30, now=datetime(2026, 6, 8, tzinfo=timezone.utc))
    eng = {"points": 50, "comments": 10}
    fresh_offtopic = Item(
        source="hackernews", lang="en", title="We Need VAT and UBI", url="off",
        date="2026-06-08", ts=_ts(2026, 6, 8), engagement=dict(eng), relevance=0.30,
    )
    stale_relevant = Item(
        source="hackernews", lang="en", title="on topic but older", url="on",
        date="2026-05-12", ts=_ts(2026, 5, 12), engagement=dict(eng), relevance=0.70,
    )
    items = [fresh_offtopic, stale_relevant]
    score.score_items(items, w)
    ranked = score.rank(items)
    assert ranked[0].url == "on"            # relevance-gated recency: relevant wins
    assert ranked[0].score > ranked[1].score


def test_engagement_raw_unknown_is_none():
    assert score.engagement_raw("hackernews", {}) is None
    assert score.engagement_raw("github", {"comments": 3}) is not None
