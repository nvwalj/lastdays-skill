"""Tiny file-backed TTL cache for HTTP GETs (stdlib only).

Repeated queries — re-running a topic, or a 'X vs Y' run where the same token is
searched several times — otherwise re-hit every source over the network (~1s per
source). Caching GET responses keyed by URL drops a warm repeat to near-zero,
which is the single biggest lever on "fast". Mirrors firecrawl's cache-first
'index' engine, scoped to our keyless JSON sources.

Design notes:
- Keyed by a hash of (method + url). The URL already carries query params.
- Stored as JSON files under a temp dir; each file holds {"t": epoch, "v": value}.
- TTL default 900s (15 min) — fresh enough for "last N days" research, long
  enough to make repeat/vs runs instant. Override per call or via LASTDAYS_CACHE_TTL.
- Disable entirely with LASTDAYS_NO_CACHE=1 (e.g. for --refresh style runs).
- Best-effort: any cache error (disk, perms, corrupt file) falls back to a live
  fetch. The cache must never be able to break a query.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Callable, Optional

DEFAULT_TTL = 900  # 15 minutes
_DIR = Path(tempfile.gettempdir()) / "lastdays-cache"


def _enabled() -> bool:
    return os.environ.get("LASTDAYS_NO_CACHE", "").strip().lower() not in ("1", "true", "yes")


def _ttl() -> int:
    raw = os.environ.get("LASTDAYS_CACHE_TTL", "").strip()
    if raw.isdigit():
        return int(raw)
    return DEFAULT_TTL


def _key(method: str, url: str) -> str:
    return hashlib.sha256(f"{method.upper()} {url}".encode("utf-8")).hexdigest()[:32]


def _path(key: str) -> Path:
    return _DIR / f"{key}.json"


def get(method: str, url: str, ttl: Optional[int] = None) -> Optional[Any]:
    """Return a cached value if present and fresh, else None."""
    if not _enabled():
        return None
    ttl = _ttl() if ttl is None else ttl
    p = _path(_key(method, url))
    try:
        entry = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(entry, dict) or "t" not in entry:
        return None
    if time.time() - entry["t"] > ttl:
        return None  # stale
    return entry.get("v")


def put(method: str, url: str, value: Any) -> None:
    """Store a value. Best-effort; never raises."""
    if not _enabled():
        return
    try:
        _DIR.mkdir(parents=True, exist_ok=True)
        p = _path(_key(method, url))
        # Atomic-ish write: temp file then replace, so a concurrent read never
        # sees a half-written file.
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps({"t": time.time(), "v": value}), encoding="utf-8")
        tmp.replace(p)
    except (OSError, ValueError, TypeError):
        pass  # value not JSON-serializable, or disk issue — skip caching


def cached(method: str, url: str, fetch: Callable[[], Any], ttl: Optional[int] = None) -> Any:
    """Return cached value if fresh, else call fetch(), store, and return it."""
    hit = get(method, url, ttl)
    if hit is not None:
        return hit
    value = fetch()
    put(method, url, value)
    return value
