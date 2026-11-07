#!/usr/bin/env python3
"""Deep Research Engine v13.0 — Multi-Hop Deep Digger, Subpage/T&C/FAQ Spider & Table Extractor.

Eliminates shallow 1-page research ("Premature Surface Skimming") across ANY domain:
  1. Multi-Angle Open-Web Discovery (`discover_web_leads`): synthesizes official,
     T&C/FAQ/pricing/rules, fine-print restriction, and adversarial postmortem
     search vectors via DDGS with keyless DuckDuckGo HTML fallback.
  2. Table- & Schema-Preserving HTML Extractor (`html_to_structured_snapshot`):
     renders HTML `<table>` grids as pipe-delimited `Col1 | Col2 | Col3` quotable
     rows and recovers collapsed `<details>` + JSON-LD `FAQPage`/`Product`/`Article`
     payloads so modern SPA/accordion FAQs and fee matrices stay verbatim-quotable.
  3. Automatic PDF Clause & Table Extraction (`fetch_document_snapshot`): detects
     linked `.pdf` Terms & Conditions, regulatory filings, and clinical papers by
     `%PDF-` magic bytes and extracts page-indexed text + tables via `parse_pdf`.
  4. Multi-Hop Subpage / Help-Center / Legal Spider (`deep_dig_urls`): follows
     high-signal links (`/terms`, `/faq`, `/rules`, `help.*`, Intercom/Zendesk
     helpdesks, linked `.pdf` schedules) up to `max_depth=2` hops concurrently,
     deduplicating by normalized SHA-256.

Pure Python 3.10+ stdlib core (optional `ddgs` & `parse_pdf` acceleration).
Windows cp1252-safe.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import hashlib
import html as html_lib
import html.parser
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

_workspace_root = Path(__file__).resolve().parent.parent.parent
if str(_workspace_root) not in sys.path:
    sys.path.insert(0, str(_workspace_root))

from dr_engine.tools.http_resilience import (  # noqa: E402
    DEFAULT_USER_AGENT,
    display_url,
    fetch_with_fallbacks,
    is_safe_url,
    resilient_fetch,
    url_as_text,
)

try:
    from ddgs import DDGS  # type: ignore
    HAS_DDGS = True
except ImportError:
    HAS_DDGS = False

__all__ = [
    "SublinkCandidate",
    "DugDocument",
    "registrable_domain",
    "html_to_structured_snapshot",
    "extract_high_value_sublinks",
    "fetch_document_snapshot",
    "build_deep_search_queries",
    "discover_web_leads",
    "deep_dig_urls",
    "dig_into_study",
]

# Linked helpdesk / CDN document hosts allowed when directly linked from an official seed URL.
LINKED_DOC_HOSTS = (
    "intercom.help",
    "zendesk.com",
    "freshdesk.com",
    "gitbook.io",
    "readme.io",
    "helpscoutdocs.com",
    "document360.io",
    "ctfassets.net",
    "cloudfront.net",
    "amazonaws.com",
    "blob.core.windows.net",
)

# High-value subpage path & anchor tokens across finance, prop firms, SaaS, law, biotech, hardware.
HIGH_VALUE_CLAUSE_TOKENS = (
    "terms", "condition", "conditions", "gtc", "tos", "legal", "agreement",
    "contract", "disclaimer", "disclosure", "rules", "rule", "faq", "faqs",
    "help", "support", "knowledge", "guide", "docs", "documentation",
    "pricing", "price", "fee", "fees", "commission", "spread", "swap",
    "drawdown", "loss", "trailing", "static", "balance", "equity",
    "copy", "copier", "ea", "expert-advisor", "bot", "bots", "automated",
    "algorithmic", "api", "rate-limit", "quota", "sla", "security",
    "prohibited", "forbidden", "restricted", "country", "countries",
    "payout", "withdrawal", "scaling", "protrader", "challenge", "evaluation",
    "high-stakes", "step", "methodology", "benchmark", "specification",
    "datasheet", "protocol", "trial", "eligibility", "adverse", "statute",
    "regulation", "article", "schedule", "appendix", "annex", "tariff",
)

JUNK_PATH_RE = re.compile(
    r"(?:/(?:wp-json|wp-admin|wp-login|xmlrpc|cart|checkout|my-account|"
    r"signin|sign-in|signup|sign-up|login|log-in|register|password-reset|"
    r"affiliate-area|cookie-policy|tag|author|share|intent/tweet)/?"
    r"|\.(?:png|jpe?g|gif|webp|svg|ico|css|js|mjs|woff2?|ttf|eot|mp4|webm|mp3|zip|rar|exe|dmg)(?:\?|$))",
    re.I,
)

NON_EN_LOCALE_SEGMENT_RE = re.compile(
    r"/(?:ja|jp|cs|cz|sk|pl|hu|ro|vi|th|id|ms|tr|ar|he|hi|ko|zh|zh-cn|zh-tw|"
    r"pt|pt-br|it|nl|sv|no|da|fi|el)(?:/|$)",
    re.I,
)

TRACKING_PARAMS = frozenset({
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "fbclid", "gclid", "msclkid", "mc_cid", "mc_eid", "_ga", "_gl", "ref",
})

SECOND_LEVEL_TLDS = frozenset({
    "co.uk", "org.uk", "gov.uk", "ac.uk", "com.au", "co.jp", "co.kr",
    "com.br", "com.sg", "co.nz", "co.za", "com.hk", "or.jp", "ne.jp",
})


def registrable_domain(url_or_host: str) -> str:
    """Return registrable root domain (e.g. 'help.fintokei.com' -> 'fintokei.com')."""
    s = url_as_text(url_or_host).strip().lower()
    if "://" in s:
        try:
            host = (urllib.parse.urlparse(s).hostname or "").lower()
        except ValueError:
            return ""
    else:
        host = s.split("/")[0].split(":")[0]
    host = host.strip(".").removeprefix("www.")
    if not host:
        return ""
    parts = host.split(".")
    if len(parts) <= 2:
        return host
    tail2 = ".".join(parts[-2:])
    if tail2 in SECOND_LEVEL_TLDS and len(parts) >= 3:
        return ".".join(parts[-3:])
    return tail2


def canonicalize_crawl_url(url: str) -> str:
    """Normalize URL for deduplication (strip fragments and tracking params)."""
    u = url_as_text(url).strip()
    if not u:
        return ""
    try:
        p = urllib.parse.urlsplit(u)
    except ValueError:
        return ""
    if p.scheme.lower() not in ("http", "https") or not p.netloc:
        return ""
    q_pairs = [
        (k, v)
        for k, v in urllib.parse.parse_qsl(p.query, keep_blank_values=False)
        if k.lower() not in TRACKING_PARAMS
    ]
    clean_query = urllib.parse.urlencode(q_pairs)
    path = re.sub(r"/{2,}", "/", p.path or "/")
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")
    return urllib.parse.urlunsplit((p.scheme.lower(), p.netloc.lower(), path, clean_query, ""))


class _StructuredHTMLParser(html.parser.HTMLParser):
    """Stdlib DOM walker preserving `<table>` columns as ` | `, headings, lists & links."""

    _SKIP_TAGS = frozenset({"script", "style", "noscript", "svg", "canvas", "iframe", "template"})
    _BLOCK_TAGS = frozenset({
        "p", "div", "section", "article", "main", "aside", "blockquote",
        "pre", "details", "summary", "dl", "dt", "dd", "figcaption", "hr",
    })
    _HEADING_TAGS = frozenset({"h1", "h2", "h3", "h4", "h5", "h6"})

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip_depth = 0
        self._in_JsonLd = False
        self._in_NextData = False
        self._script_buf: list[str] = []
        self.json_ld_blobs: list[str] = []
        self.next_data_blobs: list[str] = []

        self._in_table = 0
        self._current_row: list[str] = []
        self._current_cell: list[str] = []
        self._in_cell = False

        self._in_anchor = False
        self._anchor_href = ""
        self._anchor_buf: list[str] = []
        self.links: list[tuple[str, str]] = []

        self._lines: list[str] = []
        self._buf: list[str] = []

    def _flush_buf(self) -> None:
        if not self._buf:
            return
        line = re.sub(r"[ \t\r\f\v]+", " ", "".join(self._buf)).strip()
        self._buf.clear()
        if line:
            self._lines.append(line)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        t = tag.lower()
        attr_map = {k.lower(): (v or "") for k, v in attrs if k}

        if t == "script":
            stype = attr_map.get("type", "").lower()
            sid = attr_map.get("id", "")
            if "ld+json" in stype:
                self._in_JsonLd = True
                self._script_buf.clear()
            elif sid == "__NEXT_DATA__":
                self._in_NextData = True
                self._script_buf.clear()
            self._skip_depth += 1
            return

        if t in self._SKIP_TAGS:
            self._skip_depth += 1
            return

        if self._skip_depth > 0:
            return

        if t == "a":
            href = attr_map.get("href", "").strip()
            if href:
                self._in_anchor = True
                self._anchor_href = href
                self._anchor_buf.clear()
        elif t in ("object", "embed"):
            doc_src = (attr_map.get("data") or attr_map.get("src") or "").strip()
            if doc_src and ".pdf" in doc_src.lower():
                self.links.append((doc_src, attr_map.get("aria-label") or "embedded-pdf"))

        if t == "table":
            self._flush_buf()
            self._in_table += 1
            return
        if self._in_table > 0:
            if t == "tr":
                self._current_row = []
                return
            if t in ("td", "th"):
                self._in_cell = True
                self._current_cell = []
                return
            if t == "br" and self._in_cell:
                self._current_cell.append(" / ")
                return

        if t == "br":
            self._flush_buf()
        elif t in self._HEADING_TAGS:
            self._flush_buf()
            lvl = int(t[1])
            self._buf.append("#" * min(lvl, 4) + " ")
        elif t == "li":
            self._flush_buf()
            self._buf.append("- ")
        elif t in self._BLOCK_TAGS:
            self._flush_buf()

    def handle_endtag(self, tag: str) -> None:
        t = tag.lower()
        if t == "script":
            if self._in_JsonLd:
                blob = "".join(self._script_buf).strip()
                if blob:
                    self.json_ld_blobs.append(blob)
                self._in_JsonLd = False
                self._script_buf.clear()
            elif self._in_NextData:
                blob = "".join(self._script_buf).strip()
                if blob:
                    self.next_data_blobs.append(blob)
                self._in_NextData = False
                self._script_buf.clear()
            if self._skip_depth > 0:
                self._skip_depth -= 1
            return

        if t in self._SKIP_TAGS:
            if self._skip_depth > 0:
                self._skip_depth -= 1
            return

        if self._skip_depth > 0:
            return

        if t == "a" and self._in_anchor:
            anchor_txt = re.sub(r"\s+", " ", "".join(self._anchor_buf)).strip()
            self.links.append((self._anchor_href, anchor_txt))
            self._in_anchor = False
            self._anchor_href = ""
            self._anchor_buf.clear()

        if self._in_table > 0:
            if t in ("td", "th") and self._in_cell:
                cell_txt = re.sub(r"\s+", " ", "".join(self._current_cell)).strip()
                self._current_row.append(cell_txt)
                self._current_cell = []
                self._in_cell = False
                return
            if t == "tr":
                if any(c for c in self._current_row):
                    self._lines.append(" | ".join(c if c else "-" for c in self._current_row))
                self._current_row = []
                return
            if t == "table":
                self._in_table = max(0, self._in_table - 1)
                return

        if t in self._HEADING_TAGS or t in self._BLOCK_TAGS or t == "li":
            self._flush_buf()

    def handle_data(self, data: str) -> None:
        if self._in_JsonLd or self._in_NextData:
            self._script_buf.append(data)
            return
        if self._skip_depth > 0:
            return
        if self._in_anchor:
            self._anchor_buf.append(data)
        if self._in_table > 0 and self._in_cell:
            self._current_cell.append(data)
        else:
            self._buf.append(data)

    def get_text(self) -> str:
        self._flush_buf()
        # Collapse consecutive identical boilerplate lines
        deduped: list[str] = []
        for ln in self._lines:
            if deduped and deduped[-1] == ln:
                continue
            deduped.append(ln)
        return "\n".join(deduped)


def _strip_inline_html(val: str) -> str:
    txt = html_lib.unescape(str(val or ""))
    txt = re.sub(r"<(br|p|li|div)[^>]*>", " ", txt, flags=re.I)
    txt = re.sub(r"<[^>]+>", " ", txt)
    return re.sub(r"\s+", " ", txt).strip()


def _extract_jsonld_passages(blobs: list[str]) -> list[str]:
    """Extract structured FAQ, Product/Offer pricing, and Article bodies from JSON-LD."""
    out: list[str] = []

    def _walk(node: Any) -> None:
        if isinstance(node, list):
            for item in node:
                _walk(item)
            return
        if not isinstance(node, dict):
            return
        ntype = str(node.get("@type", "")).lower()
        if "question" in ntype:
            q = _strip_inline_html(node.get("name") or node.get("text") or "")
            ans_obj = node.get("acceptedAnswer") or node.get("suggestedAnswer") or {}
            a = _strip_inline_html(ans_obj.get("text", "") if isinstance(ans_obj, dict) else str(ans_obj))
            if q and a:
                out.append(f"FAQ Q: {q}\nFAQ A: {a}")
        elif "product" in ntype or "offer" in ntype:
            name = _strip_inline_html(node.get("name", ""))
            price = node.get("price")
            curr = node.get("priceCurrency", "")
            desc = _strip_inline_html(node.get("description", ""))
            offers = node.get("offers")
            if price is not None and (name or desc):
                out.append(f"Offer: {name} | Price: {curr} {price} | {desc}".strip(" |"))
            if offers:
                _walk(offers)
        elif "article" in ntype or "newsarticle" in ntype:
            headline = _strip_inline_html(node.get("headline", ""))
            pub = str(node.get("datePublished", ""))[:10]
            body = _strip_inline_html(node.get("articleBody", ""))
            if headline and body and len(body) >= 60:
                out.append(f"Article ({pub}): {headline} — {body}")

        for k, v in node.items():
            if k not in ("acceptedAnswer", "suggestedAnswer", "offers") and isinstance(v, (dict, list)):
                _walk(v)

    for raw in blobs:
        try:
            parsed = json.loads(raw)
            _walk(parsed)
        except (ValueError, TypeError):
            continue
    return out


def _extract_next_data_passages(blobs: list[str], max_items: int = 40) -> list[str]:
    """Recover FAQ/article text embedded in Next.js `__NEXT_DATA__` hydration JSON."""
    out: list[str] = []

    def _walk(node: Any) -> None:
        if len(out) >= max_items:
            return
        if isinstance(node, list):
            for x in node:
                _walk(x)
            return
        if not isinstance(node, dict):
            return
        q = node.get("question") or node.get("faqQuestion")
        a = node.get("answer") or node.get("faqAnswer")
        if isinstance(q, str) and isinstance(a, str) and len(q) >= 8 and len(a) >= 15:
            out.append(f"FAQ Q: {_strip_inline_html(q)}\nFAQ A: {_strip_inline_html(a)}")
        title = node.get("title") or node.get("heading")
        body = node.get("body") or node.get("content") or node.get("description")
        if (
            isinstance(title, str)
            and isinstance(body, str)
            and 5 <= len(title) <= 180
            and len(body) >= 80
        ):
            clean_b = _strip_inline_html(body)
            if len(clean_b) >= 60:
                out.append(f"{_strip_inline_html(title)}: {clean_b}")
        for v in node.values():
            if isinstance(v, (dict, list)):
                _walk(v)

    for raw in blobs:
        try:
            _walk(json.loads(raw))
        except (ValueError, TypeError):
            continue
    return out


def html_to_structured_snapshot(raw_html: str) -> str:
    """Convert raw HTML (or plain text) into a table- & FAQ-preserving text snapshot."""
    text_in = raw_html if isinstance(raw_html, str) else str(raw_html or "")
    if not text_in.strip():
        return ""
    # Fast path if input has no HTML tags at all
    if "<" not in text_in or not re.search(r"<[a-zA-Z!/]", text_in):
        return re.sub(r"\n{3,}", "\n\n", text_in).strip()

    parser = _StructuredHTMLParser()
    try:
        parser.feed(text_in)
        parser.close()
    except Exception:
        # Fallback regex strip if pathological markup trips parser
        fallback = re.sub(r"<(script|style|noscript)[^>]*>.*?</\1>", " ", text_in, flags=re.I | re.S)
        fallback = re.sub(r"<(td|th)[^>]*>", " | ", fallback, flags=re.I)
        fallback = re.sub(r"<(br|p|div|li|tr|h[1-6])[^>]*>", "\n", fallback, flags=re.I)
        fallback = re.sub(r"<[^>]+>", " ", fallback)
        return re.sub(r"\n{3,}", "\n\n", html_lib.unescape(fallback)).strip()

    dom_text = parser.get_text()
    extras: list[str] = []
    ld_items = _extract_jsonld_passages(parser.json_ld_blobs)
    if ld_items:
        for item in ld_items:
            # Append only if not already verbatim in dom_text
            probe = item.split("\n")[-1][:80]
            if probe and probe not in dom_text:
                extras.append(item)

    if len(dom_text) < 1200 and parser.next_data_blobs:
        for item in _extract_next_data_passages(parser.next_data_blobs):
            if item[:80] not in dom_text:
                extras.append(item)

    if extras:
        schema_block = "\n\n=== [STRUCTURED SCHEMA / FAQ DATA] ===\n" + "\n\n".join(extras)
        dom_text = (dom_text + schema_block).strip()
    return re.sub(r"\n{3,}", "\n\n", dom_text).strip()


@dataclass
class SublinkCandidate:
    url: str
    anchor: str
    score: float
    parent_url: str
    reason: str


def _is_allowed_sublink_host(candidate_url: str, seed_root: str) -> bool:
    cand_root = registrable_domain(candidate_url)
    if not cand_root:
        return False
    if seed_root and cand_root == seed_root:
        return True
    try:
        host = (urllib.parse.urlparse(candidate_url).hostname or "").lower()
    except ValueError:
        return False
    if any(host == h or host.endswith("." + h) for h in LINKED_DOC_HOSTS):
        return True
    if candidate_url.lower().split("?")[0].endswith(".pdf"):
        return True
    return False


def extract_high_value_sublinks(
    html_text: str,
    base_url: str,
    focus_query: str = "",
    max_links: int = 12,
    allow_private: bool = False,
) -> list[SublinkCandidate]:
    """Extract and rank internal T&C, FAQ, Help-Center, Pricing, Rules & PDF links."""
    raw = html_text if isinstance(html_text, str) else ""
    base = url_as_text(base_url).strip()
    if not raw or not base:
        return []

    parser = _StructuredHTMLParser()
    try:
        parser.feed(raw)
        parser.close()
    except Exception:
        return []

    seed_root = registrable_domain(base)
    base_canon = canonicalize_crawl_url(base)
    focus_tokens = {
        w.lower()
        for w in re.findall(r"[a-zA-Z0-9\u0400-\u04FF]{3,}", str(focus_query or ""))
        if len(w) >= 3
    }
    keep_non_en = bool(NON_EN_LOCALE_SEGMENT_RE.search(base))

    scored_by_url: dict[str, SublinkCandidate] = {}
    for raw_href, anchor in parser.links:
        if not raw_href or raw_href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        resolved = urllib.parse.urljoin(base, raw_href)
        canon = canonicalize_crawl_url(resolved)
        if not canon or canon == base_canon:
            continue
        if not is_safe_url(canon, allow_private=allow_private):
            continue
        if JUNK_PATH_RE.search(canon):
            continue
        is_pdf = urllib.parse.urlparse(canon).path.lower().endswith(".pdf")
        if not is_pdf and not _is_allowed_sublink_host(canon, seed_root):
            continue
        if not keep_non_en and NON_EN_LOCALE_SEGMENT_RE.search(urllib.parse.urlparse(canon).path):
            continue

        path_and_query = (
            urllib.parse.urlparse(canon).hostname or ""
        ) + urllib.parse.urlparse(canon).path.lower() + " " + anchor.lower()

        score = 0.0
        reasons: list[str] = []

        matched_clauses = [tok for tok in HIGH_VALUE_CLAUSE_TOKENS if tok in path_and_query]
        if matched_clauses:
            score += min(45.0, 12.0 * len(matched_clauses))
            reasons.append("clause:" + ",".join(matched_clauses[:3]))

        matched_focus = [ft for ft in focus_tokens if ft in path_and_query]
        if matched_focus:
            score += min(30.0, 8.0 * len(matched_focus))
            reasons.append("focus:" + ",".join(matched_focus[:3]))

        if canon.lower().split("?")[0].endswith(".pdf"):
            score += 22.0
            reasons.append("pdf_document")

        host_low = (urllib.parse.urlparse(canon).hostname or "").lower()
        if host_low.startswith(("help.", "support.", "docs.", "faq.", "legal.")):
            score += 18.0
            reasons.append("help_subdomain")

        if score <= 0.0:
            continue

        cand = SublinkCandidate(
            url=canon,
            anchor=anchor[:140],
            score=round(score, 2),
            parent_url=base,
            reason="; ".join(reasons) or "sublink",
        )
        prev = scored_by_url.get(canon)
        if prev is None or cand.score > prev.score:
            scored_by_url[canon] = cand

    ranked = sorted(scored_by_url.values(), key=lambda c: (-c.score, c.url))
    return ranked[: max(0, int(max_links))]


@dataclass
class DugDocument:
    url: str
    text: str
    raw_html: str
    ok: bool
    via: str
    evidence_class: str
    status: int | None
    sha256: str
    hop_depth: int
    parent_url: str = ""
    anchor: str = ""
    reason: str = ""
    is_pdf: bool = False
    error: str = ""
    warnings: list[str] = field(default_factory=list)


def _fetch_pdf_bytes(url: str, timeout: float = 15.0, max_bytes: int = 8_000_000, allow_private: bool = False) -> tuple[bytes, int | None, str]:
    if not is_safe_url(url, allow_private=allow_private):
        return b"", None, "unsafe URL"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": DEFAULT_USER_AGENT, "Accept": "application/pdf,*/*;q=0.8"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = getattr(resp, "status", 200)
            raw = resp.read(max_bytes + 1)
            if len(raw) > max_bytes:
                return b"", status, f"PDF exceeds {max_bytes} byte cap"
            return raw, status, ""
    except Exception as exc:
        return b"", None, f"{type(exc).__name__}: {exc}"[:240]


def fetch_document_snapshot(
    url: str,
    *,
    timeout: float = 12.0,
    allow_private: bool = False,
    hop_depth: int = 0,
    parent_url: str = "",
    anchor: str = "",
    reason: str = "seed",
) -> DugDocument:
    """Fetch an HTML, JSON, plain-text, or PDF URL into a structured snapshot."""
    label = display_url(url)
    clean_u = url_as_text(url).strip()
    if not is_safe_url(clean_u, allow_private=allow_private):
        return DugDocument(
            url=label, text="", raw_html="", ok=False, via="none",
            evidence_class="failed", status=None, sha256="", hop_depth=hop_depth,
            parent_url=parent_url, anchor=anchor, reason=reason,
            error=f"unsafe or malformed URL: {label[:120]}",
        )

    looks_pdf = clean_u.lower().split("?")[0].endswith(".pdf")
    if looks_pdf:
        raw_bytes, status, err = _fetch_pdf_bytes(clean_u, timeout=timeout, allow_private=allow_private)
        if raw_bytes.startswith(b"%PDF-"):
            try:
                from dr_engine.tools.parse_pdf import pdf_snapshot
                snap_text, meta = pdf_snapshot(raw_bytes, clean=True)
                sha = hashlib.sha256(snap_text.encode("utf-8")).hexdigest()
                return DugDocument(
                    url=clean_u, text=snap_text, raw_html="", ok=True,
                    via=f"direct:pdf({meta.get('parser', 'pdf')})",
                    evidence_class="primary_fetched", status=status, sha256=sha,
                    hop_depth=hop_depth, parent_url=parent_url, anchor=anchor,
                    reason=reason, is_pdf=True,
                )
            except Exception as exc:
                return DugDocument(
                    url=clean_u, text="", raw_html="", ok=False, via="direct:pdf",
                    evidence_class="failed", status=status, sha256="",
                    hop_depth=hop_depth, parent_url=parent_url, anchor=anchor,
                    reason=reason, is_pdf=True, error=f"PDF parse error: {exc}"[:240],
                )
        if err:
            return DugDocument(
                url=clean_u, text="", raw_html="", ok=False, via="none",
                evidence_class="failed", status=status, sha256="",
                hop_depth=hop_depth, parent_url=parent_url, anchor=anchor,
                reason=reason, is_pdf=True, error=err,
            )

    if allow_private:
        res = resilient_fetch(clean_u, timeout=timeout, allow_private=True)
    else:
        res = fetch_with_fallbacks(clean_u, timeout=timeout)
    if not res.ok or not res.text.strip():
        return DugDocument(
            url=clean_u, text="", raw_html="", ok=False, via=res.via,
            evidence_class=res.evidence_class, status=res.status, sha256="",
            hop_depth=hop_depth, parent_url=parent_url, anchor=anchor,
            reason=reason, error=res.error or "empty body", warnings=list(res.warnings),
        )

    # Guard against unannounced PDF returned at a non-.pdf URL
    if res.text.lstrip().startswith("%PDF-"):
        raw_bytes, status, _ = _fetch_pdf_bytes(clean_u, timeout=timeout, allow_private=allow_private)
        if raw_bytes.startswith(b"%PDF-"):
            try:
                from dr_engine.tools.parse_pdf import pdf_snapshot
                snap_text, meta = pdf_snapshot(raw_bytes, clean=True)
                sha = hashlib.sha256(snap_text.encode("utf-8")).hexdigest()
                return DugDocument(
                    url=clean_u, text=snap_text, raw_html="", ok=True,
                    via=f"direct:pdf({meta.get('parser', 'pdf')})",
                    evidence_class="primary_fetched", status=status, sha256=sha,
                    hop_depth=hop_depth, parent_url=parent_url, anchor=anchor,
                    reason=reason, is_pdf=True,
                )
            except Exception as exc:
                return DugDocument(
                    url=clean_u, text="", raw_html="", ok=False, via="direct:pdf",
                    evidence_class="failed", status=status, sha256="",
                    hop_depth=hop_depth, parent_url=parent_url, anchor=anchor,
                    reason=reason, is_pdf=True, error=f"PDF parse error: {exc}"[:240],
                )

    structured = html_to_structured_snapshot(res.text)
    if len(structured) < 40:
        return DugDocument(
            url=clean_u, text="", raw_html=res.text, ok=False, via=res.via,
            evidence_class=res.evidence_class, status=res.status, sha256="",
            hop_depth=hop_depth, parent_url=parent_url, anchor=anchor,
            reason=reason, error=f"extracted body too short ({len(structured)} chars)",
            warnings=list(res.warnings),
        )
    sha = hashlib.sha256(structured.encode("utf-8")).hexdigest()
    return DugDocument(
        url=clean_u, text=structured, raw_html=res.text, ok=True, via=res.via,
        evidence_class=res.evidence_class, status=res.status, sha256=sha,
        hop_depth=hop_depth, parent_url=parent_url, anchor=anchor,
        reason=reason, warnings=list(res.warnings),
    )


def deep_dig_urls(
    seed_urls: list[str],
    focus_query: str = "",
    *,
    max_depth: int = 2,
    max_subpages: int = 12,
    max_workers: int = 6,
    timeout: float = 12.0,
    allow_private: bool = False,
) -> list[DugDocument]:
    """Crawl seed URLs and recursively expand high-value T&C/FAQ/Rules/PDF subpages."""
    clean_seeds: list[str] = []
    seen_urls: set[str] = set()
    for u in seed_urls or []:
        c = canonicalize_crawl_url(u)
        if c and c not in seen_urls and is_safe_url(c, allow_private=allow_private):
            seen_urls.add(c)
            clean_seeds.append(c)

    if not clean_seeds:
        return []

    collected: list[DugDocument] = []
    seen_hashes: set[str] = set()

    # Hop 0: fetch all seed URLs concurrently
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, min(max_workers, len(clean_seeds)))) as pool:
        futs = [
            pool.submit(
                fetch_document_snapshot, u, timeout=timeout,
                allow_private=allow_private, hop_depth=0, reason="seed",
            )
            for u in clean_seeds
        ]
        hop0_docs = [f.result() for f in futs]

    frontier_docs: list[DugDocument] = []
    for doc in hop0_docs:
        collected.append(doc)
        if doc.ok and doc.sha256:
            seen_hashes.add(doc.sha256)
            frontier_docs.append(doc)

    remaining_budget = max(0, int(max_subpages))
    current_depth = 1
    while current_depth <= max_depth and remaining_budget > 0 and frontier_docs:
        candidates_map: dict[str, SublinkCandidate] = {}
        for parent_doc in frontier_docs:
            if not parent_doc.raw_html:
                continue
            sublinks = extract_high_value_sublinks(
                parent_doc.raw_html,
                parent_doc.url,
                focus_query=focus_query,
                max_links=max(8, remaining_budget),
                allow_private=allow_private,
            )
            for cand in sublinks:
                if cand.url in seen_urls:
                    continue
                prev = candidates_map.get(cand.url)
                if prev is None or cand.score > prev.score:
                    candidates_map[cand.url] = cand

        if not candidates_map:
            break

        batch = sorted(candidates_map.values(), key=lambda c: (-c.score, c.url))[:remaining_budget]
        for cand in batch:
            seen_urls.add(cand.url)

        with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, min(max_workers, len(batch)))) as pool:
            sub_futs = [
                pool.submit(
                    fetch_document_snapshot,
                    cand.url,
                    timeout=timeout,
                    allow_private=allow_private,
                    hop_depth=current_depth,
                    parent_url=cand.parent_url,
                    anchor=cand.anchor,
                    reason=cand.reason,
                )
                for cand in batch
            ]
            sub_docs = [f.result() for f in sub_futs]

        next_frontier: list[DugDocument] = []
        for sdoc in sub_docs:
            if sdoc.ok:
                if sdoc.sha256 in seen_hashes:
                    continue
                seen_hashes.add(sdoc.sha256)
                collected.append(sdoc)
                next_frontier.append(sdoc)
                remaining_budget -= 1
                if remaining_budget <= 0:
                    break
            else:
                collected.append(sdoc)
        frontier_docs = next_frontier
        current_depth += 1

    return collected


def build_deep_search_queries(prompt: str, entities: list[str] | None = None, domain: str = "general") -> dict[str, str]:
    """Build 4 orthogonal search vectors so web discovery digs past SEO fluff."""
    clean_p = re.sub(r"\s+", " ", str(prompt or "")).strip()
    ents = [str(e).strip() for e in (entities or []) if str(e).strip()]
    focus = " ".join(ents[:4]) if ents else " ".join(clean_p.split()[:10])

    if domain in ("quant", "finance", "trading", "microstructure"):
        return {
            "official_primary": f"{focus} official rules specifications contract fees",
            "terms_and_rules": f"{focus} (\"terms and conditions\" OR FAQ OR \"help center\" OR drawdown OR spread)",
            "fine_print_limits": f"{focus} (trailing OR static OR \"daily loss\" OR \"copy trading\" OR EA OR bot OR prohibited)",
            "adversarial_postmortem": f"{focus} (rejected OR denied OR slippage OR postmortem OR hidden rule)",
        }
    if domain in ("law", "legal", "tax", "regulatory", "compliance"):
        return {
            "official_primary": f"{focus} official statute law regulation article text",
            "terms_and_rules": f"{focus} administrative guidance binding ruling official gazette",
            "fine_print_limits": f"{focus} exception threshold penalty exclusion safe harbor treaty",
            "adversarial_postmortem": f"{focus} audit dispute court decision enforcement revocation",
        }
    if domain in ("biotech", "pharma", "medicine", "clinical"):
        return {
            "official_primary": f"{focus} clinical trial NCT protocol primary endpoint",
            "terms_and_rules": f"{focus} FDA EMA label prescribing information eligibility",
            "fine_print_limits": f"{focus} discontinuation adverse events dropout subgroup shrinkage",
            "adversarial_postmortem": f"{focus} failed phase 3 complete response letter toxicity",
        }
    if domain in ("saas", "product", "b2b"):
        return {
            "official_primary": f"{focus} official API documentation pricing limits",
            "terms_and_rules": f"{focus} terms of service SLA rate limit quota pricing",
            "fine_print_limits": f"{focus} limitation webhook failure data loss restriction",
            "adversarial_postmortem": f"{focus} migration complaint outage postmortem review",
        }
    return {
        "official_primary": f"{focus} official documentation specifications primary source",
        "terms_and_rules": f"{focus} (\"terms and conditions\" OR FAQ OR rules OR pricing OR methodology)",
        "fine_print_limits": f"{focus} (limit OR restriction OR exception OR fine print OR caveats)",
        "adversarial_postmortem": f"{focus} (postmortem OR failure OR critique OR counterexample)",
    }


def _search_ddg_html_fallback(query: str, max_results: int = 6, timeout: float = 8.0) -> list[dict[str, str]]:
    """Keyless DuckDuckGo HTML fallback when `ddgs` package is unavailable."""
    encoded = urllib.parse.quote_plus(str(query or "")[:240])
    url = f"https://html.duckduckgo.com/html/?q={encoded}"
    res = resilient_fetch(url, timeout=timeout, retries=1)
    if not res.ok or not res.text:
        return []
    hits: list[dict[str, str]] = []
    for m in re.finditer(r'<a[^>]+class="[^"]*result__a[^"]*"[^>]+href="([^"]+)"[^>]*>(.*?)</a>', res.text, re.I | re.S):
        raw_href = html_lib.unescape(m.group(1))
        title = _strip_inline_html(m.group(2))
        if "uddg=" in raw_href:
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(raw_href).query)
            raw_href = (qs.get("uddg") or [raw_href])[0]
        canon = canonicalize_crawl_url(raw_href)
        if canon and is_safe_url(canon):
            hits.append({"title": title, "url": canon, "snippet": ""})
        if len(hits) >= max_results:
            break
    return hits


def discover_web_leads(
    prompt: str,
    *,
    entities: list[str] | None = None,
    domain: str = "general",
    max_per_vector: int = 5,
    max_total: int = 16,
    timeout: int = 8,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Run multi-vector web discovery and return ranked primary/T&C/FAQ leads + telemetry."""
    vectors = build_deep_search_queries(prompt, entities=entities, domain=domain)
    seen: set[str] = set()
    leads: list[dict[str, Any]] = []
    vector_stats: dict[str, int] = {}
    errors: list[str] = []

    for vec_name, q in vectors.items():
        raw_hits: list[dict[str, str]] = []
        if HAS_DDGS:
            try:
                with DDGS(timeout=timeout) as ddgs:
                    for h in ddgs.text(q, max_results=max_per_vector):
                        href = str(h.get("href") or "")
                        if not href or "bing.com/aclick" in href:
                            continue
                        canon = canonicalize_crawl_url(href)
                        if canon and is_safe_url(canon):
                            raw_hits.append({
                                "title": str(h.get("title") or "").strip(),
                                "url": canon,
                                "snippet": str(h.get("body") or "").strip(),
                            })
            except Exception as exc:
                errors.append(f"{vec_name}/ddgs: {type(exc).__name__}: {exc}"[:160])
        if not raw_hits:
            raw_hits = _search_ddg_html_fallback(q, max_results=max_per_vector, timeout=float(timeout))

        vector_stats[vec_name] = len(raw_hits)
        for h in raw_hits:
            u = h["url"]
            if u in seen or JUNK_PATH_RE.search(u):
                continue
            seen.add(u)
            host = (urllib.parse.urlparse(u).hostname or "").lower().removeprefix("www.")
            path_low = u.lower() + " " + h["title"].lower()
            score = 28.0
            if any(tok in path_low for tok in ("terms", "faq", "help", "rules", "pricing", "legal", "docs", ".pdf")):
                score += 18.0
            if host.endswith((".gov", ".edu", ".int", ".eu")) or host.startswith(("help.", "docs.", "support.")):
                score += 14.0
            if any(c in host for c in ("reddit.com", "quora.com", "medium.com", "trustpilot.com")):
                score -= 10.0
            leads.append({
                "title": h["title"] or u,
                "url": u,
                "host": host,
                "vector": vec_name,
                "score": round(score, 2),
                "snippet": h["snippet"],
            })

    leads.sort(key=lambda x: (-float(x["score"]), str(x["url"])))
    telemetry = {
        "vectors": vectors,
        "vector_hit_counts": vector_stats,
        "total_unique_leads": len(leads),
        "errors": errors,
    }
    return leads[: max(0, int(max_total))], telemetry


def dig_into_study(
    study_dir: Path | str,
    *,
    seed_urls: list[str] | None = None,
    query: str = "",
    max_depth: int = 2,
    max_subpages: int = 12,
    discover_web: bool = False,
    timeout: float = 12.0,
) -> dict[str, Any]:
    """Expand an existing `research/<slug>/sources/` corpus via deep multi-hop digging."""
    sdir = Path(study_dir)
    sources_dir = sdir / "sources"
    sources_dir.mkdir(parents=True, exist_ok=True)
    index_path = sources_dir / "index.jsonl"

    existing_rows: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    seen_hashes: set[str] = set()
    if index_path.exists():
        for line in index_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
                existing_rows.append(row)
                seen_urls.add(canonicalize_crawl_url(str(row.get("url", ""))))
                if row.get("sha256"):
                    seen_hashes.add(str(row["sha256"]))
            except ValueError:
                continue

    spec: dict[str, Any] = {}
    spec_path = sdir / "study_spec.json"
    if spec_path.exists():
        try:
            spec = json.loads(spec_path.read_text(encoding="utf-8"))
        except ValueError:
            spec = {}

    focus = query or str(spec.get("study_title") or "")
    seeds = list(seed_urls or [])
    if not seeds:
        seeds.extend(str(r.get("url", "")) for r in existing_rows if r.get("url"))
        seeds.extend(str(u) for u in (spec.get("urls") or []))

    web_telemetry: dict[str, Any] = {}
    if discover_web and focus:
        web_leads, web_telemetry = discover_web_leads(
            focus,
            entities=spec.get("entities") if isinstance(spec.get("entities"), list) else None,
            domain=str(spec.get("domain", "general")),
            max_total=10,
        )
        for wl in web_leads:
            seeds.append(str(wl["url"]))

    dug_docs = deep_dig_urls(
        seeds,
        focus_query=focus,
        max_depth=max_depth,
        max_subpages=max_subpages,
        timeout=timeout,
    )

    next_num = len(existing_rows) + 1
    added: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    now_iso = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")

    with index_path.open("a", encoding="utf-8") as idx_out:
        for doc in dug_docs:
            canon = canonicalize_crawl_url(doc.url)
            if not doc.ok:
                failed.append({"url": doc.url, "hop_depth": doc.hop_depth, "error": doc.error})
                continue
            if canon in seen_urls or doc.sha256 in seen_hashes:
                continue
            sid = f"S{next_num:03d}"
            next_num += 1
            (sources_dir / f"{sid}.txt").write_text(doc.text, encoding="utf-8")
            host = (urllib.parse.urlparse(doc.url).hostname or "unknown").lower().removeprefix("www.")
            rec = {
                "id": sid,
                "url": doc.url,
                "host": host,
                "sha256": doc.sha256,
                "chars": len(doc.text),
                "origin": "deep_digger_pdf" if doc.is_pdf else "deep_digger_subpage",
                "via": doc.via,
                "status": doc.status,
                "evidence_class": doc.evidence_class,
                "hop_depth": doc.hop_depth,
                "parent_url": doc.parent_url,
                "link_reason": doc.reason,
                "fetched_at": now_iso,
            }
            idx_out.write(json.dumps(rec, ensure_ascii=False) + "\n")
            seen_urls.add(canon)
            seen_hashes.add(doc.sha256)
            added.append(rec)

    return {
        "added_count": len(added),
        "added": added,
        "failed_count": len(failed),
        "failed": failed,
        "web_discovery": web_telemetry,
    }


def _selftest() -> int:
    t0 = time.perf_counter()
    # 1. Registrable domain & canonicalization
    assert registrable_domain("https://help.fintokei.com/en/articles/123") == "fintokei.com"
    assert registrable_domain("https://docs.company.co.uk/terms") == "company.co.uk"
    assert (
        canonicalize_crawl_url("https://www.fintokei.com/faq/?utm_source=x&id=2#top")
        == "https://www.fintokei.com/faq?id=2"
    )

    # 2. Table & JSON-LD FAQ preservation
    sample_html = """
    <html><head>
    <script type="application/ld+json">
    {"@context":"https://schema.org","@type":"FAQPage","mainEntity":[
      {"@type":"Question","name":"Is copy trading allowed?","acceptedAnswer":{"@type":"Answer","text":"Copying trades between your own accounts is permitted up to 400,000 EUR allocation."}}
    ]}
    </script></head><body>
    <h2>ProTrader Pricing</h2>
    <table>
      <tr><th>Account</th><th>Fee</th><th>Max Loss</th></tr>
      <tr><td>100K USD</td><td>$549</td><td>10% Fixed</td></tr>
    </table>
    <a href="/en/terms-and-conditions.pdf">General Terms PDF</a>
    <a href="https://help.fintokei.com/en/articles/drawdown-rules">Drawdown Rules FAQ</a>
    <a href="/jp/protrader/">Japanese Mirror</a>
    <a href="/login">Client Login</a>
    </body></html>
    """
    snap = html_to_structured_snapshot(sample_html)
    assert "Account | Fee | Max Loss" in snap, snap
    assert "100K USD | $549 | 10% Fixed" in snap, snap
    assert "Copying trades between your own accounts is permitted up to 400,000 EUR allocation." in snap, snap

    # 3. Sublink extraction & scoring (must pick PDF + help subdomain, skip /jp/ and /login)
    links = extract_high_value_sublinks(
        sample_html, "https://www.fintokei.com/protrader/", focus_query="drawdown copy trading"
    )
    urls = [c.url for c in links]
    assert "https://www.fintokei.com/en/terms-and-conditions.pdf" in urls, urls
    assert "https://help.fintokei.com/en/articles/drawdown-rules" in urls, urls
    assert all("/jp/" not in u and "/login" not in u for u in urls), urls

    # 4. Multi-vector query builder
    qs = build_deep_search_queries("Fintokei ProTrader 100K rules", ["Fintokei", "ProTrader"], domain="quant")
    assert len(qs) == 4 and "copy trading" in qs["fine_print_limits"]

    elapsed = (time.perf_counter() - t0) * 1000.0
    print(f"[SELFTEST PASS] deep_digger v13.0 verified in {elapsed:.2f} ms.")
    return 0


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="Deep Research v13.0 Multi-Hop Deep Digger")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_dig = sub.add_parser("dig", help="Crawl subpages, help centers, T&Cs & PDFs into sources/")
    p_dig.add_argument("--dir", required=True, help="Target research/<slug> directory")
    p_dig.add_argument("--url", action="append", default=[], help="Explicit seed URL(s)")
    p_dig.add_argument("--query", default="", help="Focus query for ranking sublinks")
    p_dig.add_argument("--max-depth", type=int, default=2)
    p_dig.add_argument("--max-subpages", type=int, default=12)
    p_dig.add_argument("--discover-web", action="store_true", help="Also run 4-vector web search")

    p_st = sub.add_parser("selftest", help="Run deterministic offline selftest")
    args = ap.parse_args(argv)

    if args.cmd == "selftest":
        return _selftest()
    if args.cmd == "dig":
        out = dig_into_study(
            args.dir,
            seed_urls=args.url or None,
            query=args.query,
            max_depth=args.max_depth,
            max_subpages=args.max_subpages,
            discover_web=args.discover_web,
        )
        print(
            f"[DEEP DIG OK] Added {out['added_count']} new subpage/PDF snapshots "
            f"(failed={out['failed_count']}) -> {Path(args.dir) / 'sources'}"
        )
        for rec in out["added"]:
            print(f"  + {rec['id']} [hop={rec['hop_depth']}] {rec['url']} ({rec['chars']} chars, {rec['link_reason']})")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
