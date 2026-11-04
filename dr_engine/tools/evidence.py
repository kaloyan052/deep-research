"""Evidence pipeline: the only sanctioned way to get a fact into a report.

    page --fetch--> sources/S###.txt (snapshot + sha256)  --add--> evidence.jsonl E###
                                                                     |
    report.md cites [E###] <------------------------------------------+

`add` refuses a quote that is not present verbatim in a snapshot fetched by
`fetch`, so a search-result snippet or a remembered "fact" cannot become
evidence. `gate.py` later re-hashes the snapshots, re-checks every quote and
checks that the numbers in each report sentence appear in the quotes it cites.

Commands (run from the project root):
  init        python dr_engine/tools/evidence.py init <slug>
  fetch       python dr_engine/tools/evidence.py fetch  --dir D <url> [<url> ...]
  add         python dr_engine/tools/evidence.py add    --dir D --source S003 --sq K1 \
                  --tier T1 --kind de_jure --stance contradicts \
                  --quote "verbatim text" --claim "paraphrase" [--published YYYY-MM-DD]
                  (empirical: --sample-period of the number's own table; refused without it
                  when the page names a period near the quote)
  import      python dr_engine/tools/evidence.py import --dir D --url <url> --file captured.txt
              (page text copied from a browser tool when `fetch` is blocked; marked manual)
  log-search  python dr_engine/tools/evidence.py log-search --dir D --purpose K1 \
                  --query "firm X payout denied" [--opened S004,S005] [--note "..."]
  sources     python dr_engine/tools/evidence.py sources --dir D [--report D/report.md]
  show        python dr_engine/tools/evidence.py show --dir D [--source S003] [--grep text]
"""

from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from verify_citations import (USER_AGENT, BOT_WALL_RE, _canon, fetch_jina, html_to_text,  # noqa: E402
                              match_score, normalise, pdf_to_text)
from traps import check_source_tier_inflation  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
TEMPLATES = ROOT / ".agents" / "skills" / "deep-research" / "templates"
PROTOCOL = "4.1"  # written to study.json by init; gate.py enforces the rules of this version
TIERS = ("T1", "T2", "T3", "T4", "T5")
KINDS = ("de_jure", "de_facto", "empirical", "context", "review_pain")
STANCES = ("supports", "contradicts", "context")
# Who is speaking (conflict-of-interest axis in claims.py): disinterested vs with a stake.
INTERESTS = ("academic", "regulator", "independent", "issuer", "affiliate", "vendor")
# What the evidence was measured on (sample axis in claims.py).
SAMPLE_TYPES = ("in_sample", "out_of_sample", "post_publication", "live")
# Discovery channels (corpus.py stats estimates coverage from their overlap).
SEARCH_CHANNELS = ("web", "registry", "scholarly", "citation", "other")
SQ_RE = re.compile(r"^(SQ|K)\d+$")
MIN_SNAPSHOT_CHARS = 300


def today() -> str:
  return dt.date.today().isoformat()


def _jsonl(path: Path) -> list[dict]:
  if not path.exists():
    return []
  return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines()
          if l.strip() and not l.lstrip().startswith("//")]


def _append(path: Path, rec: dict) -> None:
  with path.open("a", encoding="utf-8") as f:
    f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def _log_failed(src_dir: Path, url: str, error: str) -> None:
  """Failed fetches are kept (sources/failed.jsonl) so the screening audit knows a lead was
  tried and why it is unreachable."""
  _append(src_dir / "failed.jsonl", {"url": url, "error": str(error)[:200],
                                     "ts": dt.datetime.now().isoformat(timespec="seconds")})


def load_evidence(d: Path) -> list[dict]:
  """Active evidence records. Retracted ones stay in evidence.jsonl (audit trail, ids are never
  reused) but no tool counts or accepts them."""
  return [r for r in _jsonl(Path(d) / "evidence.jsonl") if not r.get("retracted")]


def load_claims(d: Path) -> list[dict]:
  """Claims whose cited evidence is all still active: a claim resting on a retracted record
  drops out of conflicts, tables and saturation until it is re-added with the corrected E###."""
  active = {r["id"] for r in load_evidence(d)}
  return [c for c in _jsonl(Path(d) / "claims.jsonl") if c.get("eids") and set(c["eids"]) <= active]


def _next_id(records: list[dict], prefix: str) -> str:
  nums = [int(r["id"][len(prefix):]) for r in records
          if str(r.get("id", "")).startswith(prefix) and r["id"][len(prefix):].isdigit()]
  return f"{prefix}{(max(nums) + 1) if nums else 1:03d}"


def sha256_text(text: str) -> str:
  return hashlib.sha256(text.encode("utf-8")).hexdigest()


def study_dir_error(d: Path) -> str:
  """'' when `d` is a study folder; otherwise the exact message a model needs to recover.
  Every tool checks this first, so a wrong --dir never creates junk folders or tracebacks."""
  d = Path(d)
  known = sorted(p.name for p in (ROOT / "research").glob("*") if (p / "plan.md").exists())[-5:]
  hint = f" Recent studies: {', '.join(known)}." if known else ""
  if not d.exists():
    return (f"ERROR: --dir {d} does not exist. Use the folder printed by `evidence.py init <slug>` "
            f"(research/<YYYY-MM-DD>-<slug>).{hint}")
  if not (d / "plan.md").exists():
    return (f"ERROR: {d} is not a study folder (no plan.md). Use the folder printed by "
            f"`evidence.py init <slug>`.{hint}")
  return ""


# --------------------------------------------------------------------- fetch
def _try_jina(url: str, timeout: float, fallback_out: dict) -> dict:
  j_status, j_text = fetch_jina(url, timeout)
  if j_status == "ok" and j_text:
    text = j_text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text).strip()
    if len(text) >= MIN_SNAPSHOT_CHARS and not (len(text) < 5000 and BOT_WALL_RE.search(text)):
      return {"ok": True, "text": text, "final_url": url,
              "http_status": 200, "content_type": "text/markdown",
              "error": "", "via": "jina"}
  return fallback_out


def _html_metadata(raw: str, url: str) -> dict:
  """Title / publication date / author from the page (trafilatura, if installed). Metadata only:
  trafilatura's main-text extraction dropped 28 of 88 previously cited quotes (fee tables, rule
  lists) in a check on 2026-11-04, so the snapshot text itself stays the full page."""
  try:
    from trafilatura import extract_metadata
  except ImportError:
    return {}
  try:
    m = extract_metadata(raw, default_url=url)
  except Exception:  # metadata is a convenience; never fail a fetch over it
    return {}
  if m is None:
    return {}
  # page_date: the date in the page's metadata - often "last updated", not first published
  meta = {"title": m.title or "", "page_date": m.date or "", "author": m.author or "",
          "publisher": m.sitename or ""}
  return {k: v for k, v in meta.items() if v}


def fetch_page(url: str, timeout: float = 25, jina_fallback: bool = False) -> dict:
  """Fetches a page and returns {ok, text, final_url, http_status, content_type, error, via}."""
  out = {"ok": False, "text": "", "final_url": url, "http_status": None,
         "content_type": "", "error": "", "via": "direct"}
  try:
    r = requests.get(url, headers={"User-Agent": USER_AGENT,
                                   "Accept-Language": "en,bg;q=0.8"},
                     timeout=timeout, allow_redirects=True)
  except requests.RequestException as e:
    out["error"] = f"{type(e).__name__}: {e}"[:200]
    if jina_fallback:
      return _try_jina(url, timeout, out)
    return out
  out.update(final_url=r.url, http_status=r.status_code,
             content_type=r.headers.get("Content-Type", "").lower())
  if r.status_code in (401, 403, 429, 503) and jina_fallback:
    out["error"] = f"HTTP {r.status_code}"
    return _try_jina(url, timeout, out)
  if r.status_code >= 400:
    out["error"] = f"HTTP {r.status_code}"
    return out
  ctype = out["content_type"]
  if "pdf" in ctype or r.url.lower().split("?")[0].endswith(".pdf"):
    try:  # prose + structured tables (parse_pdf.py); plain text extraction as a fallback
      import parse_pdf
      text, info = parse_pdf.pdf_snapshot(r.content)
      out.update(parser=info["parser"], tables=info["tables"])
    except ValueError as e:  # scanned PDF without a text layer
      out["error"] = f"PDF: {e}"
      return out
    except Exception:
      text = pdf_to_text(r.content)
    if text is None:
      out["error"] = "PDF: install pdfplumber or pypdf, or open it in a browser tool"
      if jina_fallback:
        return _try_jina(url, timeout, out)
      return out
  elif "html" in ctype or "<html" in r.text[:2000].lower():
    text = html_to_text(r.text)
    out.update(_html_metadata(r.text, r.url))
  elif ctype.startswith("text/") or "json" in ctype or "xml" in ctype:
    text = r.text
  else:
    out["error"] = f"unsupported content type {ctype or '?'}"
    return out
  text = text.replace("\r\n", "\n").replace("\r", "\n")
  text = re.sub(r"[ \t]+", " ", text)
  text = re.sub(r"\n\s*\n+", "\n\n", text).strip()
  if len(text) < MIN_SNAPSHOT_CHARS or (len(text) < 5000 and BOT_WALL_RE.search(text)):
    out["error"] = "empty page or bot wall (JS-rendered?)"
    out["text"] = text
    if jina_fallback:
      return _try_jina(url, timeout, out)
    return out
  out.update(ok=True, text=text)
  return out


def cmd_fetch(args) -> int:
  d = Path(args.dir)
  src_dir = d / "sources"
  src_dir.mkdir(parents=True, exist_ok=True)
  index_path = src_dir / "index.jsonl"
  index = _jsonl(index_path)
  by_url = {_canon(r["url"]): r for r in index}
  rc = 0

  to_fetch = []
  for url in args.urls:
    if _canon(url) in by_url and not args.refresh:
      r = by_url[_canon(url)]
      print(f"{r['id']}  already fetched  {url}  ({r['chars']} chars)")
    else:
      to_fetch.append(url)

  if not to_fetch:
    return 0

  if len(to_fetch) == 1:
    url = to_fetch[0]
    page = fetch_page(url, args.timeout, jina_fallback=args.jina)
    if not page["ok"]:
      _log_failed(src_dir, url, page["error"])
      print(f"FAILED  {url}  ({page['error']}). Not a usable source: try another URL, an "
            f"archived copy (web.archive.org), or open it in a browser tool and save the text with "
            f"evidence.py import --dir <dir> --url <url> --file page.txt. Do NOT cite it from a "
            f"search snippet.")
      return 1
    sid = _next_id(index, "S")
    with open(src_dir / f"{sid}.txt", "w", encoding="utf-8", newline="\n") as f:
      f.write(page["text"])
    via = page.get("via", "direct")
    rec = {"id": sid, "url": url, "final_url": page["final_url"],
           "http_status": page["http_status"], "content_type": page["content_type"],
           "via": via, **{k: page[k] for k in ("parser", "tables", "title", "page_date", "author", "publisher") if k in page},
           "fetched_at": dt.datetime.now().isoformat(timespec="seconds"),
           "chars": len(page["text"]), "sha256": sha256_text(page["text"])}
    _append(index_path, rec)
    via_str = f" (via {via})" if via != "direct" else ""
    print(f"{sid}  fetched{via_str}  {url}  ({rec['chars']} chars) -> {src_dir / (sid + '.txt')}")
    return 0

  workers = min(10, len(to_fetch))
  with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
    futures = {executor.submit(fetch_page, u, args.timeout, jina_fallback=args.jina): u for u in to_fetch}
    for fut in concurrent.futures.as_completed(futures):
      u = futures[fut]
      try:
        page = fut.result()
      except Exception as e:
        page = {"ok": False, "error": str(e)}
      if not page.get("ok"):
        rc = 1
        _log_failed(src_dir, u, page.get("error", "error"))
        print(f"FAILED  {u}  ({page.get('error', 'error')})")
        continue
      sid = _next_id(index, "S")
      with open(src_dir / f"{sid}.txt", "w", encoding="utf-8", newline="\n") as f:
        f.write(page["text"])
      via = page.get("via", "direct")
      rec = {"id": sid, "url": u, "final_url": page.get("final_url", u),
             "http_status": page.get("http_status"), "content_type": page.get("content_type", ""),
             "via": via, **{k: page[k] for k in ("parser", "tables", "title", "page_date", "author", "publisher") if k in page},
             "fetched_at": dt.datetime.now().isoformat(timespec="seconds"),
             "chars": len(page["text"]), "sha256": sha256_text(page["text"])}
      _append(index_path, rec)
      index.append(rec)
      by_url[_canon(u)] = rec
      via_str = f" (via {via})" if via != "direct" else ""
      print(f"{sid}  fetched{via_str}  {u}  ({rec['chars']} chars) -> {src_dir / (sid + '.txt')}")

  return rc


def cmd_import(args) -> int:
  """Registers text captured from a browser tool for a page `fetch` cannot read
  (JS-rendered, bot wall). Marked manual: gate.py warns, confidence caps at Medium."""
  d = Path(args.dir)
  src_dir = d / "sources"
  src_dir.mkdir(parents=True, exist_ok=True)
  index_path = src_dir / "index.jsonl"
  index = _jsonl(index_path)
  if args.file == "-":
    text = sys.stdin.read()
  else:
    text = Path(args.file).read_text(encoding="utf-8", errors="replace")
  text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
  if len(text) < MIN_SNAPSHOT_CHARS:
    print(f"REFUSED: capture has {len(text)} chars; paste the full page text, not a snippet")
    return 1
  sid = _next_id(index, "S")
  with open(src_dir / f"{sid}.txt", "w", encoding="utf-8", newline="\n") as f:
    f.write(text)
  rec = {"id": sid, "url": args.url, "final_url": args.url, "http_status": None,
         "content_type": "manual-capture", "via": "manual",
         "fetched_at": dt.datetime.now().isoformat(timespec="seconds"),
         "chars": len(text), "sha256": sha256_text(text)}
  _append(index_path, rec)
  print(f"{sid}  imported (manual)  {args.url}  ({len(text)} chars)")
  return 0


# ------------------------------------------------------- quote context & periods
_MON = r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+"
_YM = rf"(?:{_MON})?(?:19|20)\d{{2}}(?:[./:-](?:0?[1-9]|1[0-2]|q[1-4])(?:[./-]\d{{1,2}})?)?"
PERIOD_RE = re.compile(rf"\b({_YM})\s*(?:-|–|—|to|through|until|and|до|и)\s*({_YM})\b", re.I)
SINCE_RE = re.compile(rf"\b(since|from|starting in|beginning in|от|след|от началото на)\s+({_YM})\b", re.I)
YEAR4_RE = re.compile(r"\b(?:19|20)\d{2}\b")
COPYRIGHT_RE = re.compile(r"©|\(c\)|copyright|авторск", re.I)
PERIOD_BEFORE, PERIOD_AFTER = 1500, 500  # table headers sit above the row a number comes from


def quote_span(quote: str, text: str) -> tuple[int, int] | None:
  """(start, end) of a verified quote in the ORIGINAL snapshot: word by word, any whitespace or
  punctuation between words, case-insensitive. The longest '...'-fragment is the anchor; the
  others are looked for next to it."""
  frags = [w for w in (re.findall(r"\w+", f) for f in re.split(r"\.\.\.|…", quote)) if w]
  if not frags:
    return None
  pats = [re.compile(r"\W+".join(map(re.escape, w)), re.I) for w in frags]
  k = max(range(len(frags)), key=lambda i: len(frags[i]))
  m = pats[k].search(text)
  if not m:
    return None
  start, end = m.start(), m.end()
  for pat in pats[k + 1:]:
    n = pat.search(text, end)
    if n and n.start() - end < 5000:
      end = n.end()
  for pat in reversed(pats[:k]):
    found = list(pat.finditer(text, max(0, start - 5000), start))
    if found:
      start = found[-1].start()
  # punctuation the word match leaves out: "$400,000" -> "$", "4.2%" -> "%"
  lead = re.match(r"\W*", quote).group().strip()
  trail = re.search(r"\W*$", quote).group().strip()
  if lead and text[max(0, start - len(lead)):start] == lead:
    start -= len(lead)
  if trail and text[end:end + len(trail)] == trail:
    end += len(trail)
  return start, end


def _flat(s: str) -> str:
  return re.sub(r"\s+", " ", s)


def periods_near(text: str, span: tuple[int, int] | None,
                 before: int = PERIOD_BEFORE, after: int = PERIOD_AFTER) -> list[str]:
  """Year ranges ('2004.1-2020.12', 'January 2004 to 2020') and open starts ('since 1993') named
  near the quote, nearest first, each tagged (above) / (below) / (in quote). A number belongs to
  the period of its own table or paragraph, which is often not the paper's headline period."""
  if not span:
    return []
  lo, hi = max(0, span[0] - before), span[1] + after
  window = text[lo:hi]
  s0, e0 = span[0] - lo, span[1] - lo

  def tagged(m, label: str) -> tuple[float, str]:
    where = "in quote" if m.start() < e0 and m.end() > s0 else ("above" if m.end() <= s0 else "below")
    dist = 0 if where == "in quote" else (s0 - m.end() if where == "above" else m.start() - e0)
    return dist, f"{label} ({where})"

  found, ranges = [], []
  for m in PERIOD_RE.finditer(window):
    ranges.append((m.start(), m.end()))
    if COPYRIGHT_RE.search(window[max(0, m.start() - 20):m.start()]):
      continue  # "© 2010-2025 Firm" in a footer is not a sample period
    found.append(tagged(m, f"{_flat(m.group(1))}-{_flat(m.group(2))}"))
  for m in SINCE_RE.finditer(window):
    if not any(m.start() < e and m.end() > s for s, e in ranges):  # 'from 2004 to 2020' is a range
      found.append(tagged(m, f"{m.group(1).lower()} {_flat(m.group(2))}"))
  out = []
  for _, s in sorted(found):
    if s not in out:
      out.append(s)
  return out[:6]


def _year_span(s: str) -> tuple[int, int] | None:
  ys = [int(y) for y in YEAR4_RE.findall(s or "")]
  return (min(ys), max(ys)) if ys else None


def context_excerpt(text: str, span: tuple[int, int] | None, width: int = 400) -> str:
  """The passage around a quote, the quote marked with ⟪ ⟫, whitespace collapsed."""
  if not span:
    return ""
  s, e = span
  lo, hi = max(0, s - width), min(len(text), e + width)
  return (("..." if lo else "") + _flat(text[lo:s]) + "⟪" + _flat(text[s:e]) + "⟫"
          + _flat(text[e:hi]) + ("..." if hi < len(text) else ""))


# ----------------------------------------------------------------------- add
def _nearest(quote: str, text: str, width: int = 240) -> str:
  q, t = normalise(quote), normalise(text)
  words = [w for w in re.findall(r"[\w$€%.]+", q) if len(w) > 3][:6]
  best_pos, best_hits = -1, 0
  for w in words:
    for m in re.finditer(re.escape(w), t):
      window = t[max(0, m.start() - width // 2): m.start() + width]
      hits = sum(1 for x in words if x in window)
      if hits > best_hits:
        best_pos, best_hits = m.start(), hits
  if best_pos < 0:
    return "(no similar passage found — the page may not say this at all)"
  return "..." + t[max(0, best_pos - width // 2): best_pos + width] + "..."


def cmd_add(args) -> int:
  d = Path(args.dir)
  index = {r["id"]: r for r in _jsonl(d / "sources" / "index.jsonl")}
  src = index.get(args.source)
  if not src:
    print(f"REFUSED: unknown source {args.source}. Fetch the page first: "
          f"evidence.py fetch --dir {d} <url>")
    return 1
  snap = (d / "sources" / f"{args.source}.txt").read_text(encoding="utf-8")
  if sha256_text(snap) != src["sha256"]:
    print(f"REFUSED: snapshot {args.source}.txt was modified after fetching. Re-fetch with --refresh.")
    return 1
  if not SQ_RE.match(args.sq):
    print("REFUSED: --sq must be SQ<n> (sub-question) or K<n> (kill hypothesis)")
    return 1
  inflation_err = check_source_tier_inflation(src["url"], args.tier, publisher=args.publisher or src.get("publisher", ""))
  if inflation_err:
    print(f"REFUSED: {inflation_err}")
    return 1
  score = match_score(args.quote, snap)
  if score < 1.0:
    print(f"REFUSED: quote not found verbatim in {args.source} (best match {score:.0%}).\n"
          f"Nearest passage in the snapshot:\n  {_nearest(args.quote, snap)}\n"
          f"Copy the exact words (join fragments with '...'), or drop the claim.")
    return 1
  periods = periods_near(snap, quote_span(args.quote, snap))
  given = (args.sample_period or "").strip()
  if args.kind == "empirical" and periods and not given:
    print(f"REFUSED: an empirical number belongs to a period, and {args.source} names "
          f"{', '.join(periods)} near this quote (nearest first). Add --sample-period with the "
          f"period of the exact table or paragraph the number comes from (not the paper's headline "
          f"period), or --sample-period unknown if the page does not say.")
    return 1
  if given and periods and _year_span(given) and _year_span(given) not in {_year_span(x) for x in periods}:
    print(f"NOTE: --sample-period {given} is not among the periods named near the quote "
          f"({', '.join(periods)}). Fine if the period is defined elsewhere on the page; otherwise "
          f"retract and re-add with the period of the table the number comes from.")
  evid_path = d / "evidence.jsonl"
  records = _jsonl(evid_path)
  q_norm = normalise(args.quote)
  for existing in (r for r in records if not r.get("retracted")):
    if existing.get("source") == args.source and normalise(existing.get("quote", "")) == q_norm:
      stances = {existing.get("stance"), args.stance}
      if "supports" in stances and "contradicts" in stances:
        print(f"REFUSED: exact duplicate quote on {args.source} already logged as {existing['id']} "
              f"with opposite stance ({existing.get('stance')}).")
        return 1
      if existing.get("sq") == args.sq and existing.get("stance") == args.stance:
        print(f"REFUSED: exact duplicate evidence ({args.source}, {args.sq}, {args.stance}) "
              f"already logged as {existing['id']}.")
        return 1
  rec = {"id": _next_id(records, "E"), "source": args.source, "url": src["url"],
         "sq": args.sq, "tier": args.tier, "kind": args.kind, "stance": args.stance,
         "quote": args.quote, "claim": args.claim, "title": args.title or src.get("title", ""),
         "publisher": args.publisher or src.get("publisher", ""),
         "published": args.published or "", "page_date": src.get("page_date", ""),
         "interest": args.interest or "", "sample_period": given,
         "context_periods": periods,
         "sample_type": args.sample_type or "",
         "accessed": src["fetched_at"][:10], "snapshot_sha256": src["sha256"]}
  _append(evid_path, rec)
  print(f"{rec['id']}  added  ({args.sq}, {args.tier}, {args.stance})  cite it as [{rec['id']}]")
  return 0


def cmd_add_batch(args) -> int:
  """Batch-registers multiple evidence items from a JSONL file in a single CLI call.
  Each line in the input file must be a JSON object with keys:
    source, sq, tier, kind, stance, quote, claim
  and optional keys:
    title, publisher, published, interest, sample_period, sample_type
  """
  d = Path(args.dir)
  batch_path = Path(args.file)
  if not batch_path.exists():
    print(f"ERROR: batch file not found: {batch_path}")
    return 1

  raw_items = _jsonl(batch_path)
  if not raw_items:
    print(f"REFUSED: batch file {batch_path} is empty")
    return 1

  index = {r["id"]: r for r in _jsonl(d / "sources" / "index.jsonl")}
  snaps: dict[str, str] = {}
  evid_path = d / "evidence.jsonl"
  records = _jsonl(evid_path)

  added_ids: list[str] = []
  errors: list[str] = []

  for idx, item in enumerate(raw_items, 1):
    src_id = item.get("source", "")
    src = index.get(src_id)
    if not src:
      errors.append(f"Row {idx}: unknown source {src_id!r}")
      continue
    if src_id not in snaps:
      snap_file = d / "sources" / f"{src_id}.txt"
      if not snap_file.exists():
        errors.append(f"Row {idx}: snapshot file {src_id}.txt missing")
        continue
      snap_text = snap_file.read_text(encoding="utf-8")
      if sha256_text(snap_text) != src["sha256"]:
        errors.append(f"Row {idx}: snapshot {src_id}.txt sha256 mismatch")
        continue
      snaps[src_id] = snap_text

    snap = snaps[src_id]
    sq = item.get("sq", "")
    tier = item.get("tier", "T5")
    kind = item.get("kind", "de_facto")
    stance = item.get("stance", "supports")
    quote = item.get("quote", "")
    claim = item.get("claim", "")

    if not SQ_RE.match(sq):
      errors.append(f"Row {idx}: invalid sq {sq!r} (must be SQ<n> or K<n>)")
      continue
    if tier not in TIERS or kind not in KINDS or stance not in STANCES:
      errors.append(f"Row {idx}: invalid tier/kind/stance ({tier}, {kind}, {stance})")
      continue
    if not quote or not claim:
      errors.append(f"Row {idx}: missing quote or claim")
      continue

    pub = item.get("publisher") or src.get("publisher", "")
    inflation_err = check_source_tier_inflation(src["url"], tier, publisher=pub)
    if inflation_err:
      errors.append(f"Row {idx}: {inflation_err}")
      continue

    score = match_score(quote, snap)
    if score < 1.0:
      errors.append(
          f"Row {idx} ({src_id}): quote not verbatim (match {score:.0%}). "
          f"Nearest: {_nearest(quote, snap, width=140)}"
      )
      continue

    periods = periods_near(snap, quote_span(quote, snap))
    given = (item.get("sample_period") or "").strip()
    if kind == "empirical" and periods and not given:
      errors.append(
          f"Row {idx} ({src_id}): empirical quote requires 'sample_period' "
          f"(detected near quote: {', '.join(periods[:3])})"
      )
      continue

    q_norm = normalise(quote)
    dup_err = ""
    for existing in (r for r in records if not r.get("retracted")):
      if existing.get("source") == src_id and normalise(existing.get("quote", "")) == q_norm:
        stances = {existing.get("stance"), stance}
        if "supports" in stances and "contradicts" in stances:
          dup_err = f"Row {idx}: opposite stance duplicate of {existing['id']}"
          break
        if existing.get("sq") == sq and existing.get("stance") == stance:
          dup_err = f"Row {idx}: exact duplicate of {existing['id']}"
          break
    if dup_err:
      errors.append(dup_err)
      continue

    new_id = _next_id(records, "E")
    rec = {
        "id": new_id,
        "source": src_id,
        "url": src["url"],
        "sq": sq,
        "tier": tier,
        "kind": kind,
        "stance": stance,
        "quote": quote,
        "claim": claim,
        "title": item.get("title") or src.get("title", ""),
        "publisher": pub,
        "published": item.get("published") or "",
        "page_date": src.get("page_date", ""),
        "interest": item.get("interest") or "",
        "sample_period": given,
        "context_periods": periods,
        "sample_type": item.get("sample_type") or "",
        "accessed": src["fetched_at"][:10],
        "snapshot_sha256": src["sha256"],
    }
    _append(evid_path, rec)
    records.append(rec)
    added_ids.append(new_id)

  for e in errors:
    print(f"  FAIL  {e}")
  print(f"BATCH SUMMARY: {len(added_ids)}/{len(raw_items)} added ({', '.join(added_ids[:10])}"
        f"{'...' if len(added_ids) > 10 else ''}), {len(errors)} failed.")
  return 1 if (errors and not added_ids) else 0


# ---------------------------------------------------------------- retract
def cmd_retract(args) -> int:
  """The only way to withdraw a wrong evidence record (duplicate, opposite-stance copy, wrong
  tier, quote from a changed snapshot). The record stays in the file, marked, so the audit trail
  survives; gate.py and every other tool ignore it, and a report citing it fails R2."""
  d = Path(args.dir)
  path = d / "evidence.jsonl"
  records = _jsonl(path)
  if not (args.reason or "").strip():
    print("REFUSED: --reason is required (e.g. 'duplicate of E004', 'wrong tier: forum is T5')")
    return 1
  target = next((r for r in records if r.get("id") == args.id), None)
  if target is None:
    print(f"REFUSED: {args.id} is not in evidence.jsonl (ids: {', '.join(r['id'] for r in records[:3])}...)")
    return 1
  if target.get("retracted"):
    print(f"REFUSED: {args.id} is already retracted ({target['retracted'].get('reason', '')})")
    return 1
  target["retracted"] = {"ts": dt.datetime.now().isoformat(timespec="seconds"), "reason": args.reason.strip()}
  with path.open("w", encoding="utf-8", newline="\n") as f:
    for r in records:
      f.write(json.dumps(r, ensure_ascii=False) + "\n")
  print(f"{args.id}  retracted  ({args.reason.strip()})")
  users = [c["id"] for c in _jsonl(d / "claims.jsonl") if args.id in c.get("eids", [])]
  if users:
    print(f"  claims citing it: {', '.join(users)} - re-add them with the corrected evidence (claims.py add)")
  report = d / "report.md"
  if report.exists() and re.search(rf"\b{args.id}\b", report.read_text(encoding="utf-8")):
    print(f"  report.md still cites [{args.id}] - replace it with the corrected record, or gate R2 fails")
  print("  To correct it: evidence.py add ... (the new record gets a new id)")
  return 0


# ---------------------------------------------------------------- log-search
def cmd_log_search(args) -> int:
  d = Path(args.dir)
  if not SQ_RE.match(args.purpose):
    print("REFUSED: --purpose must be SQ<n> or K<n>")
    return 1
  path = d / "searches.jsonl"
  rec = {"id": _next_id(_jsonl(path), "Q"),
         "ts": dt.datetime.now().isoformat(timespec="seconds"),
         "purpose": args.purpose, "query": args.query, "channel": args.channel,
         "opened": [s for s in (args.opened or "").split(",") if s],
         "note": args.note or ""}
  _append(path, rec)
  print(f"{rec['id']}  logged  [{args.purpose}] {args.query}")
  if args.purpose.startswith("K") and not rec["opened"]:
    print("  WARNING: a kill search with no --opened does not count toward the E4 kill budget. "
          "List what the search returned (top result URLs or S### ids), even if nothing was relevant.")
  return 0


# ------------------------------------------------------------------- sources
def cmd_sources(args) -> int:
  d = Path(args.dir)
  evidence = load_evidence(d)
  used = None
  if args.report:
    text = Path(args.report).read_text(encoding="utf-8")
    used = set(re.findall(r"\bE\d{3}\b", text))
  rows = ["| Ref | Source | Tier | Published | Accessed |", "| :-- | :-- | :-- | :-- | :-- |"]
  for r in evidence:
    if used is not None and r["id"] not in used:
      continue
    title = (r.get("title") or r.get("publisher") or r["url"]).replace("|", "/")
    rows.append(f"| [{r['id']}] | [{title}]({r['url']}) | {r.get('tier', '')} | "
                f"{r.get('published') or '—'} | {r.get('accessed', '')} |")
  print("\n".join(rows))
  return 0


def cmd_show(args) -> int:
  d = Path(args.dir)
  if args.source:
    snap = d / "sources" / f"{args.source}.txt"
    if not snap.exists():
      print(f"ERROR: {args.source} is not in {d / 'sources'} - list sources with: evidence.py show --dir {d}")
      return 1
    text = snap.read_text(encoding="utf-8")
    if args.grep:
      for m in re.finditer(re.escape(args.grep), text, re.I):
        print("..." + text[max(0, m.start() - 300): m.end() + 300].replace("\n", " ") + "...\n")
    else:
      print(text[:args.chars])
    return 0
  for r in _jsonl(d / "sources" / "index.jsonl"):
    print(f"{r['id']}  {r['chars']:>7} chars  {r['url']}")
  for r in load_evidence(d):
    print(f"{r['id']}  {r['sq']:<4} {r['tier']} {r['stance']:<11} {r['claim'][:90]}")
  return 0


def cmd_init(args) -> int:
  slug = re.sub(r"[^a-z0-9-]+", "-", args.slug.lower()).strip("-")
  d = ROOT / "research" / f"{today()}-{slug}"
  (d / "sources").mkdir(parents=True, exist_ok=True)
  for name in ("plan.md",):
    if not (d / name).exists():
      shutil.copy(TEMPLATES / name, d / name)
  for name in ("evidence.jsonl", "searches.jsonl", "notes.md"):
    (d / name).touch()
  if not (d / "study.json").exists():  # protocol marker: gate.py applies the rules of this version
    (d / "study.json").write_text(json.dumps({"created": today(), "protocol": PROTOCOL}) + "\n",
                                  encoding="utf-8")
  print(d)
  return 0


def main(argv: list[str] | None = None) -> int:
  if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
  ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
  sub = ap.add_subparsers(dest="cmd", required=True)
  p = sub.add_parser("init"); p.add_argument("slug"); p.set_defaults(fn=cmd_init)
  p = sub.add_parser("import"); p.add_argument("--dir", required=True)
  p.add_argument("--url", required=True); p.add_argument("--file", required=True)
  p.set_defaults(fn=cmd_import)
  p = sub.add_parser("fetch"); p.add_argument("--dir", required=True)
  p.add_argument("urls", nargs="+"); p.add_argument("--refresh", action="store_true")
  p.add_argument("--timeout", type=float, default=25)
  p.add_argument("--jina", action="store_true",
                 help="retry blocked pages through the third-party reader r.jina.ai (sends the URL to "
                      "that service). Off by default: use only when the user has allowed it")
  p.set_defaults(fn=cmd_fetch)
  p = sub.add_parser("add"); p.add_argument("--dir", required=True)
  p.add_argument("--source", required=True); p.add_argument("--sq", required=True)
  p.add_argument("--tier", required=True, choices=TIERS)
  p.add_argument("--kind", required=True, choices=KINDS)
  p.add_argument("--stance", required=True, choices=STANCES)
  p.add_argument("--quote", required=True); p.add_argument("--claim", required=True)
  p.add_argument("--title"); p.add_argument("--publisher"); p.add_argument("--published")
  p.add_argument("--interest", choices=INTERESTS,
                 help="academic (peer-reviewed) / regulator / independent, or with a stake: issuer "
                      "(the firm itself, broker PR) / affiliate (paid or affiliate review) / vendor "
                      "(whitepaper of a product seller)")
  p.add_argument("--sample-period",
                 help="period the number measures, e.g. 2004.1-2020.12 (from its own table, not the "
                      "paper's abstract); 'unknown' when the page does not say. Required for "
                      "--kind empirical when the page names a period near the quote")
  p.add_argument("--sample-type", choices=SAMPLE_TYPES)
  p.set_defaults(fn=cmd_add)
  p = sub.add_parser("add-batch")
  p.add_argument("--dir", required=True)
  p.add_argument("--file", required=True, help="JSONL file with batch evidence items")
  p.set_defaults(fn=cmd_add_batch)
  p = sub.add_parser("retract"); p.add_argument("--dir", required=True)
  p.add_argument("--id", required=True, help="E### to withdraw")
  p.add_argument("--reason", required=True); p.set_defaults(fn=cmd_retract)
  p = sub.add_parser("log-search"); p.add_argument("--dir", required=True)
  p.add_argument("--purpose", required=True); p.add_argument("--query", required=True)
  p.add_argument("--opened", help="comma-separated URLs or S### ids the search returned/you opened")
  p.add_argument("--channel", default="web", choices=SEARCH_CHANNELS,
                 help="where you searched: web (search engine), registry (official register / "
                      "regulator / gazette site), scholarly, citation (reference lists), other")
  p.add_argument("--note"); p.set_defaults(fn=cmd_log_search)
  p = sub.add_parser("sources"); p.add_argument("--dir", required=True)
  p.add_argument("--report"); p.set_defaults(fn=cmd_sources)
  p = sub.add_parser("show"); p.add_argument("--dir", required=True)
  p.add_argument("--source"); p.add_argument("--grep"); p.add_argument("--chars", type=int, default=3000)
  p.set_defaults(fn=cmd_show)
  args = ap.parse_args(argv)
  if getattr(args, "dir", None):
    err = study_dir_error(Path(args.dir))
    if err:
      print(err)
      return 2
  return args.fn(args)


if __name__ == "__main__":
  sys.exit(main())
