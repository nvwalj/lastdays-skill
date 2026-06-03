# Source Policy & Extension Guide

## Source matrix

| Source | Lang | Where it runs | Engagement signal | Status |
|--------|------|---------------|-------------------|--------|
| Hacker News | en | Python engine (Algolia API) | points, comments | ✅ implemented, keyless |
| GitHub | en | Python engine (Search API) | comments, reactions | ✅ implemented, keyless* |
| Reddit | en | Python engine (`.json`, RSS fallback) | score, comments (json only) | ✅ implemented, keyless** |
| Polymarket | en | Python engine (Gamma API) | volume | ✅ implemented, keyless** |
| Bilibili B站 | zh | Python engine (wbi search) | views, danmaku, favorites | ✅ implemented, keyless |
| Douyin 抖音 | zh | Python engine (hot-search board) | hot_value, rank | ✅ implemented, keyless — see note**** |
| Weibo 微博 | zh | agent WebSearch (`site:weibo.com`) | — | ⏳ stub — login-walled*** |
| Zhihu 知乎 | zh | agent WebSearch (`site:zhihu.com`) | — | ⏳ stub — anti-bot*** |
| Xiaohongshu 小红书 | zh | agent WebSearch (`site:xiaohongshu.com`) | — | ⏳ stub — login-walled |
| Open web / X | en/any | agent WebSearch | — | covered by the agent |

\*\*\* Probed 2026-05-30: **Zhihu** returns `40352` (风控/needs login) and requires an
`x-zse-96` signed header + login cookie — not viable keyless. **Weibo** (`m.weibo.cn`
getIndex, both 综合 type=1 and 实时 type=61) returns `ok=-100` anonymously / from
overseas IPs — needs a login cookie. Both stay on the WebSearch fallback. Of the
Chinese platforms, only **Bilibili** is keyless-friendly (public `wbi` md5 sign), so it
is the only one wired into the engine. Implementing Weibo/Xiaohongshu/Douyin for real
needs a locally-authenticated cookie/bridge — see the guide below.

\*\*\*\* **Douyin is a hot-search-board source, not a general search.** Douyin's
content search needs an `a_bogus` signature, but the hot-search billboard
(`douyin.com/aweme/v1/web/hot/search/list`) is public and unsigned. So this source
answers "is the topic trending on Douyin right now?" — it returns board entries
(hot topic + hot_value + rank) whose word matches the query, not arbitrary videos.
Expect hits only when the query overlaps the live top-50 (great for breaking
events, often empty for niche/evergreen topics). Entries carry `event_time`, so
they are still window-filtered.

\* GitHub is keyless but unauthenticated search is rate-limited (~10 req/min); set `GITHUB_TOKEN` to raise it.
\*\* Reddit uses the **tier fallback framework** (see below): tier `json` (quality 100, real score/comments) then tier `rss` (quality 40, degraded). `.json` returns HTTP 403 from datacenter IPs; the runner then tries `search.rss`, which IS reachable but carries **no engagement**. Because the RSS tier can't rank by upvotes, it additionally drops titles that don't match the query (a relevance gate) so noise like "Flea market find" can't ride in on the word "market". RSS items are tagged `metadata.degraded=true` + `metadata.tier=rss`, scored without upvotes (never faked), and marked `⚠ degraded:rss` in the evidence. Residential IPs get the richer `.json` path. Polymarket's public API can also 403 from some IPs; it degrades to `[]` and records the error. HN multi-word queries use Algolia `optionalWords` so phrases like "US stock market" don't AND themselves to zero.

## Tier fallback framework

A source can declare ordered `tiers` instead of a single `fetch` (`lib/registry.py` `Tier`, run by `lib/tiers.py`). Each tier has a `quality` (higher tried first; negatives are last-resort, the firecrawl convention) and a `degraded` flag. The runner uses the first tier that returns results; a tier that errors is skipped and the next runs. Items get `metadata.tier` (which strategy produced them) and, for degraded tiers, `metadata.degraded=true`. Degraded means "this path can't return a full signal" (e.g. no engagement) — such items are scored without the missing signal, relevance-gated to suppress noise, and flagged in the brief. Reddit (`json`→`rss`) is the first source on this framework; single-`fetch` sources are transparently treated as one non-degraded tier.

## Time window

- Only use content inside the engine's `from..to` window. Default 30 days, set by `--days`.
- Prefer items with explicit dates. Engine items are pre-filtered. Treat undated WebSearch items as low-confidence and verify with WebFetch before relying on them.

## Evidence quality

Rank by what real people engaged with: high upvotes/points/comments, fast growth, repeated narratives across sources, representative quotes. Engine items carry real numbers; agent-added web/X/Chinese items do not — rank those below comparable engine items and label them web-sourced.

## Adding a Chinese source (turning a stub into a real fetcher)

The registry is the only extension point. To implement e.g. Weibo:

1. **Edit** `scripts/lib/sources/weibo.py`. Implement the uniform contract:

   ```python
   def fetch(query: str, window: Window, *, env: dict, depth: str = "default") -> list[Item]:
       # 1. call the platform API/bridge via lib.http (cookie from env["WEIBO_SUB"])
       # 2. map each post to schema.Item(source="weibo", lang="zh", title=, url=,
       #    author=, date="YYYY-MM-DD", ts=<unix>, engagement={...}, snippet=, relevance=)
       # 3. return the list; the engine handles window filtering, scoring, dedupe
       ...
   ```

   Keep the existing `registry.register(...)` line but flip `implemented=False` → `implemented=True` and, if a cookie/token is needed, leave `requires_key=True`.

2. **Promote it to an engine source** so the orchestrator runs it: add its name to `ENGINE_SOURCES` in `scripts/lib/registry.py`.

3. **Add an engagement formula** for it in `scripts/lib/score.py` → `engagement_raw()` (e.g. Weibo: `0.5*log(reposts) + 0.3*log(comments) + 0.2*log(attitudes)`).

4. **Store credentials** as env / `~/.config/lastdays/.env` / macOS keychain (`lastdays-WEIBO_SUB`). Add the key name to `KEYCHAIN_KEYS` in `scripts/lib/env.py` if you want keychain pickup.

5. **Add a fixture test** in `tests/` (offline parse of a saved sample payload) so the source is covered without live network.

That's the whole contract: one `fetch`, one register line, one engagement formula. No change to the orchestration in `lastdays.py`.

## Hard rule

Douyin ≠ TikTok; Xiaohongshu ≠ generic web; Weibo evidence must come from `weibo.com`. Do not substitute one platform's data for another. If a platform is unavailable, say so once and lower confidence rather than silently swapping in a different source.
