"""Xiaohongshu local-bridge source: probe gating, zh counts, detail dating."""

from datetime import datetime, timezone

import lastdays as engine
from lib.dates import Window
from lib.sources import xiaohongshu as xhs


def _w(days=7):
    return Window(days=days, now=datetime(2026, 6, 10, tzinfo=timezone.utc))


# --- helpers -----------------------------------------------------------------

def test_zh_count_parses_wan_yi_and_ints():
    assert xhs._zh_count("1.2万") == 12000
    assert xhs._zh_count("3亿") == 300_000_000
    assert xhs._zh_count("156") == 156
    assert xhs._zh_count(42) == 42
    assert xhs._zh_count("赞") == 0
    assert xhs._zh_count(None) == 0
    assert xhs._zh_count("-5") == 0          # regex rejects negatives -> 0
    assert xhs._zh_count("10万+") == 100_000  # XHS truncated-count suffix
    assert xhs._zh_count("1000+") == 1000


def test_publish_time_never_emits_one_month():
    # Upstream filterOptionsMap has no 一个月内 (the CN-fork bug). 30d -> 半年内.
    assert xhs._publish_time(1) == "一天内"
    assert xhs._publish_time(7) == "一周内"
    assert xhs._publish_time(30) == "半年内"
    assert xhs._publish_time(365) == "半年内"


# --- probe -------------------------------------------------------------------

def test_probe_false_when_unreachable(monkeypatch):
    def boom(*a, **k):
        raise xhs.http.HTTPError("connection refused")
    monkeypatch.setattr(xhs.http, "request", boom)
    assert xhs.probe({}) is False


def test_probe_respects_login_state(monkeypatch):
    monkeypatch.setattr(
        xhs.http, "request",
        lambda *a, **k: '{"success": true, "data": {"is_logged_in": false}}')
    assert xhs.probe({}) is False
    monkeypatch.setattr(
        xhs.http, "request",
        lambda *a, **k: '{"success": true, "data": {"is_logged_in": true}}')
    assert xhs.probe({}) is True


def test_probe_bypasses_get_cache(monkeypatch):
    seen = {}
    def fake_request(method, url, **kw):
        seen.update(kw, method=method)
        return '{"data": {"is_logged_in": true}}'
    monkeypatch.setattr(xhs.http, "request", fake_request)
    assert xhs.probe({}) is True
    assert seen.get("raw") is True            # raw=True skips the day-TTL cache


# --- fetch -------------------------------------------------------------------

def _feed(fid, title, likes="1.2万", token="tok"):
    return {
        "id": fid,
        "xsecToken": token,
        "noteCard": {
            "displayTitle": title,
            "user": {"nickname": "小白"},
            "interactInfo": {"likedCount": likes, "commentCount": "88", "collectedCount": "2300"},
        },
    }


def _detail(t_ms, desc="详情描述", title=None):
    note = {"time": t_ms, "desc": desc}
    if title:
        note["title"] = title
    return {"success": True, "data": {"data": {"note": note}}}


def _wire(monkeypatch, feeds, details):
    """details: feed_id -> detail response (or Exception to raise)."""
    def fake_post(url, body, **kw):
        if url.endswith("/feeds/search"):
            return {"success": True, "data": {"feeds": feeds, "count": len(feeds)}}
        fid = body["feed_id"]
        d = details[fid]
        if isinstance(d, Exception):
            raise d
        return d
    monkeypatch.setattr(xhs.http, "post", fake_post)


def test_fetch_dates_from_detail_in_utc(monkeypatch):
    # 2026-06-08 16:00 UTC in epoch ms.
    t_ms = int(datetime(2026, 6, 8, 16, 0, tzinfo=timezone.utc).timestamp() * 1000)
    _wire(monkeypatch, [_feed("abc", "AI 编程笔记")], {"abc": _detail(t_ms, title="AI 编程实战")})
    items = xhs.fetch("AI 编程", _w(), env={})
    assert len(items) == 1
    it = items[0]
    assert it.date == "2026-06-08" and abs(it.ts - t_ms / 1000) < 1
    assert it.title == "AI 编程实战"              # detail title wins over card title
    assert it.url == "https://www.xiaohongshu.com/explore/abc"
    assert it.engagement == {"likes": 12000, "comments": 88, "collects": 2300}
    assert it.author == "小白"
    assert it.item_id == "xhsabc"
    assert it.metadata["bridge"] == "xiaohongshu-mcp"


def test_fetch_drops_notes_without_timestamp(monkeypatch):
    # No time in detail -> dropped, never guessed; bad detail call -> skipped.
    t_ms = int(datetime(2026, 6, 9, tzinfo=timezone.utc).timestamp() * 1000)
    _wire(monkeypatch,
          [_feed("a", "AI 编程一"), _feed("b", "AI 编程二"), _feed("c", "AI 编程三")],
          {"a": _detail(None), "b": xhs.http.HTTPError("500"), "c": _detail(t_ms)})
    items = xhs.fetch("AI 编程", _w(), env={})
    assert [it.item_id for it in items] == ["xhsc"]


def test_fetch_gates_off_topic_and_ranks_by_likes(monkeypatch):
    t_ms = int(datetime(2026, 6, 9, tzinfo=timezone.utc).timestamp() * 1000)
    feeds = [
        _feed("low", "AI 编程入门", likes="100"),
        _feed("noise", "周末探店日记", likes="9999万"),   # off-topic -> gated out
        _feed("hot", "AI 编程避坑", likes="2万"),
    ]
    _wire(monkeypatch, feeds, {"low": _detail(t_ms), "hot": _detail(t_ms)})
    items = xhs.fetch("AI 编程", _w(7), env={})
    # noise never reaches a detail call; hot (more likes) detailed before low.
    assert [it.item_id for it in items] == ["xhshot", "xhslow"]


def test_fetch_respects_depth_cap(monkeypatch):
    t_ms = int(datetime(2026, 6, 9, tzinfo=timezone.utc).timestamp() * 1000)
    feeds = [_feed(f"f{i}", f"AI 编程 {i}") for i in range(8)]
    _wire(monkeypatch, feeds, {f"f{i}": _detail(t_ms) for i in range(8)})
    assert len(xhs.fetch("AI 编程", _w(), env={}, depth="quick")) == 3


def test_fetch_search_failure_returns_empty(monkeypatch):
    def boom(*a, **k):
        raise xhs.http.HTTPError("bridge gone")
    monkeypatch.setattr(xhs.http, "post", boom)
    assert xhs.fetch("AI", _w(), env={}) == []
    monkeypatch.setattr(xhs.http, "post", lambda *a, **k: {"data": {"feeds": "wat"}})
    assert xhs.fetch("AI", _w(), env={}) == []


def test_fetch_sends_valid_publish_time(monkeypatch):
    sent = {}
    def fake_post(url, body, **kw):
        if url.endswith("/feeds/search"):
            sent.update(body)
            return {"data": {"feeds": []}}
        raise AssertionError("no detail expected")
    monkeypatch.setattr(xhs.http, "post", fake_post)
    xhs.fetch("AI 编程", _w(30), env={})
    assert sent["filters"]["publish_time"] == "半年内"
    assert sent["filters"]["sort_by"] == "最新"   # >7d: lead detail slots to fresh notes
    assert sent["keyword"] == "AI 编程"
    xhs.fetch("AI 编程", _w(7), env={})
    assert sent["filters"]["publish_time"] == "一周内"
    assert sent["filters"]["sort_by"] == "综合"   # platform filter already in-window


# --- orchestrator promotion ---------------------------------------------------

def test_run_promotes_bridge_source_when_probe_passes(monkeypatch):
    # Source is a frozen dataclass, so steer the STORED probe via its http call.
    monkeypatch.setattr(
        xhs.http, "request", lambda *a, **k: '{"data": {"is_logged_in": true}}')
    t_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    _wire(monkeypatch, [_feed("abc", "AI 编程笔记")], {"abc": _detail(t_ms)})
    report = engine.run("AI 编程", 7, "zh", "xiaohongshu", "default", False, {})
    assert report.items_by_source.get("xiaohongshu")          # ran in the ENGINE
    assert not report.web_layers_requested                    # not a web layer this run


def test_run_keeps_web_layer_when_bridge_down(monkeypatch):
    def refused(*a, **k):
        raise xhs.http.HTTPError("connection refused")
    monkeypatch.setattr(xhs.http, "request", refused)
    report = engine.run("AI 编程", 7, "zh", "xiaohongshu", "default", False, {})
    assert "xiaohongshu" not in report.items_by_source
    assert any("xiaohongshu" in w for w in report.web_layers_requested)


# --- codex-review regressions (probe drift, whole-source budget, rollback) ----

def test_probe_non_dict_data_field_is_false(monkeypatch):
    # API drift: data is a string, not an object -> False, never AttributeError.
    monkeypatch.setattr(xhs.http, "request", lambda *a, **k: '{"data": "ok"}')
    assert xhs.probe({}) is False
    monkeypatch.setattr(xhs.http, "request", lambda *a, **k: '[1, 2]')
    assert xhs.probe({}) is False


def test_budget_caps_whole_source_no_detail_after_search(monkeypatch):
    # Budget ~0 is already spent once search returns -> NO detail call may fire
    # (details={} would KeyError if one did) and search timeout is clamped >= 2.
    seen = {}
    def fake_post(url, body, **kw):
        if url.endswith("/feeds/search"):
            seen["timeout"] = kw.get("timeout")
            return {"data": {"feeds": [_feed("a", "AI 编程笔记")]}}
        raise AssertionError("detail call fired past the budget")
    monkeypatch.setattr(xhs.http, "post", fake_post)
    items = xhs.fetch("AI 编程", _w(), env={"LASTDAYS_XHS_BUDGET": "0.5"})
    assert items == []
    assert seen["timeout"] == 2                  # clamped floor, not the full 30


def test_run_restores_web_layer_when_promoted_bridge_returns_nothing(monkeypatch):
    # Probe passes (promotion happens) but search yields nothing -> the
    # site:xiaohongshu.com fallback line must come back; coverage never shrinks.
    monkeypatch.setattr(
        xhs.http, "request", lambda *a, **k: '{"data": {"is_logged_in": true}}')
    monkeypatch.setattr(xhs.http, "post", lambda *a, **k: {"data": {"feeds": []}})
    report = engine.run("AI 编程", 7, "zh", "xiaohongshu", "default", False, {})
    assert not report.items_by_source.get("xiaohongshu")
    assert any("xiaohongshu" in w and "bridge ran but returned nothing" in w
               for w in report.web_layers_requested)


def test_fetch_tolerates_epoch_seconds(monkeypatch):
    # A seconds-emitting bridge build must not date everything to 1970.
    t_s = int(datetime(2026, 6, 9, tzinfo=timezone.utc).timestamp())
    _wire(monkeypatch, [_feed("a", "AI 编程笔记")], {"a": _detail(t_s)})
    items = xhs.fetch("AI 编程", _w(), env={})
    assert items and items[0].date == "2026-06-09"


def test_run_30d_overfetch_narrowed_by_window_with_fallback(monkeypatch):
    # 半年内 over-fetch: a note dated outside the 30d window must be dropped by
    # filter_window and the WebSearch fallback line restored.
    monkeypatch.setattr(
        xhs.http, "request", lambda *a, **k: '{"data": {"is_logged_in": true}}')
    from datetime import timedelta
    old_ms = int((datetime.now(timezone.utc) - timedelta(days=90)).timestamp() * 1000)
    _wire(monkeypatch, [_feed("old", "AI 编程旧帖")], {"old": _detail(old_ms)})
    report = engine.run("AI 编程", 30, "zh", "xiaohongshu", "default", False, {})
    assert not report.items_by_source.get("xiaohongshu")
    assert any("bridge ran but returned nothing" in w for w in report.web_layers_requested)
