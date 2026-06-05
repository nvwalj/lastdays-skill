# lastdays
[English](README.md) | 简体中文

**研究最近 N 天里人们究竟如何谈论某个话题（默认 30 天，可配置）- 零配置，使用你的订阅运行，不消耗任何 API key。**

这是对多源「最近 30 天」研究 skill 的轻量重写，对订阅用户友好。零 key 的 Python 引擎会在严格、可配置的时间窗口内抓取 **Reddit、Hacker News、GitHub 和 Polymarket** 的真实互动数据（赞同票、points、评论、交易量）。agent 宿主（Claude Code 或 OpenAI Codex）负责规划目标，通过 WebSearch 补齐 open-web / X / 中文层面的材料，并综合成一份有依据、有引用的简报。无需 API key：agent 本身就是 LLM。

## 相对原版有哪些变化

- **时间窗口可配置。** `--days N`（默认 30，范围 1–365），严格执行。
- **只用订阅，零额外成本。** 引擎使用 stdlib + 无 key 的公开 API；推理由你的 Claude/Codex 订阅完成。不需要 ScrapeCreators/Brave/OpenRouter key。
- **为扩展中文媒体而设计。** 内置 source registry 和单函数契约；Bilibili(B站)与 Douyin(抖音)已实现，Weibo / Xiaohongshu / Zhihu 作为已注册 stub 随包提供，可继续实现。
- **只支持 Claude + OpenAI。** Claude Code plugin (`.claude-plugin/plugin.json`) 和 OpenAI Codex adapter (`agents/openai.yaml`)。

## 安装

```bash
bash install.sh            # symlinks skills/lastdays -> ~/.claude/skills/lastdays
```

然后在 Claude Code 中运行：

```
/lastdays Claude Code 7
/lastdays nvidia earnings
/lastdays "AI video tools" 14 --lang both
```

## 用法（直接运行引擎）

```bash
python3 skills/lastdays/scripts/lastdays.py "Claude Code" --days 7 --emit compact
python3 skills/lastdays/scripts/lastdays.py "AI agents" --lang zh --emit json
python3 skills/lastdays/scripts/lastdays.py --diagnose      # list sources + auth status
```

| Flag | 说明 |
|------|------|
| `--days N` | 窗口大小，默认 30，范围 1–365 |
| `--lang en\|zh\|both` | 来源语言组（默认 `en`） |
| `--sources a,b,c` | 选择来源（别名：`hn`、`gh`、`pm`、`r`） |
| `--depth quick\|default\|deep` | 每个来源的结果量 |
| `--emit compact\|json` | 证据块（默认）或 JSON |
| `--allow-undated` | 保留无法检测到日期的条目 |
| `--synthesize` | 同时通过推理 provider 输出简报（headless/cron） |
| `--provider local\|auto\|openai\|anthropic` | `--synthesize` 使用的 provider（默认 `local` = agent 宿主） |
| `--diagnose` | 列出来源 + OpenAI/GitHub 认证状态，然后退出 |

## 综合生成（可选，headless）

在 Claude Code 中，agent 会自己写简报：**零成本、默认行为、无需 flag**。
用于 headless/cron 时，`--synthesize` 会让引擎也写出简报，并且**优先使用订阅**：
如果检测到你的 ChatGPT/Codex 登录状态，它会直接使用（无需 API key，不产生花费）；否则回退到付费的
`OPENAI_API_KEY` / `ANTHROPIC_API_KEY`。综合生成失败不会影响引擎输出证据。

注意：OpenAI 的 Codex 订阅端点并非官方接口，目前不稳定（HTTP 400）。如需可靠的 headless 简报，请使用带 `ANTHROPIC_API_KEY` 的 `--provider anthropic`，或在配置 `OPENAI_API_KEY` 的同时设置
`LASTDAYS_OPENAI_PREFER_KEY=1`。

## 来源矩阵

| 来源 | 语言 | 引擎 | 互动指标 | 状态 |
|------|------|------|----------|------|
| Hacker News | en | ✅ Algolia | points, comments | 无需 API key |
| GitHub | en | ✅ Search API | comments, reactions | 无需 API key（`GITHUB_TOKEN` 可提高限额） |
| Reddit | en | ✅ public `.json` | score, comments | 无需 API key（数据中心 IP 可能 403 → agent 补充） |
| Polymarket | en | ✅ Gamma | volume | 无需 API key（数据中心 IP 可能 403 → agent 补充） |
| Bilibili(B站) | zh | ✅ wbi search | views, danmaku, favorites | 无需 API key（匿名 buvid3 + wbi md5 签名） |
| Douyin(抖音) | zh | ✅ hot-search board | hot_value, rank | 无需 API key；趋势榜匹配，不是完整搜索 |
| Weibo / Zhihu / Xiaohongshu | zh | ⏳ stub | — | 登录墙 / 反 bot → agent WebSearch `site:` |
| Open web / X | any | — | — | agent WebSearch |

参见 [`skills/lastdays/references/source-policy.md`](skills/lastdays/references/source-policy.md)，
了解这一契约，以及如何把中文 stub 逐步改造成真正的 fetcher。

## 目录布局

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

## 环境要求

Python 3.12+（引擎 **零** 第三方依赖）。使用 `python3 -m pytest` 运行测试。

## 许可证

MIT
