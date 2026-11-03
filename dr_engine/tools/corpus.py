"""Study corpus: a persistent BM25 index over every fetched snapshot, so the agent
reads ranked passages instead of whole pages. This is what lets a study use 100-500
sources without flooding the model's context.

Every passage is an exact character span of a snapshot (S003@1200-1490), so any
passage can be passed verbatim to `evidence.py add --quote`.

  build    python dr_engine/tools/corpus.py build   --dir D
  query    python dr_engine/tools/corpus.py query   --dir D "news window stop loss" \
               [--k 12] [--per-source 2] [--log --purpose K3]
  triage   python dr_engine/tools/corpus.py triage  --dir D
           reading order per SQ/K, blind spots (items no source answers well), the
           surprise queue (fetched sources that match no item or are never cited), and
           shared-text pairs (sources on different sites with the same sentences - a
           syndicated release or a mirror is one source for triangulation, not two)
  numbers  python dr_engine/tools/corpus.py numbers --dir D "FXIFY US100 spread"
           passages that mention the terms AND contain figures (tables, footnotes)
  aliases  python dr_engine/tools/corpus.py aliases [--dir D] "CySEC warning"
           how the query expands: acronyms and synonyms from dr_engine/tools/aliases.json
           plus the study's own aliases.json (add groups, or "disable" a global one)
  stats    python dr_engine/tools/corpus.py stats   --dir D [--channels scholarly,web] [--save]
           coverage of the relevant source population (Chapman capture-recapture across two
           discovery channels) and a saturation curve (new claim keys per 10 sources);
           VERDICT SATURATED needs coverage >= 80% and no new decisive fact in the last 2 batches

Storage: <dir>/corpus.sqlite (rebuilt per source when its sha256 changes). Stdlib only
(sqlite3 with FTS5).
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import re
import sqlite3
import sys
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
from evidence import _append, _jsonl, _next_id, load_claims, load_evidence, study_dir_error  # noqa: E402

SENT_BOUNDARY_RE = re.compile(r"(?<=[.!?;])\s+(?=[\"“(\[]?[A-ZА-Я0-9])|\n+")
TOKEN_RE = re.compile(r"\w+", re.U)
DIGIT_RE = re.compile(r"\d")
STOPWORDS = frozenset(
    "a an and are as at be by for from has have how in is it of on or that the this to "
    "was were what when which who why will with does do can not no vs versus "
    "на за от по да се че са ще".split())
GLOBAL_ALIASES = Path(__file__).resolve().parent / "aliases.json"
WINDOW = 3          # sentences per passage
STRIDE = 2          # sentences between passage starts (overlap of 1)
MAX_PASSAGE = 700   # characters
MIN_PASSAGE = 40
CANDIDATES = 300    # BM25 candidates re-ranked by query-term coverage
BOILER_DF = 3       # a sentence on >= this many pages of ONE site is boilerplate (menus, footers);
                    # the same sentence on different sites is syndication - kept, and reported
BOILER_MAX = 0.5    # passages that are more than half boilerplate are not returned
SHARED_MIN_LEN = 60  # sentences shorter than this are too generic to show copying
SHARED_MIN = 2       # shared sentences that make two sources one for triangulation


# ------------------------------------------------------------------ chunking
def sentence_spans(text: str) -> list[tuple[int, int]]:
  cuts = [0] + [m.end() for m in SENT_BOUNDARY_RE.finditer(text)] + [len(text)]
  spans = []
  for a, b in zip(cuts, cuts[1:]):
    seg = text[a:b]
    lead = len(seg) - len(seg.lstrip())
    trail = len(seg) - len(seg.rstrip())
    s, e = a + lead, b - trail
    if e > s:
      spans.append((s, e))
  return spans


def passage_spans(text: str) -> list[tuple[int, int]]:
  """Overlapping windows of sentences, each an exact (start, end) span of `text`."""
  sents = []
  for s, e in sentence_spans(text):
    while e - s > MAX_PASSAGE:  # very long "sentence" (tables, run-on text)
      cut = text.rfind(" ", s, s + MAX_PASSAGE)
      cut = cut if cut > s else s + MAX_PASSAGE
      sents.append((s, cut))
      s = cut + 1
    sents.append((s, e))
  out, i = [], 0
  while i < len(sents):
    j = i
    start, end = sents[i]
    while j + 1 < len(sents) and j + 1 < i + WINDOW and sents[j + 1][1] - start <= MAX_PASSAGE:
      j += 1
      end = sents[j][1]
    if end - start >= MIN_PASSAGE:
      out.append((start, end))
    if j + 1 >= len(sents):
      break
    i += max(1, min(STRIDE, j - i + 1))
  return out


def tokens(text: str) -> list[str]:
  return [t for t in TOKEN_RE.findall(text.lower()) if t not in STOPWORDS and len(t) > 1]


# ------------------------------------------------------------ query expansion
def load_aliases(d: Path | None = None) -> list[list[str]]:
  """Global groups (aliases.json next to this file) merged with research/<dir>/aliases.json;
  a local group sharing a variant with a global one extends it, `disable` switches one off."""
  groups: list[list[str]] = []
  disabled: set[tuple[str, ...]] = set()
  for path in (GLOBAL_ALIASES, d / "aliases.json" if d else None):
    if not path or not path.exists():
      continue
    data = json.loads(path.read_text(encoding="utf-8"))
    disabled |= {tuple(tokens(v)) for v in data.get("disable", [])}
    for g in data.get("groups", []):
      g = [v for v in g if tokens(v)]
      keys = {tuple(tokens(v)) for v in g}
      for existing in groups:
        if keys & {tuple(tokens(v)) for v in existing}:
          existing.extend(v for v in g if tuple(tokens(v)) not in {tuple(tokens(x)) for x in existing})
          break
      else:
        groups.append(g)
  return [g for g in groups if not ({tuple(tokens(v)) for v in g} & disabled)]


def concepts(q: str, groups: list[list[str]] | None = None) -> list[dict]:
  """Query -> concepts. A concept is satisfied by any of its variants (token tuples): plain
  query terms have one variant; an alias group named in the query brings all its forms, so
  'CySEC' also finds 'Cyprus Securities and Exchange Commission'. Longest match first."""
  toks = tokens(q)
  variants = sorted(((tuple(tokens(v)), gi) for gi, g in enumerate(groups or []) for v in g),
                    key=lambda x: -len(x[0]))
  used, found = [False] * len(toks), {}
  for vt, gi in variants:
    if gi in found:
      continue
    for i in range(len(toks) - len(vt) + 1):
      if not any(used[i:i + len(vt)]) and tuple(toks[i:i + len(vt)]) == vt:
        used[i:i + len(vt)] = [True] * len(vt)
        found[gi] = i
        break
  out, seen = [], set()
  for i, t in enumerate(toks):
    if not used[i] and t not in seen:
      seen.add(t)
      out.append({"label": t, "variants": [(t,)], "alias": False})
  for gi, _ in sorted(found.items(), key=lambda kv: kv[1]):
    vs = list(dict.fromkeys(tuple(tokens(v)) for v in groups[gi]))
    out.append({"label": groups[gi][0], "variants": vs, "alias": True})
  return out


def _variant_expr(vt: tuple[str, ...]) -> str:
  if len(vt) == 1:
    return f'"{vt[0]}"'
  return "NEAR(" + " ".join(f'"{t}"' for t in vt) + f", {2 * len(vt)})"


def concept_expr(c: dict) -> str:
  return "(" + " OR ".join(_variant_expr(v) for v in c["variants"]) + ")"


def fts_query(q: str, groups: list[list[str]] | None = None) -> str:
  return " OR ".join(concept_expr(c) for c in concepts(q, groups))


# -------------------------------------------------------------------- storage
def connect(d: Path) -> sqlite3.Connection:
  con = sqlite3.connect(d / "corpus.sqlite")
  con.executescript("""
    CREATE TABLE IF NOT EXISTS docs(sid TEXT PRIMARY KEY, url TEXT, sha256 TEXT, chars INT);
    CREATE TABLE IF NOT EXISTS passages(pid INTEGER PRIMARY KEY, sid TEXT, start INT, end INT,
                                        text TEXT, boiler REAL DEFAULT 0);
    CREATE INDEX IF NOT EXISTS passages_sid ON passages(sid);
    CREATE TABLE IF NOT EXISTS sents(sid TEXT, pid INT, h TEXT, len INT);
    CREATE INDEX IF NOT EXISTS sents_h ON sents(h);
    CREATE INDEX IF NOT EXISTS sents_pid ON sents(pid);
    CREATE TABLE IF NOT EXISTS hosts(sid TEXT PRIMARY KEY, host TEXT);
    CREATE VIRTUAL TABLE IF NOT EXISTS passages_fts USING fts5(
        text, content='passages', content_rowid='pid', tokenize='unicode61 remove_diacritics 2');
  """)
  return con


def _sent_hash(sentence: str) -> str:
  norm = re.sub(r"\s+", " ", sentence).strip().lower()
  return hashlib.sha1(norm.encode("utf-8")).hexdigest()[:16]


def host_of(url: str) -> str:
  host = (urlparse(url or "").hostname or "").lower()
  return host[4:] if host.startswith("www.") else host


def _mark_boilerplate(con: sqlite3.Connection) -> None:
  """Share of each passage's characters made of sentences repeated on >= BOILER_DF pages of
  the same site. Counting per site keeps a press release syndicated to five sites searchable."""
  con.executescript("""
    DROP TABLE IF EXISTS temp.df;
    CREATE TEMP TABLE df AS
      SELECT s.h, hs.host, COUNT(DISTINCT s.sid) AS n
      FROM sents s JOIN hosts hs ON hs.sid = s.sid GROUP BY s.h, hs.host;
    CREATE INDEX temp.df_key ON df(h, host);""")
  con.execute("""
    UPDATE passages SET boiler = COALESCE((
      SELECT SUM(CASE WHEN df.n >= ? THEN s.len ELSE 0 END) * 1.0 / NULLIF(SUM(s.len), 0)
      FROM sents s JOIN hosts hs ON hs.sid = s.sid
      JOIN temp.df df ON df.h = s.h AND df.host = hs.host
      WHERE s.pid = passages.pid), 0)""", (BOILER_DF,))
  con.execute("DROP TABLE temp.df")


def shared_text(con: sqlite3.Connection) -> list[dict]:
  """Pairs of sources on different sites that share >= SHARED_MIN substantive sentences."""
  rows = con.execute("""
    SELECT DISTINCT s.h, s.sid, hs.host FROM sents s JOIN hosts hs ON hs.sid = s.sid
    WHERE s.len >= ? AND s.h IN (
      SELECT s2.h FROM sents s2 JOIN hosts h2 ON h2.sid = s2.sid
      WHERE s2.len >= ? GROUP BY s2.h HAVING COUNT(DISTINCT h2.host) >= 2)""",
                     (SHARED_MIN_LEN, SHARED_MIN_LEN)).fetchall()
  by_hash: dict[str, list[tuple[str, str]]] = {}
  for h, sid, host in rows:
    by_hash.setdefault(h, []).append((sid, host))
  pairs: dict[tuple[str, str], int] = {}
  for members in by_hash.values():
    for i, (a, ha) in enumerate(members):
      for b, hb in members[i + 1:]:
        if ha != hb:
          key = tuple(sorted((a, b)))
          pairs[key] = pairs.get(key, 0) + 1
  return [{"a": a, "b": b, "shared_sentences": n}
          for (a, b), n in sorted(pairs.items(), key=lambda kv: -kv[1]) if n >= SHARED_MIN]


def build(d: Path) -> dict:
  con = connect(d)
  index = {r["id"]: r for r in _jsonl(d / "sources" / "index.jsonl")}
  known = {sid: sha for sid, sha in con.execute("SELECT sid, sha256 FROM docs")}
  hosts = {sid: host for sid, host in con.execute("SELECT sid, host FROM hosts")}
  new_hosts = 0
  for sid, rec in index.items():
    host = host_of(rec.get("final_url") or rec.get("url", ""))
    if hosts.get(sid) != host:
      con.execute("INSERT OR REPLACE INTO hosts VALUES(?, ?)", (sid, host))
      new_hosts += 1
  added = updated = 0
  for sid, rec in index.items():
    p = d / "sources" / f"{sid}.txt"
    if not p.exists() or known.get(sid) == rec.get("sha256"):
      continue
    text = p.read_text(encoding="utf-8")
    if sid in known:
      for pid, old in con.execute("SELECT pid, text FROM passages WHERE sid=?", (sid,)).fetchall():
        con.execute("INSERT INTO passages_fts(passages_fts, rowid, text) VALUES('delete', ?, ?)",
                    (pid, old))
      con.execute("DELETE FROM passages WHERE sid=?", (sid,))
      con.execute("DELETE FROM sents WHERE sid=?", (sid,))
      updated += 1
    else:
      added += 1
    sents = sentence_spans(text)
    for s, e in passage_spans(text):
      cur = con.execute("INSERT INTO passages(sid, start, end, text) VALUES(?,?,?,?)",
                        (sid, s, e, text[s:e]))
      con.execute("INSERT INTO passages_fts(rowid, text) VALUES(?, ?)", (cur.lastrowid, text[s:e]))
      for a, b in sents:
        if a >= s and b <= e:
          con.execute("INSERT INTO sents VALUES(?,?,?,?)",
                      (sid, cur.lastrowid, _sent_hash(text[a:b]), b - a))
    con.execute("INSERT OR REPLACE INTO docs VALUES(?,?,?,?)",
                (sid, rec.get("url", ""), rec.get("sha256", ""), len(text)))
  if added or updated or new_hosts:
    _mark_boilerplate(con)
  con.commit()
  n_docs = con.execute("SELECT COUNT(*) FROM docs").fetchone()[0]
  n_pass = con.execute("SELECT COUNT(*) FROM passages").fetchone()[0]
  con.close()
  return {"added": added, "updated": updated, "docs": n_docs, "passages": n_pass}


# ---------------------------------------------------------------------- query
def search(d: Path, q: str, k: int = 12, per_source: int = 2,
           require_digits: bool = False) -> list[dict]:
  """BM25 candidates re-ranked by the share of query concepts each passage contains. Alias
  groups (aliases.json) expand the query: an acronym also matches the full name."""
  build(d)
  cs = concepts(q, load_aliases(d))
  match = " OR ".join(concept_expr(c) for c in cs)
  if not match:
    return []
  con = connect(d)
  rows = con.execute(
      "SELECT p.pid, p.sid, p.start, p.end, p.text, bm25(passages_fts) AS s, docs.url "
      "FROM passages_fts JOIN passages p ON p.pid = passages_fts.rowid "
      "JOIN docs ON docs.sid = p.sid WHERE passages_fts MATCH ? AND p.boiler <= ? "
      "ORDER BY s LIMIT ?", (match, BOILER_MAX, CANDIDATES)).fetchall()
  weights = idf_weights(con, cs)
  con.close()
  total_w = sum(weights.values())
  scored = []
  for rank, (pid, sid, s, e, text, bm, url) in enumerate(rows):
    if require_digits and not DIGIT_RE.search(text):
      continue
    present = set(tokens(text))
    cover = sum(w for c, w in zip(cs, weights.values())
                if any(set(v) <= present for v in c["variants"])) / total_w if total_w else 0.0
    score = 0.6 * cover + 0.4 * (1 - rank / max(1, len(rows)))
    scored.append({"pid": pid, "sid": sid, "start": s, "end": e, "url": url,
                   "coverage": round(cover, 2), "score": round(score, 3), "text": text})
  scored.sort(key=lambda r: -r["score"])
  out, per = [], {}
  for r in scored:
    if per.get(r["sid"], 0) >= per_source:
      continue
    per[r["sid"]] = per.get(r["sid"], 0) + 1
    out.append(r)
    if len(out) >= k:
      break
  return out


def idf_weights(con: sqlite3.Connection, cs: list[dict]) -> dict[str, float]:
  """BM25-style IDF per query concept over non-boilerplate passages (rare concepts weigh most);
  keys follow the order of `cs`."""
  n = con.execute("SELECT COUNT(*) FROM passages WHERE boiler <= ?", (BOILER_MAX,)).fetchone()[0] or 1
  out = {}
  for i, c in enumerate(cs):
    df = con.execute(
        "SELECT COUNT(*) FROM passages_fts JOIN passages p ON p.pid = passages_fts.rowid "
        "WHERE passages_fts MATCH ? AND p.boiler <= ?", (concept_expr(c), BOILER_MAX)).fetchone()[0]
    out[f"{i}:{c['label']}"] = math.log((n - df + 0.5) / (df + 0.5) + 1.0)
  return out


def locator(r: dict) -> str:
  return f"{r['sid']}@{r['start']}-{r['end']}"


def _print(results: list[dict], width: int = 420) -> None:
  for r in results:
    text = re.sub(r"\s+", " ", r["text"]).strip()
    print(f"{locator(r):<18} cov={r['coverage']:.2f}  {r['url']}")
    print(f"    {text[:width]}{'...' if len(text) > width else ''}")


def cmd_query(args) -> int:
  d = Path(args.dir)
  res = search(d, args.query, args.k, args.per_source, require_digits=args.digits)
  if args.json:
    print(json.dumps(res, ensure_ascii=False, indent=2))
  else:
    _print(res)
  if args.log:
    if not args.purpose or not re.match(r"^(SQ|K)\d+$", args.purpose):
      print("not logged: --log needs --purpose SQn|Kn")
      return 1
    path = d / "searches.jsonl"
    rec = {"id": _next_id(_jsonl(path), "Q"), "ts": dt.datetime.now().isoformat(timespec="seconds"),
           "purpose": args.purpose, "query": args.query, "channel": "corpus",
           "opened": sorted({r["sid"] for r in res}), "results": [locator(r) for r in res],
           "note": "logged by corpus.py with its result set"}
    expanded = {c["label"]: [" ".join(v) for v in c["variants"]]
                for c in concepts(args.query, load_aliases(d)) if c["alias"]}
    if expanded:
      rec["expanded"] = expanded
    _append(path, rec)
    print(f"{rec['id']}  logged  [{args.purpose}] {len(res)} passages")
  return 0


# --------------------------------------------------------------------- triage
def plan_items(plan: str) -> dict[str, str]:
  items = {}
  for line in plan.splitlines():
    m = re.match(r"^\|\s*((?:SQ|K)\d+)\s*\|\s*([^|]+)\|", line.strip())
    if m:
      items[m.group(1)] = m.group(2).strip()
  return items


def triage(d: Path, k: int = 5, blind_cov: float = 0.4, orphan_cov: float = 0.25) -> dict:
  build(d)
  plan = (d / "plan.md").read_text(encoding="utf-8") if (d / "plan.md").exists() else ""
  items = plan_items(plan)
  con = connect(d)
  all_sids = [r[0] for r in con.execute("SELECT sid FROM docs ORDER BY sid")]
  shared = shared_text(con)
  con.close()
  cited = {r.get("source") for r in load_evidence(d)}
  best_by_source: dict[str, float] = {s: 0.0 for s in all_sids}
  reading, blind = {}, []
  for iid, text in items.items():
    res = search(d, text, k=k, per_source=1)
    reading[iid] = [(locator(r), r["coverage"]) for r in res]
    if not res or res[0]["coverage"] < blind_cov:
      blind.append(iid)
    for r in search(d, text, k=len(all_sids) or 1, per_source=1):
      best_by_source[r["sid"]] = max(best_by_source.get(r["sid"], 0.0), r["coverage"])
  unused = [s for s in all_sids if s not in cited]
  orphans = [s for s, c in best_by_source.items() if c < orphan_cov and s in unused]
  return {"items": items, "reading": reading, "blind_spots": blind,
          "orphans": orphans, "unused": unused, "sources": len(all_sids), "shared": shared}


def cmd_triage(args) -> int:
  t = triage(Path(args.dir))
  if args.json:
    print(json.dumps(t, ensure_ascii=False, indent=2))
    return 0
  print(f"Corpus: {t['sources']} sources, {len(t['items'])} plan items\n")
  for iid, rows in t["reading"].items():
    flag = "  <- BLIND SPOT" if iid in t["blind_spots"] else ""
    print(f"{iid}: {t['items'][iid][:90]}{flag}")
    for loc, cov in rows:
      print(f"    {loc:<18} cov={cov:.2f}")
  print(f"\nBlind spots (best passage covers < 40% of the item's IDF-weighted terms): "
        f"{', '.join(t['blind_spots']) or 'none'}"
        f"\n  -> search outside the corpus for these (discover.py / web), then fetch.")
  print(f"Surprise queue - uncited sources matching no plan item: {', '.join(t['orphans']) or 'none'}"
        f"\n  -> skim them: unexpected evidence or a missing sub-question.")
  print(f"Fetched but never cited: {len(t['unused'])}/{t['sources']} "
        f"({', '.join(t['unused'][:20])}{' ...' if len(t['unused']) > 20 else ''})")
  if t["shared"]:
    print("Shared text across sites (syndication / mirrors / copying) - count each pair as ONE "
          "source when triangulating:")
    for p in t["shared"][:20]:
      print(f"    {p['a']} ~ {p['b']}  ({p['shared_sentences']} identical sentences)")
  return 0


def cmd_numbers(args) -> int:
  res = search(Path(args.dir), args.query, args.k, args.per_source, require_digits=True)
  _print(res)
  return 0


def cmd_aliases(args) -> int:
  d = Path(args.dir) if args.dir else None
  cs = concepts(args.query, load_aliases(d))
  for c in cs:
    forms = " | ".join(" ".join(v) for v in c["variants"])
    print(f"{'alias' if c['alias'] else 'term ':<5}  {c['label']:<28} {forms}")
  print(f"\nFTS5: {' OR '.join(concept_expr(c) for c in cs)}")
  return 0


def cmd_build(args) -> int:
  print(json.dumps(build(Path(args.dir))))
  return 0


# ------------------------------------------------------- coverage & saturation
SID_RE = re.compile(r"^S\d{3,}$")
DISCOVERY_EXCLUDED = {"corpus"}  # re-reading the corpus finds nothing new on the web


def search_channel(s: dict) -> str:
  """Discovery channel of a logged search: scholarly registries, citation graph, web,
  official registries. corpus.py queries re-read the corpus and are not discovery."""
  if s.get("channel"):
    return s["channel"]
  tool = s.get("tool", "")
  if tool.startswith("discover.py:snowball"):
    return "citation"
  if tool.startswith("discover.py"):
    return "scholarly"
  return "web"


def source_channels(d: Path) -> dict[str, set[str]]:
  """Fetched source -> the discovery channels that surfaced it (searches' opened pages and
  candidates.jsonl leads, matched by canonical URL)."""
  from verify_citations import _canon  # noqa: PLC0415 - heavy import only when needed
  index = _jsonl(d / "sources" / "index.jsonl")
  by_url: dict[str, str] = {}
  for r in index:
    for u in (r.get("url"), r.get("final_url")):
      if u:
        by_url[_canon(u)] = r["id"]
  out: dict[str, set[str]] = {r["id"]: set() for r in index}

  def mark(ref: str, channel: str) -> None:
    sid = ref if SID_RE.match(ref or "") else by_url.get(_canon(ref)) if ref else None
    if sid in out:
      out[sid].add(channel)

  for s in _jsonl(d / "searches.jsonl"):
    ch = search_channel(s)
    if ch in DISCOVERY_EXCLUDED:
      continue
    for ref in s.get("opened") or []:
      mark(str(ref), ch)
  for c in _jsonl(d / "candidates.jsonl"):
    mark(c.get("url", ""), c.get("channel") or "scholarly")
  return out


def chapman(n1: int, n2: int, m: int) -> dict:
  """Chapman's bias-corrected Lincoln-Petersen estimate of the population size from two
  capture occasions, with Seber's variance and a normal 95% interval."""
  n_hat = (n1 + 1) * (n2 + 1) / (m + 1) - 1
  var = (n1 + 1) * (n2 + 1) * (n1 - m) * (n2 - m) / ((m + 1) ** 2 * (m + 2))
  half = 1.96 * math.sqrt(var)
  return {"n1": n1, "n2": n2, "m": m, "n_hat": n_hat, "ci_low": max(n1 + n2 - m, n_hat - half),
          "ci_high": n_hat + half}


def coverage(d: Path, relevant_only: bool = True, channels: tuple[str, str] | None = None) -> dict:
  """How much of the relevant source population the study has found. 'Relevant' = the
  source has at least one evidence record (or every fetched source with relevant_only=False)."""
  chans = source_channels(d)
  cited = {r.get("source") for r in load_evidence(d)}
  pool = {sid: ch for sid, ch in chans.items() if (sid in cited or not relevant_only)}
  found = len(pool)
  unlogged = sorted(sid for sid, ch in pool.items() if not ch)
  counts: dict[str, int] = {}
  for ch in pool.values():
    for c in ch:
      counts[c] = counts.get(c, 0) + 1
  res = {"population": "cited sources" if relevant_only else "fetched sources", "found": found,
         "channel_counts": counts, "unlogged": unlogged, "estimate": None, "coverage": None,
         "coverage_low": None, "problem": ""}
  if channels:
    a, b = channels
    if a not in counts or b not in counts:
      res["problem"] = (f"channel(s) {', '.join(c for c in channels if c not in counts)} found none "
                        f"of the {res['population']}; channels seen: {', '.join(sorted(counts)) or 'none'}")
      return res
  else:
    ranked = sorted(counts, key=lambda c: -counts[c])
    if not ranked:
      res["problem"] = (f"no {res['population'][:-1]} is linked to a logged search: log every "
                        f"search with what it returned (evidence.py log-search --opened <URLs> "
                        f"--channel web|registry, discover.py --dir) so channels can be compared")
      return res
    if len(ranked) < 2:
      res["problem"] = ("only one discovery channel found relevant sources "
                        f"({ranked[0] if ranked else 'none'}); run the same SQ/K queries in a second, "
                        "independent channel (discover.py for scholarly, evidence.py log-search "
                        "--channel web|registry for the web) and log what each returned")
      return res
    a, b = ranked[0], ranked[1]
  n1 = sum(1 for ch in pool.values() if a in ch)
  n2 = sum(1 for ch in pool.values() if b in ch)
  m = sum(1 for ch in pool.values() if a in ch and b in ch)
  est = chapman(n1, n2, m)
  est["channels"] = [a, b]
  res["estimate"] = est
  if m == 0:
    res["problem"] = (f"channels {a} and {b} share no source: the population estimate is "
                      f"unreliable and coverage is UNKNOWN - keep searching in both")
    return res
  res["coverage"] = min(1.0, found / est["n_hat"]) if est["n_hat"] > 0 else 1.0
  res["coverage_low"] = min(1.0, found / est["ci_high"]) if est["ci_high"] > 0 else 1.0
  return res


def saturation(d: Path, batch: int = 10) -> dict:
  """New claim keys per batch of `batch` sources in fetch order. Uses the claim ledger
  (load-bearing claims are the decisive ones); without one, falls back to evidence claims."""
  index = sorted(_jsonl(d / "sources" / "index.jsonl"), key=lambda r: (r.get("fetched_at", ""), r["id"]))
  order = {r["id"]: i // batch for i, r in enumerate(index)}
  evidence = {r["id"]: r for r in load_evidence(d)}
  claims = load_claims(d)
  first: dict[str, int] = {}
  decisive: set[str] = set()
  if claims:
    basis = "claims.jsonl"
    any_lb = any(c.get("load_bearing") for c in claims)
    for c in claims:
      k = f"{c['subject'].strip().lower()} | {c['attribute'].strip().lower()}"
      batches = [order[evidence[e]["source"]] for e in c.get("eids", [])
                 if e in evidence and evidence[e].get("source") in order]
      if batches:
        first[k] = min(first.get(k, 10 ** 9), min(batches))
        if c.get("load_bearing") or not any_lb:
          decisive.add(k)
  else:
    basis = "evidence.jsonl (no claim ledger - weaker: every quote looks new)"
    for r in evidence.values():
      if r.get("source") in order:
        claim = re.sub(r"\s+", " ", r.get("claim", "").strip().lower())
        k = f"{r.get('sq', '')} | {claim}"
        first[k] = min(first.get(k, 10 ** 9), order[r["source"]])
        decisive.add(k)
  n_batches = (len(index) + batch - 1) // batch
  rows = []
  for b in range(n_batches):
    keys = [k for k, fb in first.items() if fb == b]
    rows.append({"batch": b + 1, "sources": f"{index[b * batch]['id']}-{index[min(len(index), (b + 1) * batch) - 1]['id']}",
                 "size": min(batch, len(index) - b * batch), "new_keys": len(keys),
                 "new_decisive": sum(1 for k in keys if k in decisive)})
  return {"basis": basis, "batch": batch, "rows": rows,
          "load_bearing_marked": bool(claims) and any(c.get("load_bearing") for c in claims)}


def stats_verdict(cov: dict, sat: dict, min_coverage: float = 0.8) -> tuple[str, list[str]]:
  reasons = []
  full = [r for r in sat["rows"] if r["size"] == sat["batch"]]
  if len(full) < 2:
    reasons.append(f"only {len(full)} full batch(es) of {sat['batch']} sources: a saturation curve "
                   f"needs >= 2 (>= {2 * sat['batch']} sources)")
  elif any(r["new_decisive"] >= 1 for r in full[-2:]):
    reasons.append("the last 2 batches still added decisive facts: "
                   + ", ".join(f"batch {r['batch']}: {r['new_decisive']}" for r in full[-2:]))
  if cov["coverage"] is None:
    reasons.append(f"coverage not estimated: {cov['problem']}")
  elif cov["coverage"] < min_coverage:
    reasons.append(f"estimated coverage {cov['coverage']:.0%} < {min_coverage:.0%}")
  return ("SATURATED" if not reasons else "CONTINUE"), reasons


def cmd_stats(args) -> int:
  d = Path(args.dir)
  info = build(d)
  print(f"Corpus: {info['docs']} sources, {info['passages']} passages")
  if args.passages:
    con = connect(d)
    for sid, n in con.execute("SELECT sid, COUNT(*) FROM passages GROUP BY sid ORDER BY sid"):
      print(f"  {sid}: {n} passages")
    con.close()
  chans = tuple(args.channels.split(",")) if args.channels else None
  if chans and len(chans) != 2:
    print("ERROR: --channels takes exactly two names, e.g. --channels scholarly,web")
    return 2
  cov = coverage(d, relevant_only=not args.all, channels=chans)
  sat = saturation(d, args.batch)
  verdict, reasons = stats_verdict(cov, sat, args.min_coverage)
  out = {"sources": info["docs"], "coverage": cov, "saturation": sat, "verdict": verdict,
         "reasons": reasons}
  if args.save:
    (d / "coverage.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
  if args.json:
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0
  print(f"\nCoverage of {cov['population']} (Chapman capture-recapture):")
  print("  channels: " + (", ".join(f"{c}={n}" for c, n in sorted(cov["channel_counts"].items())) or "none logged"))
  if cov["unlogged"]:
    print(f"  {len(cov['unlogged'])} source(s) not linked to any logged search: "
          f"{', '.join(cov['unlogged'][:12])} - log the search that found them with --opened")
  e = cov["estimate"]
  if e:
    print(f"  {e['channels'][0]}: n1={e['n1']}  {e['channels'][1]}: n2={e['n2']}  both: m={e['m']}  "
          f"-> N^ = {e['n_hat']:.1f} (95% CI {e['ci_low']:.1f}-{e['ci_high']:.1f})")
  if cov["coverage"] is not None:
    print(f"  found {cov['found']} -> coverage ~{cov['coverage']:.0%} (lower bound {cov['coverage_low']:.0%}). "
          f"Channels that favour the same sources make this an UPPER estimate.")
  else:
    print(f"  coverage UNKNOWN: {cov['problem']}")
  print(f"\nSaturation (new claim keys per batch of {sat['batch']} sources; basis: {sat['basis']}):")
  if not sat["load_bearing_marked"] and sat["basis"] == "claims.jsonl":
    print("  no claim is marked --load-bearing: every key counts as decisive")
  for r in sat["rows"]:
    print(f"  batch {r['batch']:>2} ({r['sources']}, {r['size']} src): {r['new_keys']} new keys, "
          f"{r['new_decisive']} decisive")
  print(f"\nVERDICT: {verdict}")
  for r in reasons:
    print(f"  - {r}")
  if verdict == "CONTINUE":
    print("  -> keep discovering (blind spots: corpus.py triage; second channel; discover.py --snowball)")
  return 0


def main(argv: list[str] | None = None) -> int:
  if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
  ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
  sub = ap.add_subparsers(dest="cmd", required=True)
  for name, fn in (("build", cmd_build), ("stats", cmd_stats), ("triage", cmd_triage)):
    p = sub.add_parser(name)
    p.add_argument("--dir", required=True)
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=fn)
    if name == "stats":
      p.add_argument("--channels", help="two discovery channels to compare, e.g. scholarly,web")
      p.add_argument("--all", action="store_true", help="population = all fetched sources, not only cited ones")
      p.add_argument("--batch", type=int, default=10, help="sources per saturation batch")
      p.add_argument("--min-coverage", type=float, default=0.8)
      p.add_argument("--save", action="store_true", help="write coverage.json (read by gate.py)")
      p.add_argument("--passages", action="store_true", help="also list passages per source")
  p = sub.add_parser("aliases", help="show how a query expands (global + study aliases.json)")
  p.add_argument("query")
  p.add_argument("--dir")
  p.set_defaults(fn=cmd_aliases)
  for name, fn in (("query", cmd_query), ("numbers", cmd_numbers)):
    p = sub.add_parser(name)
    p.add_argument("--dir", required=True)
    p.add_argument("query")
    p.add_argument("--k", type=int, default=12)
    p.add_argument("--per-source", type=int, default=2)
    p.add_argument("--json", action="store_true")
    p.add_argument("--digits", action="store_true", help="only passages containing figures")
    p.add_argument("--log", action="store_true", help="record query + result set in searches.jsonl")
    p.add_argument("--purpose")
    p.set_defaults(fn=fn)
  args = ap.parse_args(argv)
  if getattr(args, "dir", None):
    err = study_dir_error(Path(args.dir))
    if err:
      print(err)
      return 2
  return args.fn(args)


if __name__ == "__main__":
  sys.exit(main())
