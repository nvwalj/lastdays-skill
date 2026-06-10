"""Date window utilities (stdlib-only).

The whole skill is built around a single configurable window: "the last N days",
default 30. `parse_days` is the one validation rule shared by the CLI and tests;
`Window` carries `days` so scoring and rendering use the real window, never a
hardcoded 30.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

DEFAULT_DAYS = 30
MAX_DAYS = 365

_ISO_FORMATS = (
    "%Y-%m-%dT%H:%M:%S.%f%z",
    "%Y-%m-%dT%H:%M:%S%z",
    "%Y-%m-%dT%H:%M:%SZ",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d",
)


def parse_days(raw, default: int = DEFAULT_DAYS) -> int:
    """Coerce and validate a `--days` value. Single source of truth.

    Accepts None/'' (-> default), int, or numeric str. Rejects <= 0, > MAX_DAYS,
    and non-numeric input with ValueError.
    """
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return default
    try:
        days = int(str(raw).strip())
    except (TypeError, ValueError):
        raise ValueError(f"days must be an integer, got {raw!r}")
    if days <= 0:
        raise ValueError(f"days must be >= 1, got {days}")
    if days > MAX_DAYS:
        raise ValueError(f"days must be <= {MAX_DAYS}, got {days}")
    return days


def to_datetime(ts) -> datetime | None:
    """Best-effort parse of a timestamp into a tz-aware UTC datetime.

    Accepts datetime, unix seconds (int/float or numeric str), or ISO / YYYY-MM-DD
    strings. Returns None if it cannot be parsed (callers treat None as "no date").
    """
    if ts is None or ts == "":
        return None
    if isinstance(ts, datetime):
        # Normalize aware datetimes to UTC (not just keep their offset): callers
        # strftime the result into the item's date string, and a -05:00 instant
        # would otherwise render the source's local date, not the UTC date.
        return ts.astimezone(timezone.utc) if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
    if isinstance(ts, (int, float)):
        try:
            return datetime.fromtimestamp(float(ts), tz=timezone.utc)
        except (ValueError, OSError, OverflowError):
            return None
    s = str(ts).strip()
    if not s:
        return None
    # Unix timestamp as a string ("1716950400" or "1716950400.0").
    try:
        return datetime.fromtimestamp(float(s), tz=timezone.utc)
    except (ValueError, OSError, OverflowError):
        pass
    iso = s.replace("Z", "+0000") if s.endswith("Z") else s
    for fmt in _ISO_FORMATS:
        try:
            dt = datetime.strptime(iso, fmt)
            return dt.astimezone(timezone.utc) if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


@dataclass(frozen=True)
class Window:
    """A [cutoff, now] date window of `days` length, in UTC."""

    days: int
    now: datetime

    @classmethod
    def from_days(cls, days: int = DEFAULT_DAYS, now: datetime | None = None) -> "Window":
        return cls(days=days, now=now or datetime.now(timezone.utc))

    @property
    def cutoff(self) -> datetime:
        return self.now - timedelta(days=self.days)

    @property
    def cutoff_day_ts(self) -> int:
        """Unix ts of the cutoff DAY's 00:00 UTC. Day-quantized on purpose: a
        second-precise cutoff makes every request URL unique and defeats the
        HTTP cache. 'Last N days' is a day-grained concept, so this loses no
        meaningful precision while letting same-day repeat queries cache-hit."""
        c = self.cutoff
        day = datetime(c.year, c.month, c.day, tzinfo=timezone.utc)
        return int(day.timestamp())

    @property
    def from_date(self) -> str:
        return self.cutoff.strftime("%Y-%m-%d")

    @property
    def to_date(self) -> str:
        return self.now.strftime("%Y-%m-%d")

    def contains(self, ts) -> bool:
        """Strict membership test. Unparseable / missing dates return False.

        Allows up to one day into the future to absorb timezone skew on
        freshly-posted items.
        """
        dt = to_datetime(ts)
        if dt is None:
            return False
        return self.cutoff <= dt <= self.now + timedelta(days=1)

    def recency(self, ts) -> float:
        """0..1 freshness: today -> 1.0, `days` ago -> 0.0, unknown -> 0.0."""
        dt = to_datetime(ts)
        if dt is None:
            return 0.0
        age_days = (self.now - dt).total_seconds() / 86400.0
        if age_days <= 0:
            return 1.0
        if age_days >= self.days:
            return 0.0
        return 1.0 - (age_days / self.days)


# Back-compat helper mirroring the upstream lastXdays API.
def get_date_range(days: int = DEFAULT_DAYS):
    w = Window.from_days(days)
    return w.from_date, w.to_date


def pages_for_window(days: int, *, base_days: int = 30, max_pages: int = 4) -> int:
    """How many API pages to fetch for a window of `days`.

    A single API response is capped (HN ~30, GitHub per-page), so a longer window
    returns the SAME count over a wider span unless we page-walk. Scale pages with
    the window — roughly one extra page per `base_days` — so "last 180 days" can
    actually surface more history than "last 7 days", while short windows stay at
    a single request. Capped at max_pages to respect rate limits (esp. GitHub).
    """
    if days <= base_days:
        return 1
    return min(max_pages, 1 + (days - 1) // base_days)
