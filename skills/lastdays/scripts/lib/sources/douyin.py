"""Douyin (抖音) source for lastdays - STUB (not implemented yet).

Planned implementation:
- Endpoint: Douyin web search / hot-search board (iesdouyin). Douyin != TikTok -
  do not substitute a TikTok pipeline here.
- Auth: web cookie (env: DOUYIN_COOKIE) for stable search.
- Engagement: digg_count (likes) / comment_count / share_count / play_count.
- Date: aweme "create_time" (unix -> YYYY-MM-DD; respect the window).

Until implemented, fetch() returns [] and the agent covers Douyin via WebSearch
`site:douyin.com`. See references/source-policy.md.
"""

from __future__ import annotations

from .. import registry
from ..dates import Window
from ..schema import Item


def fetch(query: str, window: Window, *, env: dict, depth: str = "default") -> list[Item]:
    return []  # not implemented yet


registry.register(
    registry.Source("douyin", "zh", fetch, requires_key=True, implemented=False, aliases=("dy", "抖音"))
)
