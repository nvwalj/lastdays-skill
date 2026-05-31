"""Weibo (微博) source for lastdays - STUB (not implemented yet).

Planned implementation:
- Endpoint: https://m.weibo.cn/api/container/getIndex (search container).
- Auth: WEIBO_SUB cookie (set via env/keychain key WEIBO_SUB).
- Engagement: reposts_count / comments_count / attitudes_count.
- Date: status "created_at" (parse to YYYY-MM-DD; respect the window).

Until implemented, fetch() returns [] and the agent covers Weibo via WebSearch
`site:weibo.com`. See references/source-policy.md ("Adding a Chinese source").
"""

from __future__ import annotations

from .. import registry
from ..dates import Window
from ..schema import Item


def fetch(query: str, window: Window, *, env: dict, depth: str = "default") -> list[Item]:
    return []  # not implemented yet


registry.register(
    registry.Source("weibo", "zh", fetch, requires_key=True, implemented=False, aliases=("wb", "微博"))
)
