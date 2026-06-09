"""Demand-signal detection for the demand-mining mode.

Turns one text (post, comment, issue, review) into a 0..1 "is this an unmet-need
signal?" score plus the signal TYPE. This is the rule-layer COARSE gate: the
engine keeps only texts with a real demand pattern (and drops self-promo /
already-solved noise), then the agent does the semantic judgement + clustering.

Why patterns, not keywords: searching the bare word "wish" returns "happy donut
day" noise (measured on Bluesky). A demand signal is a STRUCTURE -- "wish there
was a <tool-like thing>", "is there an app that", "I'd pay for" -- so we match
phrase shapes, REQUIRE a tool-like object for the wish/is-there forms, and
subtract for self-promo (with a link) and already-solved cues.
"""

from __future__ import annotations

import re

# Tool-like object words: a wish/is-there only counts as PRODUCT demand when it
# points at one of these, so "wish there was a rapture" / "a donut" don't match
# but "wish there was something to automate X" does.
_TOOL = (
    r"(tool|apps?|application|service|software|program|website|site|extension|"
    r"plugin|add-?on|library|package|framework|api|bot|script|automation|"
    r"integration|solution|product|platform|way|method|feature|something)"
)

# (regex, signal_type, base weight). Highest-weight matching pattern wins.
_SIGNALS: list[tuple[str, str, float]] = [
    # Willingness to pay -- the strongest signal.
    # Require a PURCHASE object ("pay for/$N/to use") -- "pay to see/fight" is
    # consumption, not product demand (measured: bare "I'd pay" was noisy).
    (r"\b(i ?'?d|i would|would happily|happy to|willing to|gladly)\s+pay\s+(for|to use|to have|to get|\$\d+|money for|good money|handsomely|monthly for|a premium|premium for)\b", "payment", 0.92),
    (r"\btake my money\b", "payment", 0.9),
    (r"\bshut up and take\b", "payment", 0.9),
    (r"\b(i ?'?d|i would|happy to)\s+(buy|purchase|subscribe to)\s+(a|an|this|some|it)\b", "payment", 0.88),
    # Explicit request for a tool that should exist.
    (rf"\bis there (a|an|any|some)\s+{_TOOL}\b", "wish_tool", 0.82),
    (rf"\bi wish (there (was|were)|i had|some ?(one|body) (would|could) (make|build))\b.{{0,25}}{_TOOL}", "wish_tool", 0.82),
    (rf"\b(does )?(any ?(one|body)|some ?(one|body)) knows? (of )?(a|an)\b.{{0,30}}{_TOOL}", "wish_tool", 0.78),
    (rf"\blooking for (a|an|some)\b.{{0,30}}{_TOOL}", "wish_tool", 0.75),
    (rf"\bwhy is ?n'?t there (a|an)\b.{{0,20}}{_TOOL}", "wish_tool", 0.78),
    (r"\bsome ?(one|body) should (build|make|create|invent)\b", "wish_tool", 0.8),
    (r"\bsomebody make this\b", "wish_tool", 0.8),
    # Self-built workaround -> strong latent need, no product yet.
    (r"\bmy (current |only )?workaround\b", "workaround", 0.72),
    (r"\bi (built|wrote|made|hacked together|cobbled together) (a|my own|this)\b.{0,25}(script|spreadsheet|bot|tool|hack|thing|macro)", "workaround", 0.7),
    (r"\bhacky (solution|workaround|way|fix)\b", "workaround", 0.68),
    # Feature request against an existing product.
    (r"\bfeature request\b", "feature_request", 0.62),
    (r"\bplease add\b", "feature_request", 0.6),
    (r"\bit would be (great|nice|helpful|amazing|awesome) if\b", "feature_request", 0.6),
    (r"\bmissing (feature|functionality|option|the ability)\b", "feature_request", 0.58),
    (r"\bwish (it|they) (could|had|would|supported)\b", "feature_request", 0.6),
    # Seeking a solution / recommendation / a better way (implicit demand). Added
    # after 3-agent review flagged these as the top recall gaps.
    (r"\b(there (has to|must) be|is there) a better way (to|of|for|than)\b", "seeking", 0.7),
    (r"\bwhat (do|are) (you|people|folks|the best)\b.{0,25}(use|using|recommend)\b", "seeking", 0.62),
    (rf"\brecommendations? for\b.{{0,20}}{_TOOL}", "seeking", 0.62),
    (r"\bhow do (you|y'?all|people|folks|i)\b.{0,30}(deal with|handle|manage|cope with|automate)\b", "seeking", 0.6),
    (r"\bneed a (better |simple |good )?way to\b", "seeking", 0.6),
    (r"\banyone else (struggle|have (trouble|issues?)|deal) with\b", "seeking", 0.55),
    (r"\bi keep having to (manually|do)\b", "seeking", 0.58),
    (r"\b(any )?alternatives? to\b", "seeking", 0.5),
    # Pain / frustration (weakest alone; needs corroboration by frequency).
    (r"\bi (hate|can'?t stand) (that|how|when|having)\b", "pain", 0.5),
    (r"\bso (frustrating|annoying|tedious|painful)\b", "pain", 0.48),
    (r"\b(i ?'?m )?(sick|tired) of\b", "pain", 0.5),
    (r"\bwasting (hours|time|so much time|my time)\b", "pain", 0.52),
    (r"\bpain in the (ass|butt|neck)\b", "pain", 0.5),
    (r"\bdrives me (crazy|nuts|insane|up the wall)\b", "pain", 0.5),
]

# Intensity amplifiers bump the score a little when present.
_INTENSITY = re.compile(
    r"\b(every (single )?time|killing me|desperate|constantly|for years|"
    r"a million times|over and over)\b", re.I)

# Anti-signals -> probably NOT an open unmet need.
# Self-promo / launch: advertising one's OWN product (counts only WITH a link).
_PROMO = re.compile(
    r"\b(check out my|i (just )?(built|made|launched|shipped|released)|"
    r"introducing|i ?'?m building|try (it|my|our) |sign ?up|waitlist|link in (bio|comments))\b",
    re.I)
_URL = re.compile(r"https?://|\b\w[\w-]*\.(com|io|dev|app|ai|co|net|org|xyz)\b", re.I)
# Already-solved cues (more common in replies, but appear in posts too).
_SOLVED = re.compile(
    r"\b(you can (just )?use|just use \w+|there ?'?s already (a|an)|already exists|"
    r"that ?'?s what \w+ (is|does|is for)|try using)\b", re.I)

_COMPILED = [(re.compile(p, re.I), t, w) for p, t, w in _SIGNALS]

DEMAND_THRESHOLD = 0.45


def demand_signal(text: str) -> tuple[float, str | None]:
    """(score 0..1, signal_type|None) for one text. 0/None = no demand signal.

    The highest-weight matching pattern sets the base; an intensity amplifier
    adds a little; self-promo paired with a link and already-solved cues
    subtract. Tuned as a COARSE gate (recall over precision) -- the agent makes
    the final semantic call and clusters.
    """
    if not text:
        return 0.0, None
    best_w = 0.0
    best_t: str | None = None
    for rx, typ, w in _COMPILED:
        if w > best_w and rx.search(text):
            best_w, best_t = w, typ
    if best_t is None:
        return 0.0, None
    score = best_w
    if _INTENSITY.search(text):
        score += 0.08
    # A bare "I built a script" is a workaround, not an ad; only treat self-promo
    # as an anti-signal when it's paired with a link/CTA.
    if _PROMO.search(text) and _URL.search(text):
        score -= 0.5
    if _SOLVED.search(text):
        score -= 0.25
    score = max(0.0, min(1.0, round(score, 3)))
    if score <= 0.0:
        return 0.0, None
    return score, best_t


def is_demand(text: str, threshold: float = DEMAND_THRESHOLD) -> bool:
    """Coarse boolean gate for the engine to keep/drop a text."""
    return demand_signal(text)[0] >= threshold
