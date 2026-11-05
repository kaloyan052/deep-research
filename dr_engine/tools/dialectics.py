"""Autonomous Dialectical Conflict Synthesis & DerSimonian-Laird Meta-Analysis Engine (v5.0).

Transforms raw claim collisions from `claims.py` into formal structured debates:
  - Thesis vs. Antithesis decomposition with full provenance
  - Automated 8-axis divergence classification (scope, time, method, unit,
    authority, rule_vs_practice, interest, sample)
  - Exact Cochran's Q, DerSimonian-Laird between-study variance tau^2, and I^2 heterogeneity
  - Mandatory Regime-Partitioning Resolution (blocks naive averaging when I^2 > 50%)

Commands:
  python dr_engine/tools/dialectics.py build --dir D
  python dr_engine/tools/dialectics.py resolve --dir D --id D001 --synthesis "..." --partition-rule "..."
  python dr_engine/tools/dialectics.py verify --dir D
  python dr_engine/tools/dialectics.py render --dir D

Stdlib only.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import claims as claims_mod  # noqa: E402
from evidence import load_claims, load_evidence, study_dir_error  # noqa: E402

RESOLUTION_RULES = {
    "scope": "REGIME_SPLIT: Both claims hold in disjoint operational domains; partition decision by scope.",
    "sample": "OOS_DOMINANCE: Out-of-sample / post-publication / live data strictly overrides in-sample backtests.",
    "interest": "DISINTERESTED_DOMINANCE: Independent/academic/regulator evidence overrides vendor/issuer/affiliate claims.",
    "rule_vs_practice": "DE_FACTO_RISK_PRICING: Statutory/T&C rule defines ceiling; de_facto practice defines tail risk.",
    "authority": "TIER_HIERARCHY: Higher primary tier (T1-T2) dominates unless lower tier is >90 days newer empirical proof.",
    "time": "RECENCY_SUPERSESSION: Later effective statutory/changelog date supersedes older state.",
    "method": "METHODOLOGICAL_MODERATOR: Divergence driven by measurement design; do not pool.",
    "unit": "UNIT_NORMALIZATION: Normalize via units.py before comparison.",
    "UNEXPLAINED": "EPISTEMIC_PENALTY: Unexplained conflict caps claim reliability at 0.50 and requires 'unresolved' flag.",
}

NAIVE_POOLING_RE = re.compile(
    r"\b(average[ds]?\s+to|mean\s+of\s+the\s+two|midpoint|pooled\s+average|осреднено|средно\s+между\s+двете)\b",
    re.I,
)


def _dial_path(d: Path) -> Path:
  return Path(d) / "dialectics.json"


def load_dialectics(d: Path) -> list[dict[str, Any]]:
  p = _dial_path(d)
  if not p.exists():
    return []
  return json.loads(p.read_text(encoding="utf-8"))


def save_dialectics(d: Path, records: list[dict[str, Any]]) -> None:
  _dial_path(d).write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def dersimonian_laird(
    estimates: list[float], standard_errors: list[float] | None = None
) -> dict[str, Any]:
  """Exact DerSimonian-Laird random-effects meta-analysis and Cochran's Q / I^2 heterogeneity.
  When standard_errors are omitted, uses a conservative 10% scale-relative SE proxy.
  """
  k = len(estimates)
  if k < 2:
    return {"numeric": False, "q_stat": 0.0, "df": 0, "i2_pct": 0.0, "tau2": 0.0, "pooling_allowed": True}

  scale = sum(abs(x) for x in estimates) / k
  if scale == 0:
    return {
        "numeric": True, "q_stat": 0.0, "df": k - 1, "i2_pct": 0.0, "tau2": 0.0,
        "fe_pooled": 0.0, "re_pooled": 0.0, "rel_spread_pct": 0.0, "pooling_allowed": True,
    }

  if not standard_errors or len(standard_errors) != k:
    se = [max(1e-6, 0.10 * scale) for _ in estimates]
  else:
    se = [max(1e-6, float(s)) for s in standard_errors]

  weights = [1.0 / (s ** 2) for s in se]
  sum_w = sum(weights)
  fe_mean = sum(w * y for w, y in zip(weights, estimates)) / sum_w
  q_stat = sum(w * ((y - fe_mean) ** 2) for w, y in zip(weights, estimates))
  df = k - 1

  c_denom = sum_w - (sum(w ** 2 for w in weights) / sum_w)
  tau2 = max(0.0, (q_stat - df) / c_denom) if c_denom > 0 else 0.0
  i2 = max(0.0, min(99.9, ((q_stat - df) / q_stat) * 100.0)) if q_stat > df else 0.0

  re_weights = [1.0 / ((s ** 2) + tau2) for s in se]
  re_mean = sum(w * y for w, y in zip(re_weights, estimates)) / sum(re_weights)
  rel_spread = (max(estimates) - min(estimates)) / scale

  return {
      "numeric": True,
      "q_stat": round(q_stat, 3),
      "df": df,
      "i2_pct": round(i2, 1),
      "tau2": round(tau2, 4),
      "fe_pooled": round(fe_mean, 4),
      "re_pooled": round(re_mean, 4),
      "rel_spread_pct": round(rel_spread * 100.0, 1),
      "pooling_allowed": i2 <= 50.0,
  }


def _compute_heterogeneity(val_a: Any, val_b: Any, se_a: float | None = None, se_b: float | None = None) -> dict[str, Any]:
  try:
    a, b = float(val_a), float(val_b)
  except (TypeError, ValueError):
    return {"numeric": False, "q_stat": None, "i2_pct": None, "tau2": None, "rel_spread_pct": None, "pooling_allowed": False}
  ses = [se_a, se_b] if (se_a is not None and se_b is not None) else None
  return dersimonian_laird([a, b], ses)


def build_dialectics(d: Path) -> list[dict[str, Any]]:
  evidence = {r["id"]: r for r in load_evidence(d)}
  claims = load_claims(d)
  raw_conflicts = claims_mod.find_conflicts(claims, evidence)
  existing = {r["key"] + "|" + r["thesis_id"] + "|" + r["antithesis_id"]: r for r in load_dialectics(d)}

  by_id = {c["id"]: c for c in claims}
  out: list[dict[str, Any]] = []

  for idx, c in enumerate(raw_conflicts, 1):
    did = f"D{idx:03d}"
    ca = by_id.get(c["a"], {})
    cb = by_id.get(c["b"], {})
    axes = c.get("axes", ["UNEXPLAINED"])
    primary_axis = axes[0] if axes else "UNEXPLAINED"
    het = _compute_heterogeneity(ca.get("value"), cb.get("value"), ca.get("se"), cb.get("se"))

    sig = f"{c['key']}|{c['a']}|{c['b']}"
    prev = existing.get(sig, {})

    rec = {
        "id": did,
        "key": c["key"],
        "thesis_id": c["a"],
        "antithesis_id": c["b"],
        "thesis": {
            "claim_id": c["a"],
            "value": ca.get("value"),
            "unit": ca.get("unit", ""),
            "scope": ca.get("scope", "general"),
            "time": ca.get("time", ""),
            "eids": c["a_eids"],
        },
        "antithesis": {
            "claim_id": c["b"],
            "value": cb.get("value"),
            "unit": cb.get("unit", ""),
            "scope": cb.get("scope", "general"),
            "time": cb.get("time", ""),
            "eids": c["b_eids"],
        },
        "axes": axes,
        "primary_axis": primary_axis,
        "heterogeneity": het,
        "canonical_rule": RESOLUTION_RULES.get(primary_axis, RESOLUTION_RULES["UNEXPLAINED"]),
        "synthesis": prev.get("synthesis", ""),
        "partition_rule": prev.get("partition_rule", ""),
        "status": prev.get("status") if prev.get("synthesis") else (
            "unresolved" if primary_axis == "UNEXPLAINED" else "pending_synthesis"
        ),
    }
    out.append(rec)

  save_dialectics(d, out)
  return out


def resolve_dialectic(
    d: Path, did: str, synthesis: str, partition_rule: str = ""
) -> tuple[bool, str]:
  """Resolves a dialectical conflict, rejecting naive averaging when I^2 > 50%."""
  recs = load_dialectics(d)
  target = next((r for r in recs if r["id"] == did), None)
  if not target:
    return False, f"Unknown dialectical ID {did}"

  het = target.get("heterogeneity", {})
  i2 = het.get("i2_pct") or 0.0
  if i2 > 50.0 or not het.get("pooling_allowed", True):
    if not (partition_rule or "").strip():
      return False, (
          f"REFUSED: {did} has high heterogeneity (I^2={i2}% > 50%); "
          f"naive pooling is prohibited — you must supply a non-empty --partition-rule"
      )
    if NAIVE_POOLING_RE.search(synthesis):
      return False, (
          f"REFUSED: {did} synthesis contains naive averaging/pooling language while I^2={i2}% > 50%; "
          f"state the regime partition instead of averaging the two numbers"
      )

  target["synthesis"] = synthesis.strip()
  target["partition_rule"] = partition_rule.strip()
  target["status"] = "resolved"
  save_dialectics(d, recs)
  return True, f"Resolved {did} ({target['key']})"


def verify_dialectics(d: Path) -> list[str]:
  """Verifies all dialectical conflicts for Gate R15."""
  recs = load_dialectics(d)
  errors: list[str] = []
  for r in recs:
    did = r["id"]
    het = r.get("heterogeneity", {})
    i2 = het.get("i2_pct") or 0.0
    if r.get("status") == "pending_synthesis":
      errors.append(f"dialectical conflict {did} [{r['key']}] is still pending_synthesis (run `dialectics.py resolve`)")
      continue
    if r.get("status") == "resolved":
      if (i2 > 50.0 or not het.get("pooling_allowed", True)) and not (r.get("partition_rule") or "").strip():
        errors.append(f"dialectical conflict {did} [{r['key']}] has I^2={i2}% > 50% but no partition_rule")
      if (i2 > 50.0) and NAIVE_POOLING_RE.search(r.get("synthesis", "")):
        errors.append(f"dialectical conflict {did} [{r['key']}] illegally averages/pools estimates under I^2={i2}% > 50%")
  return errors


def render_dialectics_markdown(d: Path) -> str:
  records = load_dialectics(d)
  if not records:
    return "No dialectical conflicts detected in `claims.jsonl`."
  lines = [
      "### Dialectical Contradiction Matrix & Regime Partitioning",
      "",
      "| ID | Subject & Attribute | Thesis (Side A) | Antithesis (Side B) | Divergence Axes & $I^2$ | Dialectical Synthesis & Regime Partition Rule |",
      "| :-- | :-- | :-- | :-- | :-- | :-- |",
  ]
  for r in records:
    t = r["thesis"]
    a = r["antithesis"]
    t_str = f"`{t['value']} {t['unit']}` (scope: *{t['scope']}*) [{', '.join(t['eids'])}]"
    a_str = f"`{a['value']} {a['unit']}` (scope: *{a['scope']}*) [{', '.join(a['eids'])}]"
    het = r["heterogeneity"]
    i2_str = f"; $Q={het['q_stat']}, I^2={het['i2_pct']}\\%$" if het.get("i2_pct") is not None else ""
    axes_str = f"`{', '.join(r['axes'])}`{i2_str}"
    synth = r["synthesis"] or r["canonical_rule"]
    part = f" **Rule:** {r['partition_rule']}" if r.get("partition_rule") else ""
    if r["primary_axis"] == "UNEXPLAINED" and "unresolved" not in synth.lower():
      synth += " *(unresolved)*"
    lines.append(f"| **{r['id']}** | `{r['key']}` | {t_str} | {a_str} | {axes_str} | {synth}{part} |")
  return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
  if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
  ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
  sub = ap.add_subparsers(dest="cmd", required=True)

  p = sub.add_parser("build"); p.add_argument("--dir", required=True)
  p = sub.add_parser("resolve"); p.add_argument("--dir", required=True)
  p.add_argument("--id", required=True); p.add_argument("--synthesis", required=True)
  p.add_argument("--partition-rule", default="", help="Decision rule separating when Thesis vs Antithesis applies")
  p = sub.add_parser("verify"); p.add_argument("--dir", required=True)
  p = sub.add_parser("render"); p.add_argument("--dir", required=True)

  args = ap.parse_args(argv)
  d = Path(args.dir)
  err = study_dir_error(d)
  if err:
    print(err)
    return 2

  if args.cmd == "build":
    recs = build_dialectics(d)
    print(f"Built {len(recs)} dialectical conflict record(s) in {d / 'dialectics.json'}")
    for r in recs:
      print(f"  {r['id']}  [{r['key']}]  axes={','.join(r['axes'])}  status={r['status']}")
    return 0
  if args.cmd == "resolve":
    ok, msg = resolve_dialectic(d, args.id, args.synthesis, args.partition_rule)
    print(msg)
    return 0 if ok else 1
  if args.cmd == "verify":
    errs = verify_dialectics(d)
    if errs:
      for e in errs:
        print(f"  FAIL  {e}")
      return 1
    print(f"[PASS] dialectics.json verified ({len(load_dialectics(d))} conflicts resolved)")
    return 0
  if args.cmd == "render":
    print(render_dialectics_markdown(d))
    return 0
  return 0


if __name__ == "__main__":
  sys.exit(main())
