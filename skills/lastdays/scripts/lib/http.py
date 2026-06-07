"""Minimal stdlib HTTP client with retry/backoff (no third-party deps).

Trimmed from the upstream last30days http.py: JSON GET/POST with 429-aware
exponential backoff, plus get_text() (browser UA, never raises) for keyless
RSS/HTML endpoints.
"""

from __future__ import annotations

import json
import re
import sys
import time
import urllib.error
import urllib.request
from typing import Any, Optional, Union
from urllib.parse import urlencode

from . import cache

DEFAULT_TIMEOUT = 30
MAX_RETRIES = 4
MAX_429_RETRIES = 2
RETRY_DELAY = 2.0
USER_AGENT = "lastdays/0.1 (research skill; +https://github.com/)"
BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

_DEBUG = False


def set_debug(on: bool) -> None:
    global _DEBUG
    _DEBUG = on


def _log(msg: str) -> None:
    if _DEBUG:
        safe = re.sub(r"([?&])(key|api_key|token|secret)=[^&]*", r"\1\2=***", msg)
        sys.stderr.write(f"[http] {safe}\n")
        sys.stderr.flush()


class HTTPError(Exception):
    def __init__(self, message: str, status_code: Optional[int] = None, body: Optional[str] = None):
        super().__init__(message)
        self.status_code = status_code
        self.body = body


def request(
    method: str,
    url: str,
    headers: Optional[dict] = None,
    json_data: Optional[dict] = None,
    params: Optional[dict] = None,
    timeout: int = DEFAULT_TIMEOUT,
    retries: int = MAX_RETRIES,
    max_429_retries: int = MAX_429_RETRIES,
    raw: bool = False,
) -> Union[dict, list, str]:
    headers = dict(headers or {})
    headers.setdefault("User-Agent", USER_AGENT)

    if params:
        filtered = {k: str(v) for k, v in params.items() if v is not None}
        if filtered:
            sep = "&" if "?" in url else "?"
            url = f"{url}{sep}{urlencode(filtered)}"

    data = None
    if json_data is not None:
        data = json.dumps(json_data).encode("utf-8")
        headers.setdefault("Content-Type", "application/json")

    # Cache only idempotent JSON GETs (no body). POSTs are LLM calls (must not be
    # cached); raw responses are handled by get_text's own caching opt-in. A warm
    # hit skips the network entirely — the main lever on repeat/vs-run latency.
    cacheable = method.upper() == "GET" and data is None and not raw
    if cacheable:
        hit = cache.get("GET", url)
        if hit is not None:
            _log(f"CACHE HIT {url}")
            return hit

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    _log(f"{method} {url}")

    last_error: Optional[HTTPError] = None
    rate_limit_count = 0

    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read().decode("utf-8", errors="replace")
                if raw:
                    return body
                parsed = json.loads(body) if body else {}
                if cacheable:
                    cache.put("GET", url, parsed)
                return parsed
        except urllib.error.HTTPError as e:
            body = None
            try:
                body = e.read().decode("utf-8", errors="replace")
            except (OSError, UnicodeDecodeError):
                pass
            last_error = HTTPError(f"HTTP {e.code}: {e.reason}", e.code, body)
            _log(f"HTTP {e.code} {e.reason}")
            # 4xx other than 429 are not retryable.
            if 400 <= e.code < 500 and e.code != 429:
                raise last_error
            if e.code == 429:
                rate_limit_count += 1
                if rate_limit_count >= max_429_retries:
                    raise last_error
            if attempt < retries - 1:
                delay = RETRY_DELAY * (2 ** attempt) + (1 if e.code == 429 else 0)
                retry_after = e.headers.get("Retry-After") if hasattr(e, "headers") else None
                if retry_after:
                    try:
                        delay = float(retry_after)
                    except ValueError:
                        pass
                time.sleep(delay)
        except urllib.error.URLError as e:
            last_error = HTTPError(f"URL error: {e.reason}")
            _log(f"URL error: {e.reason}")
            if attempt < retries - 1:
                time.sleep(RETRY_DELAY * (attempt + 1))
        except json.JSONDecodeError as e:
            raise HTTPError(f"invalid JSON response: {e}")
        except (OSError, TimeoutError) as e:
            last_error = HTTPError(f"connection error: {type(e).__name__}: {e}")
            _log(f"connection error: {e}")
            if attempt < retries - 1:
                time.sleep(RETRY_DELAY * (attempt + 1))

    if last_error:
        raise last_error
    raise HTTPError("request failed with no error details")


def get(url: str, headers: Optional[dict] = None, **kwargs):
    return request("GET", url, headers=headers, **kwargs)


def post(url: str, json_data: dict, headers: Optional[dict] = None, **kwargs):
    return request("POST", url, headers=headers, json_data=json_data, **kwargs)


def post_raw(url: str, json_data: dict, headers: Optional[dict] = None, **kwargs) -> str:
    return request("POST", url, headers=headers, json_data=json_data, raw=True, **kwargs)


def get_text(
    url: str,
    timeout: int = DEFAULT_TIMEOUT,
    retries: int = 2,
    accept: str = "*/*",
    headers: Optional[dict] = None,
) -> Optional[str]:
    """Fetch decoded text with a browser UA. Returns None on any failure."""
    merged = {
        "User-Agent": BROWSER_USER_AGENT,
        "Accept": accept,
        "Accept-Language": "en-US,en;q=0.9",
    }
    if headers:
        merged.update(headers)
    try:
        return request("GET", url, headers=merged, timeout=timeout, retries=retries, raw=True)
    except HTTPError as e:
        _log(f"get_text failed ({e}): {url}")
        return None
