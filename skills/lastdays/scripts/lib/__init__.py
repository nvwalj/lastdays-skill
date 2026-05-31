"""lastdays engine library (stdlib-only).

Lightweight rewrite of the last30days engine: the agent host (Claude / OpenAI)
is the planner and synthesizer; this engine only fetches zero-key public sources
(Reddit / Hacker News / GitHub / Polymarket) with real engagement numbers and a
strict date window. See ../../SKILL.md for the runtime contract.
"""

__version__ = "0.1.0"
