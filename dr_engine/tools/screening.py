"""Screening audit: did discovery throw away relevant sources?

Candidates are every lead a logged search returned: candidates.jsonl (discover.py,
--snowball) plus the URLs in searches.jsonl `opened` / `results`. A candidate is
REJECTED when it was never fetched into sources/. Nobody can read all of them, so:

  1. `sample` draws 20-50 rejected candidates at random. The seed is the SHA-256 of the
     sorted rejected list, so the agent cannot pick convenient ones.
  2. A verifier opens each URL (evidence.py fetch when it looks relevant) and judges it
     against the plan item it was searched for:
        relevant    - it bears on a sub-question or kill hypothesis (fetch it: --source S###)
        irrelevant  - off-topic, duplicate content, marketing, dead end
        duplicate   - already in the corpus under another URL (--source S### required)
        unreachable - dead / paywalled / bot-walled (excluded from the bound; too many = WARN)
  3. `bound` reports the one-sided 95% upper bound on the share of rejected candidates that
     were relevant (Clopper-Pearson; also the exact hypergeometric bound for this finite
     list) and the most relevant sources that could have been lost. 0 relevant in 30 ->
     at most 9.5% (Clopper-Pearson).

Every candidate judged relevant must end up in sources/ (and be cited or explained):
gate.py fails E9 until it is fetched.

  python dr_engine/tools/screening.py sample --dir D [--n 30]
  python dr_engine/tools/screening.py record --dir D --item X07 --verdict irrelevant --note "vendor brochure"
  python dr_engine/tools/screening.py record --dir D --item X09 --verdict relevant --source S031 --note "..."
  python dr_engine/tools/screening.py bound  --dir D

Stdlib only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from audit import clopper_pearson_upper, hypergeom_upper  # noqa: E402
from evidence import _jsonl, study_dir_error  # noqa: E402
from verify_citations import _canon  # noqa: E402

VERDICTS = ("relevant", "irrelevant", "duplicate", "unreachable")
MIN_N, MAX_N = 20, 50
PLAN_ROW_RE = re.compile(r"^\|\s*((?:SQ|K)\d+)\s*\|\s*([^|]+)\|")


def _path(d: Path) -> Path:
  return d / "audit" / "screening.json"


def _fetched(d: Path) -> dict[str, str]:
  out = {}
  for r in _jsonl(d / "sources" / "index.jsonl"):
    for u in (r.get("url"), r.get("final_url")):
      if u:
        out[_canon(u)] = r["id"]
  return out


def candidates(d: Path) -> list[dict]:
  """All leads with a URL, deduplicated by canonical URL (first sighting wins)."""
  seen: dict[str, dict] = {}
  for c in _jsonl(d / "candidates.jsonl"):
    if c.get("url"):
      seen.setdefault(_canon(c["url"]), {"url": c["url"], "title": c.get("title", ""),
                                         "purpose": c.get("purpose", ""), "lead": c.get("id", ""),
                                         "channel": c.get("channel", "")})
  for s in _jsonl(d / "searches.jsonl"):
    if s.get("channel") == "corpus":
      continue
    for ref in list(s.get("opened") or []) + list(s.get("results") or []):
      ref = str(ref)
      if ref.startswith(("http://", "https://")):
        seen.setdefault(_canon(ref), {"url": ref, "title": "", "purpose": s.get("purpose", ""),
                                      "lead": s.get("id", ""), "channel": s.get("channel", "web")})
  return list(seen.values())


def rejected(d: Path) -> list[dict]:
  fetched = _fetched(d)
  return sorted((c for c in candidates(d) if _canon(c["url"]) not in fetched), key=lambda c: _canon(c["url"]))


def _plan_items(d: Path) -> dict[str, str]:
  plan = d / "plan.md"
  items = {}
  if plan.exists():
    for line in plan.read_text(encoding="utf-8").splitlines():
      m = PLAN_ROW_RE.match(line.strip())
      if m:
        items[m.group(1)] = m.group(2).strip()
  return items


def _require_study(d: Path) -> bool:
  if not (d / "plan.md").exists():
    print(f"ERROR: {d} is not a study folder (no plan.md). Use the folder printed by evidence.py init.")
    return False
  return True


def cmd_sample(args) -> int:
  d = Path(args.dir)
  if not _require_study(d):
    return 2
  if not MIN_N <= args.n <= MAX_N:
    print(f"ERROR: --n must be between {MIN_N} and {MAX_N} (got {args.n})")
    return 2
  rej = rejected(d)
  if not rej:
    n_cand = len(candidates(d))
    print(f"Nothing to audit: {n_cand} candidate(s), none rejected. If that is 0, discovery was not "
          f"logged - use discover.py --dir and evidence.py log-search --opened <result URLs>.")
    return 1
  seed = hashlib.sha256("\n".join(_canon(c["url"]) for c in rej).encode("utf-8")).hexdigest()
  n = min(args.n, len(rej))
  picked = sorted(random.Random(int(seed[:12], 16)).sample(range(len(rej)), n))
  failed = {_canon(r["url"]): r.get("error", "") for r in _jsonl(d / "sources" / "failed.jsonl") if r.get("url")}
  items = [dict(rej[i], id=f"X{k:02d}", fetch_error=failed.get(_canon(rej[i]["url"]), ""))
           for k, i in enumerate(picked, 1)]
  data = {"seed_sha256": seed, "population": len(rej), "candidates": len(candidates(d)),
          "n": n, "items": items, "verdicts": {}}
  _path(d).parent.mkdir(exist_ok=True)
  _path(d).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
  plan = _plan_items(d)
  lines = ["# Screening audit brief", "",
           "These leads were returned by searches but never fetched. Open each URL and judge it",
           "against the plan item it was searched for. Fetch anything relevant first:",
           f"  evidence.py fetch --dir {d} <url>",
           "Record: python dr_engine/tools/screening.py record --dir <dir> --item <ID> --verdict "
           "relevant|irrelevant|duplicate|unreachable [--source S###] --note \"<why>\"", ""]
  for it in items:
    item_text = plan.get(it["purpose"], "")
    lines += [f"## {it['id']}", "", f"- URL: {it['url']}",
              f"- Title: {it['title'] or '(not recorded)'}",
              f"- Searched for: {it['purpose'] or '?'} {('- ' + item_text) if item_text else ''}".rstrip(),
              f"- Channel: {it['channel'] or '?'}"]
    if it.get("fetch_error"):
      lines.append(f"- Earlier fetch failed: {it['fetch_error']} (try once more; still failing -> unreachable)")
    lines.append("")
  (d / "audit" / "screening_brief.md").write_text("\n".join(lines), encoding="utf-8")
  print(f"Sampled {n} of {len(rej)} rejected candidates ({data['candidates']} total) -> {_path(d)}")
  print(f"Brief -> {d / 'audit' / 'screening_brief.md'}")
  return 0


def load(d: Path) -> dict | None:
  p = _path(d)
  return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def cmd_record(args) -> int:
  d = Path(args.dir)
  data = load(d)
  if not data:
    print("ERROR: no screening sample; run `screening.py sample --dir <dir>` first")
    return 1
  ids = [it["id"] for it in data["items"]]
  if args.item not in ids:
    print(f"ERROR: unknown item {args.item}; items are {ids[0]}..{ids[-1]}")
    return 1
  index_ids = {r["id"] for r in _jsonl(d / "sources" / "index.jsonl")}
  if args.verdict == "duplicate" and not args.source:
    print("ERROR: --verdict duplicate needs --source S### (the source already holding this content)")
    return 1
  if args.source and args.source not in index_ids:
    print(f"ERROR: {args.source} is not in sources/index.jsonl - fetch the page first: "
          f"evidence.py fetch --dir {d} <url>")
    return 1
  if not (args.note or "").strip():
    print("ERROR: --note is required: say in a few words why (e.g. 'vendor brochure, no data')")
    return 1
  data["verdicts"][args.item] = {"verdict": args.verdict, "source": args.source or "",
                                 "note": args.note.strip()}
  _path(d).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
  print(f"{args.item}: {args.verdict}" + (f" ({args.source})" if args.source else ""))
  if args.verdict == "relevant" and not args.source:
    print("  NOTE relevant but not fetched: gate.py fails E9 until it is fetched "
          "(evidence.py fetch) and re-recorded with --source S###")
  return 0


def summary(d: Path, data: dict, confidence: float = 0.95) -> dict:
  fetched = _fetched(d)
  judged = {i: v for i, v in data["verdicts"].items()}
  scored = {i: v for i, v in judged.items() if v["verdict"] != "unreachable"}
  relevant = [i for i, v in scored.items() if v["verdict"] == "relevant"]
  by_id = {it["id"]: it for it in data["items"]}
  not_fetched = [i for i in relevant
                 if not judged[i].get("source") and _canon(by_id[i]["url"]) not in fetched]
  n, k, pop = len(scored), len(relevant), data["population"]
  cp = clopper_pearson_upper(k, n, confidence) if n else 1.0
  hg = hypergeom_upper(k, n, pop, confidence) if n and pop >= n else cp
  return {"population": pop, "sampled": data["n"], "judged": len(judged), "scored": n,
          "relevant": relevant, "relevant_not_fetched": not_fetched,
          "unreachable": [i for i, v in judged.items() if v["verdict"] == "unreachable"],
          "pending": [it["id"] for it in data["items"] if it["id"] not in judged],
          "cp_upper": cp, "hypergeom_upper": hg, "max_lost": cp * pop, "confidence": confidence}


def cmd_bound(args) -> int:
  d = Path(args.dir)
  data = load(d)
  if not data:
    print("ERROR: no screening sample; run `screening.py sample --dir <dir>` first")
    return 1
  s = summary(d, data, args.confidence)
  print(f"Rejected candidates: {s['population']}  sampled: {s['sampled']}  judged: {s['judged']}  "
        f"(unreachable, not scored: {len(s['unreachable'])})")
  if s["pending"]:
    print(f"Pending: {', '.join(s['pending'])}")
  print(f"Relevant among scored: {len(s['relevant'])}/{s['scored']} {s['relevant']}")
  print(f"Upper bound on the share of rejected candidates that were relevant: "
        f"{s['cp_upper']:.1%} (Clopper-Pearson), {s['hypergeom_upper']:.1%} (hypergeometric) "
        f"at {s['confidence']:.0%} -> at most ~{s['max_lost']:.0f} relevant source(s) lost")
  if s["relevant_not_fetched"]:
    print(f"  ACTION: fetch and cite/explain {', '.join(s['relevant_not_fetched'])} "
          f"(evidence.py fetch, then screening.py record ... --source S###)")
  if s["scored"] and len(s["unreachable"]) > s["scored"] / 2:
    print("  WARN more than a third of the sample was unreachable: the bound covers only reachable leads")
  return 0


def main(argv: list[str] | None = None) -> int:
  if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
  ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
  sub = ap.add_subparsers(dest="cmd", required=True)
  p = sub.add_parser("sample")
  p.add_argument("--dir", required=True)
  p.add_argument("--n", type=int, default=30)
  p.set_defaults(fn=cmd_sample)
  p = sub.add_parser("record")
  p.add_argument("--dir", required=True)
  p.add_argument("--item", required=True)
  p.add_argument("--verdict", required=True, choices=VERDICTS)
  p.add_argument("--source", help="S### of the fetched page (required for duplicate; proves relevant ones were fetched)")
  p.add_argument("--note", required=True)
  p.set_defaults(fn=cmd_record)
  p = sub.add_parser("bound")
  p.add_argument("--dir", required=True)
  p.add_argument("--confidence", type=float, default=0.95)
  p.set_defaults(fn=cmd_bound)
  args = ap.parse_args(argv)
  if getattr(args, "dir", None):
    err = study_dir_error(Path(args.dir))
    if err:
      print(err)
      return 2
  return args.fn(args)


if __name__ == "__main__":
  sys.exit(main())
