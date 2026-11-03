"""Sampled claim audit with a statistical error bound.

Mechanical gates prove provenance (the quote is on the page, the number is in the quote).
They cannot prove entailment: that the quote actually supports the sentence. Checking
every sentence by hand does not scale to 200-source reports, so we sample:

  1. `sample` draws n claim units from the report. The seed is the report's sha256, so
     the agent cannot pick convenient sentences.
  2. A fresh-context verifier (subagent or human) reads `audit/brief.md` - each sampled
     sentence with only its cited quotes and URLs - and judges it.
  3. `bound` reports the one-sided upper bound on the share of claims in the report that
     are not supported: exact hypergeometric over the report's claim units (finite
     population), Clopper-Pearson when the population is unknown. n=30 with 0 errors from
     a large report -> <= 9.5% at 95%; a full census -> the exact error share.

Verdicts: supported | partial | unsupported | wrong_number | misattributed
(everything except `supported` counts as an error).

  python dr_engine/tools/audit.py sample --dir D [--n 30]
  python dr_engine/tools/audit.py record --dir D --item A07 --verdict supported [--note "..."]
  python dr_engine/tools/audit.py bound  --dir D

A sentence judged wrong blocks the report until it is fixed, whatever the bound says.
After fixing, re-run `sample`: the new draw is seeded by the fixed report, verdicts carry
over to sentences whose text and cited quotes are unchanged, and only fixed or new
sentences go back to a verifier (so fixes are checked too). The previous round's errors
stay in `history` and in audit/history/. Without a re-sample the gate still accepts a
report whose `supported` sentences are unchanged and whose error sentences are gone, but
then nobody has checked the replacement text. Stdlib only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_report as cr  # noqa: E402
from evidence import _jsonl, load_evidence, study_dir_error  # noqa: E402

EID_RE = re.compile(r"\bE\d{3}\b")
VERDICTS = ("supported", "partial", "unsupported", "wrong_number", "misattributed")


def clopper_pearson_upper(k: int, n: int, confidence: float = 0.95) -> float:
  """One-sided upper bound p_U with P(X <= k | n, p_U) = 1 - confidence."""
  if n <= 0:
    return 1.0
  if k >= n:
    return 1.0
  alpha = 1.0 - confidence

  def cdf(p: float) -> float:
    return sum(math.comb(n, i) * p**i * (1 - p)**(n - i) for i in range(k + 1))

  lo, hi = k / n, 1.0
  for _ in range(100):
    mid = (lo + hi) / 2
    if cdf(mid) > alpha:
      lo = mid
    else:
      hi = mid
  return hi


def hypergeom_upper(k: int, n: int, population: int, confidence: float = 0.95) -> float:
  """Finite-population version: largest share D/N of bad units in a population of N that
  is still consistent (P(X <= k) > 1 - confidence) with k bad units in a sample of n drawn
  without replacement. Tighter than Clopper-Pearson when n is a large part of N; exact
  (k/N) for a census."""
  N = population
  if n <= 0 or N <= 0:
    return 1.0
  alpha, total = 1.0 - confidence, math.comb(N, n)
  d_max = k
  for D in range(k, N - (n - k) + 1):
    cdf = sum(math.comb(D, i) * math.comb(N - D, n - i) for i in range(k + 1)) / total
    if cdf <= alpha:
      break
    d_max = D
  return d_max / N


def claim_units(report_text: str) -> list[dict]:
  units, exempt = [], False
  for u in cr._units(cr._strip_non_prose(report_text.splitlines())):
    if u.kind == "heading":
      exempt = cr.heading_exempt(u.text, exempt)
      continue
    if exempt or not cr._is_claim(u.text):
      continue
    eids = list(dict.fromkeys(EID_RE.findall(u.text)))
    if eids:
      units.append({"line": u.line, "text": u.text, "eids": eids})
  return units


def _paths(d: Path) -> tuple[Path, Path]:
  return d / "audit" / "sample.json", d / "audit" / "brief.md"


def cmd_sample(args) -> int:
  d = Path(args.dir)
  report = Path(args.report) if args.report else d / "report.md"
  text = report.read_text(encoding="utf-8")
  sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
  units = claim_units(text)
  if not units:
    print("no cited claim units in the report")
    return 1
  n = min(args.n, len(units))
  picked = sorted(random.Random(int(sha[:12], 16)).sample(range(len(units)), n))
  evidence = {r["id"]: r for r in load_evidence(d)}
  calcs = {r["id"]: r for r in _jsonl(d / "calculations.jsonl") if "id" in r}
  items = []
  for i, idx in enumerate(picked, 1):
    u = units[idx]
    items.append({"id": f"A{i:02d}", "line": u["line"], "text": u["text"], "eids": u["eids"],
                  "quotes": [{"eid": e, "url": evidence.get(e, {}).get("url", ""),
                              "quote": evidence.get(e, {}).get("quote", "(missing)")}
                             for e in u["eids"]],
                  "calcs": [{"cid": c, "label": calcs[c].get("label", ""), "expr": calcs[c].get("expr", ""),
                             "variables": calcs[c].get("variables", {}), "result": calcs[c].get("result"),
                             "unit": calcs[c].get("unit", ""), "cites": calcs[c].get("cited_eids", [])}
                            for c in dict.fromkeys(re.findall(r"\bC\d{3}\b", u["text"])) if c in calcs]})
  sample_path, brief_path = _paths(d)
  sample_path.parent.mkdir(exist_ok=True)
  data = {"report_sha256": sha, "population": len(units), "n": n, "items": items, "verdicts": {},
          "history": []}
  prev = load(d)
  if prev and prev["report_sha256"] != sha:
    # Re-audit after fixes: a verdict carries over only to a sentence whose text AND cited
    # quotes are identical. Fixed or new sentences go back to a blind verifier, so a fix
    # is checked, not just the removal of the error.
    hist = sample_path.parent / "history"
    hist.mkdir(exist_ok=True)
    (hist / f"sample-{prev['report_sha256'][:8]}.json").write_text(
        json.dumps(prev, ensure_ascii=False, indent=2), encoding="utf-8")
    s = summary(prev)
    data["history"] = prev.get("history", []) + [
        {"report_sha256": prev["report_sha256"], "judged": s["n"], "errors": s["errors"],
         "error_items": [f"{i}: {prev['verdicts'][i]['verdict']}" for i in s["error_items"]]}]
    if not args.fresh:
      judged = {_item_key(it): prev["verdicts"][it["id"]] for it in prev["items"]
                if it["id"] in prev["verdicts"]}
      for it in items:
        v = judged.get(_item_key(it))
        if v:
          data["verdicts"][it["id"]] = dict(v, carried_from=prev["report_sha256"][:8])
  sample_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
  items = [it for it in items if it["id"] not in data["verdicts"]]
  lines = [
      "# Claim audit brief (blind)", "",
      "You are a fact-checker who has NOT seen the research. For each item decide whether the",
      "cited quotes, read in context at their URLs, support the sentence exactly as written.",
      "Check numbers, units, scope (plan / population / jurisdiction), dates, and whether the",
      "sentence says more than the quote ('some' -> 'all', 'may' -> 'will').", "",
      "Verdict per item: supported | partial | unsupported | wrong_number | misattributed.",
      "Record each with: python dr_engine/tools/audit.py record --dir <dir> --item <ID> "
      "--verdict <v> --note \"<why>\"", ""]
  for it in items:
    lines += [f"## {it['id']}", "", f"> {it['text']}", ""]
    for q in it["quotes"]:
      lines += [f"- [{q['eid']}] {q['url']}", f"  \"{q['quote']}\""]
    for c in it.get("calcs", []):
      inputs = ", ".join(f"{k}={v}" for k, v in c["variables"].items())
      lines.append(f"- [{c['cid']}] {c['label']}: {c['expr']} with {inputs} = {c['result']} "
                   f"{c['unit']} (inputs cited from {', '.join(c['cites']) or 'nothing'})")
    lines.append("")
  brief_path.write_text("\n".join(lines), encoding="utf-8")
  print(f"Sampled {n} of {len(units)} claim units -> {sample_path}\nVerifier brief -> {brief_path}")
  if data["verdicts"]:
    print(f"Carried {len(data['verdicts'])} verdict(s) from the previous audit (identical text and "
          f"quotes); {len(items)} item(s) in the brief need a fresh verifier")
  return 0


def _item_key(it: dict) -> tuple:
  return (it["text"], tuple((q["eid"], q["quote"]) for q in it["quotes"]))


def load(d: Path) -> dict | None:
  p = _paths(d)[0]
  return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def cmd_record(args) -> int:
  d = Path(args.dir)
  data = load(d)
  if not data:
    print("no audit sample; run `audit.py sample` first")
    return 1
  if args.item not in {it["id"] for it in data["items"]}:
    print(f"unknown item {args.item}")
    return 1
  data["verdicts"][args.item] = {"verdict": args.verdict, "note": args.note or ""}
  _paths(d)[0].write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
  print(f"{args.item}: {args.verdict}")
  return 0


def summary(data: dict, confidence: float = 0.95) -> dict:
  judged = data["verdicts"]
  errors = [i for i, v in judged.items() if v["verdict"] != "supported"]
  n = len(judged)
  population = data.get("population", 0)
  if n and population >= n:
    bound, method = hypergeom_upper(len(errors), n, population, confidence), "hypergeometric"
  else:
    bound, method = (clopper_pearson_upper(len(errors), n, confidence) if n else 1.0), "clopper-pearson"
  return {"n": n, "sampled": data["n"], "errors": len(errors), "error_items": errors,
          "pending": [it["id"] for it in data["items"] if it["id"] not in judged],
          "upper_bound": bound, "method": method, "confidence": confidence}


def check_against_report(data: dict, report_text: str) -> list[str]:
  """Problems that make the audit invalid for this version of the report. A sentence judged
  wrong blocks the report until it is fixed, whatever the bound says."""
  unchanged = hashlib.sha256(report_text.encode("utf-8")).hexdigest() == data["report_sha256"]
  current = {u["text"] for u in claim_units(report_text)}
  problems = []
  for it in data["items"]:
    v = data["verdicts"].get(it["id"], {}).get("verdict")
    if v == "supported" and not unchanged and it["text"] not in current:
      problems.append(f"{it['id']} (L{it['line']}) was audited as supported but has since changed - re-run audit.py sample")
    elif v and v != "supported" and it["text"] in current:
      problems.append(f"{it['id']} (L{it['line']}) was judged '{v}' and is still in the report unfixed")
  return problems


def cmd_bound(args) -> int:
  d = Path(args.dir)
  data = load(d)
  if not data:
    print("no audit sample")
    return 1
  s = summary(data, args.confidence)
  print(f"Judged {s['n']}/{s['sampled']} sampled claims (population {data['population']}); "
        f"errors: {s['errors']} {s['error_items']}")
  carried = sum(1 for v in data["verdicts"].values() if v.get("carried_from"))
  if carried:
    print(f"  ({carried} verdict(s) carried from an earlier version: identical text and quotes)")
  for h in data.get("history", []):
    print(f"  earlier round {h['report_sha256'][:8]}: {h['errors']}/{h['judged']} errors "
          f"{h['error_items']} - fixed since")
  if s["pending"]:
    print(f"Pending: {', '.join(s['pending'])}")
  print(f"Upper bound on unsupported-claim rate: {s['upper_bound']:.1%} "
        f"at {s['confidence']:.0%} confidence ({s['method']}, one-sided)")
  report = d / "report.md"
  if report.exists():
    for p in check_against_report(data, report.read_text(encoding="utf-8")):
      print(f"  STALE: {p}")
  return 0


def main(argv: list[str] | None = None) -> int:
  if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
  ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
  sub = ap.add_subparsers(dest="cmd", required=True)
  p = sub.add_parser("sample")
  p.add_argument("--dir", required=True)
  p.add_argument("--n", type=int, default=30)
  p.add_argument("--report")
  p.add_argument("--fresh", action="store_true",
                 help="do not carry verdicts from the previous audit of an earlier report version")
  p.set_defaults(fn=cmd_sample)
  p = sub.add_parser("record")
  p.add_argument("--dir", required=True)
  p.add_argument("--item", required=True)
  p.add_argument("--verdict", required=True, choices=VERDICTS)
  p.add_argument("--note")
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
