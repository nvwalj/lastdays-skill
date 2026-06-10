# lastdays

English | [简体中文](README.zh-CN.md)

**Research what people actually said about a topic in the last N days (default 30, configurable) — zero config, runs on your subscription, burns no API keys.**

A lean, subscription-friendly rewrite of the multi-source "last 30 days" research
skill. A zero-key Python engine pulls **Reddit, Hacker News, GitHub, Lobsters,
Polymarket, Kalshi, Stack Overflow, Lemmy, and Bluesky** with real engagement (upvotes, points, comments, volume) inside a
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
| `--mode topic\|demand` | `topic` research (default), or `demand` to mine unmet-need signals |
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

## Demand mining (`--mode demand`)

Find unmet user needs / startup-opportunity signals instead of researching a topic.
Same engine, but it queries demand **signal phrases** ("is there a tool…", "I wish there
was…", "I'd pay for…") across technical communities, gates them by demand strength
(`lib/demand.py`), and prints a `DEMAND SIGNALS` block for you to cluster into opportunities.

```bash
python3 skills/lastdays/scripts/lastdays.py "developer tools" --mode demand --days 90
python3 skills/lastdays/scripts/lastdays.py --mode demand --days 90   # open radar (no domain)
```

Or in Claude Code: `/demandmine developer tools` — the agent runs the engine, clusters
signals into Jobs-to-be-Done, scores them Ulwick-style (breadth × demand strength ×
unmet-ness), and outputs a ranked opportunity list. Default sources are the technical set
(HN / Stack Overflow / GitHub / Lemmy / Reddit; social chatter is filtered for signal
quality). Signals are **hypotheses to validate** by talking to users, not proven demand.

## Source matrix

| Source | Lang | Engine | Engagement | Status |
|--------|------|--------|------------|--------|
| Hacker News | en | ✅ Algolia | points, comments | keyless |
| Lobsters | en | ✅ hot list | score, comments | keyless — hot-list match (no JSON search), tech-focused |
| Dev.to | en | ✅ tag API | reactions, comments | keyless — dev blog posts, tag-search + on-topic filter |
| Stack Overflow | en | ✅ search API | score, answers, views | keyless (~300/day) — strict `fromdate` window, tag-gated; technical topics |
| GitHub | en | ✅ Search API | comments, reactions | keyless (`GITHUB_TOKEN` lifts limit) |
| Reddit | en | ✅ 3-tier: `.json` → old.reddit HTML → RSS | score, comments | keyless — Reddit JA3-fingerprints non-browser TLS so `.json` often 403s; the old.reddit HTML tier still returns REAL scores/comments, RSS is the engagement-less last resort |
| Lemmy | en | ✅ search API | score, comments | keyless — federated Reddit alt; `Top<period>` sort, env `LEMMY_INSTANCE` |
| Bluesky | en | ✅ searchPosts | likes, reposts, replies | keyless — AT Proto; structured-engagement complement to the X/WebSearch layer |
| Polymarket | en | ✅ Gamma | volume | keyless (403 on datacenter IPs → agent supplements) |
| Kalshi | en | ✅ search API | volume (contracts) | keyless — CFTC-regulated US prediction market; odds quoted as a live snapshot dated at fetch time |
| Bilibili | zh | ✅ wbi search | views, danmaku, favorites | keyless (anonymous buvid3 + wbi md5 sign) |
| Douyin | zh | ✅ hot-search board | hot_value, rank | keyless — trending-board match, not full search |
| Xiaohongshu | zh | ✅ local bridge | likes, collects, comments | optional — auto-activates when a logged-in [xiaohongshu-mcp](https://github.com/xpzouying/xiaohongshu-mcp) runs locally; otherwise agent WebSearch `site:` |
| Weibo / Zhihu | zh | ⏳ stub | — | login-walled / anti-bot → agent WebSearch `site:` |
| Open web / X | any | — | — | agent WebSearch |

**Timezone convention:** everything is UTC end-to-end — the N-day window boundaries,
every item date, and the `from..to` header. Source timestamps arriving with a local
offset are converted to UTC before dating, and `Window.contains` tolerates +1 day of
skew for freshly-posted items.

### Xiaohongshu via local bridge (optional)

XHS has no keyless search path (login-gated API, rotating request signing), so the
engine instead auto-detects a locally running
[xiaohongshu-mcp](https://github.com/xpzouying/xiaohongshu-mcp): install its release
binary, scan the login QR once, keep it running (default `:18060`, override with
`XIAOHONGSHU_API_BASE`). When `--diagnose` shows `bridge up`, `--lang zh/both` runs
pull real XHS notes with likes/collects/comments and exact post dates; without the
bridge the platform falls back to the agent's WebSearch layer. Note dates require a
per-note detail call (a headless browser server-side, ~5-15s each), so this source
returns a few well-dated items, capped by `LASTDAYS_XHS_BUDGET` seconds (default 25).

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
