# Source Policy & Extension Guide

## Source matrix

| Source | Lang | Where it runs | Engagement signal | Status |
|--------|------|---------------|-------------------|--------|
| Hacker News | en | Python engine (Algolia API) | points, comments | ✅ implemented, keyless |
| GitHub | en | Python engine (Search API) | comments, reactions | ✅ implemented, keyless* |
| Reddit | en | Python engine (public `.json`) | score, comments, upvote_ratio | ✅ implemented, keyless** |
| Polymarket | en | Python engine (Gamma API) | volume | ✅ implemented, keyless** |
| Weibo 微博 | zh | agent WebSearch (`site:weibo.com`) | — | ⏳ engine stub |
| Xiaohongshu 小红书 | zh | agent WebSearch (`site:xiaohongshu.com`) | — | ⏳ engine stub |
| Douyin 抖音 | zh | agent WebSearch (`site:douyin.com`) | — | ⏳ engine stub |
| Zhihu 知乎 | zh | agent WebSearch (`site:zhihu.com`) | — | ⏳ engine stub |
| Bilibili B站 | zh | Python engine (wbi search) | views, danmaku, favorites | ✅ implemented, keyless |
| Open web / X | en/any | agent WebSearch | — | covered by the agent |

\* GitHub is keyless but unauthenticated search is rate-limited (~10 req/min); set `GITHUB_TOKEN` to raise it.
\*\* Reddit and Polymarket public endpoints often return HTTP 403 from datacenter IPs. On a residential machine they usually work; when blocked the engine degrades to `[]` and records the error, and the agent supplements via WebSearch.

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
