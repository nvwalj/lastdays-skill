"""Demand-mining orchestration — reuses the topic engine, changes nothing in it.

Key insight (measured): searching a DOMAIN ("self hosted") returns declarative
titles ("Self-hosted X released"), not needs -- so domain-query + demand-filter
yields ~0. Demand lives in SIGNAL PHRASES ("is there a tool that…", "I wish
there was…"), so we query those instead, gather candidate need-posts across
sources, demand-gate them (lib.demand), optionally narrow to a domain, and rank
by opportunity = demand strength tempered by recency. Engagement is carried but
NOT scored: the real validation is FREQUENCY across posts, which the agent
computes after clustering. Output = ranked DemandSignal list for the agent to
cluster into JTBD opportunities and score à la Ulwick.
"""

from __future__ import annotations

import concurrent.futures
from dataclasses import asdict, dataclass

from . import registry, tiers
from .dates import Window
from .demand import DEMAND_THRESHOLD, demand_signal
from .sources.base import is_on_topic

DEADLINE = 45  # total fetch budget (seconds); a wedged source can't hang the run

# Signal phrases that surface need-posts directly (the post title IS the need).
# Ordered best-first so a max_queries cap keeps the highest-value phrases.
SIGNAL_QUERIES = [
    "is there a tool",
    "I wish there was",
    "I'd pay for",
    "someone should build",
    "there has to be a better way",
    "anyone else struggle with",
    "what do you use for",
    "is there an app",
]

# Convenience source set for demand mining: technical communities only. Excludes
# bluesky / CJK-video sources, whose social chatter dilutes product-demand
# signals (measured: open radar with bluesky was much noisier than without).
TECH_SOURCES = ["hackernews", "stackexchange", "github", "lemmy", "reddit"]


@dataclass
class DemandSignal:
    source: str
    title: str
    url: str
    author: str | None
    date: str | None
    signal_type: str
    demand_score: float
    engagement: int
    opportunity: float

    def to_dict(self) -> dict:
        return asdict(self)


def _opportunity(demand_score: float, recency: float) -> float:
    """Demand strength dominates; recency lightly tempers. Frequency/breadth —
    the main validation — is added by the agent after clustering, not here."""
    return round(demand_score * (0.7 + 0.3 * recency), 3)


def _in_window(it, window: Window, allow_undated: bool) -> bool:
    stamp = it.ts if it.ts is not None else it.date
    if stamp is None or stamp == "":
        return allow_undated
    return window.contains(stamp)


def mine(window: Window, *, sources: list[str], env: dict, domain: str | None = None,
         queries: list[str] | None = None, depth: str = "default",
         threshold: float = DEMAND_THRESHOLD, allow_undated: bool = False,
         max_queries: int = 8) -> list[DemandSignal]:
    """Query signal phrases across engine sources -> demand-gate -> optional
    domain narrow -> rank by opportunity. `domain=None` = open need radar."""
    qs = (queries or SIGNAL_QUERIES)[:max_queries]
    targets = [n for n in sources if n in registry.ENGINE_SOURCES]
    tasks = [(name, q) for name in targets for q in qs]
    collected: list = []

    def _fetch(name, q):
        items, _ = tiers.run_tiers(registry.get(name), q, window, env=env, depth=depth)
        return name, items

    if tasks:
        ex = concurrent.futures.ThreadPoolExecutor(max_workers=min(8, len(tasks)))
        futs = {ex.submit(_fetch, n, q): (n, q) for n, q in tasks}
        pending = set(futs)
        try:
            for fut in concurrent.futures.as_completed(futs, timeout=DEADLINE):
                pending.discard(fut)
                try:
                    name, items = fut.result()
                    collected.extend((name, it) for it in items)
                except Exception:  # noqa: BLE001  one task must never kill the run
                    pass
        except concurrent.futures.TimeoutError:
            for fut in pending:  # tasks that blew the deadline
                fut.cancel()
        ex.shutdown(wait=False)

    signals: list[DemandSignal] = []
    seen: set = set()
    for name, it in collected:
        # (source, id) key: a post matching several signal queries collapses once,
        # and source-namespacing rules out any cross-source item_id collision.
        key = (name, it.item_id)
        if key in seen:
            continue
        if not _in_window(it, window, allow_undated):
            continue
        text = f"{it.title} {it.snippet or ''}".strip()
        sc, ty = demand_signal(text)
        if ty is None or sc < threshold:
            continue
        if domain and not is_on_topic(domain, text):  # optional narrow to a domain
            continue
        seen.add(key)
        rec = window.recency(it.ts if it.ts is not None else it.date)
        signals.append(
            DemandSignal(
                source=name,
                title=it.title,
                url=it.url,
                author=it.author,
                date=it.date,
                signal_type=ty,
                demand_score=sc,
                engagement=it.engagement_total(),
                opportunity=_opportunity(sc, rec),
            )
        )
    return sorted(signals, key=lambda s: (s.opportunity, s.engagement), reverse=True)
