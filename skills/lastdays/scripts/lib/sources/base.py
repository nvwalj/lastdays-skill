"""Shared parse helpers for source modules."""

from __future__ import annotations

import html as _html
import re

# Pure grammatical stopwords only. Domain/category words (market, stock, news,
# rate, ...) are deliberately NOT listed: blacklisting them is fragile (it
# misfires when the "category" word IS the query's core, e.g. "stock" in "US
# stock market"). Instead the coverage curve below does the work — a title that
# matches only one weak token of a multi-word query scores in the low partial
# band, while matching every token scores high.
_STOPWORDS = frozenset({
    "the", "a", "an", "of", "for", "and", "or", "to", "in", "on", "at", "is",
    "are", "vs", "us", "my", "how", "what", "why",
})
_WORD_RE = re.compile(r"[a-z0-9]+")


def to_int(v, default: int = 0) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        try:
            return int(float(v))
        except (TypeError, ValueError):
            return default


def strip_html(text: str) -> str:
    if not text:
        return ""
    text = _html.unescape(text)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


_CJK_RE = re.compile(r"[぀-ヿ㐀-鿿]")
_CJK_CHAR = re.compile(r"[一-鿿぀-ヿ]")
# CJK queries match too rarely as a whole string ("开源大模型" is almost never
# in a title verbatim; real titles say "大模型开源" or "开源模型"). Score by
# character-bigram overlap instead — the standard approach for space-less CJK.
CJK_ON_TOPIC_COVER = 0.5  # >= half the query bigrams present -> on topic


def _cjk_bigrams(s: str) -> set:
    chars = "".join(c for c in (s or "") if _CJK_CHAR.match(c))
    if len(chars) < 2:
        return {chars} if chars else set()
    return {chars[i:i + 2] for i in range(len(chars) - 1)}


def _cjk_coverage(query: str, text: str) -> float:
    """Fraction of the query's CJK bigrams present in text (0..1)."""
    qb = _cjk_bigrams(query)
    if not qb:
        return 0.0
    return len(qb & _cjk_bigrams(text)) / len(qb)


def _query_hits(query: str, text: str):
    """(unique meaningful query tokens, how many appear whole-word in text).
    Returns (None, 0) for the CJK path (handled separately by callers)."""
    q = (query or "").strip().lower()
    w = (text or "").lower()
    if not q or not w:
        return [], 0
    toks = [t for t in _WORD_RE.findall(q) if t not in _STOPWORDS and len(t) > 1]
    if not toks:
        toks = _WORD_RE.findall(q)  # query was all stopwords -> use everything
    uniq = list(dict.fromkeys(toks))
    title_words = set(_WORD_RE.findall(w))
    hits = sum(1 for t in uniq if t in title_words)  # whole-word, not substring
    return uniq, hits


def _cjk_required_cover(n_bigrams: int) -> float:
    """Coverage needed to call a CJK query on-topic, scaled by query length.

    A short query has so few bigrams that the flat 0.5 floor means HALF the word
    matching counts as on-topic -- "瑞达" (a game NPC, or 瑞达利欧/Ray Dalio) then
    satisfies "泰瑞达" (Teradyne). Require the WHOLE short word; keep the lenient
    0.5 for longer queries, where the full string rarely appears verbatim and
    reordered fragments ("大模型开源" for "开源大模型") should still match.
    """
    return 1.0 if n_bigrams <= 2 else CJK_ON_TOPIC_COVER


def _cjk_match(query: str, text: str) -> bool:
    # On-topic if enough query bigrams appear (not the whole string verbatim).
    # The threshold scales with query length so a short word ("泰瑞达", 2 bigrams)
    # is not satisfied by a single shared bigram ("瑞达").
    qb = _cjk_bigrams(query)
    if not qb:
        return False
    return _cjk_coverage(query, text) >= _cjk_required_cover(len(qb))


def is_on_topic(query: str, text: str) -> bool:
    """Boolean topic gate: does `text` actually discuss `query`?

    Rules (no fragile domain stopword list — coverage does the work):
    - CJK: substring containment.
    - 1 meaningful token: one whole-word hit is enough ("Nvidia").
    - 2 tokens: BOTH must hit (so "Tesla stock" is not satisfied by "Ford stock").
    - 3+ tokens: at least 2 must hit (so "US stock market" is not satisfied by
      "market" alone in "Flea market find", but is by "stock market crash").
    Used as the hard gate by the Reddit RSS tier and the Douyin board, which have
    no engagement to fall back on and must drop off-topic noise outright.
    """
    if not query or not text:
        return False
    if _CJK_RE.search(query.replace(" ", "")):
        return _cjk_match(query, text)
    uniq, hits = _query_hits(query, text)
    if not uniq or hits == 0:
        return False
    if len(uniq) <= 1:
        return True
    if len(uniq) == 2:
        return hits == 2
    return hits >= 2


def title_relevance(query: str, text: str) -> float:
    """Continuous 0..0.9 relevance for RANKING (not gating — use is_on_topic to
    gate). Full coverage scores 0.9; partial scales down so a weak match can't
    masquerade as a full one. CJK is scored by bigram-overlap coverage (full
    overlap 0.9, partial scaled) since space-less CJK rarely matches verbatim.
    Used by HN scoring and the Douyin hot-value blend.
    """
    if _CJK_RE.search((query or "").replace(" ", "")):
        cover = _cjk_coverage(query, text)
        if cover <= 0:
            return 0.0
        return 0.9 if cover >= 0.999 else round(0.2 + 0.7 * cover, 3)
    uniq, hits = _query_hits(query, text)
    if not uniq or hits == 0:
        return 0.0
    if hits == len(uniq):
        return 0.9
    return round(0.2 + 0.4 * (hits / len(uniq)), 3)  # partial: below a full match


def meaningful_token_count(query: str) -> int:
    """How many distinct topic tokens the query carries — EN meaningful words, or
    CJK character bigrams. 1 means a single concept (recall matters, don't gate);
    >=2 means is_on_topic can safely require real coverage."""
    if not query:
        return 0
    if _CJK_RE.search(query.replace(" ", "")):
        return len(_cjk_bigrams(query))
    uniq, _ = _query_hits(query, query)
    return len(uniq)


GATE_MIN_FILL = 3


def adaptive_topic_gate(query: str, items: list, text_of=lambda it: it.title,
                        *, min_fill: int = GATE_MIN_FILL) -> list:
    """Adaptively drop off-topic items from a BROAD full-text source.

    The tag/handle sources (Stack Exchange, Dev.to, Lemmy, Bluesky, Kalshi) gate
    themselves at fetch. The broad full-text sources (Hacker News, GitHub,
    Polymarket) match server-side over body text too, so they can return items
    whose TITLE is irrelevant — historically floored (kept but sunk). This applies
    the same `is_on_topic` gate to their output, but only when it is safe to:

    - Single-token / sub-bigram queries pass through untouched (one weak word is
      all the recall there is; a hard gate would gut it).
    - For >=2-token queries, the on-topic subset is returned ONLY when it has
      >=min_fill items. A thin/niche topic with few on-topic hits keeps ALL its
      items (recall over precision) — the engine never empties a source whose
      weak matches are the only thing it found.
    """
    if meaningful_token_count(query) < 2:
        return items
    on = [it for it in items if is_on_topic(query, text_of(it))]
    return on if len(on) >= min_fill else items
