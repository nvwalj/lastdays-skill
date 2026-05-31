from datetime import datetime, timezone

import pytest

from lib import dates
from lib.dates import Window


def test_parse_days_default():
    assert dates.parse_days(None) == 30
    assert dates.parse_days("") == 30
    assert dates.parse_days("7") == 7
    assert dates.parse_days(14) == 14


@pytest.mark.parametrize("bad", ["0", "-1", "366", "999", "abc", "1.5"])
def test_parse_days_invalid(bad):
    with pytest.raises(ValueError):
        dates.parse_days(bad)


def test_window_dates():
    w = Window(days=7, now=datetime(2026, 5, 30, tzinfo=timezone.utc))
    assert w.to_date == "2026-05-30"
    assert w.from_date == "2026-05-23"


def test_window_contains_strict():
    w = Window(days=7, now=datetime(2026, 5, 30, 12, 0, tzinfo=timezone.utc))
    in_ts = datetime(2026, 5, 25, tzinfo=timezone.utc).timestamp()
    assert w.contains("2026-05-25")
    assert w.contains(in_ts)
    assert not w.contains("2026-01-01")   # out of window
    assert not w.contains(None)           # missing
    assert not w.contains("garbage")      # unparseable


def test_recency():
    w = Window(days=10, now=datetime(2026, 5, 30, tzinfo=timezone.utc))
    assert w.recency("2026-05-30") == 1.0
    assert w.recency("2026-05-20") == 0.0
    assert w.recency(None) == 0.0
    assert 0.4 < w.recency("2026-05-25") < 0.6
