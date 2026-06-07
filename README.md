# lastdays

English | [简体中文](README.zh-CN.md)

**Research what people actually said about a topic in the last N days (default 30, configurable) — zero config, runs on your subscription, burns no API keys.**

A lean, subscription-friendly rewrite of the multi-source "last 30 days" research
skill. A zero-key Python engine pulls **Reddit, Hacker News, GitHub, and
Polymarket** with real engagement (upvotes, points, comments, volume) inside a
strict, configurable date window. The agent host (Claude Code or OpenAI Codex)
plans the targeting, fills the open-web / X / Chinese layers via WebSearch, and
synthesizes one grounded, cited brief. No API key required — the agent is the LLM.

## What's different from the original

- **Configurable window.** `--days N` (default 30, range 1–365), strictly enforced.
- **Subscription-only, zero cost.** Engine uses stdlib + keyless public APIs; reasoning is done by your Claude/Codex subscription. No ScrapeCreators/Brave/OpenRouter keys.
- **Built to grow into Chinese media.** A source registry with a one-function contract; Bilibili and Douyin are implemented, Weibo / Xiaohongshu / Zhihu ship as registered stubs ready to implement.
- **Claude + OpenAI only.** Claude Code plugin (`.claude-plugin/plugin.json`) and OpenAI Codex adapter (`agents/openai.yaml`).

## Install

```bash
bash install.sh            # symlinks skills/lastdays -> ~/.claude/skills/lastdays
```

Then, inside Claude Code:

```
/lastdays Claude Code 7
/lastdays nvidia earnings
/lastdays "AI video tools" 14 --lang both
```

## Usage (engine directly)

```bash
python3 skills/lastdays/scripts/lastdays.py "Claude Code" --days 7 --emit compact
python3 skills/lastdays/scripts/lastdays.py "AI agents" --lang zh --emit json
python3 skills/lastdays/scripts/lastdays.py --diagnose      # list sources + auth status
```

| Flag | Meaning |
|------|---------|
| `--days N` | window size, default 30, range 1–365 |
| `--lang en\|zh\|both` | source language group (default `en`) |
| `--sources a,b,c` | pick sources (aliases: `hn`, `gh`, `pm`, `r`) |
| `--depth quick\|default\|deep` | result volume per source |
| `--emit compact\|json` | evidence block (default) or JSON |
| `--allow-undated` | keep items with no detectable date |
| `--synthesize` | also emit a brief via a reasoning provider (headless/cron) |
| `--provider local\|auto\|openai\|anthropic` | provider for `--synthesize` (default `local` = the agent host) |
| `--diagnose` | list sources + OpenAI/GitHub auth, then exit |

## Synthesis (optional, headless)

In Claude Code the agent writes the brief itself - **zero cost, default, no flag needed**.
For headless/cron use, `--synthesize` makes the engine write the brief too, **subscription-first**:
it uses your ChatGPT/Codex login if present (no API key, no spend) and falls back to a paid
`OPENAI_API_KEY` / `ANTHROPIC_API_KEY`. Synthesis failures never affect the engine's evidence output.

Note: OpenAI's Codex subscription endpoint is unofficial and currently flaky (HTTP 400). For a
reliable headless brief, use `--provider anthropic` with `ANTHROPIC_API_KEY`, or set
`LASTDAYS_OPENAI_PREFER_KEY=1` with `OPENAI_API_KEY`.

## Source matrix

| Source | Lang | Engine | Engagement | Status |
|--------|------|--------|------------|--------|
| Hacker News | en | ✅ Algolia | points, comments | keyless |
| Lobsters | en | ✅ hot list | score, comments | keyless — hot-list match (no JSON search), tech-focused |
| GitHub | en | ✅ Search API | comments, reactions | keyless (`GITHUB_TOKEN` lifts limit) |
| Reddit | en | ✅ public `.json` | score, comments | keyless (403 on datacenter IPs → agent supplements) |
| Polymarket | en | ✅ Gamma | volume | keyless (403 on datacenter IPs → agent supplements) |
| Bilibili | zh | ✅ wbi search | views, danmaku, favorites | keyless (anonymous buvid3 + wbi md5 sign) |
| Douyin | zh | ✅ hot-search board | hot_value, rank | keyless — trending-board match, not full search |
| Weibo / Zhihu / Xiaohongshu | zh | ⏳ stub | — | login-walled / anti-bot → agent WebSearch `site:` |
| Open web / X | any | — | — | agent WebSearch |

See [`skills/lastdays/references/source-policy.md`](skills/lastdays/references/source-policy.md)
for the contract and a step-by-step guide to turning a Chinese stub into a real fetcher.

## Layout

```
.claude-plugin/plugin.json     Claude Code plugin manifest
agents/openai.yaml             OpenAI Codex adapter
skills/lastdays/
  SKILL.md                     agent instruction contract
  references/                  source-policy.md, synthesis-rules.md
  scripts/lastdays.py          CLI + orchestration
  scripts/lib/                 dates, schema, registry, http, normalize, score,
                               env, providers, render, sources/
tests/                         pytest (stdlib-only, offline)
```

## Requirements

Python 3.12+ (engine has **zero** third-party dependencies). Run tests with `python3 -m pytest`.

## License

MIT
