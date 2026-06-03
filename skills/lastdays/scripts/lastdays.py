#!/usr/bin/env python3
"""lastdays engine entrypoint.

Fetches zero-key public sources (Reddit / Hacker News / GitHub / Polymarket) for
a topic over the last N days (default 30), with real engagement and a strict
date window, and prints a structured evidence block. The agent host does the
planning + synthesis and fills the web / X / Chinese layers via WebSearch.

Usage:
    python3 lastdays.py "<topic>" [--days N] [--lang en|zh|both]
                        [--sources reddit,hn,...] [--depth quick|default|deep]
                        [--emit compact|json] [--allow-undated] [--diagnose]
"""

from __future__ import annotations

import argparse
import concurrent.futures
import datetime
import os
import sys

MIN_PYTHON = (3, 12)
if sys.version_info < MIN_PYTHON:
    sys.stderr.write(f"lastdays requires Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+\n")
    raise SystemExit(1)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lib import dates, normalize, registry, score, tiers  # noqa: E402
from lib import env as env_mod  # noqa: E402
from lib import http as http_mod  # noqa: E402
from lib import providers  # noqa: E402
from lib import render as render_mod  # noqa: E402
from lib import sources as _sources  # noqa: E402,F401  import side effect: registers sources
from lib.schema import Report  # noqa: E402

_ZH_DOMAINS = {
    "weibo": "weibo.com",
    "xiaohongshu": "xiaohongshu.com",
    "douyin": "douyin.com",
    "zhihu": "zhihu.com",
    "bilibili": "bilibili.com",
}
_LAYER_LABELS = {
    "web": "Open web articles/blogs - WebSearch the topic with a recency filter",
    "x": "X / Twitter discussion - WebSearch site:x.com",
}


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _diagnose() -> int:
    cfg = env_mod.get_config()
    auth = env_mod.openai_auth(cfg)
    print("lastdays sources:")
    for s in registry.all_sources():
        kind = "engine" if s.name in registry.ENGINE_SOURCES else "agent-web"
        status = "ok" if s.implemented else "stub"
        need = " (needs key/cookie)" if s.requires_key else ""
        print(f"  - {s.name:12} lang={s.lang}  {kind:9} [{status}]{need}")
    print(f"openai auth : {auth['source']}")
    has_gh = bool(cfg.get("GITHUB_TOKEN") or cfg.get("GH_TOKEN"))
    print(f"github token: {'set' if has_gh else 'not set (keyless, lower rate limit)'}")
    return 0


def run(topic, days, lang, sources_arg, depth, allow_undated, config):
    window = dates.Window.from_days(days)
    requested = registry.resolve_names(sources_arg, lang)
    engine_targets = [n for n in requested if n in registry.ENGINE_SOURCES]
    web_layers = [n for n in requested if n not in registry.ENGINE_SOURCES]

    report = Report(
        topic=topic,
        days=days,
        from_date=window.from_date,
        to_date=window.to_date,
        generated_at=_now_iso(),
    )

    def _fetch(name):
        items, _tier = tiers.run_tiers(registry.get(name), topic, window, env=config, depth=depth)
        return name, items

    raw: dict[str, list] = {}
    if engine_targets:
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(8, len(engine_targets))) as ex:
            futs = {ex.submit(_fetch, n): n for n in engine_targets}
            for fut in concurrent.futures.as_completed(futs):
                name = futs[fut]
                try:
                    _, items = fut.result(timeout=60)
                    raw[name] = items
                except Exception as e:  # noqa: BLE001  one source must never kill the run
                    report.errors_by_source[name] = f"{type(e).__name__}: {e}"
                    raw[name] = []

    # per-source: strict window filter -> score -> rank
    for name in engine_targets:
        items = normalize.filter_window(raw.get(name, []), window, allow_undated=allow_undated)
        score.score_items(items, window)
        report.items_by_source[name] = score.rank(items)

    # cross-source URL dedupe (preserve per-source grouping)
    seen: set[str] = set()
    for name in engine_targets:
        kept = []
        for it in report.items_by_source.get(name, []):
            key = normalize.canonical_url(it.url)
            if key and key in seen:
                continue
            if key:
                seen.add(key)
            kept.append(it)
        report.items_by_source[name] = kept

    # layers the engine does not cover -> route to the agent's WebSearch
    for name in web_layers:
        src = registry.get(name)
        if src and src.lang == "zh":
            report.web_layers_requested.append(
                f"{name} (site:{_ZH_DOMAINS.get(name, name)}) - Chinese source, not yet in engine"
            )
        else:
            report.web_layers_requested.append(_LAYER_LABELS.get(name, name))

    total = sum(len(v) for v in report.items_by_source.values())
    if not engine_targets and not web_layers:
        report.warnings.append("no sources resolved for the requested --lang/--sources")
    elif engine_targets and total == 0:
        report.warnings.append(
            "engine sources returned 0 items in-window - supplement via WebSearch and lower confidence"
        )
    return report


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="lastdays", description="Research a topic over the last N days.")
    ap.add_argument("topic", nargs="*", help="research topic")
    ap.add_argument("--days", default=None, help="window size in days (default 30, range 1..365)")
    ap.add_argument("--lang", default="en", choices=["en", "zh", "both"], help="source language group")
    ap.add_argument("--sources", default=None, help="comma-separated source names/aliases (overrides --lang)")
    ap.add_argument("--depth", default="default", choices=["quick", "default", "deep"])
    ap.add_argument("--emit", default="compact", choices=["compact", "json"])
    ap.add_argument("--allow-undated", action="store_true", help="keep items with no detectable date")
    ap.add_argument(
        "--provider",
        default="local",
        choices=["local", "auto", "openai", "anthropic"],
        help="reasoning provider for --synthesize: local=agent host does it; auto=subscription-first; or force openai/anthropic",
    )
    ap.add_argument(
        "--synthesize",
        action="store_true",
        help="also emit a brief via a reasoning provider (headless/cron; subscription-first, API key optional)",
    )
    ap.add_argument("--debug", action="store_true")
    ap.add_argument("--diagnose", action="store_true", help="list sources + auth status, then exit")
    args = ap.parse_args(argv)

    if args.debug:
        http_mod.set_debug(True)
    if args.diagnose:
        return _diagnose()

    topic = " ".join(args.topic).strip()
    if not topic:
        ap.error('a topic is required, e.g. lastdays "Claude Code" --days 7')
    try:
        days = dates.parse_days(args.days)
    except ValueError as e:
        ap.error(str(e))

    config = env_mod.get_config()
    report = run(topic, days, args.lang, args.sources, args.depth, args.allow_undated, config)
    print(render_mod.render(report, args.emit))

    if args.synthesize:
        prov = "auto" if args.provider == "local" else args.provider
        pname, client = providers.resolve_runtime(config, prov)
        if client is None:
            sys.stderr.write(
                "[synthesis] no reasoning provider available - in an agent host the agent "
                "synthesizes; for headless use pass --provider openai|anthropic with a "
                "Codex/ChatGPT login or an API key.\n"
            )
        else:
            try:
                brief = providers.synthesize(
                    client, report.topic, report.days, render_mod.render_compact(report)
                )
                print(f"\n## Synthesis ({pname})\n\n{brief.strip()}")
            except Exception as e:  # noqa: BLE001  synthesis is optional; never crash the run
                sys.stderr.write(f"[synthesis] {pname} call failed: {type(e).__name__}: {e}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
