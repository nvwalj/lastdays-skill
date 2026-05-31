"""Zhihu (知乎) source for lastdays - STUB (not implemented yet).

Planned implementation:
- Endpoint: Zhihu search API (api.zhihu.com / www.zhihu.com/api/v4/search_v3).
- Auth: web cookie (env: ZHIHU_COOKIE) for non-rate-limited search.
- Engagement: voteup_count / comment_count for answers/articles.
- Date: "created_time" / "updated_time" (unix -> YYYY-MM-DD; respect the window).

Until implemented, fetch() returns [] and the agent covers Zhihu via WebSearch
`site:zhihu.com`. See references/source-policy.md.
"""

from __future__ import annotations

from .. import registry
from ..dates import Window
from ..schema import Item


def fetch(query: str, window: Window, *, env: dict, depth: str = "default") -> list[Item]:
    return []  # not implemented yet


registry.register(
    registry.Source("zhihu", "zh", fetch, requires_key=True, implemented=False, aliases=("知乎",))
)
