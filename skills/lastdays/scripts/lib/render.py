"""Emit the engine report as JSON or a compact evidence block for the agent."""

from __future__ import annotations

import json
from collections import Counter

from .schema import Report

# A source whose best item still scores below this has no real token match — every
# item is at the no-match floor (~0.3), i.e. front-page/optionalWords noise the
# adaptive gate kept only because nothing on-topic existed. We say so explicitly
# rather than letting the agent read floored noise as findings. A genuine partial
# match (e.g. 2 of 4 query tokens -> 0.4) sits at/above this and is NOT flagged.
WEAK_RELEVANCE_CEILING = 0.4


def _source_is_weak(items: list) -> bool:
    """True when no item carries a real (above-floor) relevance match."""
    return bool(items) and max((it.relevance for it in items), default=0.0) < WEAK_RELEVANCE_CEILING


def render_json(report: Report) -> str:
    return json.dumps(report.to_dict(), indent=2, ensure_ascii=False)


def render_compact(report: Report) -> str:
    """Markdown evidence block the agent reads (and transforms), never emits verbatim."""
    out: list[str] = []
    out.append(f"# lastdays evidence: {report.topic}")
    out.append(f"window: {report.from_date} .. {report.to_date} ({report.days} days)")
    counts = ", ".join(f"{s}={len(i)}" for s, i in report.items_by_source.items()) or "(none)"
    out.append(f"engine sources: {counts}")
    for s, e in report.errors_by_source.items():
        out.append(f"  ! {s} error: {e}")
    out.append("")
    out.append("<!-- EVIDENCE FOR SYNTHESIS: read this, do not emit verbatim. -->")
    for src, items in report.items_by_source.items():
        if not items:
            continue
        weak = _source_is_weak(items)
        header = f"## {src} ({len(items)})"
        if weak:
            header += "  ⚠ no strongly-relevant results in-window — weak/floor matches only; corroborate or omit"
        out.append(header)
        for it in items:
            eng = " ".join(f"{k}={v}" for k, v in (it.engagement or {}).items() if v)
            head = f"- [{it.item_id or src}] score={it.score:.0f} rel={it.relevance:.2f} | {it.date or 'undated'}"
            if it.container:
                head += f" | {it.container}"
            if eng:
                head += f" | {eng}"
            if it.is_foreign():
                head += f" | ⚠ lang={it.title_script()} (translate or skip; do not copy verbatim)"
            if it.metadata.get("degraded"):
                note = it.metadata.get("degraded_note") or "partial signal"
                head += f" | ⚠ degraded:{it.metadata.get('tier', '?')} ({note})"
            out.append(head)
            out.append(f"  {it.title}")
            out.append(f"  {it.url}")
            if it.snippet:
                out.append(f"  > {it.snippet[:240].strip()}")
        out.append("")
    out.append("<!-- END EVIDENCE FOR SYNTHESIS -->")
    out.append("")
    all_items = [it for items in report.items_by_source.values() for it in items]
    if all_items and not any(it.relevance >= WEAK_RELEVANCE_CEILING for it in all_items):
        out.append(
            f'NOTE: no strongly-relevant engine results for "{report.topic}" in the last '
            f"{report.days} days — every item is a weak/floor match. Lean on the web layers "
            "below and lower confidence; do not present these as established findings."
        )
        out.append("")
    if report.web_layers_requested:
        out.append("## WEB LAYERS TO FILL (use WebSearch/WebFetch, then synthesize)")
        out.append(
            "Not covered by the engine. Fetch these yourself, label them web-sourced "
            "(no structured engagement, rank below engine items), and keep only items "
            f"dated within {report.from_date}..{report.to_date}:"
        )
        for layer in report.web_layers_requested:
            out.append(f"- {layer}")
        out.append("")
    for w in report.warnings:
        out.append(f"NOTE: {w}")
    return "\n".join(out)


def render(report: Report, emit: str = "compact") -> str:
    return render_json(report) if emit == "json" else render_compact(report)


def _one_line(s: str) -> str:
    """Collapse whitespace and neutralize the comment fence so a hostile or
    multi-line title/url can't break the DEMAND SIGNALS block or inject a fence."""
    return " ".join((s or "").split()).replace("-->", "->").replace("<!--", "<-")


def render_demand(signals: list, window, domain: str | None = None) -> str:
    """Demand-signal block for the agent to cluster into opportunities (--mode demand)."""
    label = _one_line(domain) if domain else "open radar (no domain filter)"
    out: list[str] = []
    out.append(f"# lastdays demand signals: {label}")
    out.append(f"window: {window.from_date} .. {window.to_date} ({window.days} days)")
    out.append(f"signals: {len(signals)}")
    if signals:
        types = Counter(s.signal_type for s in signals)
        out.append("by type: " + ", ".join(f"{t}={n}" for t, n in types.most_common()))
    out.append("")
    out.append("<!-- DEMAND SIGNALS: cluster into opportunities, do not emit verbatim. -->")
    for s in signals:
        out.append(
            f"- [opp={s.opportunity:.2f}] {s.signal_type} | {s.source} | {s.date or 'undated'} | eng={s.engagement}"
        )
        out.append(f"  {_one_line(s.title)}")
        out.append(f"  {_one_line(s.url)}")
    out.append("<!-- END DEMAND SIGNALS -->")
    out.append("")
    out.append("CLUSTER INTO OPPORTUNITIES: group signals voicing the SAME underlying need;")
    out.append("infer the Job-to-be-Done (not the user's proposed solution); score")
    out.append("Opportunity = breadth (independent authors & sources) x demand strength x")
    out.append("unmet-ness; output a ranked opportunity list with evidence links. Treat")
    out.append("these as HYPOTHESES to validate by talking to users, not proven needs.")
    if not signals:
        out.append("")
        out.append("NOTE: no demand signals in-window - widen --days, broaden --sources, "
                   "or drop the domain (run with no topic for an open radar).")
    return "\n".join(out)
