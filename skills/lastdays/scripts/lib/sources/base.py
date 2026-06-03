"""Shared parse helpers for source modules."""

from __future__ import annotations

import html as _html
import re


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
    """How well `text` matches `query`. 0..~0.75.

    CJK has no word spaces, so combine ASCII whitespace-token overlap with a
    substring containment check (catches Chinese). Shared by the Douyin source
    and the Reddit RSS fallback tier (which has no engagement signal and leans on
    this to drop off-topic noise like "Flea market find" for query "Nvidia").
    """
    q = (query or "").strip().lower()
    w = (text or "").lower()
    if not q or not w:
        return 0.0
    qc = q.replace(" ", "")
    wc = w.replace(" ", "")
    if qc and qc in wc:  # exact containment, e.g. 人工智能 in 人工智能写作
        return 0.75 if len(qc) >= 4 else 0.6
    q_tokens = {t for t in q.split() if t}
    if q_tokens:
        hits = sum(1 for t in q_tokens if t in w)
        if hits:
            return min(0.7, 0.3 + 0.4 * hits / len(q_tokens))
    return 0.0
