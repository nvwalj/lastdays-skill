# lastdays crawler — improvement backlog

Self-improving loop: each iteration uses `lastdays` to research current web-scraping
techniques + keyless sources, then folds the best findings back into the engine.
Goal: the fastest, most accurate keyless info-gathering tool. Constraint stays fixed:
**Python 3.12 stdlib only, zero third-party deps, zero API keys for engine sources.**

Sourced from a 5-angle research workflow (anti-bot/TLS, new sources, speed, Reddit,
precision) + synthesis, run 2026-06-11. Re-run the workflow each iteration to refresh.

---

## Status log

- **2026-06-11 · iteration 7 — DONE: thread-pool sizing (backlog #16); speed measured & found already-good.**
  Measured first (the right move for a speed pass): cold full run ≈ **1.9s**, warm ≈ 0
  (cache-dominated), wall-clock ≈ the slowest single source (bluesky ~1.6s, reddit ~1.5s,
  both network-bound). The one real issue: `max_workers=min(8, N)` silently QUEUED 4 of the
  12 EN sources behind the first 8 once Google News + arXiv landed. Fixed → `_pool_size()`
  with cap 24 so every source runs concurrently; wall-clock is now the slowest source, not
  sum-of-waves. Gain is modest on a fast run (within network noise) but real under load /
  growth. 3-assert test; 241 green. **Honest finding: speed has little headroom left** — the
  cache is the dominant lever and it's already strong, so #11 (conditional GET/ETag) and #14
  (keep-alive) are deprioritized (marginal cold-cross-day savings, added complexity). Future
  iterations return to accuracy/coverage where the value is.

- **2026-06-11 · iteration 6 — DONE: arXiv research source (backlog #12); #8 deferred with reasoning.**
  Added `sources/arxiv.py` (`export.arxiv.org/api/query`, Atom) as a keyless **degraded**
  engine source — primary CS/ML/physics research, the layer news/social/forum miss. Phrase
  `all:"<q>"` search, gated on title OR abstract, window-rechecked on `published`, authors
  collapsed to "First et al.", no engagement (never faked). 7 fixture tests; 238 green;
  live: "large language model agents" → 29 papers (rel 0.90), "taylor swift tour" → 0
  (honest empty). Registered + ENGINE_SOURCES + docs (SKILL.md, source-policy.md). 12 EN
  engine sources now. **#8 (stemming/synonym) deferred on purpose:** the gaps that
  motivated it ("model context protocol"↔MCP, "rust async runtime") are acronym/semantic,
  NOT stemming-fixable; the high-value acronym map is arbitrary/unscalable without
  embeddings (no deps); and it touches shared relevance code (gate-noise regression risk).
  Re-scoped #8 below to the genuinely safe slice (phrase-adjacency ranking bonus).

- **2026-06-11 · iteration 5 — DONE: no-strong-results signal + selective URL canonicalization (backlog #9).**
  (a) `render.py`: a source whose best item is below the no-match floor ceiling
  (max relevance < 0.4) gets a per-source `⚠ no strongly-relevant results` flag, and
  when the WHOLE pool is weak a global `NOTE` tells the agent to lean on web layers +
  lower confidence. Completes the precision arc — iter 1 found the noise flood, iter 4
  gates it when on-topic items exist, iter 5 honestly signals it when none do. (b)
  `normalize.canonical_url()`: was dropping ALL query strings, which wrongly merged
  distinct `?v=A`/`?v=B`/`?id=` resources. Now strips only tracking params (utm_*,
  fbclid, gclid, ref, oc, …) and keeps content params (order-normalized, value case
  preserved); unfolds m./mobile./amp. hosts + trailing `/amp`. 10 new tests; 232 green.
  Live: "web scraping anti-bot bypass" HN now shows the weak flag + global NOTE.

- **2026-06-11 · iteration 4 — DONE: adaptive precision gate for multi-word queries (backlog #5).**
  Audit first overturned the scope: 5 of the 8 listed sources (stackexchange, devto,
  lemmy, bluesky, kalshi) ALREADY hard-gate with `is_on_topic` at fetch — their
  `NO_MATCH_FLOOR` is only a relevance floor for *already-on-topic* items. Only the 3
  broad server-side full-text sources (hackernews, github, polymarket) floored without
  gating. Added `base.adaptive_topic_gate()` + `meaningful_token_count()`, wired into
  the orchestrator (`lastdays.py`) for those 3 only — kept OUT of the source fetch so
  the source unit tests (which assert floored items are kept) stay valid. Rule: ≥2-token
  queries return the on-topic subset only when it has ≥3 items, else keep all (recall on
  thin topics). Live: "open source LLM" HN 27→13 (dropped 14 noise, kept 13 on-topic);
  pure-noise queries ("web scraping anti-bot bypass": 0 on-topic) correctly keep all —
  that case is backlog #9's banner, not this gate. 7 new tests; 224 green.
  **Reinforced #8:** "model context protocol" / "rust async runtime" had 0 *title*
  matches (acronym/phrasing gaps) → stemming/synonym/acronym expansion (#8) would let
  the gate help there too.

- **2026-06-11 · iteration 3 — DONE: cross-source near-duplicate clustering (backlog #4).**
  `normalize.dedupe()` now runs a 2nd pass after the exact URL/title pass: token-set
  Jaccard (EN) / char-trigram Jaccard (CJK) at `NEAR_DUP_JACCARD=0.6`, keeping the
  highest-scored copy. Conservative by design — short titles (EN <4 content tokens,
  CJK <6 chars) dedupe on exact only (false-merge of a distinct story is worse than a
  shown dup). Also refactored `lastdays.py` to reuse `normalize.dedupe()` (it had a
  duplicated inline exact-only dedup that bypassed the new pass) — single source of
  truth now. 6 new dedupe tests incl. over-merge guards; 217 tests green. Live delta:
  "OpenAI" 10d merged **7 extra cross-source dups** (158→151) the exact pass missed
  ("Model routing…" and "OpenAI mulls slashing…" each were in HN *and* Google News),
  while correctly KEEPING distinct same-event articles (8 different outlets' IPO-filing
  coverage stayed separate — event-clustering is the agent's job, not the engine's).
  **New finding → backlog #20:** Bluesky post "titles" embed the article URL
  ("…www.axios.com/2026/06/08"), polluting both relevance scoring and dedup Jaccard.

- **2026-06-11 · iteration 2 — DONE: Google News RSS source (backlog #6); backlog #1 overturned by live probing.**
  Added `sources/googlenews.py` (`news.google.com/rss/search?q=…+when:{N}d`) as a keyless
  **degraded** engine source (no engagement → relevance+recency only, `is_on_topic`-gated,
  pubDate re-checked vs window, " - Publisher" suffix stripped, publisher in `author`).
  Registered + `ENGINE_SOURCES` + 7 fixture tests; 211 tests green; live run returns 4
  on-topic in-window articles. Docs updated (SKILL.md, source-policy.md matrix).
  **Backlog #1 (PullPush + Arctic-Shift) NOT built — live probing overturned the premise:**
  (a) PullPush is frozen — its newest indexed submission across the whole index is 2025-05-19
  (~13 months stale), so it returns nothing inside any recent window → excluded. (b) Arctic-Shift
  is alive & fresh (returned 2026-06-11 data with real score/comments) BUT `posts/search` requires
  `subreddit` or `author` — no Reddit-wide free-text, and `subreddits/search` is name-PREFIX only
  (no topical mapping), so there's no good keyless topic→subreddit step. (c) Critically, the
  existing **`oldweb` tier already does Reddit-wide search WITH real engagement** (live: 14 in-window
  hits, all with score/comments) even while `json` 403s on the JA3 wall — so the problem #1 set out
  to fix is already solved. Arctic-Shift remains a *possible future* per-subreddit resilience tier
  (see revised #1 below), not a priority.

- **2026-06-11 · iteration 1 — DONE: realistic browser identity + gzip in `http.py`.**
  Centralized `browser_headers()` (pinned macOS Chrome 124 UA + `sec-ch-ua`/`Sec-Fetch-*`,
  navigate vs api modes) applied to ALL requests, killing the bot `lastdays/0.1` UA that
  11/12 sources sent on JSON GETs. Added `Accept-Encoding: gzip, deflate` + `_decode_body`
  (stdlib `zlib`/`gzip` inflate; `br`/`zstd` deliberately not advertised). Documented the
  TLS/JA4/h2/PQ ceiling in `references/source-policy.md`. 204 tests green; live run parses
  all JSON sources; wire-verified UA + sec-ch-ua + cors Sec-Fetch (no `Sec-Fetch-User` on api).

---

## Next up (prioritized for future iterations)

Ranked by value × safety / effort. All stdlib-safe unless noted.

| # | Cat | Item | val | eff | risk |
|---|-----|------|-----|-----|------|
| ~~1~~ | reddit | **REVISED 2026-06-11 (live-probed) — premise dead, DEPRIORITIZED (see Status log).** PullPush frozen (newest item 2025-05-19); Arctic-Shift needs `subreddit`/`author` (no Reddit-wide) + name-prefix-only subreddit search; and the `oldweb` tier already does Reddit-wide real-engagement search. *Low-pri remnant:* Arctic-Shift (`posts/search?subreddit=<sub>&query=<q>&after=<ISO>&sort=desc`) as a per-subreddit resilience tier seeded from `oldweb`-surfaced subreddits, only if old.reddit starts blocking. | low | med | low |
| 2 | new-source | **HN: switch fully to Algolia `search_by_date` with native epoch date window + server-side `points>` gate.** `hn.algolia.com/api/v1/search_by_date?query=&tags=story&numericFilters=created_at_i>{epoch},points>{n}`. (Largely already in place — verify/strengthen; optionally merge a relevance-sorted `/search` pass deduped by objectID for popular older hits.) | high | med | low |
| 3 | precision | **IDF-aware BM25F relevance in `base.py` (replace flat term-coverage).** Approximate IDF from doc-frequency across the CURRENT fetched candidate pool (no corpus needed) so rare terms ("teradyne") outweigh common ones ("market"). Length-normalize title-TF vs body/tags-TF, title boost ~3×, one saturation curve (k1~1.4, b~0.4). Keep output in the existing 0..0.9 range so `score.py` weights stay valid. | high | med | **med** |
| ~~4~~ | precision | **✅ DONE 2026-06-11 (iteration 3)** — token-set (EN) / char-trigram (CJK) Jaccard ≥0.6 near-dup pass in `normalize.dedupe()`, after the exact pass, highest-score copy wins; short-title guard against over-merge. `lastdays.py` refactored to reuse it. Live: merged 7 extra cross-source dups on "OpenAI" 10d. | high | med | low |
| ~~5~~ | precision | **✅ DONE 2026-06-11 (iteration 4)** — `base.adaptive_topic_gate()` wired into the orchestrator for the 3 ungated full-text sources (hackernews/github/polymarket); ≥2-token queries return on-topic subset when ≥3 remain, else keep all (recall). Audit found the other 5 listed sources already gate at fetch. xiaohongshu (bridge source) left as-is. Live: "open source LLM" HN 27→13. | high | small | med |
| ~~6~~ | new-source | **✅ DONE 2026-06-11 (iteration 2)** — `sources/googlenews.py`, degraded RSS tier, `when:{N}d` + window re-check + `is_on_topic` gate. Mainstream-news layer HN/Reddit miss. | high | small | low |
| 7 | reddit | **Opt-in official-OAuth Reddit tier** gated behind `REDDIT_CLIENT_ID`/`SECRET` env (top-priority tier ONLY when present). `client_credentials` → `oauth.reddit.com/r/<sub>/search` for full engagement at 100 QPM. Engine stays zero-key by default; dormant unless the user opts in. The only ToS-clean live-complete-engagement path. | high | med | low |
| 8 | precision | **RE-SCOPED 2026-06-11 — do the SAFE slice only.** Original (Porter stemmer + acronym map) deferred: observed gaps (MCP↔"model context protocol", "rust async runtime") are acronym/semantic, NOT stemming-fixable, and an acronym map is arbitrary/unscalable without embeddings (no deps). SAFE slice worth doing: a **phrase/bigram adjacency bonus** in `title_relevance` only (contiguous query tokens beat scattered), capped below a full match — ranking-only, does NOT touch the `is_on_topic` gate, so no noise-regression risk. Optionally a *very* light plural/tense normalizer (-s/-es/-ed) with length guards, but only after measuring it doesn't loosen the gate. | med | small | low |
| ~~9~~ | precision | **✅ DONE 2026-06-11 (iteration 5)** — (a) per-source `⚠ no strongly-relevant results` flag + global NOTE when max relevance < 0.4 (`render.py`). (b) `canonical_url` strips only tracking params + unfolds m./amp. hosts + `/amp`, keeps content params (fixes `?v=`/`?id=` over-collapse). 10 new tests. | med | small | low |
| 10 | reddit | **Formalize Reddit `.rss` as the honest degraded FLOOR tier** (`www.reddit.com/r/<sub>/search.rss?...` + site-wide, via `get_text`; Atom parse; `degraded=true`, no engagement). Guarantees the engine never returns zero Reddit results when PullPush/Arctic-Shift/JSON are down. (Partly exists; make it the explicit last tier.) | med | small | low |
| 11 | speed | **DEPRIORITIZED 2026-06-11** (measured: speed headroom is small, cache already dominates). Conditional GET (ETag / If-Modified-Since + 304) on the day cache — saves payload transfer cross-day for sources that emit validators. Revisit only if cold-run latency becomes a problem. | low | med | low |
| ~~12~~ | new-source | **✅ DONE 2026-06-11 (iteration 6)** — `sources/arxiv.py`, degraded Atom source, phrase `all:"<q>"` search, title-OR-abstract gate, window-rechecked. Live: 29 papers for "large language model agents". | med | small | low |
| 13 | new-source | **Bing News RSS** (`www.bing.com/news/search?q=<q>&format=rss`) as a 2nd mainstream corroborator; dedupe against Google News by normalized URL/title. Degraded. | med | small | low |
| 14 | speed | **Keep-alive connection reuse within paginated same-host sources** (Algolia/HN pages, multi-page GitHub) via a module-local, per-thread `http.client.HTTPSConnection` (NOT a global pool — that reinvents urllib3). Drops repeated TCP+TLS handshakes. | med | med | **med** |
| 15 | new-source | **Mastodon hashtag-timeline source** (`mastodon.social/api/v1/timelines/tag/<tag>?limit=40`). Real `favourites/reblogs/replies` counts. CAVEAT: free-text `/api/v2/search` returns empty statuses without a token — only the hashtag-timeline path is keyless. Register lower-confidence so fresh 0-engagement posts don't distort normalization. | med | med | **med** |
| ~~16~~ | speed | **✅ DONE 2026-06-11 (iteration 7)** — `_pool_size()` cap 24; all 12 EN sources run concurrently (was queuing 4 behind 8). Measured cold ≈1.9s, warm ≈0. | med | small | low |
| 17 | anti-bot | **Per-source "protection class" tag** (`ja4_gated`/`header_heuristic`/`open`) in the tier framework so JA4-gated endpoints (`www.reddit.com search.json`) skip straight to the lenient tier instead of burning the retry budget on an unfixable 403. Pairs with the documented TLS limitation. | med | med | low |
| 18 | precision | **2nd large Lemmy instance** (lemmy.ml / programming.dev) deduped by post URL + a header-builder lint test (never emit `sec-ch-ua` with a non-Chromium UA; keep platform aligned with UA OS; never attach `Sec-Fetch-User`/`Upgrade-Insecure-Requests` on api). | low | small | low |
| 19 | new-source | **Popularity-enrichment helpers** (pypistats / npm downloads / Wikipedia pageviews) keyed by a resolved entity, attached to `Item.metadata` for the synthesizer ONLY (NOT into cross-source engagement normalization — units differ). Heavy daily cache. Narrow applicability. | low | med | low |
| 20 | precision | **Clean Bluesky post titles before scoring/dedup** (found iteration 3). Bluesky uses post text as the "title", which often ends with the shared article's bare URL ("…www.axios.com/2026/06/08"). Strip trailing/inline bare URLs (and collapse to the article's real title where a link card exists) in `sources/bluesky.py` so relevance scoring and the near-dup Jaccard aren't diluted by URL tokens. | med | small | low |

---

## New keyless sources, ranked (detail for #1, #6, #12, #13, #15)

1. **PullPush.io** (Pushshift successor) — `api.pullpush.io/reddit/search/submission/?q=&after=&before=&sort=desc&sort_type=created_utc&size=100` (+ `/search/comment/`). Real Reddit-WIDE `score`+`num_comments`. Keyless, alive 2026. Limits: soft 15/min, hard 30/min, 1000/hr. 3rd-party; can lag very recent items. **Single best fix for the Reddit pain point.**
2. **Arctic-Shift** — `arctic-shift.photon-reddit.com/api` (posts/comments search; confirm path casing live). Real `score`+`num_comments`; better for per-subreddit/per-user (PullPush better Reddit-wide). Maintained 2026; also bulk torrent dumps.
3. **HN Algolia `search_by_date`** — keyword + native epoch date window + points gate. Strict upgrade over Firebase/front-page HN.
4. **Google News RSS** — `news.google.com/rss/search?q=<q>%20when:{N}d&hl=en-US&gl=US&ceid=US:en`. No engagement (degraded). Server-side recency. ~100-item cap.
5. **arXiv API** — Atom, no engagement. Highest value for AI/research queries.
6. **Bing News RSS** — `www.bing.com/news/search?q=<q>&format=rss`. 2nd mainstream feed for cross-check.
7. **Mastodon hashtag timeline** — real engagement on older posts; only the hashtag path is keyless.
8. **Lemmy 2nd instance** — widen the only mature keyless Reddit-alternative search.
9. **Product Hunt front-page RSS** (`producthunt.com/feed`) — no vote counts, front-page only; low priority (GraphQL needs a token).

---

## Documented hard limitations (stdlib ceiling — keep honest, do NOT try to "fix")

- **TLS fingerprinting (JA3/JA4)** is computed at the ClientHello before any header is sent; Python's OpenSSL ClientHello matches no browser. **No header craft fixes it.** Root cause of `www.reddit.com search.json` 403s. Needs a 3rd-party TLS stack (`curl_cffi`/`tls-client`/`rnet`) — out of scope.
- `ssl.SSLContext` **cannot** build a Chrome-matching JA4 (TLS1.3 ciphersuite order not settable, OpenSSL extension order fixed/non-browser, GREASE differs).
- **HTTP/2 not in stdlib** (urllib is HTTP/1.1). Never speaking h2 is itself a mismatch. Multiplexing needs httpx/h2 (3rd-party). Concurrency stays thread-based.
- **Post-quantum TLS** (X25519MLKEM768, default Chrome 131+) is a pre-HTTP signal stdlib can't send → UA pinned to 124 to reduce (not eliminate) the inconsistency.
- **Brotli** has no stdlib decoder; **zstd** only in 3.14 `compression.zstd` (engine on 3.12). Only `gzip`/`deflate` advertised.
- **UA rotation is net-NEGATIVE** over a fixed JA4 — pin one self-consistent identity instead.
- urllib's single `timeout=` is both connect + per-read inactivity; no separate connect/read or true wall-clock cap without a 3rd-party lib.
- urllib opens a fresh TCP+TLS connection per `urlopen` (no pooling). `http.client` keep-alive is serial + not thread-safe → reuse only module-local/per-thread.
- **NOT viable keyless in 2026 — do not add:** Nitter/X mirrors (need real X accounts, often blocked → X stays on WebSearch), Tildes (no RSS/JSON), Mastodon free-text status search (token-gated), OpenAlex/Semantic Scholar recency (key/queue-gated), Product Hunt GraphQL (token), Mbin/PieFed (no mature query API).

---

## How this loop runs

1. Run `lastdays` on a current web-scraping topic to gather intel (using the tool dogfoods it).
2. Re-run the research workflow (or a focused single-angle agent) to refresh techniques/sources.
3. Implement the top stdlib-safe item from "Next up", run `python3 -m pytest tests/ -q`, verify live.
4. Append a Status log entry, move the item to Done, local-commit checkpoint (no push unless asked).
