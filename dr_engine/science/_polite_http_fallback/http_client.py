"""Stdlib-only stand-in for the subset of `polite_http.http_client` used here.

The science scripts were vendored from google-deepmind/science-skills, which
declares `polite-http` as a dependency. When that package is installed it is
used; otherwise the scripts fall back to this module so they still run with
nothing but the standard library.

Implements: HttpClient (per-host rate limit, retries with exponential backoff
and jitter), HttpResponse, HttpError and the DEFAULT_* backoff constants.
"""

from __future__ import annotations

import gzip
import json
import random
import threading
import time
import urllib.error
import urllib.request
import zlib
from typing import Any

DEFAULT_BACKOFF_BASE_SECS = 1.0
DEFAULT_BACKOFF_MAX_SECS = 60.0
DEFAULT_JITTER_SECS = 0.5
DEFAULT_TIMEOUT_SECS = 30.0
DEFAULT_MAX_RETRIES = 3
DEFAULT_RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})
DEFAULT_USER_AGENT = "dr-engine-science/1.0 (+polite_http fallback)"


def _decode_body(body: bytes, encoding: str | None) -> bytes:
  encoding = (encoding or "").lower()
  try:
    if encoding == "gzip" or body[:2] == b"\x1f\x8b":
      return gzip.decompress(body)
    if encoding == "deflate":
      return zlib.decompress(body)
  except (OSError, zlib.error):
    pass
  return body


class HttpResponse:
  """A completed HTTP response."""

  def __init__(self, status_code: int, headers: dict[str, str], body: bytes):
    self.status_code = status_code
    self.headers = headers
    self.body = body

  @property
  def text(self) -> str:
    return self.body.decode("utf-8", errors="replace")

  def json(self) -> Any:
    return json.loads(self.text)


class HttpError(Exception):
  """Raised for non-2xx responses and network failures (status_code=None)."""

  def __init__(self, message: str, status_code: int | None = None,
               body: bytes = b"", headers: dict[str, str] | None = None):
    self.status_code = status_code
    self.body = body
    self.headers = headers or {}
    summary = _decode_body(body, None)[:300].decode("utf-8", errors="replace")
    super().__init__(f"{message} {summary}".strip())


class HttpClient:
  """Rate-limited HTTP client bound to one base URL."""

  def __init__(self, base_url: str, qps: float = 1.0, referer: str | None = None,
               user_agent: str = DEFAULT_USER_AGENT,
               max_retries: int = DEFAULT_MAX_RETRIES,
               timeout: float = DEFAULT_TIMEOUT_SECS):
    self.base_url = base_url
    self.min_interval = 1.0 / qps if qps > 0 else 0.0
    self.referer = referer
    self.user_agent = user_agent
    self.max_retries = max_retries
    self.timeout = timeout
    self.retryable_status_codes = DEFAULT_RETRYABLE_STATUS_CODES
    self._lock = threading.Lock()
    self._next_allowed = 0.0

  def wait(self, min_sleep: float = 0.0) -> None:
    """Blocks until the rate limit allows another request."""
    with self._lock:
      now = time.monotonic()
      start = max(now + min_sleep, self._next_allowed)
      self._next_allowed = start + self.min_interval
    delay = start - time.monotonic()
    if delay > 0:
      time.sleep(delay)

  def _url(self, url: str) -> str:
    if url.startswith(("http://", "https://")):
      return url
    return self.base_url.rstrip("/") + "/" + url.lstrip("/")

  def _once(self, url: str, method: str, data: bytes | None,
            timeout: float) -> HttpResponse:
    headers = {"User-Agent": self.user_agent, "Accept-Encoding": "gzip"}
    if self.referer:
      headers["Referer"] = self.referer
    if data is not None and method == "POST":
      headers["Content-Type"] = "application/x-www-form-urlencoded"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
      with urllib.request.urlopen(req, timeout=timeout) as resp:
        resp_headers = dict(resp.headers.items())
        body = _decode_body(resp.read(), resp_headers.get("Content-Encoding"))
        return HttpResponse(resp.status, resp_headers, body)
    except urllib.error.HTTPError as e:
      raw = e.read() if e.fp else b""
      raise HttpError(f"HTTP {e.code} for {url}:", e.code, raw,
                      dict(e.headers.items()) if e.headers else {}) from None
    except (urllib.error.URLError, TimeoutError, OSError) as e:
      raise HttpError(f"Network error for {url}: {e}") from None

  def fetch(self, url: str, method: str = "GET", data: bytes | None = None,
            max_retries: int | None = None,
            timeout: float | None = None) -> HttpResponse:
    """Fetches `url`, retrying retryable statuses and network errors."""
    url = self._url(url)
    retries = self.max_retries if max_retries is None else max_retries
    timeout = self.timeout if timeout is None else timeout
    attempt = 0
    while True:
      self.wait()
      try:
        return self._once(url, method, data, timeout)
      except HttpError as e:
        retryable = (e.status_code is None
                     or e.status_code in self.retryable_status_codes)
        if not retryable or attempt >= retries:
          raise
        delay = min(DEFAULT_BACKOFF_BASE_SECS * 2**attempt,
                    DEFAULT_BACKOFF_MAX_SECS)
        retry_after = e.headers.get("Retry-After", "")
        if retry_after.isdigit():
          delay = max(delay, float(retry_after))
        time.sleep(delay + random.uniform(0, DEFAULT_JITTER_SECS))
        attempt += 1

  def fetch_bytes(self, url: str, **kwargs: Any) -> bytes:
    return self.fetch(url, **kwargs).body

  def fetch_text(self, url: str, **kwargs: Any) -> str:
    return self.fetch(url, **kwargs).text

  def fetch_json(self, url: str, **kwargs: Any) -> Any:
    return self.fetch(url, **kwargs).json()
