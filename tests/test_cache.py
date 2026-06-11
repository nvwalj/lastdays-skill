"""TTL cache: hits within TTL, misses when stale/disabled, GET-only in http."""

import time

from lib import cache, http


def _isolate(monkeypatch, tmp_path):
    monkeypatch.setattr(cache, "_DIR", tmp_path / "c")
    monkeypatch.delenv("LASTDAYS_NO_CACHE", raising=False)
    monkeypatch.delenv("LASTDAYS_CACHE_TTL", raising=False)


def test_put_then_get_hits(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    cache.put("GET", "https://x/y", {"a": 1})
    assert cache.get("GET", "https://x/y") == {"a": 1}


def test_distinct_urls_dont_collide(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    cache.put("GET", "https://x/y?q=1", {"n": 1})
    cache.put("GET", "https://x/y?q=2", {"n": 2})
    assert cache.get("GET", "https://x/y?q=1") == {"n": 1}
    assert cache.get("GET", "https://x/y?q=2") == {"n": 2}


def test_stale_entry_misses(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    cache.put("GET", "https://x/y", {"a": 1})
    assert cache.get("GET", "https://x/y", ttl=0) is None  # ttl=0 => immediately stale


def test_disabled_by_env(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    monkeypatch.setenv("LASTDAYS_NO_CACHE", "1")
    cache.put("GET", "https://x/y", {"a": 1})
    assert cache.get("GET", "https://x/y") is None


def test_unserializable_value_skipped(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    cache.put("GET", "https://x/y", {1, 2, 3})  # set is not JSON-serializable
    assert cache.get("GET", "https://x/y") is None  # silently skipped, no crash


def test_http_get_uses_cache(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    calls = {"n": 0}

    class FakeResp:
        status = 200
        headers = {}  # real urllib responses always expose .headers (for Content-Encoding)
        def read(self): return b'{"hello": "world"}'
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def fake_urlopen(req, timeout=None):
        calls["n"] += 1
        return FakeResp()

    monkeypatch.setattr(http.urllib.request, "urlopen", fake_urlopen)
    r1 = http.get("https://api.example/search?q=ai")
    r2 = http.get("https://api.example/search?q=ai")
    assert r1 == r2 == {"hello": "world"}
    assert calls["n"] == 1  # second call served from cache, no network


def test_http_get_text_uses_cache(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    calls = {"n": 0}

    class FakeResp:
        status = 200
        headers = {}  # real urllib responses always expose .headers (for Content-Encoding)
        def read(self): return b"<rss>feed body</rss>"
        def __enter__(self): return self
        def __exit__(self, *a): return False

    monkeypatch.setattr(http.urllib.request, "urlopen",
                        lambda req, timeout=None: calls.update(n=calls["n"] + 1) or FakeResp())
    a = http.get_text("https://reddit.com/search.rss?q=python")
    b = http.get_text("https://reddit.com/search.rss?q=python")
    assert a == b == "<rss>feed body</rss>"
    assert calls["n"] == 1  # second call served from the text cache


def test_get_text_and_json_keys_dont_collide(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    # Same URL string, different fetch kind -> distinct cache entries.
    cache.put("GET", "https://x/y", {"json": True})
    cache.put("GET-TEXT", "https://x/y", "text body")
    assert cache.get("GET", "https://x/y") == {"json": True}
    assert cache.get("GET-TEXT", "https://x/y") == "text body"


def test_eviction_removes_stale_files_keeps_fresh(monkeypatch, tmp_path):
    import os
    _isolate(monkeypatch, tmp_path)
    monkeypatch.setattr(cache, "_EVICT_EVERY", 1)  # sweep every put for the test
    # Seed one fresh and one ancient entry.
    cache.put("GET", "https://fresh/x", {"a": 1})
    old = cache._path(cache._key("GET", "https://old/y"))
    old.write_text('{"t": 0, "v": {"b": 2}}', encoding="utf-8")
    ancient = time.time() - cache.EVICT_AGE - 100
    os.utime(old, (ancient, ancient))            # backdate mtime past EVICT_AGE
    # A put triggers the sweep.
    cache.put("GET", "https://trigger/z", {"c": 3})
    assert not old.exists()                       # stale file deleted
    assert cache.get("GET", "https://fresh/x") == {"a": 1}  # fresh survives


def test_eviction_is_amortized_not_every_put(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    # Default cadence: not every put sweeps (cost stays near zero).
    assert cache._EVICT_EVERY > 1


def test_http_post_not_cached(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    calls = {"n": 0}

    class FakeResp:
        status = 200
        headers = {}  # real urllib responses always expose .headers (for Content-Encoding)
        def read(self): return b'{"ok": 1}'
        def __enter__(self): return self
        def __exit__(self, *a): return False

    monkeypatch.setattr(http.urllib.request, "urlopen", lambda req, timeout=None: calls.update(n=calls["n"] + 1) or FakeResp())
    http.post("https://api.example/x", {"body": 1})
    http.post("https://api.example/x", {"body": 1})
    assert calls["n"] == 2  # POST is never cached (LLM calls etc.)


def test_paged_requests_are_cached(monkeypatch, tmp_path):
    """Long-window page-walk must cache every page URL, so a warm repeat does
    zero network (guards the paging x cache interaction added in round 17)."""
    _isolate(monkeypatch, tmp_path)
    net = {"n": 0}

    class FakeResp:
        status = 200
        headers = {}  # real urllib responses always expose .headers (for Content-Encoding)
        def __init__(self, body): self._b = body
        def read(self): return self._b
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def fake_urlopen(req, timeout=None):
        net["n"] += 1
        # distinct body per page so each URL is a distinct cache entry
        return FakeResp(b'{"hits": [{"objectID": "x"}]}')

    monkeypatch.setattr(http.urllib.request, "urlopen", fake_urlopen)
    # Two distinct page URLs, fetched twice each.
    for _ in range(2):
        http.get("https://api.example/search?q=ai&page=0")
        http.get("https://api.example/search?q=ai&page=1")
    assert net["n"] == 2  # 2 unique pages hit once each; second round all cached
