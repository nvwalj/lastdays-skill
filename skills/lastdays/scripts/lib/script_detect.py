"""Detect the dominant writing script of a string (stdlib-only, no deps).

Used to flag items whose title is NOT Chinese/English so the synthesis can
translate or skip them instead of copying foreign characters verbatim into the
brief (the user's global rule: never mix Japanese/Korean/other scripts into a
reply). Returns a coarse script tag, not a full language ID.

Note ordering matters: Japanese is detected by its kana (hiragana/katakana),
checked BEFORE Han, because Japanese text mixes kana with Han characters. Plain
Han with no kana is reported as "zh".
"""

from __future__ import annotations

# (tag, lo, hi) inclusive Unicode codepoint ranges.
_RANGES = [
    ("ja", 0x3040, 0x309F),   # Hiragana
    ("ja", 0x30A0, 0x30FF),   # Katakana
    ("ko", 0xAC00, 0xD7A3),   # Hangul syllables
    ("ko", 0x1100, 0x11FF),   # Hangul Jamo
    ("zh", 0x4E00, 0x9FFF),   # CJK Unified (Han)
    ("zh", 0x3400, 0x4DBF),   # CJK Ext A
    ("ru", 0x0400, 0x04FF),   # Cyrillic
    ("ar", 0x0600, 0x06FF),   # Arabic
    ("th", 0x0E00, 0x0E7F),   # Thai
]

# Scripts a Chinese/English reader can consume directly. Everything else is
# "foreign" and gets flagged for translate-or-skip.
NATIVE = {"zh", "en"}


def _script_of(ch: str) -> str:
    cp = ord(ch)
    if 0x41 <= cp <= 0x5A or 0x61 <= cp <= 0x7A:  # ASCII letters
        return "en"
    for tag, lo, hi in _RANGES:
        if lo <= cp <= hi:
            return tag
    return ""  # digits, punctuation, emoji, spaces — script-neutral


def detect_script(text: str) -> str:
    """Return the dominant script tag of `text`.

    Counts letters by script and returns the most common. Japanese wins ties
    against Han when any kana is present (kana is unambiguously Japanese).
    Returns "en" for empty/neutral input.
    """
    if not text:
        return "en"
    counts: dict[str, int] = {}
    for ch in text:
        s = _script_of(ch)
        if s:
            counts[s] = counts.get(s, 0) + 1
    if not counts:
        return "en"
    if counts.get("ja"):  # any kana => Japanese, even if Han dominates the count
        return "ja"
    return max(counts, key=counts.get)


def is_foreign(text: str) -> bool:
    """True when the text's dominant script is neither Chinese nor English."""
    return detect_script(text) not in NATIVE
