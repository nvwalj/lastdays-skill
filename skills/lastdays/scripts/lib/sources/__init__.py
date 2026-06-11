"""Importing this package registers every source with the registry.

Order here = order sources appear in the engine output. English engine sources
first, then the Chinese stubs.
"""

from . import hackernews, reddit, github, polymarket, kalshi, lobsters, devto, stackexchange, lemmy, bluesky, googlenews, arxiv  # noqa: F401  English (real)
from . import weibo, xiaohongshu, douyin, zhihu, bilibili  # noqa: F401  Chinese (stubs)
