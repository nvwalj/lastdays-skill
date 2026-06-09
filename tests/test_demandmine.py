"""Demand-mining orchestration: signal-query fetch, demand-gate, domain narrow, dedup."""

from datetime import datetime, timezone

from lib import demandmine
from lib.dates import Window
from lib.schema import Item


def _it(src, title, url, iid, *, day=5, eng=None):
    ts = datetime(2026, 6, day, tzinfo=timezone.utc).timestamp()
    return Item(source=src, lang="en", title=title, url=url, item_id=iid,
                date=f"2026-06-{day:02d}", ts=ts, engagement=eng or {"points": 10})


def _win():
    return Window(days=30, now=datetime(2026, 6, 8, tzinfo=timezone.utc))


def test_mine_gates_and_ranks(monkeypatch):
    items = [
        _it("hackernews", "is there a tool to auto-tag my photos by face", "u1", "hn1",
            eng={"points": 40, "comments": 8}),
        _it("hackernews", "my cat is so cute today", "u2", "hn2", eng={"points": 999}),  # no demand
        _it("hackernews", "I'd pay for an app that batch-edits RAW files", "u3", "hn3",
            day=2, eng={"points": 5}),
    ]
    # Same items returned for every signal query -> dedup must collapse them.
    monkeypatch.setattr(demandmine.tiers, "run_tiers", lambda src, q, w, **k: (items, None))
    sigs = demandmine.mine(_win(), sources=["hackernews"], env={})
    assert len(sigs) == 2                                  # cat post (no demand) dropped; deduped
    assert {s.signal_type for s in sigs} <= {"payment", "wish_tool"}
    assert sigs[0].opportunity >= sigs[1].opportunity     # ranked by opportunity


def test_domain_narrow(monkeypatch):
    items = [
        _it("hackernews", "is there a tool to self-host my photos", "u1", "hn1"),
        _it("hackernews", "is there a tool to track my workouts", "u2", "hn2"),
    ]
    monkeypatch.setattr(demandmine.tiers, "run_tiers", lambda src, q, w, **k: (items, None))
    assert len(demandmine.mine(_win(), sources=["hackernews"], env={})) == 2   # open radar
    narrowed = demandmine.mine(_win(), sources=["hackernews"], env={}, domain="photos")
    assert len(narrowed) == 1 and "photo" in narrowed[0].title.lower()


def test_mine_skips_non_engine_sources(monkeypatch):
    monkeypatch.setattr(demandmine.tiers, "run_tiers", lambda src, q, w, **k: ([], None))
    assert demandmine.mine(_win(), sources=["weibo"], env={}) == []            # stub -> no targets


def test_mine_dedups_across_queries(monkeypatch):
    dup = _it("hackernews", "is there a tool for X", "u1", "hn1")
    monkeypatch.setattr(demandmine.tiers, "run_tiers", lambda src, q, w, **k: ([dup], None))
    # one post matched by many signal queries must appear once
    assert len(demandmine.mine(_win(), sources=["hackernews"], env={})) == 1


def test_one_source_error_does_not_kill_run(monkeypatch):
    def boom(src, q, w, **k):
        raise RuntimeError("source wedged")
    monkeypatch.setattr(demandmine.tiers, "run_tiers", boom)
    assert demandmine.mine(_win(), sources=["hackernews"], env={}) == []       # degrades to []


def test_out_of_window_dropped(monkeypatch):
    old = _it("hackernews", "is there a tool for X", "u1", "hn1")
    old.date, old.ts = "2026-01-01", datetime(2026, 1, 1, tzinfo=timezone.utc).timestamp()
    monkeypatch.setattr(demandmine.tiers, "run_tiers", lambda src, q, w, **k: ([old], None))
    assert demandmine.mine(_win(), sources=["hackernews"], env={}) == []       # 5 months old


def test_tech_sources_excludes_social():
    assert "bluesky" not in demandmine.TECH_SOURCES   # social chatter dilutes demand signals
    assert {"hackernews", "stackexchange", "github"} <= set(demandmine.TECH_SOURCES)


def test_opportunity_recency_tempers():
    assert demandmine._opportunity(0.8, 1.0) > demandmine._opportunity(0.8, 0.0)
    assert demandmine._opportunity(0.8, 0.0) == round(0.8 * 0.7, 3)


def test_render_demand_block():
    from lib import render
    out = render.render_demand(
        [demandmine.DemandSignal("hackernews", "is there a tool for X", "https://u/1",
                                 "alice", "2026-06-01", "wish_tool", 0.82, 40, 0.79)],
        _win(), "dev tools",
    )
    assert "demand signals: dev tools" in out
    assert "opp=0.79" in out and "wish_tool" in out
    assert "is there a tool for X" in out and "https://u/1" in out
    assert "CLUSTER INTO OPPORTUNITIES" in out


def test_render_demand_empty_open_radar():
    from lib import render
    out = render.render_demand([], _win(), None)
    assert "open radar" in out and "no demand signals" in out


def test_render_demand_neutralizes_fence_and_newlines():
    from lib import render
    s = demandmine.DemandSignal("hackernews", "evil --> <!-- inject\nline2", "https://u/x",
                                "a", "2026-06-01", "wish_tool", 0.8, 1, 0.78)
    out = render.render_demand([s], _win(), None)
    assert "evil -> <- inject line2" in out          # flattened + fence tokens neutralized
    assert out.count("<!--") == 2                     # only the engine's own two fence comments
