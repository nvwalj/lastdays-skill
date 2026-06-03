"""Shared parse helpers for source modules."""

from __future__ import annotations

import html as _html
import re

# Words too generic to count as a topic match on their own (avoids "AI" or
# "market" alone qualifying an off-topic title).
_STOPWORDS = frozenset({
    "the", "a", "an", "of", "for", "and", "or", "to", "in", "on", "at", "is",
    "are", "vs", "us", "my", "how", "what", "why", "new", "best", "top",
    # Broad category words that, alone, do not make a title on-topic. Keeps
    # "market" from qualifying "Flea market find" for query "US stock market"
    # while the specific token ("stock") still must appear.
    "market", "stock", "stocks", "news", "price", "update", "today", "app",
    "ai", "tech", "data", "guide", "review", "list",
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


def title_relevance(query: str, text: str) -> float:
    """How well `text` matches `query`. 0..~0.9.

    ASCII and CJK need different matching because CJK has no word spaces:
    - CJK: substring containment (e.g. 人工智能 inside 人工智能写作).
    - ASCII: WHOLE-WORD matching of the query's meaningful (non-stopword) tokens,
      scored by the fraction covered. Word-boundary matching is deliberate so
      "AI" does not match "stainless" and "market" alone does not let
      "Flea market find" through for query "US stock market".
    Shared by the Douyin source and the Reddit RSS fallback tier (which has no
    engagement to rank by and relies on this to suppress off-topic noise).
    """
    q = (query or "").strip().lower()
    w = (text or "").lower()
    if not q or not w:
        return 0.0

    # CJK containment path (covers Chinese/Japanese topics with no word breaks).
    qc = q.replace(" ", "")
    if re.search(r"[぀-ヿ㐀-鿿]", qc) and qc in w.replace(" ", ""):
        return 0.85 if len(qc) >= 4 else 0.6

    # ASCII whole-word path. Meaningful tokens only; require real coverage.
    q_tokens = [t for t in _WORD_RE.findall(q) if t not in _STOPWORDS and len(t) > 1]
    if not q_tokens:
        q_tokens = _WORD_RE.findall(q)  # query is all stopwords -> fall back to all
    if not q_tokens:
        return 0.0
    title_words = set(_WORD_RE.findall(w))
    # De-dup query tokens so a repeated word can't inflate coverage.
    uniq = list(dict.fromkeys(q_tokens))
    hits = sum(1 for t in uniq if t in title_words)  # whole-word, not substring
    if not hits:
        return 0.0
    # Require real coverage: a multi-word query must match at least half its
    # meaningful tokens, so "US stock market" is NOT satisfied by "market" alone
    # in "Flea market find" (1/3). A single-token query passes on its one hit.
    needed = (len(uniq) + 1) // 2  # ceil(half); ==1 for single-token queries
    if hits < needed:
        return 0.0
    coverage = hits / len(uniq)
    return round(min(0.9, 0.25 + 0.65 * coverage), 3)
