"""Emit the engine report as JSON or a compact evidence block for the agent."""

from __future__ import annotations

import json

from .schema import Report


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
        out.append(f"## {src} ({len(items)})")
        for it in items:
            eng = " ".join(f"{k}={v}" for k, v in (it.engagement or {}).items() if v)
            head = f"- [{it.item_id or src}] score={it.score:.0f} | {it.date or 'undated'}"
            if it.container:
                head += f" | {it.container}"
            if eng:
                head += f" | {eng}"
            out.append(head)
            out.append(f"  {it.title}")
            out.append(f"  {it.url}")
            if it.snippet:
                out.append(f"  > {it.snippet[:240].strip()}")
        out.append("")
    out.append("<!-- END EVIDENCE FOR SYNTHESIS -->")
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
