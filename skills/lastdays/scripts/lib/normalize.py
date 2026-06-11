"""Dedupe + strict date-window filtering."""

from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .dates import Window
from .schema import Item

# Tracking/analytics params carry no content identity — two share links of the
# same article differ only here, so they must be stripped for dedup to collapse
# them. (All utm_* are dropped by prefix too.) Everything else is KEPT, because a
# query param is often the content id: youtube ?v=, ?id=, ?p=, paginated ?page=.
# Dropping ALL query (the old behavior) wrongly merged distinct ?v=A and ?v=B.
_TRACKING_PARAMS = frozenset({
    "fbclid", "gclid", "gclsrc", "dclid", "msclkid", "yclid", "twclid",
    "mc_cid", "mc_eid", "igshid", "si", "ref", "ref_src", "ref_url", "referrer",
    "source", "cmpid", "spm", "scm", "oc", "feature", "_hsenc", "_hsmi",
})
# Host prefixes that point at the same content as the bare host (mobile / AMP /
# www mirrors) — unfold so m.site/x and site/x, amp.site and site dedupe.
_HOST_PREFIXES = ("www.", "m.", "mobile.", "amp.")
_AMP_PATH_RE = re.compile(r"/amp(?:\.html?)?$")


def canonical_url(u: str) -> str:
    """Normalize a URL for dedup keying: https, unfold www/m/amp host, drop the
    fragment + trailing slash + AMP suffix, strip tracking params (keep the rest,
    order-normalized, case preserved so ?v=A and ?v=B stay distinct)."""
    if not u:
        return ""
    try:
        parts = urlsplit(u.strip())
    except ValueError:
        return u.strip().lower()
    netloc = parts.netloc.lower()
    for pre in _HOST_PREFIXES:
        if netloc.startswith(pre):
            netloc = netloc[len(pre):]
            break  # strip at most one leading mirror prefix
    path = re.sub(r"/+$", "", parts.path)
    path = _AMP_PATH_RE.sub("", path)
    kept = [
        (k, v) for k, v in parse_qsl(parts.query, keep_blank_values=False)
        if k.lower() not in _TRACKING_PARAMS and not k.lower().startswith("utm_")
    ]
    # Lowercase only scheme/host/path (the original behavior); keep query values
    # case-exact (?v=dQw4 != ?v=DQW4 are different resources).
    base = urlunsplit(("https", netloc, path, "", "")).lower()
    return f"{base}?{urlencode(sorted(kept))}" if kept else base


_TITLE_NORM_RE = re.compile(r"[^a-z0-9一-鿿]+")


def norm_title(title: str) -> str:
    """Normalize a title for cross-source matching: lowercase, strip punctuation/
    whitespace, keep ASCII alnum + CJK. So 'OpenAI releases GPT-6' and
    'openai releases gpt-6' (HN original vs a Reddit discussion of it) collapse
    to one key even when their URLs differ."""
    return _TITLE_NORM_RE.sub(" ", (title or "").lower()).strip()


def dedupe_keys(item: Item) -> tuple:
    """The keys that identify an item across sources: its canonical URL AND its
    normalized title. Two items collide if EITHER matches — the same story shared
    to two platforms usually keeps the title but not the URL."""
    cu = canonical_url(item.url)
    nt = norm_title(item.title)
    return (cu or None, nt or None)


# --- near-duplicate detection (beyond EXACT url/title) ------------------------
# The exact pass above only collapses identical normalized titles. The same story
# reworded or reordered across platforms ("OpenAI files paperwork for an IPO" vs
# "OpenAI confidentially files IPO paperwork"), or a news article that appears as
# both a Google News item and an HN/Reddit link to the publisher (whose URL never
# matches Google's redirect URL), still survives N times. A token-set / CJK-char-
# trigram Jaccard catches those. The threshold is deliberately conservative:
# losing a distinct story (false merge) is worse than showing a near-dup (false
# split), so short titles dedupe on EXACT match only and only clear overlaps merge.
NEAR_DUP_JACCARD = 0.6
_MIN_EN_TOKENS = 4          # shorter EN titles -> exact-only (Jaccard unstable)
_MIN_CJK_CHARS = 6          # shorter CJK titles -> exact-only
_CJK_RE = re.compile(r"[一-鿿]")  # matches norm_title's kept CJK range
# Grammatical stopwords only; dropping them keeps two unrelated headlines from
# merging just because they share "the/of/for". (Local copy to keep normalize
# free of source-layer imports.)
_DUP_STOPWORDS = frozenset({
    "the", "a", "an", "of", "for", "and", "or", "to", "in", "on", "at", "is",
    "are", "vs", "how", "what", "why", "with", "by", "from", "as", "it", "its",
    "this", "that", "new", "via", "you", "your", "be", "will", "has", "have",
})


def _dup_signature(title: str) -> frozenset | None:
    """A comparison set for near-dup detection, or None when the title is too
    short to compare safely (those dedupe on exact match only). EN -> content
    word-token set (order-insensitive, so reordered headlines match); CJK ->
    character-trigram set (space-less scripts have no word tokens)."""
    nt = norm_title(title)
    if not nt:
        return None
    if _CJK_RE.search(nt):
        cjk = "".join(c for c in nt if _CJK_RE.match(c))
        if len(cjk) < _MIN_CJK_CHARS:
            return None
        return frozenset(cjk[i:i + 3] for i in range(len(cjk) - 2))
    toks = [t for t in nt.split() if t not in _DUP_STOPWORDS]
    if len(toks) < _MIN_EN_TOKENS:
        return None
    return frozenset(toks)


def _jaccard(a: frozenset, b: frozenset) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _is_near_dup(sig: frozenset, kept_sigs: list) -> bool:
    """True if sig overlaps an already-kept signature at/above the threshold.
    (EN token sets and CJK trigram sets never overlap, so mixing is harmless.)"""
    return any(_jaccard(sig, k) >= NEAR_DUP_JACCARD for k in kept_sigs)


def dedupe(items: list[Item]) -> list[Item]:
    """Drop duplicates, keeping the higher-scored / higher-engagement copy.
    Process highest-score-first so the survivor is the strongest copy (e.g. an HN
    original over a low-score reshare). Two passes: (1) EXACT canonical URL or
    normalized title; (2) NEAR-duplicate titles via Jaccard (catches reworded /
    reordered headlines and the same article surfacing on Google News and as an
    HN/Reddit link, whose URLs differ)."""
    seen_url: set = set()
    seen_title: set = set()
    kept_sigs: list = []
    out: list[Item] = []
    for it in sorted(items, key=lambda i: (i.score, i.engagement_total()), reverse=True):
        cu, nt = dedupe_keys(it)
        if (cu and cu in seen_url) or (nt and nt in seen_title):
            continue  # exact: a stronger copy already kept
        sig = _dup_signature(it.title)
        if sig is not None and _is_near_dup(sig, kept_sigs):
            continue  # near-dup: a stronger copy of the same story already kept
        if cu:
            seen_url.add(cu)
        if nt:
            seen_title.add(nt)
        if sig is not None:
            kept_sigs.append(sig)
        out.append(it)
    return out


def filter_window(items: list[Item], window: Window, *, allow_undated: bool = False) -> list[Item]:
    """Keep items whose date falls inside the window.

    Out-of-window dated items are always dropped. Undated items are dropped by
    default (strict) and kept only when allow_undated=True.
    """
    out: list[Item] = []
    for it in items:
        stamp = it.ts if it.ts is not None else it.date
        if window.contains(stamp):
            out.append(it)
        elif allow_undated and it.ts is None and not it.date:
            out.append(it)
    return out
