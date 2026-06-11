"""Adaptive precision gate (base.adaptive_topic_gate + the engine wiring).

Broad full-text sources (HN/GitHub/Polymarket) can return title-irrelevant items
that were only floored. For multi-word queries the engine drops them — but only
when enough on-topic items remain, so thin niche topics still return their weak
matches (recall over precision)."""

from datetime import datetime, timezone

import lastdays as engine
from lib.schema import Item
from lib.sources import base


def _i(title, source="hackernews"):
    return Item(source=source, lang="en", title=title, url=f"https://e/{abs(hash(title))%10**9}")


def test_token_count_en_and_cjk():
    assert base.meaningful_token_count("web scraping anti-bot") >= 3
    assert base.meaningful_token_count("nvidia") == 1
    assert base.meaningful_token_count("") == 0
    assert base.meaningful_token_count("开源大模型") >= 2  # CJK bigrams


def test_single_token_query_keeps_everything():
    # One concept -> recall matters; never gate (an off-title item may body-match).
    items = [_i("Nvidia ships Blackwell"), _i("A totally unrelated story"), _i("More noise here")]
    out = base.adaptive_topic_gate("nvidia", items, lambda it: it.title)
    assert len(out) == 3


def test_drops_off_topic_when_enough_on_topic():
    # >=3 on-topic for a multi-word query -> floored noise is dropped.
    items = [
        _i("A fast web scraping framework"),
        _i("web scraping with proxies"),
        _i("anti-bot web scraping guide"),
        _i("We forget"),                 # rode in on optionalWords; title off-topic
        _i("Unrelated startup raises $5M"),
    ]
    out = base.adaptive_topic_gate("web scraping", items, lambda it: it.title)
    titles = {it.title for it in out}
    assert "We forget" not in titles and "Unrelated startup raises $5M" not in titles
    assert len(out) == 3


def test_thin_topic_keeps_all_for_recall():
    # Only 1 on-topic (< min_fill) -> keep everything rather than near-empty.
    items = [_i("A fast web scraping framework"), _i("We forget"), _i("Unrelated news")]
    out = base.adaptive_topic_gate("web scraping anti-bot", items, lambda it: it.title)
    assert len(out) == 3


def test_min_fill_boundary():
    on = [_i("web scraping one"), _i("web scraping two"), _i("web scraping three")]
    off = [_i("noise a"), _i("noise b")]
    assert len(base.adaptive_topic_gate("web scraping", on + off, lambda it: it.title)) == 3  # 3>=3 -> drop off
    assert len(base.adaptive_topic_gate("web scraping", on[:2] + off, lambda it: it.title)) == 4  # 2<3 -> keep all


# --- engine wiring: gate applies to HN/GitHub/Polymarket, not to others -------

def _run_with(monkeypatch, source, items, topic="web scraping anti-bot"):
    monkeypatch.setattr(engine.tiers, "run_tiers",
                        lambda src, *a, **k: (items if src.name == source else [], None))
    # stamp recent dates so the window filter keeps them
    now = datetime.now(timezone.utc)
    for it in items:
        it.ts = now.timestamp(); it.date = now.strftime("%Y-%m-%d")
    return engine.run(topic, 7, "en", source, "default", False, {})


def test_engine_gates_hackernews(monkeypatch):
    # Three distinct on-topic titles (pairwise dissimilar so the near-dup pass
    # doesn't merge them) + two off-topic that only rode in on optionalWords.
    items = [_i("web scraping anti-bot tool released"),
             _i("defeating cloudflare while web scraping at scale"),
             _i("python anti-bot bypass guide for scraping bots"),
             _i("We forget"), _i("Random startup AMA today")]
    rep = _run_with(monkeypatch, "hackernews", items)
    kept = {it.title for it in rep.items_by_source["hackernews"]}
    assert "We forget" not in kept and "Random startup AMA today" not in kept
    assert len(kept) == 3


def test_engine_does_not_gate_lemmy(monkeypatch):
    # Lemmy is NOT in _GATED_FULLTEXT (it gates itself at fetch); the engine must
    # not second-guess it — items pass through untouched.
    items = [_i("web scraping x", source="lemmy"), _i("zzz", source="lemmy"),
             _i("qqq", source="lemmy"), _i("www", source="lemmy")]
    rep = _run_with(monkeypatch, "lemmy", items)
    assert len(rep.items_by_source["lemmy"]) == 4
