"""Unified Multi-Registry Academic & Primary Discovery CLI for Deep Research.

Queries OpenAlex, CrossRef, arXiv (surfacing full-text HTML links for direct
`evidence.py fetch`), and EuropePMC in a single command, deduplicates by DOI/title,
classifies suggested source tier (T3 peer-reviewed vs T4 preprint), and optionally
logs verified search provenance directly into `research/<dir>/searches.jsonl`.

Remember: discovery results are LEADS, never evidence. Always run
`evidence.py fetch --dir <dir> <fetch_url>` and `evidence.py add --quote "..."`
on the primary pages you rely on.

Usage:
  python dr_engine/tools/discover.py "prop trading daily drawdown stopping time" \\
      --dir research/<slug> --purpose SQ1 --limit 8

  python dr_engine/tools/discover.py "intraday momentum futures slippage" \\
      --sources openalex,arxiv,crossref --purpose K3 --dir research/<slug> --json

  python dr_engine/tools/discover.py --snowball 10.1111/jofi.12345 --direction both \\
      --dir research/<slug> --purpose SQ2 --limit 25
      citation graph via OpenAlex: backward = the seed's references (referenced_works),
      forward = works citing it (cited_by_api_url); one request per OPENALEX_MIN_INTERVAL
      seconds (default 1); mailto only from the OPENALEX_MAILTO environment variable.

Every lead goes to candidates.jsonl (fetched or not): corpus.py stats uses it to estimate
coverage by channel, screening.py samples the ones never fetched.

Dependency-light: stdlib + requests.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import os
import re
import sys
import time
import urllib.parse
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from evidence import SQ_RE, _append, _jsonl, _next_id  # noqa: E402

UA = "DeepResearchEngine/3.0 (mailto:research@local.workspace; scholarly-discovery)"
ALL_REGISTRIES = ("openalex", "crossref", "arxiv", "europepmc", "semanticscholar")


def _norm_title(title: str) -> str:
  return re.sub(r"[^a-z0-9]+", " ", (title or "").lower()).strip()


def _norm_doi(doi: str) -> str:
  d = (doi or "").strip().lower()
  for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
    if d.startswith(prefix):
      d = d[len(prefix):]
  return d.strip()


def _reconstruct_inverted_abstract(inv: dict[str, list[int]] | None, max_words: int = 45) -> str:
  if not inv or not isinstance(inv, dict):
    return ""
  pairs: list[tuple[int, str]] = []
  for word, positions in inv.items():
    if isinstance(positions, list):
      for pos in positions:
        if isinstance(pos, int):
          pairs.append((pos, word))
  if not pairs:
    return ""
  pairs.sort(key=lambda x: x[0])
  words = [w for _, w in pairs[:max_words]]
  return " ".join(words) + (" ..." if len(pairs) > max_words else "")


OPENALEX = "https://api.openalex.org"
OPENALEX_MIN_INTERVAL = float(os.environ.get("OPENALEX_MIN_INTERVAL", "1.0"))  # seconds between calls
_last_openalex_call = 0.0


def openalex_get(url: str, params: dict | None = None, timeout: int = 12, retries: int = 3) -> dict:
  """Polite OpenAlex GET: at most one call per OPENALEX_MIN_INTERVAL seconds, mailto from the
  OPENALEX_MAILTO environment variable (OpenAlex's polite pool; never a hard-coded address),
  backoff on 429/5xx honouring Retry-After. Raises RuntimeError with the reason on failure."""
  global _last_openalex_call
  params = dict(params or {})
  if os.environ.get("OPENALEX_MAILTO"):
    params["mailto"] = os.environ["OPENALEX_MAILTO"]
  full = url + (("&" if "?" in url else "?") + urllib.parse.urlencode(params) if params else "")
  last = ""
  for attempt in range(retries + 1):
    wait = _last_openalex_call + OPENALEX_MIN_INTERVAL - time.monotonic()
    if wait > 0:
      time.sleep(wait)
    _last_openalex_call = time.monotonic()
    retry_after = 0.0
    try:
      resp = requests.get(full, headers={"User-Agent": UA}, timeout=timeout)
      resp.raise_for_status()
      return resp.json()
    except requests.HTTPError as e:
      status = e.response.status_code if e.response is not None else 0
      last = f"HTTP {status}"
      if status not in (429, 500, 502, 503, 504):
        break
      try:
        retry_after = float(e.response.headers.get("Retry-After", "")) if e.response is not None else 0.0
      except ValueError:
        retry_after = 0.0
    except requests.RequestException as e:
      last = f"{type(e).__name__}: {e}"[:200]
    if attempt < retries:
      time.sleep(max(retry_after, 2.0 ** (attempt + 1)))
  raise RuntimeError(f"OpenAlex request failed after {attempt + 1} attempt(s) ({last}): {full}")


def _openalex_item(item: dict) -> dict[str, Any] | None:
  title = (item.get("title") or item.get("display_name") or "").strip()
  if not title:
    return None
  doi_raw = item.get("doi") or ""
  doi = _norm_doi(doi_raw)
  loc = item.get("primary_location") or {}
  src = loc.get("source") or {}
  venue = src.get("display_name") or ""
  work_type = (item.get("type") or "").lower()
  src_type = (src.get("type") or "").lower()
  is_peer = (
      work_type in ("article", "book-chapter", "review")
      and src_type != "repository"
      and "arxiv" not in venue.lower()
      and "ssrn" not in venue.lower()
  )
  oa = item.get("open_access") or {}
  oa_url = oa.get("oa_url") or ""
  landing_url = loc.get("landing_page_url") or (f"https://doi.org/{doi}" if doi else item.get("id", ""))
  fetch_url = landing_url or oa_url
  if "arxiv.org/abs/" in (oa_url or ""):
    arx_id = oa_url.split("arxiv.org/abs/")[-1].split("v")[0].strip("/")
    fetch_url = f"https://arxiv.org/html/{arx_id}"
  return {
      "registry": "openalex",
      "openalex_id": (item.get("id") or "").rsplit("/", 1)[-1],
      "title": title,
      "year": item.get("publication_year"),
      "venue": venue or "OpenAlex",
      "doi": doi,
      "citations": int(item.get("cited_by_count") or 0),
      "suggested_tier": "T3" if is_peer else "T4",
      "url": landing_url or fetch_url,
      "fetch_url": fetch_url,
      "oa_url": oa_url,
      "snippet": _reconstruct_inverted_abstract(item.get("abstract_inverted_index")),
  }


def search_openalex(query: str, limit: int = 5, timeout: int = 12) -> list[dict[str, Any]]:
  """Searches OpenAlex works endpoint."""
  data = openalex_get(f"{OPENALEX}/works", {"search": query, "per-page": max(1, min(limit, 25))},
                      timeout=timeout)
  return [r for r in (_openalex_item(i) for i in data.get("results") or []) if r]


# ------------------------------------------------------------- snowballing
SEED_W_RE = re.compile(r"(?:openalex\.org/)?(W\d+)$", re.I)
SEED_DOI_RE = re.compile(r"(?:doi\.org/|doi:)?(10\.\d{4,9}/\S+)$", re.I)


def resolve_seed(seed: str, timeout: int = 12) -> dict:
  """OpenAlex work for a seed given as an OpenAlex id (W123..., or its URL) or a DOI."""
  s = (seed or "").strip()
  m = SEED_W_RE.search(s)
  if m:
    return openalex_get(f"{OPENALEX}/works/{m.group(1).upper()}", timeout=timeout)
  m = SEED_DOI_RE.search(s)
  if m:
    return openalex_get(f"{OPENALEX}/works/doi:{m.group(1)}", timeout=timeout)
  raise ValueError(f"--snowball seed {seed!r} is neither an OpenAlex work id (W2741809807 or "
                   f"https://openalex.org/W2741809807) nor a DOI (10.1111/jofi.12345). Find the "
                   f"seed's DOI on its landing page, or run a normal discover.py query first.")


TITLE_STOP = {"the", "a", "an", "of", "and", "in", "on", "for", "to", "with", "from", "by", "at",
              "versus", "vs", "evidence", "new", "theory", "model", "models", "market", "markets",
              "analysis", "study", "returns", "return", "stock", "stocks"}


def _title_terms(title: str) -> set[str]:
  return {w for w in re.findall(r"[a-z]{3,}", (title or "").lower()) if w not in TITLE_STOP}


def snowball(seed: str, direction: str = "both", limit: int = 25, timeout: int = 12) -> dict:
  """Citation-graph expansion of one seed work: backward = its reference list
  (referenced_works), forward = works citing it (cited_by_api_url), most cited first."""
  if direction not in ("forward", "backward", "both"):
    raise ValueError("--direction must be forward, backward or both")
  work = resolve_seed(seed, timeout)
  back: list[dict[str, Any]] = []
  fwd: list[dict[str, Any]] = []
  if direction in ("backward", "both"):
    refs = [r.rsplit("/", 1)[-1] for r in work.get("referenced_works") or []]
    for i in range(0, len(refs), 50):  # OpenAlex OR-filter batches
      data = openalex_get(f"{OPENALEX}/works", {"filter": "openalex:" + "|".join(refs[i:i + 50]),
                                                "per-page": 50}, timeout=timeout)
      back += [dict(r, direction="backward")
               for r in (_openalex_item(it) for it in data.get("results") or []) if r]
  if direction in ("forward", "both"):
    wid = (work.get("id") or "").rsplit("/", 1)[-1]
    cited_by = work.get("cited_by_api_url") or f"{OPENALEX}/works?filter=cites:{wid}"
    data = openalex_get(cited_by, {"sort": "cited_by_count:desc", "per-page": max(1, min(limit, 50))},
                        timeout=timeout)
    fwd = [dict(r, direction="forward")
           for r in (_openalex_item(it) for it in data.get("results") or []) if r]
  # A reference list is full of generic classics (CAPM, Fama-French) with huge citation
  # counts; rank by title overlap with the seed first, citations only break ties.
  seed_terms = _title_terms((work.get("title") or work.get("display_name") or ""))
  for r in back:
    r["seed_overlap"] = len(seed_terms & _title_terms(r["title"]))
  back = sorted(back, key=lambda r: (-r["seed_overlap"], -r["citations"]))[:limit]
  seed_item = _openalex_item(work) or {}
  return {"seed": seed, "seed_title": seed_item.get("title", ""),
          "seed_id": seed_item.get("openalex_id", ""), "direction": direction,
          "references_total": len(work.get("referenced_works") or []),
          "cited_by_total": int(work.get("cited_by_count") or 0), "results": back + fwd[:limit]}


def log_candidates(study_dir: Path, results: list[dict], channel: str, via: str, purpose: str,
                   query_id: str) -> int:
  """Every lead a discovery step returned goes into candidates.jsonl - fetched or not - so
  screening.py can audit what was left out. Returns how many new candidates were added."""
  from verify_citations import _canon  # local: heavy import
  path = Path(study_dir) / "candidates.jsonl"
  existing = _jsonl(path)
  seen = {_canon(c.get("url", "")) for c in existing}
  added = 0
  for r in results:
    url = r.get("fetch_url") or r.get("url")
    if not url or _canon(url) in seen:
      continue
    seen.add(_canon(url))
    rec = {"id": _next_id(existing, "L"), "ts": dt.datetime.now().isoformat(timespec="seconds"),
           "url": url, "title": r.get("title", ""), "doi": r.get("doi", ""), "year": r.get("year"),
           "suggested_tier": r.get("suggested_tier", ""), "channel": channel, "via": via,
           "purpose": purpose, "query_id": query_id}
    existing.append(rec)
    _append(path, rec)
    added += 1
  return added


def search_crossref(query: str, limit: int = 5, timeout: int = 12) -> list[dict[str, Any]]:
  """Searches CrossRef works API."""
  url = "https://api.crossref.org/works?" + urllib.parse.urlencode({
      "query": query,
      "rows": max(1, min(limit, 25)),
  })
  resp = requests.get(url, headers={"User-Agent": UA}, timeout=timeout)
  resp.raise_for_status()
  items = ((resp.json().get("message") or {}).get("items")) or []
  out: list[dict[str, Any]] = []
  for item in items:
    titles = item.get("title") or []
    title = (titles[0] if titles else "").strip()
    if not title:
      continue
    doi = _norm_doi(item.get("DOI") or "")
    containers = item.get("container-title") or []
    venue = (containers[0] if containers else "").strip()
    ctype = (item.get("type") or "").lower()
    is_peer = ctype in ("journal-article", "proceedings-article", "book-chapter") and bool(venue)
    year = None
    for date_key in ("published-print", "published-online", "issued", "created"):
      parts = ((item.get(date_key) or {}).get("date-parts") or [[]])[0]
      if parts:
        year = parts[0]
        break
    doi_url = f"https://doi.org/{doi}" if doi else (item.get("URL") or "")
    out.append({
        "registry": "crossref",
        "title": title,
        "year": year,
        "venue": venue or "CrossRef",
        "doi": doi,
        "citations": int(item.get("is-referenced-by-count") or 0),
        "suggested_tier": "T3" if is_peer else "T4",
        "url": doi_url,
        "fetch_url": item.get("URL") or doi_url,
        "oa_url": "",
        "snippet": "",
    })
  return out


def search_arxiv(query: str, limit: int = 5, timeout: int = 12) -> list[dict[str, Any]]:
  """Searches arXiv Atom API and constructs full-text HTML URLs for frictionless fetching."""
  url = "https://export.arxiv.org/api/query?" + urllib.parse.urlencode({
      "search_query": f"all:{query}",
      "start": 0,
      "max_results": max(1, min(limit, 25)),
  })
  resp = requests.get(url, headers={"User-Agent": UA}, timeout=timeout)
  resp.raise_for_status()
  root = ET.fromstring(resp.text)
  ns = {
      "atom": "http://www.w3.org/2005/Atom",
      "arxiv": "http://arxiv.org/schemas/atom",
  }
  out: list[dict[str, Any]] = []
  for entry in root.findall("atom:entry", ns):
    title = re.sub(r"\s+", " ", (entry.findtext("atom:title", default="", namespaces=ns) or "")).strip()
    id_url = (entry.findtext("atom:id", default="", namespaces=ns) or "").strip()
    if not title or not id_url:
      continue
    arx_id = id_url.rstrip("/").split("/abs/")[-1]
    published = entry.findtext("atom:published", default="", namespaces=ns) or ""
    year = int(published[:4]) if len(published) >= 4 and published[:4].isdigit() else None
    jref = (entry.findtext("arxiv:journal_ref", default="", namespaces=ns) or "").strip()
    doi = _norm_doi(entry.findtext("arxiv:doi", default="", namespaces=ns) or "")
    summary = re.sub(r"\s+", " ", (entry.findtext("atom:summary", default="", namespaces=ns) or "")).strip()
    words = summary.split()
    snippet = " ".join(words[:45]) + (" ..." if len(words) > 45 else "")
    html_url = f"https://arxiv.org/html/{arx_id}"
    abs_url = f"https://arxiv.org/abs/{arx_id}"
    out.append({
        "registry": "arxiv",
        "title": title,
        "year": year,
        "venue": jref if jref else f"arXiv:{arx_id}",
        "doi": doi,
        "citations": 0,
        "suggested_tier": "T3" if jref else "T4",
        "url": abs_url,
        "fetch_url": html_url,
        "oa_url": f"https://ar5iv.labs.arxiv.org/html/{arx_id}",
        "snippet": snippet,
    })
  return out


def search_europepmc(query: str, limit: int = 5, timeout: int = 12) -> list[dict[str, Any]]:
  """Searches EuropePMC REST API for biomedical, statistical, and interdisciplinary papers."""
  url = "https://www.ebi.ac.uk/europepmc/webservices/rest/search?" + urllib.parse.urlencode({
      "query": query,
      "format": "json",
      "pageSize": max(1, min(limit, 25)),
  })
  resp = requests.get(url, headers={"User-Agent": UA}, timeout=timeout)
  resp.raise_for_status()
  results = ((resp.json().get("resultList") or {}).get("result")) or []
  out: list[dict[str, Any]] = []
  for item in results:
    title = (item.get("title") or "").strip().rstrip(".")
    if not title:
      continue
    doi = _norm_doi(item.get("doi") or "")
    pmcid = (item.get("pmcid") or "").strip()
    pmid = (item.get("pmid") or "").strip()
    venue = (item.get("journalTitle") or item.get("bookOrReportDetails", {}).get("publisher") or "EuropePMC").strip()
    pub_type = (item.get("pubType") or "").lower()
    is_preprint = "preprint" in pub_type or item.get("source") == "PPR"
    pub_year = item.get("pubYear")
    year = int(pub_year) if str(pub_year).isdigit() else None
    if pmcid:
      fetch_url = f"https://europepmc.org/article/PMC/{pmcid}"
    elif pmid:
      fetch_url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
    elif doi:
      fetch_url = f"https://doi.org/{doi}"
    else:
      fetch_url = ""
    out.append({
        "registry": "europepmc",
        "title": title,
        "year": year,
        "venue": venue,
        "doi": doi,
        "citations": int(item.get("citedByCount") or 0),
        "suggested_tier": "T4" if is_preprint else "T3",
        "url": fetch_url,
        "fetch_url": fetch_url,
        "oa_url": f"https://europepmc.org/article/PMC/{pmcid}" if pmcid else "",
        "snippet": "",
    })
  return out


def search_semanticscholar(query: str, limit: int = 5, timeout: int = 10) -> list[dict[str, Any]]:
  """Searches Semantic Scholar Graph API for scholarly works with citation counts and TLDRs."""
  url = "https://api.semanticscholar.org/graph/v1/paper/search?" + urllib.parse.urlencode({
      "query": query,
      "limit": max(1, min(limit, 25)),
      "fields": "title,url,year,citationCount,influentialCitationCount,openAccessPdf,externalIds,abstract,venue,publicationTypes",
  })
  headers = {"User-Agent": UA}
  api_key = os.environ.get("S2_API_KEY") or os.environ.get("SEMANTIC_SCHOLAR_API_KEY")
  if api_key:
    headers["x-api-key"] = api_key
  try:
    resp = requests.get(url, headers=headers, timeout=timeout)
    if resp.status_code in (429, 403):
      return []  # Gracefully fall back if unauthenticated rate limit reached
    resp.raise_for_status()
    data = (resp.json() or {}).get("data") or []
  except Exception:
    return []

  out: list[dict[str, Any]] = []
  for item in data:
    title = (item.get("title") or "").strip().rstrip(".")
    if not title:
      continue
    ext_ids = item.get("externalIds") or {}
    doi = _norm_doi(ext_ids.get("DOI") or "")
    arx_id = ext_ids.get("ArXiv") or ""
    oa_pdf = (item.get("openAccessPdf") or {}).get("url") or ""
    venue = (item.get("venue") or "").strip()
    pub_types = [t.lower() for t in (item.get("publicationTypes") or [])]
    is_peer = "journalarticle" in pub_types or (bool(venue) and "arxiv" not in venue.lower())

    if arx_id:
      fetch_url = f"https://arxiv.org/html/{arx_id}"
    elif oa_pdf:
      fetch_url = oa_pdf
    elif doi:
      fetch_url = f"https://doi.org/{doi}"
    else:
      fetch_url = item.get("url") or ""

    abstract = item.get("abstract") or ""
    words = abstract.split()
    snippet = " ".join(words[:45]) + (" ..." if len(words) > 45 else "")
    out.append({
        "registry": "semanticscholar",
        "title": title,
        "year": item.get("year"),
        "venue": venue or "Semantic Scholar",
        "doi": doi,
        "citations": int(item.get("citationCount") or 0),
        "suggested_tier": "T3" if is_peer else "T4",
        "url": item.get("url") or fetch_url,
        "fetch_url": fetch_url,
        "oa_url": oa_pdf,
        "snippet": snippet,
    })
  return out


REGISTRY_FNS = {
    "openalex": search_openalex,
    "crossref": search_crossref,
    "arxiv": search_arxiv,
    "europepmc": search_europepmc,
    "semanticscholar": search_semanticscholar,
}


def discover_sources(
    query: str,
    sources: list[str] | tuple[str, ...] = ("openalex", "crossref", "arxiv"),
    limit: int = 8,
    timeout: int = 12,
) -> dict[str, Any]:
  """Queries multiple scholarly registries, deduplicates by DOI/title, and ranks leads."""
  per_reg = max(3, min(15, limit))
  raw_hits: list[dict[str, Any]] = []
  errors: dict[str, str] = {}

  for reg in sources:
    fn = REGISTRY_FNS.get(reg)
    if not fn:
      errors[reg] = f"unknown registry {reg!r}"
      continue
    try:
      raw_hits.extend(fn(query, limit=per_reg, timeout=timeout))
    except Exception as exc:
      errors[reg] = str(exc)

  # Deduplicate by DOI first, then normalized title; merge best metadata & full-text links
  merged: list[dict[str, Any]] = []
  by_doi: dict[str, dict[str, Any]] = {}
  by_title: dict[str, dict[str, Any]] = {}

  for hit in raw_hits:
    doi = hit.get("doi") or ""
    ntitle = _norm_title(hit.get("title", ""))
    existing = (by_doi.get(doi) if doi else None) or (by_title.get(ntitle) if ntitle else None)
    if existing:
      existing["citations"] = max(existing.get("citations", 0), hit.get("citations", 0))
      if hit.get("suggested_tier") == "T3":
        existing["suggested_tier"] = "T3"
      if not existing.get("snippet") and hit.get("snippet"):
        existing["snippet"] = hit["snippet"]
      # Prefer direct full-text HTML fetch URLs (arxiv/html or europepmc PMC) over bare DOI redirects
      if ("arxiv.org/html/" in hit.get("fetch_url", "") or "europepmc.org/article/PMC/" in hit.get("fetch_url", "")):
        existing["fetch_url"] = hit["fetch_url"]
      if hit["registry"] not in existing["registries"]:
        existing["registries"].append(hit["registry"])
      continue

    entry = dict(hit)
    entry["registries"] = [hit["registry"]]
    merged.append(entry)
    if doi:
      by_doi[doi] = entry
    if ntitle:
      by_title[ntitle] = entry

  # Rank: T3 peer-reviewed > T4 preprint, open full-text URL bonus, log1p(citations)
  def _rank_key(item: dict[str, Any]) -> float:
    tier_bonus = 2.0 if item.get("suggested_tier") == "T3" else 0.8
    oa_bonus = 0.8 if (item.get("oa_url") or "arxiv.org/html/" in item.get("fetch_url", "")) else 0.0
    cite_score = math.log1p(max(0, int(item.get("citations") or 0))) * 0.5
    return tier_bonus + oa_bonus + cite_score

  merged.sort(key=_rank_key, reverse=True)
  top = merged[:limit]
  return {
      "query": query,
      "sources_queried": list(sources),
      "total_unique_hits": len(merged),
      "results": top,
      "errors": errors,
  }


def log_discovery_search(study_dir: Path, purpose: str, discovery_res: dict[str, Any],
                         tool: str | None = None, channel: str = "scholarly",
                         query: str | None = None) -> dict[str, Any]:
  """Appends the search AND its full result set to research/<dir>/searches.jsonl, and every
  lead to candidates.jsonl (for coverage estimates and the screening audit)."""
  if not SQ_RE.match(purpose):
    raise ValueError(f"--purpose must be SQ<n> or K<n>, got {purpose!r}")
  path = Path(study_dir) / "searches.jsonl"
  results = discovery_res.get("results") or []
  urls = [r.get("fetch_url") or r.get("url") for r in results if (r.get("fetch_url") or r.get("url"))]
  t3_count = sum(1 for r in results if r.get("suggested_tier") == "T3")
  rec = {
      "id": _next_id(_jsonl(path), "Q"),
      "ts": dt.datetime.now().isoformat(timespec="seconds"),
      "purpose": purpose,
      "query": query or discovery_res["query"],
      "tool": tool or "discover.py:" + ",".join(discovery_res.get("sources_queried", [])),
      "channel": channel,
      "hits": discovery_res.get("total_unique_hits", len(results)),
      "opened": urls[:3],
      "results": urls,
      "note": f"discover.py returned {len(results)} leads ({t3_count} T3 peer-reviewed)",
  }
  _append(path, rec)
  rec["candidates_added"] = log_candidates(Path(study_dir), results, channel, rec["tool"], purpose,
                                           rec["id"])
  return rec


def _print_results(results: list[dict[str, Any]]) -> None:
  for i, r in enumerate(results, 1):
    yr = r.get("year") or "n.d."
    regs = "+".join(r.get("registries", [r["registry"]]))
    tag = f" {r['direction']}" if r.get("direction") else ""
    print(f"\n  {i}. [{r['suggested_tier']}{tag}] {r['title']} ({yr}) — {r['venue']}  "
          f"[cites={r['citations']}, via={regs}]")
    print(f"     fetch_url : {r['fetch_url']}")
    if r.get("url") and r["url"] != r["fetch_url"]:
      print(f"     canonical : {r['url']}")
    if r.get("oa_url") and r["oa_url"] not in (r["fetch_url"], r.get("url")):
      print(f"     alt_html  : {r['oa_url']}")
    if r.get("snippet"):
      print(f"     lead_note : {r['snippet']}")


def main(argv: list[str] | None = None) -> int:
  if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
  ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
  ap.add_argument("query", nargs="?", help="scholarly / technical search query")
  ap.add_argument("--snowball", metavar="SEED",
                  help="citation-graph expansion of one work: OpenAlex id (W...) or DOI (10....)")
  ap.add_argument("--direction", default="both", choices=("forward", "backward", "both"),
                  help="with --snowball: forward = works citing the seed, backward = its references")
  ap.add_argument("--sources", default="openalex,crossref,arxiv",
                  help=f"comma-separated registries from {','.join(ALL_REGISTRIES)}")
  ap.add_argument("--limit", type=int, default=8)
  ap.add_argument("--timeout", type=int, default=12)
  ap.add_argument("--dir", type=Path, help="research/<slug> folder: logs the search, its results and candidates")
  ap.add_argument("--purpose", default="", help="SQ<n> or K<n> (required when --dir is passed)")
  ap.add_argument("--json", action="store_true")
  args = ap.parse_args(argv)

  if bool(args.query) == bool(args.snowball):
    print('REFUSED: give either a query ("discover.py \\"<terms>\\" ...") or --snowball <W-id|DOI>, '
          'not both and not neither', file=sys.stderr)
    return 2
  if args.dir and not SQ_RE.match(args.purpose):
    print("REFUSED: --purpose (SQ<n> or K<n>) is required when --dir is specified", file=sys.stderr)
    return 1
  if args.dir and not (args.dir / "plan.md").exists():
    print(f"REFUSED: {args.dir} is not a study folder (no plan.md); create it with "
          f"evidence.py init <slug>", file=sys.stderr)
    return 1

  if args.snowball:
    try:
      res = snowball(args.snowball, args.direction, max(args.limit, 1), args.timeout)
    except (ValueError, RuntimeError) as e:
      print(f"ERROR: {e}", file=sys.stderr)
      return 1
    res["query"] = f"snowball:{args.direction}:{res['seed_id'] or args.snowball}"
    res["total_unique_hits"] = len(res["results"])
    logged = None
    if args.dir:
      logged = log_discovery_search(args.dir, args.purpose, res, tool=f"discover.py:snowball:{args.direction}",
                                    channel="citation", query=res["query"])
      res["logged_search_id"] = logged["id"]
    if args.json:
      print(json.dumps(res, ensure_ascii=False, indent=2))
      return 0
    print(f"[SNOWBALL] seed={res['seed_id']} \"{res['seed_title']}\"  direction={args.direction}  "
          f"references={res['references_total']}  cited_by={res['cited_by_total']}  "
          f"returned={len(res['results'])}")
    if logged:
      print(f"  Logged {logged['id']} [{args.purpose}] channel=citation; "
            f"{logged['candidates_added']} new candidate(s) in candidates.jsonl")
    _print_results(res["results"])
    return 0

  srcs = [s.strip().lower() for s in args.sources.split(",") if s.strip()]
  bad = [s for s in srcs if s not in ALL_REGISTRIES]
  if bad:
    print(f"REFUSED: unknown registry {', '.join(bad)}; choose from {','.join(ALL_REGISTRIES)}",
          file=sys.stderr)
    return 2
  res = discover_sources(args.query, sources=srcs, limit=args.limit, timeout=args.timeout)
  logged = None
  if args.dir:
    logged = log_discovery_search(args.dir, args.purpose, res)
    res["logged_search_id"] = logged["id"]

  if args.json:
    print(json.dumps(res, ensure_ascii=False, indent=2))
    return 0

  print(f"[DISCOVER] query={args.query!r}  registries={','.join(srcs)}  "
        f"unique_hits={res['total_unique_hits']}")
  if logged:
    print(f"  Logged verified search -> {logged['id']} [{args.purpose}] in {args.dir / 'searches.jsonl'}; "
          f"{logged['candidates_added']} new candidate(s) in candidates.jsonl")
  for reg, err in res["errors"].items():
    print(f"  WARN  {reg}: {err}")
  _print_results(res["results"])
  return 0


if __name__ == "__main__":
  sys.exit(main())
