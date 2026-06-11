# lastdays crawler — improvement backlog

Self-improving loop: each iteration uses `lastdays` to research current web-scraping
techniques + keyless sources, then folds the best findings back into the engine.
Goal: the fastest, most accurate keyless info-gathering tool. Constraint stays fixed:
**Python 3.12 stdlib only, zero third-party deps, zero API keys for engine sources.**

Sourced from a 5-angle research workflow (anti-bot/TLS, new sources, speed, Reddit,
precision) + synthesis, run 2026-06-11. Re-run the workflow each iteration to refresh.

---

## Status log

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
| 4 | precision | **Cross-source near-duplicate title clustering in `normalize.py dedupe()`.** After the exact URL/title pass, add SimHash (64-bit, blake2b per token, Hamming≤3) OR token-shingle Jaccard≥0.6 (simpler/more accurate for small N; 3-char shingles for CJK). Process highest-score-first so the strongest copy of a reshared story survives. | high | med | low |
| 5 | precision | **Adaptive hard precision gate: unify `is_on_topic` across the ~8 sources still using bare `NO_MATCH_FLOOR`** (hackernews, github, polymarket, kalshi, lemmy, bluesky, stackexchange, xiaohongshu). For ≥2-meaningful-token queries, DROP zero-hit items instead of flooring them; keep the floor for single-token queries (recall). Make it result-count-adaptive so thin niche topics still return something. | high | small | **med** |
| ~~6~~ | new-source | **✅ DONE 2026-06-11 (iteration 2)** — `sources/googlenews.py`, degraded RSS tier, `when:{N}d` + window re-check + `is_on_topic` gate. Mainstream-news layer HN/Reddit miss. | high | small | low |
| 7 | reddit | **Opt-in official-OAuth Reddit tier** gated behind `REDDIT_CLIENT_ID`/`SECRET` env (top-priority tier ONLY when present). `client_credentials` → `oauth.reddit.com/r/<sub>/search` for full engagement at 100 QPM. Engine stays zero-key by default; dormant unless the user opts in. The only ToS-clean live-complete-engagement path. | high | med | low |
| 8 | precision | **Phrase/bigram adjacency bonus + inlined Porter stemmer in `base.py`.** Small additive bonus when consecutive query tokens are adjacent in the title (contiguous "web scraping" beats scattered), capped below a true full match. Inline a ~200-line public-domain Porter stemmer (zero deps) on query+title tokens for recall. Leave the CJK bigram path unchanged. | high | med | **med** |
| 9 | precision | **"No strongly-relevant results" signal + selective URL canonicalization.** (a) If the merged pool's max relevance < 0.5 or all top items are floored/degraded, emit an explicit banner instead of presenting noise as findings. (b) In `canonical_url`, strip only known tracking params (utm_*, fbclid, gclid, ref) + unfold AMP/mobile hosts, instead of dropping ALL query strings. | med | small | low |
| 10 | reddit | **Formalize Reddit `.rss` as the honest degraded FLOOR tier** (`www.reddit.com/r/<sub>/search.rss?...` + site-wide, via `get_text`; Atom parse; `degraded=true`, no engagement). Guarantees the engine never returns zero Reddit results when PullPush/Arctic-Shift/JSON are down. (Partly exists; make it the explicit last tier.) | med | small | low |
| 11 | speed | **Conditional GET (ETag / If-Modified-Since + 304) layered on the day cache.** Persist last ETag + Last-Modified per URL in `cache.py`; on a cache MISS send `If-None-Match`/`If-Modified-Since`; catch `HTTPError` code 304 and serve the cached body. Saves payload transfer cross-day + for non-day-cached sources. Scope to sources that actually return validators. | med | med | low |
| 12 | new-source | **arXiv source** for research/ML topics (`export.arxiv.org/api/query?search_query=all:<q>&sortBy=submittedDate&sortOrder=descending&max_results=50`, Atom). Window-filter on `published`. Degraded (no engagement). Etiquette ≤1 req/3s single connection; sporadic 429s since ~Feb 2026 (engine backs off). | med | small | low |
| 13 | new-source | **Bing News RSS** (`www.bing.com/news/search?q=<q>&format=rss`) as a 2nd mainstream corroborator; dedupe against Google News by normalized URL/title. Degraded. | med | small | low |
| 14 | speed | **Keep-alive connection reuse within paginated same-host sources** (Algolia/HN pages, multi-page GitHub) via a module-local, per-thread `http.client.HTTPSConnection` (NOT a global pool — that reinvents urllib3). Drops repeated TCP+TLS handshakes. | med | med | **med** |
| 15 | new-source | **Mastodon hashtag-timeline source** (`mastodon.social/api/v1/timelines/tag/<tag>?limit=40`). Real `favourites/reblogs/replies` counts. CAVEAT: free-text `/api/v2/search` returns empty statuses without a token — only the hashtag-timeline path is keyless. Register lower-confidence so fresh 0-engagement posts don't distort normalization. | med | med | **med** |
| 16 | speed | **Tune `ThreadPoolExecutor` max_workers** to total expected in-flight requests (cap ~24–32) so all ~12 sources + sub-requests run concurrently, not queued. Verify the slowest source defines latency, not pool starvation. | med | small | low |
| 17 | anti-bot | **Per-source "protection class" tag** (`ja4_gated`/`header_heuristic`/`open`) in the tier framework so JA4-gated endpoints (`www.reddit.com search.json`) skip straight to the lenient tier instead of burning the retry budget on an unfixable 403. Pairs with the documented TLS limitation. | med | med | low |
| 18 | precision | **2nd large Lemmy instance** (lemmy.ml / programming.dev) deduped by post URL + a header-builder lint test (never emit `sec-ch-ua` with a non-Chromium UA; keep platform aligned with UA OS; never attach `Sec-Fetch-User`/`Upgrade-Insecure-Requests` on api). | low | small | low |
| 19 | new-source | **Popularity-enrichment helpers** (pypistats / npm downloads / Wikipedia pageviews) keyed by a resolved entity, attached to `Item.metadata` for the synthesizer ONLY (NOT into cross-source engagement normalization — units differ). Heavy daily cache. Narrow applicability. | low | med | low |

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
