"""Minimal stdlib HTTP client with retry/backoff (no third-party deps).

Trimmed from the upstream last30days http.py: JSON GET/POST with 429-aware
exponential backoff, plus get_text() (browser UA, never raises) for keyless
RSS/HTML endpoints.
"""

from __future__ import annotations

import gzip
import json
import re
import sys
import time
import urllib.error
import urllib.request
import zlib
from typing import Any, Optional, Union
from urllib.parse import urlencode

from . import cache

DEFAULT_TIMEOUT = 30
MAX_RETRIES = 4
MAX_429_RETRIES = 2
RETRY_DELAY = 2.0
# One self-consistent macOS Chrome identity, sent on EVERY request (JSON + HTML).
# We do NOT rotate the UA: rotating a browser UA over the single fixed OpenSSL
# ClientHello (whose JA4 matches no real browser) maps many identities onto one
# impossible TLS fingerprint — a STRONGER bot tell than a stable UA. The UA
# version, the sec-ch-ua brand version, and the platform token must stay in
# lockstep (a non-Chromium UA carrying Chrome-only sec-ch-ua, or a platform that
# disagrees with the UA OS token, is an instant cross-layer fail). Pinned to
# Chrome 124, which predates Chrome's default post-quantum key share, so a stdlib
# ClientHello that cannot send X25519MLKEM768 is at least not claiming a version
# that always would. See references/source-policy.md for the TLS/JA4 ceiling this
# header layer deliberately does NOT try to beat.
BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
SEC_CH_UA = '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"'
SEC_CH_UA_PLATFORM = '"macOS"'
HTML_ACCEPT = (
    "text/html,application/xhtml+xml,application/xml;q=0.9,"
    "image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7"
)
API_ACCEPT = "application/json, text/plain, */*"
# Only gzip + deflate: stdlib (zlib/gzip) decodes both. Brotli ('br') has no
# stdlib decoder and zstd only lands in 3.14's compression.zstd — advertising an
# encoding we cannot decode is worse than omitting it.
ACCEPT_ENCODING = "gzip, deflate"

_DEBUG = False


def set_debug(on: bool) -> None:
    global _DEBUG
    _DEBUG = on


def _log(msg: str) -> None:
    if _DEBUG:
        safe = re.sub(r"([?&])(key|api_key|token|secret)=[^&]*", r"\1\2=***", msg)
        sys.stderr.write(f"[http] {safe}\n")
        sys.stderr.flush()


def browser_headers(mode: str = "api", accept: Optional[str] = None) -> dict:
    """A self-consistent macOS-Chrome-124 header set.

    mode="navigate": a top-level HTML/RSS document GET (get_text). Carries the
        navigation Sec-Fetch-* set + Upgrade-Insecure-Requests, as a real browser
        does when you type a URL / follow a link.
    mode="api": a JSON/XHR fetch (request). Uses the cors/empty Sec-Fetch set and
        DELIBERATELY omits Sec-Fetch-User / Upgrade-Insecure-Requests — emitting
        those on an XHR is itself a cross-layer inconsistency a detector can flag.

    UA + sec-ch-ua + sec-ch-ua-platform are one pinned identity (no rotation —
    see BROWSER_USER_AGENT). Callers layer their own headers ON TOP of this, so a
    source can still override Accept / add Authorization / Referer / Cookie.
    """
    h = {
        "User-Agent": BROWSER_USER_AGENT,
        "Accept": accept or (HTML_ACCEPT if mode == "navigate" else API_ACCEPT),
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": ACCEPT_ENCODING,
        "sec-ch-ua": SEC_CH_UA,
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": SEC_CH_UA_PLATFORM,
    }
    if mode == "navigate":
        h["Upgrade-Insecure-Requests"] = "1"
        h["Sec-Fetch-Site"] = "none"
        h["Sec-Fetch-Mode"] = "navigate"
        h["Sec-Fetch-User"] = "?1"
        h["Sec-Fetch-Dest"] = "document"
    else:
        h["Sec-Fetch-Site"] = "same-origin"
        h["Sec-Fetch-Mode"] = "cors"
        h["Sec-Fetch-Dest"] = "empty"
    return h


def _decode_body(raw: bytes, encoding: str) -> str:
    """Decode a response body, transparently inflating gzip/deflate.

    A server MAY ignore our Accept-Encoding and reply identity, so we branch on
    the actual Content-Encoding header rather than assume. Unknown/identity →
    decode as-is. All decode failures fall back to the raw bytes (never raise).
    """
    if not raw:
        return ""
    enc = (encoding or "").lower().strip()
    data = raw
    if enc == "gzip":
        try:
            data = zlib.decompress(raw, 31)  # 16 + MAX_WBITS: gzip wrapper
        except zlib.error:
            try:
                data = gzip.decompress(raw)  # multi-member / trailing-garbage path
            except (OSError, zlib.error):
                data = raw
    elif enc == "deflate":
        try:
            data = zlib.decompress(raw)  # zlib-wrapped deflate
        except zlib.error:
            try:
                data = zlib.decompress(raw, -15)  # raw deflate, no zlib header
            except zlib.error:
                data = raw
    return data.decode("utf-8", errors="replace")


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
    # Start from a realistic Chrome identity, then let the caller's headers win
    # (sources override Accept / add Authorization, Referer, Cookie, …). This
    # kills the old bot "lastdays/0.1" UA that 11 of 12 sources sent on JSON GETs.
    merged = browser_headers("api")
    merged.update(headers or {})
    headers = merged

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
                body = _decode_body(resp.read(), resp.headers.get("Content-Encoding", ""))
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
    accept: Optional[str] = None,
    headers: Optional[dict] = None,
) -> Optional[str]:
    """Fetch decoded text as a navigating browser. Returns None on any failure.

    Sends the full navigation header set (Sec-Fetch document, Upgrade-Insecure,
    sec-ch-ua, gzip) so RSS/HTML endpoints see a plausible top-level request, not
    a bare UA. Cached like JSON GETs (RSS/HTML endpoints are idempotent), under a
    distinct GET-TEXT key so it never collides with a JSON GET to the same URL. A
    warm hit skips the network — the Reddit RSS fallback tier benefits on repeats.
    """
    hit = cache.get("GET-TEXT", url)
    if hit is not None:
        _log(f"CACHE HIT (text) {url}")
        return hit
    merged = browser_headers("navigate", accept=accept)
    if headers:
        merged.update(headers)
    try:
        text = request("GET", url, headers=merged, timeout=timeout, retries=retries, raw=True)
    except HTTPError as e:
        _log(f"get_text failed ({e}): {url}")
        return None
    if text is not None:
        cache.put("GET-TEXT", url, text)
    return text
