"""Claim ledger and contradiction mapper.

Evidence records are quotes; claims are the normalised facts the report is built from:

  subject | attribute | value | unit | scope | time | method  -> evidence IDs

Two claims about the same (subject, attribute) with different values are a conflict.
Numbers are first normalised with units.py, so "3 USD per side" and "6 USD RT" are the same
fact, while "6% p.a." vs "1.5 bp per trade" is a unit conflict (a holding period is
missing). The mapper explains each conflict by the axes on which the two sides differ -
scope / population, time / version, method, unit / definition, authority (tier), rule vs
practice (de_jure vs de_facto), interest (a side with a stake: issuer, affiliate, vendor vs
peer-reviewed, regulator, independent), sample (different sample period, e.g. pre- vs
post-crisis, or in-sample vs out-of-sample) - and marks it UNEXPLAINED when no axis
differs. Gate R11 then requires every conflict to be confronted in the report's Conflicts
section.

Synthesis reads `claims.py table`, not raw sources: a few hundred claim rows fit in
context where a few hundred pages never will.

  add        python dr_engine/tools/claims.py add --dir D --subject FXIFY \
                 --attribute "index commission per lot" --value 6 --unit "USD RT" \
                 --scope "Raw feed" --time 2026-10 --method "help-centre FAQ" --eids E002,E003 \
                 [--sample-period 2010-2019 --sample-type out_of_sample]
  keys       python dr_engine/tools/claims.py keys --dir D       (reuse exact wording)
  conflicts  python dr_engine/tools/claims.py conflicts --dir D [--tol 0.05] [--json]
  table      python dr_engine/tools/claims.py table --dir D [--subject FXIFY]

Numeric values must appear in a quote of a cited evidence record (same rule as gate R3).
Stdlib only.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from itertools import combinations
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
import units  # noqa: E402
from evidence import SAMPLE_TYPES, _append, _jsonl, _next_id, load_claims, load_evidence, study_dir_error  # noqa: E402

TIER_RANK = {"T1": 1, "T2": 2, "T3": 3, "T4": 4, "T5": 5}
NUM_ONLY_RE = re.compile(r"^\s*[-+]?[$€£]?\s*\d[\d,]*(?:\.\d+)?\s*%?\s*$")
YEAR_RE = re.compile(r"(?<!\d)((?:1[89]|20)\d{2})(?!\d)")
INTERESTED = {"issuer", "affiliate", "vendor"}
DISINTERESTED = {"academic", "regulator", "independent"}
AXES_HELP = {
    "scope": "different population / product / account type - usually both true",
    "time": "different date or version - newest version in force wins",
    "method": "different measurement or study design - compare designs, do not average",
    "unit": "different unit, dimension or convention - normalise with units.py; an annual rate "
            "vs a per-trade cost needs a holding period (hold_cost_bp), RT vs per side a stated side",
    "authority": "different source tiers - higher tier wins unless the lower is >90 days newer",
    "rule_vs_practice": "de_jure vs de_facto - not a contradiction; the gap is the finding",
    "interest": "one side has a stake (issuer's own PR, affiliate review, vendor whitepaper) - prefer "
                "the disinterested side (peer-reviewed, regulator, independent) on performance and "
                "practice; the issuer still binds for its own rules",
    "sample": "different sample period (e.g. pre- vs post-crisis) or in-sample vs out-of-sample - for "
              "'does it still work' the later / out-of-sample / post-publication evidence wins; "
              "do not average",
}


def norm(s: str) -> str:
  return re.sub(r"\s+", " ", (s or "").strip().lower())


def key(c: dict) -> str:
  return f"{norm(c['subject'])} | {norm(c['attribute'])}"


def numeric(value: str) -> float | None:
  if not NUM_ONLY_RE.match(value or ""):
    return None
  raw = re.sub(r"[$€£%\s]", "", value)
  raw = raw.replace(",", "") if re.fullmatch(r"[-+]?\d{1,3}(,\d{3})+(\.\d+)?", raw) else raw.replace(",", ".")
  try:
    return float(raw)
  except ValueError:
    return None


def _jaccard(a: str, b: str) -> float:
  sa, sb = set(re.findall(r"\w+", a)), set(re.findall(r"\w+", b))
  return len(sa & sb) / len(sa | sb) if sa | sb else 0.0


# ---------------------------------------------------------------------- add
def cmd_add(args) -> int:
  d = Path(args.dir)
  evidence = {r["id"]: r for r in load_evidence(d)}
  eids = [e.strip() for e in args.eids.split(",") if e.strip()]
  missing = [e for e in eids if e not in evidence]
  if not eids or missing:
    print(f"REFUSED: unknown or missing evidence IDs: {missing or 'none given'}")
    return 1
  val = numeric(args.value)
  if val is not None:
    import gate  # local import: gate imports formula/calc
    bound = set()
    for e in eids:
      bound |= gate.numbers(evidence[e].get("quote", ""))
    if round(val, 6) not in {round(float(b), 6) for b in bound}:
      print(f"REFUSED: value {args.value} does not appear in the quotes of {', '.join(eids)}. "
            f"Cite the evidence that states it, or derive it with calc.py and claim the result "
            f"against that calculation's inputs.")
      return 1
  path = d / "claims.jsonl"
  claims = _jsonl(path)
  rec = {"id": _next_id(claims, "CL"), "subject": args.subject.strip(),
         "attribute": args.attribute.strip(), "value": args.value.strip(),
         "unit": (args.unit or "").strip(), "scope": (args.scope or "").strip(),
         "time": (args.time or "").strip(), "method": (args.method or "").strip(),
         "sample_period": (args.sample_period or "").strip(),
         "sample_type": args.sample_type or "", "load_bearing": bool(args.load_bearing),
         "eids": eids, "note": (args.note or "").strip()}
  if val is not None and rec["unit"] and not units.parse(rec["unit"]):
    print(f"  NOTE unit '{rec['unit']}' is not known to units.py - it can only be compared with the "
          f"exact same unit string (see `units.py parse`)")
  k = key(rec)
  near = sorted({key(c) for c in claims if key(c) != k and _jaccard(key(c), k) >= 0.5})
  _append(path, rec)
  print(f"{rec['id']}  added  [{k}] = {rec['value']} {rec['unit']}".rstrip())
  for n in near:
    print(f"  WARN similar existing key: [{n}] - if this is the same fact, re-add with that exact "
          f"subject/attribute, otherwise conflicts between them cannot be detected")
  return 0


# ---------------------------------------------------------------- conflicts
def _interest(r: dict, subject: str) -> str:
  """Declared interest, else a conservative guess: the subject's own site is the issuer,
  a peer-reviewed (T3) source is academic. Unknown stays unknown."""
  if r.get("interest"):
    return r["interest"]
  host = re.sub(r"[^a-z0-9]", "", (urlparse(r.get("url", "")).hostname or "").lower())
  subj = re.sub(r"[^a-z0-9]", "", (subject or "").lower())
  if len(subj) >= 3 and subj in host:
    return "issuer"
  return "academic" if r.get("tier") == "T3" else ""


def _years(period: str) -> tuple[int, int] | None:
  ys = [int(y) for y in YEAR_RE.findall(period or "")]
  return (min(ys), max(ys)) if ys else None


def _side_meta(c: dict, evidence: dict) -> dict:
  recs = [evidence[e] for e in c["eids"] if e in evidence]
  tiers = [TIER_RANK.get(r.get("tier", "T5"), 5) for r in recs] or [5]
  kinds = {r.get("kind", "") for r in recs}
  dates = sorted(r.get("published") or r.get("page_date", "") for r in recs
                 if r.get("published") or r.get("page_date"))
  interests = {i for i in (_interest(r, c.get("subject", "")) for r in recs) if i}
  periods = [c["sample_period"]] if c.get("sample_period") else [
      r["sample_period"] for r in recs if r.get("sample_period")]
  spans = [s for s in map(_years, periods) if s]
  types = {c["sample_type"]} if c.get("sample_type") else {
      r["sample_type"] for r in recs if r.get("sample_type")}
  return {"best_tier": min(tiers), "kinds": kinds, "latest": dates[-1] if dates else "",
          "interests": interests, "sample_types": types,
          "span": (min(s[0] for s in spans), max(s[1] for s in spans)) if spans else None}


def _unit_of(c: dict) -> str:
  return c.get("unit", "") or ("%" if "%" in c.get("value", "") else "")


def _compare_numbers(va: float, ua: str, vb: float, ub: str, tol: float) -> tuple[bool, bool, str]:
  """(same, unit_axis, note) for two numeric claims, after normalising units."""
  qa, qb = units.quantity(va, ua), units.quantity(vb, ub)
  if qa and qb and qa.dim == qb.dim:
    denom = max(abs(qa.value), abs(qb.value)) or 1.0
    same = abs(qa.value - qb.value) / denom <= tol
    return same, False, (f"normalised: {qa} vs {qb}" if norm(ua) != norm(ub) else "")
  if qa and qb:
    dims = {qa.dim, qb.dim}
    if "bp/year" in dims and dims & {"bp", "bp/trade", "bp/trade?"}:
      hint = ("an annual rate is not a per-trade cost: hold_cost_bp(nights, annual_bp, spread_bp) "
              "(trap G9)")
    elif any(d.endswith("?") for d in dims):
      hint = "one side does not say whether it is round-turn or per side"
    elif len({d.split("/")[0] for d in dims}) == 2 and all(d.split("/")[0].isupper() for d in dims):
      hint = "different currencies - convert at a dated FX rate with calc.py"
    else:
      hint = "different dimensions"
    return False, True, f"{qa.label} vs {qb.label}: {hint}"
  if norm(ua) == norm(ub):
    denom = max(abs(va), abs(vb)) or 1.0
    return abs(va - vb) / denom <= tol, False, ""
  return False, True, f"units '{ua}' vs '{ub}' not comparable by units.py"


def find_conflicts(claims: list[dict], evidence: dict, tol: float = 0.05) -> list[dict]:
  groups: dict[str, list[dict]] = {}
  for c in claims:
    groups.setdefault(key(c), []).append(c)
  out = []
  for k, cs in groups.items():
    for a, b in combinations(cs, 2):
      va, vb = numeric(a["value"]), numeric(b["value"])
      ua, ub = _unit_of(a), _unit_of(b)
      unit_axis, notes = False, []
      if va is not None and vb is not None:
        same, unit_axis, note = _compare_numbers(va, ua, vb, ub, tol)
        if same:
          continue
        if note:
          notes.append(note)
      elif norm(a["value"]) == norm(b["value"]) and norm(ua) == norm(ub):
        continue
      ma, mb = _side_meta(a, evidence), _side_meta(b, evidence)
      axes = [f for f in ("scope", "time", "method") if norm(a.get(f, "")) != norm(b.get(f, ""))]
      if unit_axis:  # a unit only means something when both sides are numbers
        axes.append("unit")
      if "time" not in axes and ma["latest"] and mb["latest"] and ma["latest"] != mb["latest"]:
        axes.append("time")
      if ma["best_tier"] != mb["best_tier"]:
        axes.append("authority")
      if ({"de_jure"} & ma["kinds"] and {"de_facto"} & mb["kinds"]) or (
          {"de_facto"} & ma["kinds"] and {"de_jure"} & mb["kinds"]):
        axes.append("rule_vs_practice")
      cls = [("interested" if m["interests"] <= INTERESTED else "disinterested")
             if m["interests"] and (m["interests"] <= INTERESTED or m["interests"] & DISINTERESTED)
             else "" for m in (ma, mb)]
      if all(cls) and cls[0] != cls[1]:
        axes.append("interest")
        notes.append(f"interest: {'/'.join(sorted(ma['interests']))} vs "
                     f"{'/'.join(sorted(mb['interests']))}")
      if ma["sample_types"] and mb["sample_types"] and ma["sample_types"] != mb["sample_types"]:
        axes.append("sample")
        notes.append(f"sample type: {'/'.join(sorted(ma['sample_types']))} vs "
                     f"{'/'.join(sorted(mb['sample_types']))}")
      sa, sb = ma["span"], mb["span"]
      if sa and sb and sa != sb:
        if "sample" not in axes:
          axes.append("sample")
        apart = sa[1] < sb[0] or sb[1] < sa[0]
        notes.append(f"sample period {sa[0]}-{sa[1]} vs {sb[0]}-{sb[1]}"
                     f"{' (non-overlapping, e.g. pre- vs post-crisis)' if apart else ''}")
      out.append({"key": k, "a": a["id"], "b": b["id"], "a_value": f"{a['value']} {ua}".strip(),
                  "b_value": f"{b['value']} {ub}".strip(), "a_eids": a["eids"],
                  "b_eids": b["eids"], "axes": axes or ["UNEXPLAINED"], "notes": notes})
  return out


def cmd_conflicts(args) -> int:
  d = Path(args.dir)
  evidence = {r["id"]: r for r in load_evidence(d)}
  conflicts = find_conflicts(load_claims(d), evidence, args.tol)
  if args.json:
    print(json.dumps(conflicts, ensure_ascii=False, indent=2))
    return 0
  if not conflicts:
    print("No conflicts among logged claims.")
    return 0
  for c in conflicts:
    print(f"[{c['key']}]  {c['a']} = {c['a_value']} {c['a_eids']}  vs  "
          f"{c['b']} = {c['b_value']} {c['b_eids']}")
    for ax in c["axes"]:
      print(f"    axis: {ax:<17} {AXES_HELP.get(ax, 'no axis differs: investigate (method, sample, conflict of interest) or report as unresolved')}")
    for n in c.get("notes", []):
      print(f"          {n}")
  n_unexp = sum(1 for c in conflicts if c["axes"] == ["UNEXPLAINED"])
  print(f"\n{len(conflicts)} conflict(s), {n_unexp} unexplained. Each must appear in the report's "
        f"Conflicts section citing evidence from both sides (gate R11).")
  return 0


# -------------------------------------------------------------------- table
def cmd_table(args) -> int:
  d = Path(args.dir)
  claims = load_claims(d)
  if args.subject:
    claims = [c for c in claims if norm(c["subject"]) == norm(args.subject)]
  print("| Claim | Subject | Attribute | Value | Scope | Time | Evidence |")
  print("| :-- | :-- | :-- | :-- | :-- | :-- | :-- |")
  for c in sorted(claims, key=lambda c: (key(c), c["id"])):
    print(f"| {c['id']} | {c['subject']} | {c['attribute']} | {c['value']} {c['unit']} | "
          f"{c['scope'] or '-'} | {c['time'] or '-'} | {', '.join(f'[{e}]' for e in c['eids'])} |")
  return 0


def cmd_keys(args) -> int:
  for k in sorted({key(c) for c in _jsonl(Path(args.dir) / "claims.jsonl")}):
    print(k)
  return 0


def main(argv: list[str] | None = None) -> int:
  if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
  ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
  sub = ap.add_subparsers(dest="cmd", required=True)
  p = sub.add_parser("add")
  p.add_argument("--dir", required=True)
  for f in ("subject", "attribute", "value", "eids"):
    p.add_argument(f"--{f}", required=True)
  for f in ("unit", "scope", "time", "method", "note", "sample-period"):
    p.add_argument(f"--{f}")
  p.add_argument("--sample-type", choices=SAMPLE_TYPES)
  p.add_argument("--load-bearing", action="store_true",
                 help="the decision rests on this fact (counts as decisive in corpus.py stats)")
  p.set_defaults(fn=cmd_add)
  p = sub.add_parser("conflicts")
  p.add_argument("--dir", required=True)
  p.add_argument("--tol", type=float, default=0.05, help="relative tolerance for numeric values")
  p.add_argument("--json", action="store_true")
  p.set_defaults(fn=cmd_conflicts)
  p = sub.add_parser("table")
  p.add_argument("--dir", required=True)
  p.add_argument("--subject")
  p.set_defaults(fn=cmd_table)
  p = sub.add_parser("keys")
  p.add_argument("--dir", required=True)
  p.set_defaults(fn=cmd_keys)
  args = ap.parse_args(argv)
  if getattr(args, "dir", None):
    err = study_dir_error(Path(args.dir))
    if err:
      print(err)
      return 2
  return args.fn(args)


if __name__ == "__main__":
  sys.exit(main())
