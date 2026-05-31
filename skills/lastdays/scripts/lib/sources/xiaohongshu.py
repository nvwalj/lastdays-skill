"""Xiaohongshu / RED (小红书) source for lastdays - STUB (not implemented yet).

Planned implementation:
- Path: a local xiaohongshu API/MCP bridge (cookie-authenticated), since RED has
  no open search API. Reference: github.com/xpzouying/xiaohongshu-mcp.
- Auth: logged-in cookie via a local bridge service (env: XHS_COOKIE).
- Engagement: liked_count / collected_count / comments_count / shares.
- Date: note "time" field (parse to YYYY-MM-DD; respect the window).

Until implemented, fetch() returns [] and the agent covers RED via WebSearch
`site:xiaohongshu.com`. See references/source-policy.md.
"""

from __future__ import annotations

from .. import registry
from ..dates import Window
from ..schema import Item


def fetch(query: str, window: Window, *, env: dict, depth: str = "default") -> list[Item]:
    return []  # not implemented yet


registry.register(
    registry.Source(
        "xiaohongshu", "zh", fetch, requires_key=True, implemented=False, aliases=("xhs", "rednote", "小红书")
    )
)
