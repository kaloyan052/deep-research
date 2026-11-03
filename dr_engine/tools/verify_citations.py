"""Checks that cited sources exist and actually say what the evidence log claims.

The evidence log is JSONL, one record per piece of evidence:

  {"id": "E1", "url": "https://...", "quote": "verbatim sentence from the page",
   "claim": "what the report uses it for", "accessed": "2026-10-28"}

For each record the page is fetched (HTML, plain text or PDF) and the quote is
searched for after normalising whitespace, quotes, dashes and case:

  VERIFIED   quote found verbatim (normalised)
  PARTIAL    >= 80% of the quote's words found in order in one window
  NOT_FOUND  page fetched but the quote is not there -> likely fabricated or
             paraphrased; fix the quote or drop the claim
  DEAD       HTTP error / network failure
  BLOCKED    page fetched but empty, bot wall or unsupported type
             (re-try with --jina, or verify manually and note it)

With --report, every URL in the report that is missing from the evidence log is
listed as UNLOGGED, and with no --evidence the report's URLs are only checked
for liveness.

Usage:
  python dr_engine/tools/verify_citations.py --evidence research/x/evidence.jsonl
  python dr_engine/tools/verify_citations.py --evidence ev.jsonl --report report.md
  python dr_engine/tools/verify_citations.py --report report.md        # links only
  ... [--jina] [--workers 6] [--timeout 20] [--json]

--jina retries BLOCKED/DEAD pages through https://r.jina.ai/<url> (a third-party
reader service: only the URL is sent). Exit code 1 if anything is NOT_FOUND,
DEAD or UNLOGGED.
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import difflib
import html
import io
import json
import re
import sys
import unicodedata
from dataclasses import asdict, dataclass
from pathlib import Path

import requests

USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/130.0 Safari/537.36 dr-engine-verifier")
URL_RE = re.compile(r"https?://[^\s<>\)\]\"'`|]+")
BOT_WALL_RE = re.compile(
    r"(just a moment|checking your browser|enable javascript|access denied|"
    r"attention required|verify you are human|captcha)", re.I)
PARTIAL_THRESHOLD = 0.8


@dataclass
class Check:
  id: str
  url: str
  status: str
  detail: str = ""
  match: float = 0.0
  via: str = "direct"


def normalise(text: str) -> str:
  text = unicodedata.normalize("NFKC", html.unescape(text))
  text = (text.replace("’", "'").replace("‘", "'")
          .replace("“", '"').replace("”", '"')
          .replace("–", "-").replace("—", "-").replace(" ", " "))
  text = re.sub(r"[*_`#>|]", " ", text)  # markdown noise from reader proxies
  return re.sub(r"\s+", " ", text).strip().lower()


def _words(text: str) -> list[str]:
  return re.findall(r"[\w$€%.]+", text)


NEGATION_TOKENS = {
    "not", "never", "no", "nor",
    "prohibited", "prohibit", "prohibits", "prohibiting",
    "banned", "ban", "bans", "banning",
    "neither", "except", "excluding",
    "не", "никога", "нито",
    "забранено", "забранена", "забранени", "забранява", "забраняват",
    "освен",
}


def match_score(quote: str, page: str) -> float:
  """1.0 if the normalised quote is a substring of the page, else the best
  share of quote words matched in order inside one window of the page."""
  q, p = normalise(quote), normalise(page)
  if not q:
    return 0.0
  if q in p:
    return 1.0
  # "a ... b": every fragment verbatim, in order, gap <= 250 chars, no introduced negations.
  frags = [f.strip(" .,;") for f in re.split(r"\[\s*(?:\.\.\.|…)\s*\]|\.\.\.|…", q)]
  frags = [f for f in frags if f]
  if len(frags) == 1:
    if frags[0] in p:
      return 1.0
  elif len(frags) > 1:
    quote_words = set(re.findall(r"\w+", q.lower()))
    start_pos = 0
    while True:
      idx = p.find(frags[0], start_pos)
      if idx < 0:
        break
      curr_end = idx + len(frags[0])
      matched_all = True
      for next_frag in frags[1:]:
        search_window = p[curr_end : curr_end + 250 + len(next_frag)]
        sub_start = 0
        found_valid = False
        while True:
          rel_idx = search_window.find(next_frag, sub_start)
          if rel_idx < 0 or rel_idx > 250:
            break
          gap = search_window[:rel_idx]
          gap_words = set(re.findall(r"\w+", gap.lower()))
          if not ((gap_words & NEGATION_TOKENS) - quote_words):
            curr_end = curr_end + rel_idx + len(next_frag)
            found_valid = True
            break
          sub_start = rel_idx + 1
        if not found_valid:
          matched_all = False
          break
      if matched_all:
        return 1.0
      start_pos = idx + 1
  qw, pw = _words(q), _words(p)
  if not qw or not pw:
    return 0.0
  anchors = set(qw[:3])
  starts = [i for i, w in enumerate(pw) if w in anchors][:3000]
  window = int(len(qw) * 1.3) + 3
  best = 0
  for i in starts:
    sm = difflib.SequenceMatcher(None, qw, pw[i:i + window], autojunk=False)
    best = max(best, sum(b.size for b in sm.get_matching_blocks()))
    if best == len(qw):
      break
  return min(best / len(qw), 0.99)  # non-verbatim is never VERIFIED


def html_to_text(raw: str) -> str:
  try:
    from bs4 import BeautifulSoup
  except ImportError:
    return re.sub(r"<[^>]+>", " ", raw)
  soup = BeautifulSoup(raw, "html.parser")
  for tag in soup(["script", "style", "noscript", "svg"]):
    tag.decompose()
  return soup.get_text(" ")


def pdf_to_text(data: bytes) -> str | None:
  try:
    import fitz  # PyMuPDF
  except ImportError:
    fitz = None
  if fitz is not None:
    with fitz.open(stream=data, filetype="pdf") as doc:
      return " ".join(page.get_text("text") for page in doc)
  try:
    from pypdf import PdfReader
  except ImportError:
    return None
  return " ".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(data)).pages)


def fetch_text(url: str, timeout: float) -> tuple[str, str | None]:
  """Returns (status, text). status in {ok, dead, blocked}."""
  try:
    r = requests.get(url, headers={"User-Agent": USER_AGENT,
                                   "Accept-Language": "en,bg;q=0.8"},
                     timeout=timeout, allow_redirects=True)
  except requests.RequestException as e:
    return "dead", f"{type(e).__name__}: {e}"[:200]
  if r.status_code in (401, 403, 429, 503):
    return "blocked", f"HTTP {r.status_code}"
  if r.status_code >= 400:
    return "dead", f"HTTP {r.status_code}"
  ctype = r.headers.get("Content-Type", "").lower()
  if "pdf" in ctype or url.lower().split("?")[0].endswith(".pdf"):
    text = pdf_to_text(r.content)
    if text is None:
      return "blocked", "PDF (install PyMuPDF or pypdf, or use --jina)"
  elif "html" in ctype or "<html" in r.text[:2000].lower():
    text = html_to_text(r.text)
  elif ctype.startswith("text/") or "json" in ctype or "xml" in ctype:
    text = r.text
  else:
    return "blocked", f"unsupported content type {ctype or '?'}"
  if len(text.strip()) < 200 or (len(text) < 5000 and BOT_WALL_RE.search(text)):
    return "blocked", "empty page or bot wall"
  return "ok", text


def fetch_jina(url: str, timeout: float) -> tuple[str, str | None]:
  try:
    r = requests.get("https://r.jina.ai/" + url, timeout=timeout * 2,
                     headers={"User-Agent": USER_AGENT})
  except requests.RequestException as e:
    return "dead", f"jina: {type(e).__name__}"
  if r.status_code >= 400 or len(r.text.strip()) < 200:
    return "blocked", f"jina: HTTP {r.status_code}"
  return "ok", r.text


class PageCache:
  def __init__(self, timeout: float, jina: bool):
    self.timeout, self.jina = timeout, jina
    self._cache: dict[str, tuple[str, str | None, str]] = {}

  def get(self, url: str) -> tuple[str, str | None, str]:
    if url not in self._cache:
      status, text = fetch_text(url, self.timeout)
      via = "direct"
      if status != "ok" and self.jina:
        j_status, j_text = fetch_jina(url, self.timeout)
        if j_status == "ok":
          status, text, via = j_status, j_text, "jina"
      self._cache[url] = (status, text, via)
    return self._cache[url]


def check_record(rec: dict, cache: PageCache) -> Check:
  rid = str(rec.get("id", "?"))
  url = (rec.get("url") or "").strip()
  quote = (rec.get("quote") or "").strip()
  if not url.startswith(("http://", "https://")):
    return Check(rid, url, "NOT_FOUND", "record has no http(s) URL")
  status, text, via = cache.get(url)
  if status == "dead":
    return Check(rid, url, "DEAD", text or "", via=via)
  if status == "blocked":
    return Check(rid, url, "BLOCKED", text or "", via=via)
  if not quote:
    return Check(rid, url, "PARTIAL", "page is live but record has no quote", via=via)
  score = match_score(quote, text or "")
  if score >= 1.0:
    return Check(rid, url, "VERIFIED", match=1.0, via=via)
  if score >= PARTIAL_THRESHOLD:
    return Check(rid, url, "PARTIAL", "quote is close but not verbatim",
                 round(score, 2), via)
  return Check(rid, url, "NOT_FOUND", f"best word match {score:.0%}",
               round(score, 2), via)


def load_evidence(path: Path) -> list[dict]:
  records = []
  for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
    line = line.strip()
    if not line or line.startswith("//"):
      continue
    try:
      records.append(json.loads(line))
    except json.JSONDecodeError as e:
      raise SystemExit(f"{path}:{n}: invalid JSON ({e})")
  return records


def report_urls(path: Path) -> list[str]:
  text = path.read_text(encoding="utf-8", errors="replace")
  seen, out = set(), []
  for u in URL_RE.findall(text):
    u = u.rstrip(".,;:")
    if u not in seen:
      seen.add(u)
      out.append(u)
  return out


def _canon(url: str) -> str:
  url = url.split("#")[0].lower()
  return re.sub(r"^https?://(www\.)?", "", url).rstrip("/")


def main(argv: list[str] | None = None) -> int:
  if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
  ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
  ap.add_argument("--evidence", type=Path)
  ap.add_argument("--report", type=Path)
  ap.add_argument("--jina", action="store_true")
  ap.add_argument("--workers", type=int, default=6)
  ap.add_argument("--timeout", type=float, default=20)
  ap.add_argument("--json", action="store_true")
  args = ap.parse_args(argv)
  if not args.evidence and not args.report:
    ap.error("give --evidence and/or --report")

  records = load_evidence(args.evidence) if args.evidence else []
  unlogged: list[str] = []
  if args.report:
    urls = report_urls(args.report)
    if records:
      logged = {_canon(r.get("url", "")) for r in records}
      unlogged = [u for u in urls if _canon(u) not in logged]
    else:
      records = [{"id": f"U{i}", "url": u, "quote": ""}
                 for i, u in enumerate(urls, 1)]

  cache = PageCache(args.timeout, args.jina)
  # Fetch each distinct URL once, in parallel, then score records.
  with cf.ThreadPoolExecutor(max_workers=max(1, args.workers)) as ex:
    list(ex.map(cache.get, sorted({r.get("url", "") for r in records
                                   if str(r.get("url", "")).startswith("http")})))
  checks = [check_record(r, cache) for r in records]
  if args.report and not args.evidence:
    for c in checks:  # liveness-only mode
      if c.status == "PARTIAL":
        c.status, c.detail = "LIVE", ""

  counts: dict[str, int] = {}
  for c in checks:
    counts[c.status] = counts.get(c.status, 0) + 1
  if unlogged:
    counts["UNLOGGED"] = len(unlogged)

  if args.json:
    print(json.dumps({"counts": counts, "checks": [asdict(c) for c in checks],
                      "unlogged": unlogged}, ensure_ascii=False, indent=2))
  else:
    order = {"NOT_FOUND": 0, "DEAD": 1, "BLOCKED": 2, "PARTIAL": 3,
             "LIVE": 4, "VERIFIED": 5}
    for c in sorted(checks, key=lambda c: order.get(c.status, 9)):
      extra = f" ({c.detail})" if c.detail else ""
      via = " [jina]" if c.via == "jina" else ""
      print(f"{c.status:<9} {c.id:<6} {c.url}{via}{extra}")
    for u in unlogged:
      print(f"UNLOGGED  -      {u} (cited in report, absent from evidence log)")
    print("\nSummary: " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))
  bad = sum(counts.get(k, 0) for k in ("NOT_FOUND", "DEAD", "UNLOGGED"))
  return 1 if bad else 0


if __name__ == "__main__":
  sys.exit(main())
