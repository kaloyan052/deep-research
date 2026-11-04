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

The brief shows each quote inside its passage in the saved page, with the periods the page
names near it, so the verifier can check scope (period, population, units), not just wording.

A sentence judged wrong blocks the report until it is fixed, whatever the bound says.
After fixing, re-run `sample`: the new draw is seeded by the fixed report, verdicts carry
over to sentences whose text and cited quotes are unchanged, and only fixed or new
sentences go back to a verifier. Two items are kept on purpose even when the new draw misses
them: an error sentence still in the report (it keeps blocking; an edit elsewhere cannot hide
it) and the sentence that replaced a fixed error (so the fix is checked). They count toward
the verdicts but not toward the random-sample error bound. Re-running `sample` on an
unchanged report keeps every verdict; `--fresh` drops carried `supported` verdicts but never
an error. The previous round's errors stay in `history` and in audit/history/. Stdlib only.
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
from difflib import SequenceMatcher  # noqa: E402
from evidence import (_jsonl, context_excerpt, load_evidence, periods_near,  # noqa: E402
                      quote_span, study_dir_error)

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


def _quote_info(d: Path, eid: str, evidence: dict, snaps: dict) -> dict:
  """The cited quote with the passage around it in the saved page and the periods named near it:
  a quote alone hides its scope (the trial's 'right number, wrong sample period' error)."""
  rec = evidence.get(eid, {})
  q = {"eid": eid, "url": rec.get("url", ""), "quote": rec.get("quote", "(missing)"),
       "source": rec.get("source", "")}
  path = d / "sources" / f"{q['source']}.txt"
  if rec and q["source"] and path.exists():
    if q["source"] not in snaps:
      snaps[q["source"]] = path.read_text(encoding="utf-8")
    text = snaps[q["source"]]
    span = quote_span(q["quote"], text)
    q["context"], q["periods"] = context_excerpt(text, span), periods_near(text, span)
  return q


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
  snaps: dict[str, str] = {}

  def make_item(u: dict, iid: str) -> dict:
    return {"id": iid, "line": u["line"], "text": u["text"], "eids": u["eids"],
            "quotes": [_quote_info(d, e, evidence, snaps) for e in u["eids"]],
            "calcs": [{"cid": c, "label": calcs[c].get("label", ""), "expr": calcs[c].get("expr", ""),
                       "variables": calcs[c].get("variables", {}), "result": calcs[c].get("result"),
                       "unit": calcs[c].get("unit", ""), "cites": calcs[c].get("cited_eids", [])}
                      for c in dict.fromkeys(re.findall(r"\bC\d{3}\b", u["text"])) if c in calcs]}

  items = [make_item(units[idx], f"A{i:02d}") for i, idx in enumerate(picked, 1)]
  sample_path, brief_path = _paths(d)
  sample_path.parent.mkdir(exist_ok=True)
  data = {"report_sha256": sha, "population": len(units), "n": n, "items": items, "verdicts": {},
          "history": [], "unit_hashes": sorted({_h(u["text"]) for u in units})}
  prev = load(d)
  if prev:
    same = prev["report_sha256"] == sha
    tag = {} if same else {"carried_from": prev["report_sha256"][:8]}
    if same:  # re-running sample on the same report keeps what was already judged
      data["history"] = prev.get("history", [])
    else:
      hist = sample_path.parent / "history"
      hist.mkdir(exist_ok=True)
      (hist / f"sample-{prev['report_sha256'][:8]}.json").write_text(
          json.dumps(prev, ensure_ascii=False, indent=2), encoding="utf-8")
      s = summary(prev)
      data["history"] = prev.get("history", []) + [
          {"report_sha256": prev["report_sha256"], "judged": s["n"], "errors": s["errors"],
           "error_items": [f"{i}: {prev['verdicts'][i]['verdict']}" for i in s["error_items"]]}]
    judged = {_item_key(it): (it, prev["verdicts"][it["id"]]) for it in prev["items"]
              if it["id"] in prev["verdicts"]}
    # 1. A verdict carries over only to a sentence whose text AND cited quotes are identical.
    #    --fresh drops carried 'supported' verdicts (an independent second look), never an error.
    for it in items:
      hit = judged.get(_item_key(it))
      if hit and (hit[1]["verdict"] != "supported" or not args.fresh):
        data["verdicts"][it["id"]] = dict(hit[1], **tag)
    current = {u["text"]: u for u in units}
    drawn = {it["text"] for it in items}
    # Items kept on purpose last round stay while they are in the report: all of them on an
    # unchanged report, the ones nobody has judged yet after an edit (a pending fix stays pending).
    for old in prev["items"]:
      if (old.get("forced") and old["text"] in current and old["text"] not in drawn
          and (same or old["id"] not in prev["verdicts"])):
        it = dict(make_item(current[old["text"]], f"A{len(items) + 1:02d}"), forced=old["forced"])
        items.append(it)
        drawn.add(it["text"])
        v = prev["verdicts"].get(old["id"])
        if v and _item_key(it) == _item_key(old):
          data["verdicts"][it["id"]] = dict(v, **tag)
    for key, (old, v) in judged.items():
      # 2. An error sentence still in the report stays in the audit even when the new draw misses
      #    it: otherwise any edit elsewhere re-seeds the draw and hides the unfixed error.
      if v["verdict"] != "supported" and old["text"] in current and old["text"] not in drawn:
        it = dict(make_item(current[old["text"]], f"A{len(items) + 1:02d}"), forced="unfixed error")
        items.append(it)
        drawn.add(it["text"])
        if _item_key(it) == key:  # same quotes: still wrong; changed quotes: judge it again
          data["verdicts"][it["id"]] = dict(v, **tag)
    # 3. The sentence that replaced a fixed error goes to the verifier even when the draw misses it,
    #    so the fix itself is checked, not just the removal of the error.
    before = set(prev.get("unit_hashes") or ())  # every sentence of the previous report version
    old_texts = {it["text"] for it in prev["items"]}
    new_units = [u for u in units if u["text"] not in drawn and
                 (_h(u["text"]) not in before if before else u["text"] not in old_texts)]
    for key, (old, v) in judged.items():
      if v["verdict"] == "supported" or old["text"] in current or not new_units:
        continue
      best = max(new_units, key=lambda u: SequenceMatcher(None, old["text"], u["text"]).ratio())
      if SequenceMatcher(None, old["text"], best["text"]).ratio() >= 0.5 and best["text"] not in drawn:
        items.append(dict(make_item(best, f"A{len(items) + 1:02d}"), forced=f"replaces a sentence judged {v['verdict']}"))
        drawn.add(best["text"])
  sample_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
  items = [it for it in items if it["id"] not in data["verdicts"]]
  lines = [
      "# Claim audit brief (blind)", "",
      "You are a fact-checker who has NOT seen the research. For each item decide whether the",
      "cited quotes, read in context at their URLs, support the sentence exactly as written.",
      "Check numbers, units, scope (plan / population / jurisdiction), dates, and whether the",
      "sentence says more than the quote ('some' -> 'all', 'may' -> 'will').",
      "Each quote is shown inside its passage in the saved page (marked with ⟪ ⟫) with the periods",
      "the page names near it: a number belongs to the period of its own table or paragraph, not",
      "to the paper's headline period. The full saved pages are in sources/<S###>.txt.", "",
      "Verdict per item: supported | partial | unsupported | wrong_number | misattributed.",
      "Record each with: python dr_engine/tools/audit.py record --dir <dir> --item <ID> "
      "--verdict <v> --note \"<why>\"", ""]
  for it in items:
    lines += [f"## {it['id']}", "", f"> {it['text']}", ""]
    for q in it["quotes"]:
      lines += [f"- [{q['eid']}] {q['url']}", f"  \"{q['quote']}\""]
      if q.get("context"):
        lines.append(f"  In context ({q['source']}): \"{q['context']}\"")
      elif q.get("source"):
        lines.append(f"  (passage not located automatically: read sources/{q['source']}.txt)")
      if q.get("periods"):
        lines.append(f"  Periods named near it: {'; '.join(q['periods'])}")
    for c in it.get("calcs", []):
      inputs = ", ".join(f"{k}={v}" for k, v in c["variables"].items())
      lines.append(f"- [{c['cid']}] {c['label']}: {c['expr']} with {inputs} = {c['result']} "
                   f"{c['unit']} (inputs cited from {', '.join(c['cites']) or 'nothing'})")
    lines.append("")
  brief_path.write_text("\n".join(lines), encoding="utf-8")
  forced = sum(1 for it in data["items"] if it.get("forced"))
  print(f"Sampled {n} of {len(units)} claim units"
        + (f" + {forced} kept from the previous audit (unfixed errors / their fixes)" if forced else "")
        + f" -> {sample_path}\nVerifier brief -> {brief_path}")
  if data["verdicts"]:
    print(f"Kept {len(data['verdicts'])} verdict(s) from the previous audit (identical text and "
          f"quotes); {len(items)} item(s) in the brief need a fresh verifier")
  return 0


def _h(text: str) -> str:
  return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


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
  """Counts over every judged item; the error bound only over the random draw (items kept on
  purpose - unfixed errors and their fixes - are not a random sample, and block on their own)."""
  judged = data["verdicts"]
  errors = [i for i, v in judged.items() if v["verdict"] != "supported"]
  drawn = {it["id"] for it in data["items"] if not it.get("forced")}
  n = sum(1 for i in judged if i in drawn)
  k = sum(1 for i in errors if i in drawn)
  population = data.get("population", 0)
  if n and population >= n:
    bound, method = hypergeom_upper(k, n, population, confidence), "hypergeometric"
  else:
    bound, method = (clopper_pearson_upper(k, n, confidence) if n else 1.0), "clopper-pearson"
  return {"n": len(judged), "sampled": len(data["items"]), "errors": len(errors), "error_items": errors,
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
                 help="send every unchanged 'supported' sentence back to a verifier too (error "
                      "verdicts on sentences still in the report are always kept)")
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
