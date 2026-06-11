# Source Policy & Extension Guide

## Source matrix

| Source | Lang | Where it runs | Engagement signal | Status |
|--------|------|---------------|-------------------|--------|
| Hacker News | en | Python engine (Algolia API) | points, comments | ✅ implemented, keyless |
| Lobsters | en | Python engine (hottest.json + is_on_topic) | score, comments | ✅ implemented, keyless — hot-list match, not full search |
| Dev.to | en | Python engine (articles API, tag search) | reactions, comments | ✅ implemented, keyless |
| Stack Overflow | en | Python engine (search/advanced API) | score, answers, views | ✅ implemented, keyless — server-side `fromdate` window; tag-gated, technical topics |
| GitHub | en | Python engine (Search API) | comments, reactions | ✅ implemented, keyless* |
| Reddit | en | Python engine (3 tiers: `.json` → old.reddit HTML → RSS) | score, comments (json + oldweb) | ✅ implemented, keyless** |
| Lemmy | en | Python engine (search API, `Top<period>` sort) | score, comments | ✅ implemented, keyless — federated Reddit alt; zero-key complement when Reddit 403s (env `LEMMY_INSTANCE`) |
| Bluesky | en | Python engine (searchPosts, 2-host tier) | likes, reposts, replies | ✅ implemented, keyless — AT Proto; structured-engagement complement to the X/WebSearch layer |
| Polymarket | en | Python engine (Gamma API) | volume | ✅ implemented, keyless** |
| Kalshi | en | Python engine (public search API) | volume (contracts) | ✅ implemented, keyless — CFTC-regulated US prediction market; open markets are dated at fetch time (live-odds snapshot, recorded in `metadata.date_basis`) |
| Google News | en | Python engine (RSS search, `when:{N}d`) | — | ✅ implemented, keyless — **degraded** (`metadata.degraded`, no engagement; relevance+recency only). Mainstream-news layer HN/Reddit miss; `is_on_topic`-gated; links are Google redirect URLs (publisher surfaced via `author`). Re-checks each pubDate against the window |
| arXiv | en | Python engine (Atom API, `sortBy=submittedDate`) | — | ✅ implemented, keyless — **degraded** (no engagement; citations not in the feed; relevance+recency only). Primary-research layer for CS/ML/physics topics; phrase `all:"<q>"` search, gated on title OR abstract; legitimately empty for non-research topics (say so). Etiquette: ≤1 req/3s, engine backs off on 429 |
| Bilibili B站 | zh | Python engine (wbi search) | views, danmaku, favorites | ✅ implemented, keyless |
| Douyin 抖音 | zh | Python engine (hot-search board) | hot_value, rank | ✅ implemented, keyless — see note**** |
| Weibo 微博 | zh | agent WebSearch (`site:weibo.com`) | — | ⏳ stub — login-walled*** |
| Zhihu 知乎 | zh | agent WebSearch (`site:zhihu.com`) | — | ⏳ stub — anti-bot*** |
| Xiaohongshu 小红书 | zh | Python engine via LOCAL bridge (xiaohongshu-mcp REST on `:18060`), else agent WebSearch | likes, collects, comments | ✅ implemented — bridge-gated: `Source.bridge_probe` checks `GET /api/v1/login/status`; probe passes → promoted to engine for that run, else stays a web layer. Dates come from per-note `feeds/detail` calls (`note.time`, epoch ms) under a `LASTDAYS_XHS_BUDGET`-second budget — undetailed notes are dropped, never guess-dated. `publish_time` filter accepts only 不限/一天内/一周内/半年内 (NO 一个月内) |
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
\*\* Reddit uses the **tier fallback framework** (see below): tier `json` (quality 100, real score/comments + upvote_ratio) → tier `oldweb` (quality 70, old.reddit HTML, real score/comments, not degraded) → tier `rss` (quality 40, degraded). Reddit JA3-fingerprints the TLS handshake, so `.json` 403s for non-browser clients even on residential IPs (measured 2026-06); `old.reddit.com/search` HTML is server-rendered outside that wall and still carries real engagement, leaving `search.rss` — reachable but with **no engagement** — as the last resort. Because the RSS tier can't rank by upvotes, it additionally drops titles that don't match the query (a relevance gate) so noise like "Flea market find" can't ride in on the word "market". RSS items are tagged `metadata.degraded=true` + `metadata.tier=rss`, scored without upvotes (never faked), and marked `⚠ degraded:rss` in the evidence. Residential IPs get the richer `.json` path. Polymarket's public API can also 403 from some IPs; it degrades to `[]` and records the error. HN multi-word queries use Algolia `optionalWords` so phrases like "US stock market" don't AND themselves to zero.

## Tier fallback framework

A source can declare ordered `tiers` instead of a single `fetch` (`lib/registry.py` `Tier`, run by `lib/tiers.py`). Each tier has a `quality` (higher tried first; negatives are last-resort, the firecrawl convention) and a `degraded` flag. The runner uses the first tier that returns results; a tier that errors is skipped and the next runs. Items get `metadata.tier` (which strategy produced them) and, for degraded tiers, `metadata.degraded=true`. Degraded means "this path can't return a full signal" — the missing signal is named in `metadata.degraded_note` (e.g. Reddit RSS: "no engagement"; Douyin v2: "no timestamps, dates synthesized") — such items are scored without the missing signal, gated/flagged accordingly, and marked in the brief. Sources on this framework: Reddit (`json`→`rss` degraded), Bilibili (`search`→`wbi-search`, both full-signal — just two routes), Douyin (`aweme`→`v2` degraded). Single-`fetch` sources are transparently treated as one non-degraded tier.

## Time window

- Only use content inside the engine's `from..to` window. Default 30 days, set by `--days`.
- Prefer items with explicit dates. Engine items are pre-filtered. Treat undated WebSearch items as low-confidence and verify with WebFetch before relying on them.

## Evidence quality

Rank by what real people engaged with: high upvotes/points/comments, fast growth, repeated narratives across sources, representative quotes. Engine items carry real numbers; agent-added web/X/Chinese items do not — rank those below comparable engine items and label them web-sourced.

## HTTP layer: browser identity & the stdlib TLS ceiling

Every fetch goes through `scripts/lib/http.py`, which presents **one pinned, self-consistent macOS Chrome 124 identity** on the wire — not a bot UA:

- **Headers** (`browser_headers()`): real Chrome `User-Agent` + matching `sec-ch-ua` / `sec-ch-ua-mobile` / `sec-ch-ua-platform`, `Accept-Language`, and `Accept-Encoding: gzip, deflate`. JSON/XHR calls (`request`) use `Sec-Fetch-Mode: cors` / `Dest: empty`; HTML/RSS navigations (`get_text`) use the `navigate`/`document` set plus `Upgrade-Insecure-Requests`. The two modes are kept distinct on purpose — emitting `Sec-Fetch-User`/`Upgrade-Insecure-Requests` on an XHR is itself a cross-layer tell. Callers layer their own headers on top, so a source can still override `Accept` or add `Authorization`/`Referer`/`Cookie`.
- **No UA rotation.** Rotating a browser UA over the single fixed OpenSSL ClientHello (whose JA4 matches no real browser) maps many identities onto one impossible TLS fingerprint — a *stronger* bot signal than a stable UA. The UA version, `sec-ch-ua` brand version, and platform token must always move together.
- **Compression** (`_decode_body`): `gzip`/`deflate` are advertised and inflated via stdlib `zlib`/`gzip`. `br`/`zstd` are deliberately **not** advertised (no stdlib decoder on 3.12) — claiming an encoding you can't decode is worse than omitting it.

**The ceiling this layer does NOT try to beat (stdlib-only, honest limits):**

- **TLS fingerprinting (JA3, and JA4 — now primary at Cloudflare/Akamai/AWS WAF/DataDome).** It is computed from the ClientHello *before any HTTP header is sent*. Python's `urllib` uses the system OpenSSL ClientHello, whose JA4 matches no browser, so a request can be flagged a bot before the request line is read. **No header craft fixes a wrong ClientHello.** This is the root cause of `www.reddit.com` `search.json` 403s and is unfixable without a third-party TLS stack (`curl_cffi`, `tls-client`, `rnet`) — out of scope for the zero-dependency engine.
- **HTTP/2** is not in stdlib (`urllib` is HTTP/1.1 only). Real Chrome always negotiates h2 via ALPN, so never speaking h2 is itself a mismatch (Akamai's h2 fingerprint inspects SETTINGS + pseudo-header order). Concurrency stays thread-based HTTP/1.1.
- **Post-quantum TLS** (X25519MLKEM768) is a live pre-HTTP signal in Chrome 131+. The UA is pinned to **124**, which predates default PQ, so the stdlib ClientHello at least doesn't claim a version that always sends it.

What header realism *does* buy: it moves requests from "obvious bot" toward "plausible" on the **bulk of keyless sources**, which gate on UA/header heuristics rather than full JA4 + JS challenges — and the `gzip` path also cuts transfer latency on every fetch. It does not, and is not meant to, defeat a strict JA4/h2 edge. When a source is JA4-gated, the tier framework should fall straight to its lenient tier (RSS/HTML/third-party mirror) rather than burn retries on a 403 header craft can't fix.

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
