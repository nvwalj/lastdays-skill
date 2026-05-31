"""Bilibili (B站) source for lastdays - STUB (not implemented yet).

Planned implementation:
- Endpoint: api.bilibili.com/x/web-interface/search/type (video search).
- Auth: usually keyless for search; a SESSDATA cookie raises limits (env: BILI_COOKIE).
- Engagement: view / danmaku / like / coin / favorite / reply counts.
- Date: "pubdate" (unix -> YYYY-MM-DD; respect the window).

Until implemented, fetch() returns [] and the agent covers Bilibili via WebSearch
`site:bilibili.com`. See references/source-policy.md.
"""

from __future__ import annotations

from .. import registry
from ..dates import Window
from ..schema import Item


def fetch(query: str, window: Window, *, env: dict, depth: str = "default") -> list[Item]:
    return []  # not implemented yet


registry.register(
    registry.Source("bilibili", "zh", fetch, requires_key=False, implemented=False, aliases=("bili", "b站"))
)
