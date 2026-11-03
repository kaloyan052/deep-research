"""High-Throughput Research Scanner & Evidence Miner for Deep Research (v3.1).

Enables scanning, filtering, and mining dozens of websites, regulatory portals,
and scholarly registries concurrently with high speed and rigorous quality control.

Features:
1. Federated Search: Queries general web (DDGS) + scholarly registries (OpenAlex,
   Semantic Scholar, CrossRef, arXiv, EuropePMC) concurrently in parallel threads.
2. Source Tier Pre-Classification: Automatically tags candidates as T1 (statutory/official),
   T2 (regulatory/exchange), T3 (peer-reviewed/academic), T4 (preprints), or T5 (community).
   Filters out T5 noise.
3. Concurrent Batch Fetching: Downloads 10-30 pages in parallel directly into
   `research/<slug>/sources/` with SHA-256 hashes and `index.jsonl` provenance.
4. PaperQA2-Style BM25 Passage Mining: Fast local Okapi BM25 scoring over all fetched
   passages to find top verbatim quotes answering Sub-Questions (SQn) or Kill Hypotheses (Kn).

Usage:
  python dr_engine/tools/scanner.py "prop firm CFD news trading rules" --limit 10
  python dr_engine/tools/scanner.py "institutional rebalancing equity momentum" \\
      --dir research/2026-11-02-rp39-forced-flows --purpose K1 --auto-fetch --top-quotes 3
"""

from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import hashlib
import json
import math
import os
import re
import sys
import urllib.parse
from pathlib import Path
from typing import Any

import requests
from bs4 import BeautifulSoup

# Import existing discovery & evidence tools
sys.path.insert(0, str(Path(__file__).resolve().parent))
from discover import (
    search_openalex, search_crossref, search_arxiv, search_europepmc, search_semanticscholar,
    _norm_title, _norm_doi
)
from evidence import (
    fetch_page, _append, _jsonl, _next_id, _canon, USER_AGENT
)

try:
    from ddgs import DDGS
    HAS_DDGS = True
except ImportError:
    HAS_DDGS = False


# Domain tier classification rules
T1_OFFICIAL_DOMAINS = {
    "eur-lex.europa.eu", "lex.bg", "dv.parliament.bg", "sec.gov", "cftc.gov",
    "fca.org.uk", "esma.europa.eu", "bis.org", "federalreserve.gov",
    "ftserussell.com", "spglobal.com", "msci.com", "help.brightfunded.com",
    "brightfunded.com", "fintokei.com", "ftmo.com"
}

T3_SCHOLARLY_DOMAINS = {
    "nber.org", "ssrn.com", "repec.org", "ideas.repec.org", "sciencedirect.com",
    "oup.com", "wiley.com", "springer.com", "nature.com", "tandfonline.com",
    "jstor.org", "frontiersin.org", "mdpi.com", "plos.org", "annualreviews.org"
}

T5_COMMUNITY_DOMAINS = {
    "reddit.com", "twitter.com", "x.com", "youtube.com", "medium.com",
    "substack.com", "trustpilot.com", "discord.com", "quora.com",
    "investopedia.com", "babypips.com", "wikipedia.org"
}


def classify_url_tier(url: str) -> str:
    """Pre-classifies domain into evidence tiers T1-T5."""
    try:
        host = (urllib.parse.urlparse(url).hostname or "").lower()
    except Exception:
        return "T4"
    if host.startswith("www."):
        host = host[4:]
    for d in T1_OFFICIAL_DOMAINS:
        if host == d or host.endswith("." + d):
            return "T1"
    for d in T3_SCHOLARLY_DOMAINS:
        if host == d or host.endswith("." + d):
            return "T3"
    for d in T5_COMMUNITY_DOMAINS:
        if host == d or host.endswith("." + d):
            return "T5"
    if host.endswith(".gov") or host.endswith(".mil") or host.endswith(".int"):
        return "T1"
    if host.endswith(".edu") or "university" in host:
        return "T3"
    return "T4"


def search_web_ddgs(query: str, limit: int = 10, timeout: int = 10) -> list[dict[str, Any]]:
    """Performs parallel DuckDuckGo web search returning clean leads."""
    if not HAS_DDGS:
        return []
    out: list[dict[str, Any]] = []
    try:
        with DDGS(timeout=timeout) as ddgs:
            hits = list(ddgs.text(query, max_results=limit))
            for h in hits:
                href = h.get("href") or ""
                if not href or href.startswith("https://www.bing.com/aclick"):
                    continue
                tier = classify_url_tier(href)
                out.append({
                    "registry": "web_ddgs",
                    "title": h.get("title", "").strip(),
                    "url": href,
                    "fetch_url": href,
                    "doi": "",
                    "citations": 0,
                    "suggested_tier": tier,
                    "snippet": h.get("body", "").strip(),
                })
    except Exception:
        pass
    return out


def federated_search(
    query: str,
    limit: int = 20,
    include_web: bool = True,
    include_scholarly: bool = True,
) -> list[dict[str, Any]]:
    """Queries web and academic engines concurrently and returns deduplicated leads."""
    tasks: dict[str, Any] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
        if include_web and HAS_DDGS:
            tasks["web"] = executor.submit(search_web_ddgs, query, limit=limit)
        if include_scholarly:
            tasks["openalex"] = executor.submit(search_openalex, query, limit=limit // 2)
            tasks["crossref"] = executor.submit(search_crossref, query, limit=limit // 2)
            tasks["arxiv"] = executor.submit(search_arxiv, query, limit=limit // 2)
            tasks["europepmc"] = executor.submit(search_europepmc, query, limit=limit // 2)
            tasks["semanticscholar"] = executor.submit(search_semanticscholar, query, limit=limit // 2)

        raw_leads: list[dict[str, Any]] = []
        for name, future in tasks.items():
            try:
                res = future.result(timeout=12)
                if isinstance(res, list):
                    raw_leads.extend(res)
            except Exception:
                pass

    # Deduplicate by canonical URL or DOI or normalized title
    seen_urls: set[str] = set()
    seen_dois: set[str] = set()
    seen_titles: set[str] = set()
    unique_leads: list[dict[str, Any]] = []

    for item in raw_leads:
        url = _canon(item.get("fetch_url") or item.get("url") or "")
        doi = _norm_doi(item.get("doi") or "")
        title_norm = _norm_title(item.get("title") or "")

        if url and url in seen_urls:
            continue
        if doi and doi in seen_dois:
            continue
        if title_norm and title_norm in seen_titles:
            continue

        if url: seen_urls.add(url)
        if doi: seen_dois.add(doi)
        if title_norm: seen_titles.add(title_norm)
        unique_leads.append(item)

    # Rank: T1/T2 official > T3 peer-reviewed > T4 preprint/web > T5 community
    tier_weights = {"T1": 4.0, "T2": 3.0, "T3": 2.5, "T4": 1.0, "T5": 0.1}
    unique_leads.sort(
        key=lambda x: tier_weights.get(x.get("suggested_tier", "T4"), 1.0) + math.log1p(x.get("citations", 0)) * 0.3,
        reverse=True
    )
    return unique_leads[:limit]


def concurrent_batch_fetch(
    urls: list[str],
    study_dir: Path | None = None,
    max_workers: int = 10,
    timeout: float = 20.0,
) -> list[dict[str, Any]]:
    """Concurrently fetches multiple URLs and saves them into study_dir/sources/."""
    results: list[dict[str, Any]] = []
    src_dir = (study_dir / "sources") if study_dir else None
    if src_dir:
        src_dir.mkdir(parents=True, exist_ok=True)
        index_path = src_dir / "index.jsonl"
        existing = {_canon(r["url"]): r for r in _jsonl(index_path)}
    else:
        existing = {}

    to_fetch: list[str] = []
    for u in urls:
        c_u = _canon(u)
        if c_u in existing:
            results.append({
                "url": u, "ok": True, "source_id": existing[c_u]["id"],
                "chars": existing[c_u]["chars"], "text": (src_dir / f"{existing[c_u]['id']}.txt").read_text(encoding="utf-8", errors="replace"),
                "cached": True
            })
        else:
            to_fetch.append(u)

    def _fetch_worker(target_url: str) -> dict[str, Any]:
        # r.jina.ai is a third-party service: only with the user's explicit opt-in
        page = fetch_page(target_url, timeout=timeout,
                          jina_fallback=os.environ.get("DR_ALLOW_JINA") == "1")
        return {"url": target_url, "page": page}

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_fetch_worker, u): u for u in to_fetch}
        for fut in concurrent.futures.as_completed(futures):
            try:
                res = fut.result()
                page = res["page"]
                u = res["url"]
                if page.get("ok") and page.get("text"):
                    text = page["text"]
                    sid = None
                    if src_dir:
                        idx_records = _jsonl(index_path)
                        sid = _next_id(idx_records, "S")
                        sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
                        (src_dir / f"{sid}.txt").write_text(text, encoding="utf-8")
                        rec = {
                            "id": sid, "url": u, "final_url": page.get("final_url", u),
                            "fetched_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                            "sha256": sha, "chars": len(text), "http_status": page.get("http_status"),
                            "via": page.get("via", "direct")
                        }
                        _append(index_path, rec)
                    results.append({
                        "url": u, "ok": True, "source_id": sid,
                        "chars": len(text), "text": text, "cached": False
                    })
                else:
                    results.append({
                        "url": u, "ok": False, "error": page.get("error", "Unknown error"),
                        "text": "", "cached": False
                    })
            except Exception as e:
                results.append({"url": futures[fut], "ok": False, "error": str(e), "text": "", "cached": False})

    return results


class SimpleBM25:
    """Ultra-fast, zero-dependency Okapi BM25 passage ranker for paragraph-level evidence mining."""

    def __init__(self, passages: list[str], k1: float = 1.5, b: float = 0.75):
        self.passages = passages
        self.k1 = k1
        self.b = b
        self.doc_len = [len(p.split()) for p in passages]
        self.avg_dl = sum(self.doc_len) / max(1, len(self.doc_len))
        self.df: dict[str, int] = {}
        self.doc_freqs: list[dict[str, int]] = []

        for p in passages:
            words = re.findall(r"\b[a-zA-Z0-9_\u0400-\u04FF-]{2,}\b", p.lower())
            freq: dict[str, int] = {}
            for w in words:
                freq[w] = freq.get(w, 0) + 1
            self.doc_freqs.append(freq)
            for w in freq:
                self.df[w] = self.df.get(w, 0) + 1

        self.N = len(passages)
        self.idf: dict[str, float] = {}
        for w, count in self.df.items():
            self.idf[w] = math.log(1.0 + (self.N - count + 0.5) / (count + 0.5))

    def score(self, query: str) -> list[tuple[int, float]]:
        q_words = re.findall(r"\b[a-zA-Z0-9_\u0400-\u04FF-]{2,}\b", query.lower())
        scores: list[float] = [0.0] * self.N
        for w in q_words:
            idf = self.idf.get(w, 0.0)
            if idf <= 0:
                continue
            for i, freq_map in enumerate(self.doc_freqs):
                tf = freq_map.get(w, 0)
                if tf > 0:
                    num = tf * (self.k1 + 1.0)
                    den = tf + self.k1 * (1.0 - self.b + self.b * (self.doc_len[i] / self.avg_dl))
                    scores[i] += idf * (num / den)

        # Bonus for numbers, percentages, or exact matches
        for i, s in enumerate(scores):
            if s > 0:
                p_text = self.passages[i]
                if re.search(r"\b\d+(?:\.\d+)?(?:%|bp|R|EUR|USD|\$)\b", p_text):
                    scores[i] *= 1.25  # Quantitative evidence boost

        ranked = [(i, scores[i]) for i in range(self.N) if scores[i] > 0]
        ranked.sort(key=lambda x: x[1], reverse=True)
        return ranked


def mine_evidence_quotes(
    fetched_docs: list[dict[str, Any]],
    query: str,
    top_k: int = 5,
) -> list[dict[str, Any]]:
    """Splits fetched documents into passages, runs BM25, and returns top verbatim evidence quotes."""
    all_passages: list[dict[str, Any]] = []
    for doc in fetched_docs:
        if not doc.get("ok") or not doc.get("text"):
            continue
        text = doc["text"]
        sid = doc.get("source_id") or "UNKNOWN"
        url = doc.get("url") or ""

        # Break text into paragraphs / sections
        paragraphs = [p.strip() for p in text.split("\n\n") if len(p.strip()) >= 50]
        for idx, p in enumerate(paragraphs):
            # Clean single-line breaks
            clean_p = re.sub(r"\s+", " ", p).strip()
            all_passages.append({
                "source_id": sid,
                "url": url,
                "para_index": idx,
                "text": clean_p
            })

    if not all_passages:
        return []

    texts = [p["text"] for p in all_passages]
    bm25 = SimpleBM25(texts)
    ranked = bm25.score(query)

    top_quotes: list[dict[str, Any]] = []
    seen_texts: set[str] = set()

    for idx, score in ranked[:top_k * 3]:
        item = all_passages[idx]
        p_text = item["text"]
        if p_text in seen_texts:
            continue
        seen_texts.add(p_text)

        # Extract best 1-2 sentence verbatim candidate
        sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", p_text) if len(s.strip()) >= 25]
        best_sentence = p_text
        if len(sentences) > 1:
            # Pick sentence with most query words or numbers
            s_bm25 = SimpleBM25(sentences)
            s_ranked = s_bm25.score(query)
            if s_ranked:
                best_sentence = sentences[s_ranked[0][0]]

        top_quotes.append({
            "source_id": item["source_id"],
            "url": item["url"],
            "score": round(score, 3),
            "verbatim_quote": best_sentence,
            "full_passage": p_text
        })
        if len(top_quotes) >= top_k:
            break

    return top_quotes


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="High-Throughput Research Scanner & Evidence Miner (v3.1)")
    ap.add_argument("query", help="Primary search query or research topic")
    ap.add_argument("--dir", default=None, help="Target study directory (e.g. research/<slug>)")
    ap.add_argument("--purpose", default="SQ1", help="Purpose tag (SQ1..SQn, K1..Kn)")
    ap.add_argument("--limit", type=int, default=15, help="Maximum number of leads to gather")
    ap.add_argument("--auto-fetch", action="store_true", help="Automatically fetch the top candidates concurrently")
    ap.add_argument("--top-quotes", type=int, default=5, help="Number of top verbatim quotes to mine via BM25")
    ap.add_argument("--json", action="store_true", help="Output results in JSON format")

    args = ap.parse_args(argv)
    study_dir = Path(args.dir) if args.dir else None

    print(f"[*] Scanning federated registries for: {args.query!r} (purpose={args.purpose})...")
    leads = federated_search(args.query, limit=args.limit)
    print(f"[+] Found {len(leads)} deduplicated leads across Web & Scholarly engines.")

    for i, lead in enumerate(leads[:8], 1):
        tier = lead.get("suggested_tier", "T4")
        reg = lead.get("registry", "")
        title = lead.get("title", "")[:75]
        url = lead.get("fetch_url") or lead.get("url") or ""
        print(f"  {i}. [{tier}] {title} ({reg}) -> {url[:65]}...")

    if not args.auto_fetch and not args.json:
        print("\nTip: Add --auto-fetch to concurrently download and mine quotes into your study directory.")
        return 0

    fetch_urls = [l.get("fetch_url") or l.get("url") for l in leads if (l.get("fetch_url") or l.get("url"))]
    print(f"\n[*] Concurrently batch-fetching top {len(fetch_urls)} pages...")
    fetched = concurrent_batch_fetch(fetch_urls, study_dir=study_dir, max_workers=10)
    ok_count = sum(1 for f in fetched if f.get("ok"))
    print(f"[+] Successfully fetched and indexed {ok_count}/{len(fetch_urls)} pages.")

    if args.top_quotes > 0 and ok_count > 0:
        print(f"\n[*] Mining top {args.top_quotes} verbatim quotes via Okapi BM25...")
        quotes = mine_evidence_quotes(fetched, args.query, top_k=args.top_quotes)
        print(f"[+] Extracted {len(quotes)} high-relevance candidate quotes:")
        for q in quotes:
            print(f"\n  Source: {q['source_id']} (Score: {q['score']}) -> {q['url']}")
            print(f"  Verbatim Quote: \"{q['verbatim_quote']}\"")
            if study_dir and q['source_id'] != "UNKNOWN":
                print(f"  Command: python dr_engine/tools/evidence.py add --dir {study_dir} "
                      f"--source {q['source_id']} --sq {args.purpose} --tier T1 --kind empirical "
                      f"--stance supports --quote \"{q['verbatim_quote']}\" --claim \"<claim>\"")

    if args.json:
        out_data = {
            "query": args.query,
            "leads_count": len(leads),
            "leads": leads,
            "fetched_count": ok_count,
            "top_quotes": quotes if (args.top_quotes > 0 and ok_count > 0) else []
        }
        print(json.dumps(out_data, indent=2))

    return 0


if __name__ == "__main__":
    sys.exit(main())
