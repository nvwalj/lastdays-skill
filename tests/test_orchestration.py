"""Engine orchestration: a wedged source must not hang the whole run — it's
abandoned at the overall deadline and recorded as a timeout error, while fast
sources still return their results."""

import time
from datetime import datetime, timezone

import lastdays as engine
from lib.schema import Item


def _items(name):
    # Stamp a recent date so the strict window filter keeps the item (the
    # orchestration is what's under test, not date filtering). Per-source unique
    # title/url so cross-source dedupe doesn't collapse them.
    ts = datetime.now(timezone.utc).timestamp()
    return [Item(source=name, lang="en", title=f"{name} story", url=f"https://e/{name}",
                 date=datetime.now(timezone.utc).strftime("%Y-%m-%d"), ts=ts)]


def test_slow_source_is_abandoned_at_deadline(monkeypatch):
    # reddit is fast; hackernews wedges past the deadline.
    def fake_run_tiers(src, topic, window, *, env, depth="default"):
        if src.name == "hackernews":
            time.sleep(5)            # exceeds the shrunk deadline below
        return _items(src.name), None

    monkeypatch.setattr(engine.tiers, "run_tiers", fake_run_tiers)
    monkeypatch.setattr(engine, "ENGINE_DEADLINE", 1)   # 1s budget for the test

    t = time.time()
    report = engine.run("topic", 7, "en", "reddit,hackernews", "default", False, {})
    elapsed = time.time() - t

    assert elapsed < 4                                   # did NOT wait the full 5s
    assert report.items_by_source.get("reddit")          # fast source returned
    assert "hackernews" in report.errors_by_source       # slow source flagged
    assert "timeout" in report.errors_by_source["hackernews"]


def test_all_fast_sources_complete(monkeypatch):
    monkeypatch.setattr(engine.tiers, "run_tiers",
                        lambda src, *a, **k: (_items(src.name), None))
    report = engine.run("topic", 7, "en", "reddit,hackernews", "default", False, {})
    assert report.items_by_source["reddit"] and report.items_by_source["hackernews"]
    assert not report.errors_by_source


def test_pool_size_runs_every_engine_source_concurrently():
    # I/O-bound fan-out: no source should queue behind another (the old min(8,N)
    # cap silently queued 4 of the 12 EN sources once Google News + arXiv landed).
    from lib import registry
    en = registry.resolve_names(None, "en")
    assert engine._pool_size(len(en)) == len(en)          # all run at once
    assert engine._pool_size(1000) == engine._MAX_WORKERS_CAP  # capped for growth
    assert engine._pool_size(0) == 1                       # never zero workers
