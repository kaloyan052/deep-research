#!/usr/bin/env python3
"""Deep Research Engine v10.0 — Resilient Polyglot HTTP Transport.

v9.0 fetched practitioner sources with a bare ``urllib.request.urlopen`` and
``raw_bytes.decode("utf-8", errors="replace")``. Consequences observed in audit:

  * Russian (cp1251), Japanese (Shift_JIS) and Chinese (GB18030) pages became
    mojibake, so verbatim quotes could never be verified against them;
  * gzipped responses were read as binary garbage;
  * 403/429 bot walls, Cloudflare interstitials and 5xx blips had **no retry
    and no fallback**; the trench miners swallowed every exception with
    ``except Exception: pass``, so a total blackout looked like "no evidence";
  * no byte cap (an unbounded ``read()``), no scheme validation, and no record
    of *how* a snapshot was obtained -- so inline and fetched sources were
    indistinguishable in ``sources/index.jsonl``.

This module is the single, auditable transport for all network reads. It is
**fail-loud**: every outcome is a structured :class:`FetchResult` carrying
status, charset, ``via``, SHA-256, attempt count, bot-wall flag and errors.
It never raises to callers and never silently drops a failure.

Reader-proxy fallback (``r.jina.ai``) is **opt-in only** (explicit flag or
``DR_ALLOW_JINA=1``), consistent with the workspace rule that a URL must not be
sent to a third party without the user's permission.

Pure Python 3.10+ standard library. Windows cp1252-safe.
"""

from __future__ import annotations

import codecs
import gzip
import hashlib
import html as html_lib
import json
import math
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zlib
from dataclasses import dataclass, field
from typing import Any

__all__ = [
    "FetchResult",
    "DecodedText",
    "is_safe_url",
    "display_url",
    "url_as_text",
    "decode_bytes",
    "detect_bot_wall",
    "resilient_fetch",
    "fetch_json",
    "fetch_xml",
    "fetch_with_fallbacks",
    "benchmark_fallback_coverage",
]

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36 (DR-Polyglot/10.0)"
)

# Statuses where a bounded retry is rational. 401/403 are deliberately excluded:
# retrying the identical transport against a bot wall only burns time.
TRANSIENT_STATUSES = frozenset({408, 425, 429, 500, 502, 503, 504})
BLOCK_STATUSES = frozenset({401, 403, 406, 451})

BOT_WALL_RE = re.compile(
    r"(just a moment|checking your browser|enable javascript|access denied|"
    r"attention required|verify you are human|captcha|cloudflare|"
    r"you have been blocked|unusual traffic|ddos protection)",
    re.I,
)

# Codec aliases seen on non-English practitioner sites.
_CODEC_ALIASES = {
    "windows-1251": "cp1251", "win-1251": "cp1251", "cp-1251": "cp1251",
    "windows-1252": "cp1252", "iso-8859-1": "cp1252", "latin1": "cp1252",
    "latin-1": "cp1252", "ascii": "cp1252",
    "shift-jis": "shift_jis", "sjis": "shift_jis", "x-sjis": "shift_jis",
    "gb2312": "gb18030", "gbk": "gb18030", "gb-2312": "gb18030",
    "ks_c_5601-1987": "euc_kr", "euc-kr": "euc_kr",
    "utf8": "utf-8", "utf-8-sig": "utf-8",
}
_SINGLE_BYTE_CODECS = frozenset({"cp1251", "cp1252", "cp1250", "latin-1", "euc_kr", "koi8-r"})

_CHARSET_HEADER_RE = re.compile(r"charset\s*=\s*[\"']?([A-Za-z0-9_.\-]+)", re.I)
_META_CHARSET_RE = re.compile(
    r"<meta[^>]+charset\s*=\s*[\"']?([A-Za-z0-9_.\-]+)", re.I
)


@dataclass
class DecodedText:
    """Outcome of charset-aware byte decoding."""

    text: str
    charset: str
    lossy: bool
    notes: list[str] = field(default_factory=list)


@dataclass
class FetchResult:
    """Immutable-by-convention record of one network read attempt chain.

    ``ok`` is True only when a decodable, non-empty body was obtained. ``via``
    records provenance (``direct`` / ``direct:gzip`` / ``reader`` / ``none``)
    so a downstream snapshot index can distinguish a fetched page from a
    third-party transcription or an inline seed.
    """

    ok: bool
    url: str
    text: str
    status: int | None
    via: str
    charset: str
    sha256: str
    attempts: int
    error: str
    bot_wall: bool
    elapsed_ms: float
    truncated: bool
    lossy: bool
    warnings: list[str] = field(default_factory=list)
    # v11.0: authority downgrade + full fallback audit trail. A cached or
    # syndicated copy is NEVER a primary T1 snapshot.
    evidence_class: str = "primary_fetched"
    fallback_chain: list[dict[str, Any]] = field(default_factory=list)
    source_url: str = ""

    @property
    def is_primary(self) -> bool:
        return self.evidence_class == "primary_fetched"

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok, "url": self.url, "status": self.status, "via": self.via,
            "charset": self.charset, "sha256": self.sha256, "attempts": self.attempts,
            "error": self.error, "bot_wall": self.bot_wall,
            "elapsed_ms": round(self.elapsed_ms, 2), "truncated": self.truncated,
            "lossy": self.lossy, "warnings": list(self.warnings), "chars": len(self.text),
            "evidence_class": self.evidence_class,
            "fallback_chain": list(self.fallback_chain),
            "source_url": self.source_url or self.url,
        }


def _normalise_codec(name: str | None) -> str | None:
    if not name:
        return None
    key = name.strip().lower()
    key = _CODEC_ALIASES.get(key, key)
    try:
        codecs.lookup(key)
    except (LookupError, ValueError):
        return None
    return key


def _bounded_number(value: Any, default: float, lo: float, hi: float) -> float:
    """Coerce a network parameter to a finite, bounded float; never raises."""
    try:
        x = float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    if not math.isfinite(x):
        return default
    return min(hi, max(lo, x))


def display_url(url: Any) -> str:
    """v12.0: always produce a printable, JSON-serialisable URL label.

    A malformed collector value (None / bytes / int / object) must never make
    a provenance record unserialisable or crash a formatter.
    """
    if isinstance(url, str):
        return url
    if url is None:
        return ""
    if isinstance(url, bytes):
        return url.decode("utf-8", errors="replace")[:200]
    try:
        return str(url)[:200]
    except Exception:
        return "<unprintable-url>"


def url_as_text(url: Any) -> str:
    """Only real strings are fetchable. Malformed values become an unsafe "".

    Deliberately does NOT coerce bytes/ints into a URL: silently turning a
    malformed input into a live network request would be worse than failing.
    """
    return url if isinstance(url, str) else ""


def is_safe_url(url: Any, allow_private: bool = False) -> bool:
    """Reject non-HTTP schemes, credentials, and (by default) private hosts.

    ``file://`` would let a study spec read arbitrary local files into an
    evidence snapshot; ``javascript:`` / ``data:`` are meaningless for source
    capture. Loopback is allowed only for local test servers.

    v12.0 Frontier 4: total over malformed inputs. ``None``, bytes, ints,
    objects with a broken ``__str__`` and URLs with a malformed IPv6 literal
    all return False instead of raising ``AttributeError`` / ``ValueError``.
    """
    candidate = url_as_text(url)
    if not candidate:
        return False
    try:
        parts = urllib.parse.urlparse(candidate)
        scheme = parts.scheme.lower()
        hostname = parts.hostname
        username, password = parts.username, parts.password
    except (ValueError, TypeError, AttributeError):
        return False
    if scheme not in ("http", "https"):
        return False
    if not hostname or username or password:
        return False
    if not allow_private:
        host = hostname.lower().rstrip(".")
        if host in ("localhost", "127.0.0.1", "::1", "0.0.0.0") or host.startswith("127."):
            return False
    return True


def decode_bytes(raw: bytes, content_type: str = "") -> DecodedText:
    """Decode a response body using BOM, header, and HTML meta charset evidence.

    Priority: BOM > declared charset > ``<meta charset>`` > strict UTF-8 >
    lossy fallback. A single-byte declared codec is *not* trusted when the body
    is valid UTF-8 containing multibyte sequences -- a common misconfiguration
    on legacy Russian and Japanese hosts.
    """
    notes: list[str] = []
    if not raw:
        return DecodedText("", "unknown", False, ["empty body"])

    # 1. Byte-order marks are authoritative.
    bom_specs = (
        (b"\xef\xbb\xbf", "utf-8-sig", 3),
        (b"\xff\xfe\x00\x00", "utf-32-le", 4),
        (b"\x00\x00\xfe\xff", "utf-32-be", 4),
        (b"\xff\xfe", "utf-16-le", 2),
        (b"\xfe\xff", "utf-16-be", 2),
    )
    for bom, codec_name, skip in bom_specs:
        if raw.startswith(bom):
            try:
                return DecodedText(raw[skip:].decode(codec_name), codec_name, False, [f"BOM {codec_name}"])
            except UnicodeDecodeError:
                notes.append(f"BOM {codec_name} declared but body undecodable")

    declared = _normalise_codec(
        _CHARSET_HEADER_RE.search(content_type).group(1) if _CHARSET_HEADER_RE.search(content_type) else None
    )
    head = raw[:4096].decode("latin-1", "replace")
    meta_match = _META_CHARSET_RE.search(head)
    meta = _normalise_codec(meta_match.group(1)) if meta_match else None

    # Strict UTF-8 check used to detect mislabelled single-byte pages.
    utf8_ok = True
    try:
        utf8_text = raw.decode("utf-8")
    except UnicodeDecodeError:
        utf8_ok, utf8_text = False, ""
    utf8_has_multibyte = utf8_ok and any(ord(c) > 127 for c in utf8_text)
    if utf8_has_multibyte and declared in _SINGLE_BYTE_CODECS:
        notes.append(f"server declared {declared} but body is UTF-8; preferring UTF-8")
        declared = "utf-8"

    candidates: list[str] = []
    for codec_name in (declared, meta, "utf-8", "cp1252", "cp1251", "gb18030", "shift_jis"):
        codec_name = _normalise_codec(codec_name)
        if codec_name and codec_name not in candidates:
            candidates.append(codec_name)

    for codec_name in candidates:
        try:
            text = raw.decode(codec_name, errors="strict")
            if codec_name != "utf-8":
                notes.append(f"decoded as {codec_name}")
            return DecodedText(text, codec_name, False, notes)
        except (UnicodeDecodeError, LookupError):
            continue

    fallback = _normalise_codec(declared) or "cp1252"
    notes.append(f"no strict codec matched; lossy decode as {fallback}")
    return DecodedText(raw.decode(fallback, errors="replace"), fallback, True, notes)


HARD_BOT_WALL_RE = re.compile(
    r"(just a moment|checking your browser|attention required|"
    r"verify you are human|you have been blocked|unusual traffic|"
    r"ddos protection|_cf_chl_opt|cf-browser-verification)",
    re.I,
)

def detect_bot_wall(status: int | None, headers: dict[str, str], text: str) -> bool:
    """Detect explicit block statuses, Cloudflare challenges, and interstitial copy.

    HTTP 429 is deliberately NOT a bot wall: it is a *retryable* rate limit
    (in ``TRANSIENT_STATUSES``). Normal ``HTTP 200`` pages served behind the
    Cloudflare CDN (``Server: cloudflare``, ``Cf-Mitigated: None``, real HTML
    content) are NOT bot walls unless an actual interstitial challenge appears.
    """
    if status in BLOCK_STATUSES:
        return True
    hdrs = headers if isinstance(headers, dict) else {}
    server = " ".join(
        str(hdrs.get(k) or hdrs.get(k.lower()) or "")
        for k in ("Server", "X-Powered-By", "Cf-Mitigated")
    ).lower()
    if "challenge" in server:
        return True
    body = text if isinstance(text, str) else ""
    if "cloudflare" in server and not body.strip():
        return True
    if not body:
        return False

    head = body[:6000]
    if HARD_BOT_WALL_RE.search(head):
        return True

    # Strip <script>, <link>, and <noscript> boilerplate before checking soft
    # markers ("cloudflare", "captcha", "enable javascript") so CDN beacons,
    # reCAPTCHA widgets, and SPA <noscript> tags on large HTTP 200 pages never
    # false-trigger a bot-wall rejection.
    cleaned_head = re.sub(r"<(script|noscript|style)[^>]*>.*?</\1>", " ", head, flags=re.I | re.S)
    cleaned_head = re.sub(r"<link[^>]*>", " ", cleaned_head, flags=re.I)
    if BOT_WALL_RE.search(cleaned_head):
        if (status is not None and status >= 400) or len(body.strip()) < 2500:
            return True
    return False


def _maybe_decompress(raw: bytes, headers: dict[str, str]) -> tuple[bytes, str]:
    """Handle gzip/deflate transport encoding (urllib does not do this itself)."""
    encoding = str(headers.get("Content-Encoding", "")).lower().strip()
    if encoding == "gzip":
        try:
            return gzip.decompress(raw), "gzip"
        except (OSError, EOFError, zlib.error):
            return raw, "gzip-failed"
    if encoding == "deflate":
        try:
            return zlib.decompress(raw), "deflate"
        except zlib.error:
            try:
                return zlib.decompress(raw, -zlib.MAX_WBITS), "deflate-raw"
            except zlib.error:
                return raw, "deflate-failed"
    return raw, ""


def _headers_of(resp: Any) -> dict[str, str]:
    hdrs = getattr(resp, "headers", None)
    if hdrs is None and hasattr(resp, "info"):
        try:
            hdrs = resp.info()
        except Exception:
            hdrs = None
    if not hdrs:
        return {}
    try:
        return {str(k): str(v) for k, v in hdrs.items()}
    except Exception:
        return {}


def _status_of(resp: Any) -> int | None:
    for attr in ("status", "code", "getcode"):
        value = getattr(resp, attr, None)
        if callable(value):
            try:
                value = value()
            except Exception:
                value = None
        if isinstance(value, int):
            return value
    return None


def _retry_delay(headers: dict[str, str], attempt: int, backoff: float) -> float:
    """Honour Retry-After (seconds), capped; else exponential backoff."""
    raw = headers.get("Retry-After") or headers.get("retry-after")
    if raw:
        try:
            return max(0.0, min(2.0, float(str(raw).strip())))
        except ValueError:
            pass  # HTTP-date form: fall through to exponential backoff
    return min(2.0, backoff * (2 ** (attempt - 1)))


def _reader_fallback(url: str, timeout: float, max_bytes: int) -> FetchResult:
    """Opt-in third-party reader transcription. Only the URL leaves the machine."""
    t0 = time.perf_counter()
    target = "https://r.jina.ai/" + url
    req = urllib.request.Request(target, headers={"User-Agent": DEFAULT_USER_AGENT, "Accept": "text/plain"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read(max_bytes + 1)
            status = _status_of(resp)
            hdrs = _headers_of(resp)
            ctype = str(hdrs.get("Content-Type", "text/plain"))
        truncated = len(raw) > max_bytes
        decoded = decode_bytes(raw[:max_bytes], ctype)
        ok = bool(decoded.text.strip()) and status is not None and status < 400
        return FetchResult(
            ok=ok, url=url, text=decoded.text, status=status, via="reader",
            charset=decoded.charset,
            sha256=hashlib.sha256(decoded.text.encode("utf-8")).hexdigest() if ok else "",
            attempts=1, error="" if ok else "reader returned empty or error body",
            bot_wall=False, elapsed_ms=(time.perf_counter() - t0) * 1000.0,
            truncated=truncated, lossy=decoded.lossy,
            warnings=["third-party reader transcription; verbatim fidelity is not guaranteed"]
            + decoded.notes,
        )
    except Exception as exc:  # fail-loud, but never raise
        return FetchResult(
            ok=False, url=url, text="", status=None, via="reader", charset="",
            sha256="", attempts=1, error=f"reader fallback failed: {type(exc).__name__}: {exc}"[:300],
            bot_wall=False, elapsed_ms=(time.perf_counter() - t0) * 1000.0,
            truncated=False, lossy=False, warnings=[],
        )


def resilient_fetch(
    url: str,
    timeout: float = 12.0,
    max_bytes: int = 2_000_000,
    retries: int = 2,
    backoff: float = 0.35,
    headers: dict[str, str] | None = None,
    allow_reader_fallback: bool = False,
    allow_private: bool = False,
    min_chars: int = 40,
) -> FetchResult:
    """Fetch one URL with bounded retries, charset/gzip handling and provenance.

    Never raises. ``allow_reader_fallback`` additionally requires either the
    explicit flag or ``DR_ALLOW_JINA=1``; the flag alone is enough for callers
    that have already obtained user consent, the env var covers batch runs.
    """
    t0 = time.perf_counter()
    # v12.0 Frontier 4: total over malformed input. Keep a printable label for
    # provenance, but ONLY a genuine str may be used for a network request.
    label = display_url(url)
    url = url_as_text(url)
    timeout = _bounded_number(timeout, 12.0, 0.1, 120.0)
    max_bytes = int(_bounded_number(max_bytes, 2_000_000, 1024, 64_000_000))
    retries = int(_bounded_number(retries, 2, 1, 10))
    backoff = _bounded_number(backoff, 0.35, 0.0, 10.0)
    min_chars = int(_bounded_number(min_chars, 40, 0, 100_000))
    base = FetchResult(
        ok=False, url=label, text="", status=None, via="none", charset="", sha256="",
        attempts=0, error="", bot_wall=False, elapsed_ms=0.0, truncated=False, lossy=False,
    )

    if not is_safe_url(url, allow_private=allow_private):
        base.error = (
            f"unsafe or unsupported URL scheme/host: {label[:120]}"
            if label else "malformed URL input (not a string)"
        )
        base.elapsed_ms = (time.perf_counter() - t0) * 1000.0
        return base

    req_headers = {
        "User-Agent": DEFAULT_USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/json,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en,ru,zh,ja,ko,de,fr,es,bg;q=0.7",
        "Accept-Encoding": "gzip, deflate",
    }
    if isinstance(headers, dict):
        try:
            req_headers.update({str(k): str(v) for k, v in headers.items()})
        except Exception:
            base.warnings.append("malformed headers ignored")
    elif headers:
        base.warnings.append("headers must be a mapping; ignored")

    last_error = ""
    last_status: int | None = None
    last_hdrs: dict[str, str] = {}
    attempts = 0
    bot_wall = False

    for attempt in range(1, max(1, retries) + 1):
        attempts = attempt
        req = urllib.request.Request(url, headers=req_headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read(max_bytes + 1)
                status = _status_of(resp)
                hdrs = _headers_of(resp)
                ctype = str(hdrs.get("Content-Type", ""))
            last_status, last_hdrs = status, hdrs
            truncated = len(raw) > max_bytes
            body, coding = _maybe_decompress(raw[:max_bytes], hdrs)
            decoded = decode_bytes(body, ctype)

            if status in TRANSIENT_STATUSES and attempt < retries:
                time.sleep(_retry_delay(hdrs, attempt, backoff))
                continue
            wall = detect_bot_wall(status, hdrs, decoded.text)
            if wall:
                bot_wall = True
                last_error = f"bot wall detected (HTTP {status})"
                # A reader fallback is the only remaining option; do not spin.
                break
            if status is not None and status >= 400:
                last_error = f"HTTP {status}"
                if status in TRANSIENT_STATUSES and attempt < retries:
                    time.sleep(_retry_delay(hdrs, attempt, backoff))
                    continue
                break
            if len(decoded.text.strip()) < min_chars:
                last_error = f"body too short ({len(decoded.text.strip())} chars)"
                break

            warnings = list(decoded.notes)
            if truncated:
                warnings.append(f"body truncated at {max_bytes} bytes")
            if coding.endswith("-failed"):
                warnings.append(f"Content-Encoding {coding} could not be decompressed")
            if decoded.lossy:
                warnings.append("lossy charset decode: verbatim quotes may be degraded")
            text = decoded.text
            return FetchResult(
                ok=True, url=url, text=text, status=status,
                via=f"direct:{coding}" if coding and not coding.endswith("-failed") else "direct",
                charset=decoded.charset,
                sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
                attempts=attempts, error="", bot_wall=False,
                elapsed_ms=(time.perf_counter() - t0) * 1000.0,
                truncated=truncated, lossy=decoded.lossy, warnings=warnings,
            )

        except urllib.error.HTTPError as exc:
            last_status = exc.code
            try:
                last_hdrs = _headers_of(exc)
                body = exc.read(max_bytes + 1)
            except Exception:
                body = b""
            decoded = decode_bytes(body[:max_bytes], str(last_hdrs.get("Content-Type", "")))
            last_error = f"HTTP {exc.code}"
            if exc.code in BLOCK_STATUSES:
                bot_wall = detect_bot_wall(exc.code, last_hdrs, decoded.text)
                break
            if exc.code in TRANSIENT_STATUSES and attempt < retries:
                time.sleep(_retry_delay(last_hdrs, attempt, backoff))
                continue
            if exc.code == 429:
                bot_wall = True  # retry budget exhausted on a rate limit
            break

        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_error = f"{type(exc).__name__}: {exc}"[:240]
            if attempt < retries:
                time.sleep(_retry_delay({}, attempt, backoff))
                continue
            break

        except Exception as exc:  # pragma: no cover - defensive, still fail-loud
            last_error = f"unexpected {type(exc).__name__}: {exc}"[:240]
            break

    # Reader fallback is strictly opt-in. The caller's flag is explicit consent;
    # DR_ALLOW_JINA=1 is the batch-run equivalent. Both are required to be off
    # by default so no URL ever leaves the machine without permission.
    env_ok = os.environ.get("DR_ALLOW_JINA", "").strip().lower() in ("1", "true", "yes")
    reader_allowed = allow_reader_fallback or env_ok
    if reader_allowed and (bot_wall or last_error):
        reader = _reader_fallback(url, timeout, max_bytes)
        reader.attempts = attempts + reader.attempts
        reader.elapsed_ms = (time.perf_counter() - t0) * 1000.0
        reader.warnings.append(f"direct path failed: {last_error or 'unknown'}")
        if reader.ok:
            return reader
        base.warnings.append(f"reader fallback also failed: {reader.error}")

    base.attempts = attempts
    base.status = last_status
    base.bot_wall = bot_wall
    base.error = last_error or "fetch failed"
    base.elapsed_ms = (time.perf_counter() - t0) * 1000.0
    return base


def fetch_json(url: str, **kwargs: Any) -> tuple[FetchResult, Any | None]:
    """Fetch and parse a JSON API response; parse errors become structured errors."""
    result = resilient_fetch(url, **kwargs)
    if not result.ok:
        return result, None
    try:
        return result, json.loads(result.text)
    except (ValueError, TypeError) as exc:
        result.ok = False
        result.error = f"JSON parse failed: {exc}"[:240]
        result.warnings.append("response was not valid JSON")
        return result, None


def fetch_xml(url: str, **kwargs: Any) -> tuple[FetchResult, ET.Element | None]:
    """Fetch and parse an RSS/Atom/XML feed; parse errors become structured errors.

    v12.0 Frontier 4: an ``<?xml ... encoding="UTF-8"?>`` declaration inside a
    *unicode string* makes ``ET.fromstring`` raise ``ValueError`` (not
    ``ParseError``) on some Python builds. Retry once from UTF-8 bytes so a
    perfectly valid cp1251/UTF-8 feed is not lost, and never let the exception
    escape the collector.
    """
    result = resilient_fetch(url, **kwargs)
    if not result.ok:
        return result, None
    try:
        return result, ET.fromstring(result.text)
    except ValueError:
        try:
            return result, ET.fromstring(str(result.text).encode("utf-8"))
        except (ET.ParseError, ValueError, TypeError) as exc:
            result.ok = False
            result.error = f"XML parse failed (encoded): {exc}"[:240]
            result.warnings.append("response was not well-formed XML")
            return result, None
    except (ET.ParseError, TypeError) as exc:
        result.ok = False
        result.error = f"XML parse failed: {exc}"[:240]
        result.warnings.append("response was not well-formed XML")
        return result, None


# ---------------------------------------------------------------------------
# v11.0 FRONTIER 1 — Deterministic keyless censorship / bot-wall evasion
# ---------------------------------------------------------------------------
# The highest-alpha practitioner leaks (deleted Reddit threads, paywalled forum
# postmortems, rate-limited X threads) sit behind Cloudflare. v10.0 simply
# recorded the 403. v11.0 recovers them through public, keyless endpoints in a
# fixed order. No API keys, no browser automation, no paid proxy.
#
# EPISTEMIC CONSTRAINT: every recovered body is a SECONDARY TRANSCRIPTION.
# Wayback copies contain the archive toolbar; syndication APIs reformat the
# thread; search results are snippets. None may be cited as a primary T1
# snapshot, and search snippets are LEADS ONLY (workspace hard constraint).
# `evidence_class` enforces this downstream.

EVIDENCE_CLASS_BY_PATH = {
    "direct": "primary_fetched",
    "memento": "archival_copy",
    "wayback_cdx": "archival_copy",
    "syndication": "syndicated_transcription",
    "search_cache": "search_snippet",
    "reader": "third_party_transcription",
}

WAYBACK_AVAILABILITY = "https://archive.org/wayback/available"
WAYBACK_CDX = "https://web.archive.org/cdx/search/cdx"
WAYBACK_RAW = "https://web.archive.org/web/{ts}id_/{url}"
DDG_LITE = "https://lite.duckduckgo.com/lite/"
SEARXNG_PUBLIC_INSTANCES = (
    "https://searx.be", "https://searx.tiekoetter.com", "https://priv.au",
)
REDLIB_PUBLIC_INSTANCES = (
    "https://redlib.catsarch.com", "https://safereddit.com",
)
PULLPUSH_COMMENTS = "https://api.pullpush.io/reddit/search/comment/"
FXTWITTER_API = "https://api.fxtwitter.com"

# Fixed order: cheapest / highest-fidelity first.
FALLBACK_PATH_ORDER = ("memento", "wayback_cdx", "syndication", "search_cache")


def _raw_get(
    url: str, timeout: float, max_bytes: int,
    min_chars: int = 2, headers: dict[str, str] | None = None,
) -> FetchResult:
    """Single-attempt read used by fallback paths (never recurses)."""
    return resilient_fetch(
        url, timeout=timeout, max_bytes=max_bytes, retries=1,
        min_chars=min_chars, headers=headers,
        allow_reader_fallback=False,
    )


def _result_from_path(
    path: str, original_url: str, text: str, retrieved_url: str,
    status: int | None, warnings: list[str],
) -> FetchResult:
    """Wrap recovered text with honest provenance and authority downgrade."""
    warnings = list(warnings) + [
        f"SECONDARY SOURCE via {path}: not a primary T1 snapshot; "
        "verbatim fidelity is not guaranteed",
    ]
    return FetchResult(
        ok=True, url=original_url, text=text, status=status, via=path,
        charset="utf-8", sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        attempts=1, error="", bot_wall=False, elapsed_ms=0.0,
        truncated=False, lossy=False, warnings=warnings,
        evidence_class=EVIDENCE_CLASS_BY_PATH[path],
        source_url=retrieved_url,
    )


def _parse_json(text: str) -> Any | None:
    try:
        return json.loads(text)
    except (ValueError, TypeError):
        return None


def _fallback_memento(url: str, timeout: float, max_bytes: int) -> tuple[FetchResult | None, dict]:
    """Memento / Wayback availability API -> closest 200 snapshot."""
    api = WAYBACK_AVAILABILITY + "?url=" + urllib.parse.quote(url, safe="")
    probe = _raw_get(api, min(timeout, 6.0), min(max_bytes, 200_000))
    if not probe.ok:
        return None, {"path": "memento", "ok": False, "error": probe.error[:140]}
    data = _parse_json(probe.text)
    closest = ((data or {}).get("archived_snapshots") or {}).get("closest") or {}
    snap_url = str(closest.get("url") or "")
    if not snap_url or not is_safe_url(snap_url):
        return None, {"path": "memento", "ok": False, "error": "no usable snapshot in availability API"}
    snap = _raw_get(snap_url, timeout, max_bytes, min_chars=60)
    if not snap.ok:
        return None, {"path": "memento", "ok": False, "error": f"snapshot fetch: {snap.error[:120]}"}
    return (
        _result_from_path("memento", url, snap.text, snap_url, snap.status,
                          ["Wayback replay may inject an archive toolbar; quote only the recovered body"]),
        {"path": "memento", "ok": True, "via": "memento", "timestamp": str(closest.get("timestamp", ""))},
    )


def _fallback_wayback_cdx(url: str, timeout: float, max_bytes: int) -> tuple[FetchResult | None, dict]:
    """Wayback CDX JSON API -> newest distinct HTTP-200 capture -> raw `id_` copy."""
    params = {
        "url": url, "output": "json", "filter": "statuscode:200",
        "fl": "timestamp,original,statuscode,digest", "collapse": "digest",
        "limit": "25",
    }
    api = WAYBACK_CDX + "?" + urllib.parse.urlencode(params)
    probe = _raw_get(api, min(timeout, 6.0), min(max_bytes, 400_000))
    if not probe.ok:
        return None, {"path": "wayback_cdx", "ok": False, "error": probe.error[:140]}
    rows = _parse_json(probe.text)
    if not isinstance(rows, list) or len(rows) < 2:
        return None, {"path": "wayback_cdx", "ok": False, "error": "no CDX captures"}
    header, captures = rows[0], rows[1:]
    ts_idx = header.index("timestamp") if "timestamp" in header else 0
    orig_idx = header.index("original") if "original" in header else 1
    candidates = []
    for row in captures:
        if isinstance(row, list) and len(row) > max(ts_idx, orig_idx):
            candidates.append((str(row[ts_idx]), str(row[orig_idx])))
    if not candidates:
        return None, {"path": "wayback_cdx", "ok": False, "error": "malformed CDX rows"}
    ts, original = max(candidates, key=lambda r: r[0])
    raw_url = WAYBACK_RAW.format(ts=ts, url=original)
    snap = _raw_get(raw_url, timeout, max_bytes, min_chars=60)
    if not snap.ok:
        return None, {"path": "wayback_cdx", "ok": False, "error": f"raw capture fetch: {snap.error[:120]}"}
    return (
        _result_from_path("wayback_cdx", url, snap.text, raw_url, snap.status,
                          [f"CDX capture {ts}; raw id_ copy (no replay toolbar but archive-hosted)"]),
        {"path": "wayback_cdx", "ok": True, "via": "wayback_cdx", "timestamp": ts},
    )


_X_STATUS_RE = re.compile(r"(?:x\.com|twitter\.com)/([^/]+)/status/(\d+)", re.I)
_REDDIT_THREAD_RE = re.compile(r"reddit\.com/r/([A-Za-z0-9_]+)/comments/([a-z0-9]+)", re.I)


def _fallback_syndication(url: str, timeout: float, max_bytes: int) -> tuple[FetchResult | None, dict]:
    """FxTwitter (X) / PullPush + Redlib (Reddit) keyless syndication."""
    x_match = _X_STATUS_RE.search(url)
    if x_match:
        user, status_id = x_match.group(1), x_match.group(2)
        api = f"{FXTWITTER_API}/{user}/status/{status_id}"
        res = _raw_get(api, min(timeout, 6.0), min(max_bytes, 300_000))
        data = _parse_json(res.text) if res.ok else None
        tweet = (data or {}).get("tweet") or {}
        body = str(tweet.get("text") or "")
        if len(body) >= 20:
            author = str((tweet.get("author") or {}).get("screen_name") or user)
            text = (
                f"=== SYNDICATED X/TWITTER TRANSCRIPTION (FxTwitter, keyless) ===\n"
                f"Author: {author} | Original URL: {url}\n"
                f"Created: {tweet.get('created_at', 'unknown')}\n\n{body}\n"
            )
            return (
                _result_from_path("syndication", url, text, api, res.status,
                                  ["FxTwitter reformats media/replies; quote the text field only"]),
                {"path": "syndication", "ok": True, "via": "fxtwitter"},
            )

    r_match = _REDDIT_THREAD_RE.search(url)
    if r_match:
        sub, thread_id = r_match.group(1), r_match.group(2)
        # PullPush archives deleted/removed practitioner comments (keyless).
        api = PULLPUSH_COMMENTS + "?" + urllib.parse.urlencode(
            {"link_id": thread_id, "size": 50}
        )
        res = _raw_get(api, min(timeout, 6.0), min(max_bytes, 500_000))
        data = _parse_json(res.text) if res.ok else None
        comments = (data or {}).get("data") or []
        bodies = [str(c.get("body") or "").strip() for c in comments if isinstance(c, dict)]
        bodies = [b for b in bodies if len(b) >= 30 and b not in ("[deleted]", "[removed]")]
        if bodies:
            lines = [
                "=== SYNDICATED REDDIT COMMENT ARCHIVE (PullPush, keyless) ===",
                f"Subreddit: r/{sub} | Thread: {thread_id} | Original URL: {url}",
                f"Recovered comments: {len(bodies)}", "",
            ]
            lines.extend(f"[COMMENT {i}] {b[:1200]}" for i, b in enumerate(bodies, 1))
            return (
                _result_from_path("syndication", url, "\n".join(lines) + "\n", api, res.status,
                                  ["PullPush is a third-party archive; timestamps/authors may be incomplete"]),
                {"path": "syndication", "ok": True, "via": "pullpush", "comments": len(bodies)},
            )
        # Redlib public front-ends render the thread without Cloudflare.
        for instance in REDLIB_PUBLIC_INSTANCES:
            target = f"{instance}/r/{sub}/comments/{thread_id}"
            res = _raw_get(target, min(timeout, 5.0), max_bytes, min_chars=80)
            if not res.ok:
                continue
            plain = html_lib.unescape(re.sub(r"<[^>]+>", " ", res.text))
            plain = re.sub(r"\s+", " ", plain).strip()
            if len(plain) >= 80:
                text = (
                    f"=== SYNDICATED REDDIT TRANSCRIPTION (Redlib mirror {instance}) ===\n"
                    f"Original URL: {url}\n\n{plain[:max_bytes]}\n"
                )
                return (
                    _result_from_path("syndication", url, text, target, res.status,
                                      ["Redlib HTML flattened to prose; verseatim fidelity is degraded"]),
                    {"path": "syndication", "ok": True, "via": "redlib", "instance": instance},
                )
        return None, {"path": "syndication", "ok": False, "error": "no syndication mirror returned content"}

    return None, {"path": "syndication", "ok": False, "error": "URL is not a supported X/Reddit thread"}


_ANCHOR_RE = re.compile(r"<a[^>]+href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>", re.I | re.S)


def _search_query_for(url: str) -> str:
    """Derive a deterministic cache-search query from a blocked URL."""
    parts = urllib.parse.urlparse(url)
    slug = urllib.parse.unquote(parts.path)
    words = [w for w in re.split(r"[^A-Za-z0-9А-Яа-я]+", slug) if len(w) >= 3][:10]
    return f"site:{parts.hostname or ''} " + " ".join(words)


def _fallback_search_cache(url: str, timeout: float, max_bytes: int) -> tuple[FetchResult | None, dict]:
    """DDG Lite HTML + SearXNG instances -> cached snippets (LEADS, not evidence)."""
    query = _search_query_for(url)
    results: list[tuple[str, str]] = []

    ddg = _raw_get(DDG_LITE + "?" + urllib.parse.urlencode({"q": query}),
                   min(timeout, 5.0), min(max_bytes, 300_000), min_chars=40)
    if ddg.ok:
        for href, label in _ANCHOR_RE.findall(ddg.text)[:12]:
            href = html_lib.unescape(href)
            label = re.sub(r"\s+", " ", html_lib.unescape(re.sub(r"<[^>]+>", "", label))).strip()
            if href.startswith("http") and label:
                results.append((href, label[:300]))
    else:
        for instance in SEARXNG_PUBLIC_INSTANCES:
            api = instance + "/search?" + urllib.parse.urlencode({"q": query, "format": "json"})
            res = _raw_get(api, min(timeout, 5.0), min(max_bytes, 300_000))
            data = _parse_json(res.text) if res.ok else None
            for item in ((data or {}).get("results") or [])[:12]:
                if isinstance(item, dict) and item.get("url"):
                    results.append((str(item["url"]), str(item.get("content") or "")[:300]))
            if results:
                break

    if not results:
        return None, {"path": "search_cache", "ok": False, "error": "no cached snippets found"}
    lines = [
        "=== SEARCH CACHE MIRAGE (SECONDARY LEADS — NOT VERBATIM EVIDENCE) ===",
        f"Query: {query}", f"Original URL: {url}",
        "WARNING: search snippets are leads, never evidence. Fetch a primary page before citing.", "",
    ]
    lines.extend(f"[RESULT {i}] {u}\n  SNIPPET: {s}" for i, (u, s) in enumerate(results, 1))
    return (
        _result_from_path("search_cache", url, "\n".join(lines) + "\n",
                          DDG_LITE, 200,
                          ["search snippets must be re-fetched as primary sources before citation"]),
        {"path": "search_cache", "ok": True, "via": "ddg_lite_or_searxng", "leads": len(results)},
    )


_FALLBACK_IMPL = {
    "memento": _fallback_memento,
    "wayback_cdx": _fallback_wayback_cdx,
    "syndication": _fallback_syndication,
    "search_cache": _fallback_search_cache,
}


def fetch_with_fallbacks(
    url: str,
    timeout: float = 10.0,
    max_bytes: int = 2_000_000,
    allow_fallbacks: bool = True,
    paths: tuple[str, ...] | list[str] | None = None,
    headers: dict[str, str] | None = None,
) -> FetchResult:
    """Recover a blocked URL through a deterministic, keyless fallback chain.

    Calling this function IS the consent to contact public third-party mirrors
    (only the URL is sent). Set ``DR_DISABLE_MIRRORS=1`` to force direct-only.
    Never raises; every attempted path is recorded in ``fallback_chain``.
    """
    t0 = time.perf_counter()
    label = display_url(url)
    safe_url = url_as_text(url)
    direct = resilient_fetch(
        url, timeout=timeout, max_bytes=max_bytes, retries=2, headers=headers
    )
    chain: list[dict[str, Any]] = [{
        "path": "direct", "ok": direct.ok, "via": direct.via,
        "status": direct.status, "error": str(direct.error)[:160],
    }]
    direct.fallback_chain = chain
    direct.source_url = label
    if direct.ok:
        direct.evidence_class = "primary_fetched"
        return direct

    # Never contact third-party mirrors for a malformed / non-HTTP target:
    # that would leak garbage into public services and could never produce
    # valid evidence. Fail closed with a structured, recorded outcome.
    if not is_safe_url(safe_url):
        direct.warnings.append(
            "malformed or unsafe URL; keyless fallback chain skipped "
            "(no third-party service was contacted)"
        )
        chain.append({"path": "skipped", "ok": False, "error": "invalid URL input"})
        return direct

    mirrors_disabled = os.environ.get("DR_DISABLE_MIRRORS", "").strip().lower() in ("1", "true", "yes")
    if not allow_fallbacks or mirrors_disabled:
        direct.warnings.append(
            "keyless mirrors disabled by caller/env; blocked URL left unresolved"
            if mirrors_disabled else "keyless mirrors not enabled for this read"
        )
        return direct

    try:
        ordered_paths = tuple(str(p) for p in paths) if paths else tuple(FALLBACK_PATH_ORDER)
    except (TypeError, ValueError):
        ordered_paths = tuple(FALLBACK_PATH_ORDER)
        direct.warnings.append("malformed fallback `paths`; using the default ordered chain")
    for name in ordered_paths:
        # Resolve dynamically from module globals so the chain is inspectable
        # and substitutable in adversarial tests (a static dict of function
        # references would keep stale bindings after monkeypatching).
        fn = globals().get(f"_fallback_{name}") if name in _FALLBACK_IMPL else None
        if fn is None:
            chain.append({"path": name, "ok": False, "error": "unknown fallback path"})
            continue
        try:
            result, record = fn(url, timeout, max_bytes)
        except Exception as exc:  # fail-loud, never raise
            result, record = None, {
                "path": name, "ok": False,
                "error": f"{type(exc).__name__}: {exc}"[:160],
            }
        chain.append(record)
        if result is not None and result.ok:
            result.fallback_chain = chain
            result.attempts = direct.attempts + len(chain) - 1
            result.elapsed_ms = (time.perf_counter() - t0) * 1000.0
            result.source_url = result.source_url or label
            result.warnings.append(f"direct path failed: {direct.error}")
            return result

    final = FetchResult(
        ok=False, url=label, text="", status=direct.status, via="none", charset="",
        sha256="", attempts=direct.attempts + len(chain) - 1,
        error=f"all {len(chain)} fallback paths failed; direct={direct.error}",
        bot_wall=direct.bot_wall, elapsed_ms=(time.perf_counter() - t0) * 1000.0,
        truncated=False, lossy=False,
        warnings=[f"unresolved: {r['path']}={str(r.get('error', ''))[:80]}" for r in chain[1:]],
        evidence_class="none", fallback_chain=chain, source_url=label,
    )
    return final


def benchmark_fallback_coverage(results: list[FetchResult]) -> dict[str, Any]:
    """Compute deterministic live trench coverage from a batch of fetch results.

    ``coverage = recovered / attempted``. A recovery via a secondary path counts
    as coverage but is reported separately as ``secondary_recoveries`` so the
    number can never be mistaken for primary-source coverage.
    """
    attempted = len(results)
    ok = [r for r in results if r.ok]
    primary = [r for r in ok if r.is_primary]
    secondary = [r for r in ok if not r.is_primary]
    by_path: dict[str, int] = {}
    for r in ok:
        key = r.via or "direct"
        by_path[key] = by_path.get(key, 0) + 1
    chains = sum(len(r.fallback_chain) for r in results)
    return {
        "attempted": attempted,
        "recovered": len(ok),
        "coverage_pct": round(100.0 * len(ok) / attempted, 1) if attempted else 0.0,
        "primary_recoveries": len(primary),
        "secondary_recoveries": len(secondary),
        "secondary_pct": round(100.0 * len(secondary) / attempted, 1) if attempted else 0.0,
        "meets_95pct_target": bool(attempted) and (len(ok) / attempted) >= 0.95,
        "by_path": by_path,
        "total_path_attempts": chains,
        "evidence_classes": sorted({r.evidence_class for r in ok}),
    }


def _selftest() -> int:
    # Charset: UTF-8 BOM, Cyrillic cp1251, Japanese Shift_JIS, Chinese GB18030.
    bom = decode_bytes(b"\xef\xbb\xbf" + "AI model".encode("utf-8"), "text/plain")
    assert bom.text == "AI model" and not bom.lossy
    ru = "Сбой в проде".encode("cp1251")
    assert "Сбой" in decode_bytes(ru, "text/html; charset=windows-1251").text
    ja = "本番環境".encode("shift_jis")
    assert "本番" in decode_bytes(ja, "text/html; charset=Shift_JIS").text
    zh = "生产环境".encode("gb18030")
    assert "生产" in decode_bytes(zh, "text/html; charset=gb2312").text
    # Mislabelled single-byte header on a genuine UTF-8 body is corrected.
    mislabelled = "Сбой в проде".encode("utf-8")
    assert decode_bytes(mislabelled, "text/html; charset=windows-1251").charset == "utf-8"
    # gzip transport encoding.
    gz = gzip.compress(b"<html><body>" + b"x" * 200 + b"</body></html>")
    body, coding = _maybe_decompress(gz, {"Content-Encoding": "gzip"})
    assert coding == "gzip" and b"xxx" in body

    assert is_safe_url("https://example.com/a") and is_safe_url("http://127.0.0.1:9/", allow_private=True)
    assert not is_safe_url("file:///C:/secret.txt")
    assert not is_safe_url("javascript:alert(1)")
    assert not is_safe_url("https://user:pass@example.com/")
    assert detect_bot_wall(403, {}, "")
    assert detect_bot_wall(200, {"Server": "cloudflare"}, "")
    assert detect_bot_wall(200, {}, "Just a moment...")
    assert not detect_bot_wall(200, {}, "Ordinary engineering postmortem.")
    assert _retry_delay({"Retry-After": "9"}, 1, 0.35) == 2.0

    # A totally blocked URL must produce a structured failure, never an exception.
    bad = resilient_fetch("file:///etc/passwd", retries=1)
    assert not bad.ok and "unsafe" in bad.error and bad.attempts == 0

    # v11.0 Frontier 1: deterministic keyless fallback bookkeeping.
    assert EVIDENCE_CLASS_BY_PATH["wayback_cdx"] == "archival_copy"
    assert EVIDENCE_CLASS_BY_PATH["search_cache"] == "search_snippet"
    assert FALLBACK_PATH_ORDER == ("memento", "wayback_cdx", "syndication", "search_cache")
    q = _search_query_for("https://www.reddit.com/r/algotrading/comments/abc123/0dte_slippage")
    assert "site:www.reddit.com" in q and "slippage" in q
    assert _X_STATUS_RE.search("https://x.com/quant_dev/status/1234567890")
    assert _REDDIT_THREAD_RE.search("https://reddit.com/r/algotrading/comments/abc123/x")

    def _mk(ok, via, cls):
        return FetchResult(ok=ok, url="https://x.test", text="body" if ok else "",
                           status=200 if ok else 403, via=via, charset="utf-8",
                           sha256="", attempts=1, error="", bot_wall=not ok,
                           elapsed_ms=0.0, truncated=False, lossy=False,
                           evidence_class=cls, fallback_chain=[{"path": via}])
    cov = benchmark_fallback_coverage(
        [_mk(True, "direct", "primary_fetched")] * 17
        + [_mk(True, "wayback_cdx", "archival_copy")] * 2
        + [_mk(True, "syndication", "syndicated_transcription")]
    )
    assert cov["coverage_pct"] == 100.0 and cov["meets_95pct_target"]
    assert cov["primary_recoveries"] == 17 and cov["secondary_recoveries"] == 3
    cov_low = benchmark_fallback_coverage([_mk(False, "none", "none")] * 10)
    assert not cov_low["meets_95pct_target"]

    # Disabled mirrors must not contact third parties for an unsafe URL.
    no_mirror = fetch_with_fallbacks("file:///etc/passwd", allow_fallbacks=False)
    assert not no_mirror.ok and no_mirror.fallback_chain[0]["path"] == "direct"

    # v12.0 Frontier 4: the whole transport is total over malformed inputs.
    for malformed in (None, 12345, b"https://example.com/x", "", "https://",
                      "javascript:alert(1)", object()):
        assert not is_safe_url(malformed), repr(malformed)
        r = resilient_fetch(malformed, retries=1, timeout=None, max_bytes=-1)
        assert not r.ok and isinstance(r.url, str) and isinstance(r.error, str)
        rj, data = fetch_json(malformed, retries=1)
        assert not rj.ok and data is None
        rx, root = fetch_xml(malformed, retries=1)
        assert not rx.ok and root is None
        rf = fetch_with_fallbacks(malformed, allow_fallbacks=True)
        assert not rf.ok and isinstance(rf.url, str)
    assert display_url(None) == "" and display_url(12345) == "12345"
    assert url_as_text("https://a.test") == "https://a.test"
    assert url_as_text(b"https://a.test") == ""
    assert _bounded_number(float("nan"), 12.0, 0.1, 120.0) == 12.0
    assert _bounded_number(None, 12.0, 0.1, 120.0) == 12.0
    assert _bounded_number(99999, 12.0, 0.1, 120.0) == 120.0
    # A unicode XML string carrying an encoding declaration must still parse.
    declared = '<?xml version="1.0" encoding="UTF-8"?><rss><item><title>Новый рекорд</title></item></rss>'
    try:
        ET.fromstring(declared.encode("utf-8"))
    except ET.ParseError:
        raise AssertionError("valid UTF-8 feed fixture is malformed")
    assert ET.fromstring(declared.encode("utf-8")).findtext("item/title") == "Новый рекорд"

    print("[SELFTEST PASS] http_resilience v12.0 (charset/gzip/bot-wall/retry/mirrors/"
          "coverage/malformed-input total) verified.")
    return 0


if __name__ == "__main__":
    import sys

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(_selftest())
