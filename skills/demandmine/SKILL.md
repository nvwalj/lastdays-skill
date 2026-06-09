---
name: demandmine
description: >-
  Mine real unmet user needs and startup-opportunity signals from what people
  actually ask for across communities (Hacker News, GitHub issues, Stack
  Overflow, Lemmy, Reddit, Bluesky). Reuses the lastdays zero-key engine but
  queries demand SIGNAL PHRASES ("is there a tool…", "I wish there was…", "I'd
  pay for…"), gates by demand strength, and you cluster the signals into ranked
  opportunities with Jobs-to-be-Done. Use to find what to build, validate a
  niche, or scan a domain for pain points and feature requests.
argument-hint: "demandmine [domain] [days]"
allowed-tools: Bash, Read, WebSearch
user-invocable: true
license: MIT
---

# demandmine

Find real unmet needs from what people ask for in public. A Python engine pulls
demand-signal posts across zero-key sources; **you** cluster them into ranked
opportunities. Signals are HYPOTHESES to validate, not proven needs.

## Step 1 — Parse the request

- **Domain**: the niche to mine (e.g. "developer tools", "note taking"). Leave
  empty for an open radar across technical communities.
- **Days**: a bare number is the window. Default **90** for demand mining (needs
  accrue slowly; a 7-day window is too thin). Range 1–365.

Restate domain + window in one line before running.

## Step 2 — Run the engine

`SKILL_DIR` is the directory of THIS file. The engine lives at
`$SKILL_DIR/../lastdays/scripts/lastdays.py`. Use `python3`.

```bash
python3 "<lastdays.py>" "<DOMAIN>" --mode demand --days <N>
```

- Default sources = the technical set (HN / Stack Overflow / GitHub / Lemmy /
  Reddit) — social chatter is filtered out for signal quality. Add `--sources`
  to override, or `--lang both` to include Chinese sources.
- An empty `<DOMAIN>` runs the open radar. A 1-word domain ("photos") narrows
  loosely; a 2-word domain ("note taking") narrows strictly (both words must
  appear), so prefer 1 strong word if recall is low.

It prints a `DEMAND SIGNALS` block: each item = opportunity score, signal type
(payment / wish_tool / workaround / feature_request / seeking / pain), source,
date, engagement, title, url.

## Step 3 — Cluster into opportunities (your job, the real work)

Read the signals, then:

1. **Group** signals voicing the SAME underlying need into clusters.
2. **Infer the Job-to-be-Done** — the root need, NOT the user's proposed
   solution. ("They asked for X to accomplish Y; the real job is Y.")
3. **Score each cluster's Opportunity** (Ulwick-style): breadth (how many
   INDEPENDENT authors & sources voice it) × demand strength (payment >
   wish_tool / feature_request > seeking / pain) × unmet-ness (no existing good
   solution mentioned). Recurring + fresh beats a one-off.
4. **Drop noise**: jokes, already-solved (a reply points to an existing tool),
   one-person rants, and literal matches that aren't real product needs.

## Step 4 — Output a ranked opportunity list

Top opportunity first, each with:

- **One-line need** + the JTBD.
- **Opportunity read**: how broad / intense / unmet it is, citing the strongest
  evidence posts inline as `[title](url)`.
- **Existing-solution gap**: what's already out there and why it falls short (if
  known).
- An honest caveat wherever the signal is thin (single author, one source).

Close with: which 1–2 look strongest, and a reminder that these are signals to
**validate by talking to ~5 real users** before building anything.

## Honesty (do not skip)

- Signals ≠ validated demand. Frequency can be an echo chamber — verify
  independent authorship, not just post count.
- Survivorship bias: you only see people who post (developers / English
  communities are over-represented). Say so.
- `seeking` / `pain` are weak alone; weight `payment` / `wish_tool` /
  `feature_request` higher and corroborate by frequency before calling it real.
