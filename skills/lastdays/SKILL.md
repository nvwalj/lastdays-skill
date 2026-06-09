---
name: lastdays
description: >-
  Research what people actually said about a topic over the last N days (default
  30, configurable). A zero-key Python engine pulls Reddit, Hacker News, GitHub,
  Polymarket, Lobsters, Stack Overflow, Lemmy, and Chinese sources (Bilibili, Douyin) with real
  engagement (upvotes, points, comments, volume) and a strict date window; you
  supplement the open web and X via WebSearch and
  synthesize one grounded, cited brief. Use for recent-trend research, "what's
  new with X", pre-meeting/pre-launch scans, and time-boxed topic deep-dives.
argument-hint: 'lastdays Claude Code 7 | lastdays nvidia earnings | lastdays "AI video tools" 14'
allowed-tools: Bash, Read, Write, WebSearch, WebFetch, AskUserQuestion
version: "0.1.0"
license: MIT
user-invocable: true
metadata:
  emoji: "🗓"
  engine: scripts/lastdays.py
  default_days: 30
---

# lastdays

Research a topic across the last **N days** (default 30). This is a structured
research tool, not an improvised web search: a Python engine fetches zero-key
public sources with real engagement numbers, and **you** (the reasoning model
running this skill) plan the targeting, fill the web/X/Chinese layers via
WebSearch, and synthesize the final brief. You need no API key — you are the LLM.

## Step 0 — Load WebSearch/WebFetch first

They are deferred tools in Claude Code; if you do not load them, calls fail.
Your first action on every run:

```
ToolSearch select:WebSearch,WebFetch
```

## Step 1 — Parse the request

- **Topic**: the subject to research.
- **Days**: a bare number anywhere in the args is the window (e.g. `lastdays Claude Code 7` → 7 days). Default **30** if none given. Valid range 1–365.
- **Language**: default `en`. If the user asks for Chinese platforms or writes the topic in Chinese, use `--lang zh` (or `--lang both`).

Restate the topic, window, and sources in one line before any tool call. Do not promise a specific runtime.

## Step 2 — Run the engine (zero-key structured data)

`SKILL_DIR` is the directory of THIS file (your harness told you its path when you Read it). The engine is always at `$SKILL_DIR/scripts/lastdays.py`. Use `python3` (not `python3.12`).

```bash
SKILL_DIR="<absolute dir of this SKILL.md>"
python3 "$SKILL_DIR/scripts/lastdays.py" "<TOPIC>" --days <N> --lang <en|zh|both> --emit compact
```

The engine prints an `EVIDENCE FOR SYNTHESIS` block (ranked Reddit / Hacker News / GitHub / Polymarket / Lobsters / Stack Overflow / Lemmy items — plus Bilibili / Douyin under `--lang zh`/`both` — with real engagement, strictly inside the window) and a `WEB LAYERS TO FILL` list. Each item line shows `score=` and `rel=` (relevance 0–0.9); prefer high-`rel` items and treat low-`rel` ones (engine kept them but flagged weak) with skepticism. Read the evidence; **do not** paste it back verbatim. Run `--diagnose` once if you want to see which sources are live vs stub.

## Step 3 — Fill the web / X / Chinese layers yourself

For each entry under `WEB LAYERS TO FILL`, use WebSearch (and WebFetch to confirm dates):

- **Open web**: `"<topic>" <recent month/year>` — articles, blogs, release notes.
- **X / Twitter**: `"<topic>" site:x.com`.
- **Chinese platforms** (when `--lang zh`/`both`): Bilibili and Douyin are handled by the engine itself (see the status note below) — do **not** re-cover them via WebSearch. The three still-stubbed platforms you cover via WebSearch are `"<topic>" site:weibo.com` (微博), `site:xiaohongshu.com` (小红书), `site:zhihu.com` (知乎).

These layers have **no structured engagement numbers** — never invent likes/upvotes for them.

## Step 4 — Strict date window

Keep only items dated within `from..to` from the engine header. For WebSearch results, verify the publish date with WebFetch or drop the item. Never let an undated item anchor a finding.

## Step 5 — Synthesize

Read `references/synthesis-rules.md` and follow it. In short: first line is the badge `🗓 lastdays · last N days · <today>`, then `What I learned:`, then engagement-grounded prose with inline `[name](url)` citations, honestly labeling which layers are web-sourced (no engagement) and which sources came back empty. Match the user's language (Chinese topic → Chinese brief). No trailing `Sources:` block.

## Source switches & Chinese status

- `--sources reddit,hackernews,github,polymarket,lobsters` — pick a subset (aliases: `hn`, `gh`, `pm`, `r`, `lob`).
- `--lang zh` routes the five Chinese platforms to your WebSearch layer; `--lang both` adds them on top of the English engine sources.
- `--allow-undated` keeps items with no detectable date (off by default).
- You write the synthesis here in chat (zero cost). `--synthesize` (engine-side LLM) is for headless/cron only - do not use it in this interactive flow.
- Chinese sources: **Bilibili and Douyin are live in the engine** (`--sources bilibili,douyin`, or they run under `--lang zh`/`both`). Bilibili is full video search (real views/danmaku/favorites). Douyin is the hot-search board (hot_value + rank) — it only hits when the topic is trending right now, so expect it to be empty for niche/evergreen queries; say so in the brief rather than implying Douyin had nothing to say. Weibo / Xiaohongshu / Zhihu are still stubs — the agent covers them via WebSearch. See `references/source-policy.md`.

If the user gives no topic, ask once for a topic and stop. Do not run the engine or WebSearch on an empty topic.
