"""Deterministic quantitative calculation & decision-matrix engine for Deep Research.

Eliminates LLM mental-arithmetic errors and prose 'Извод:' smuggling by recording
reproducible, AST-evaluated, SHA-256-verified [C###] records in calculations.jsonl.

Usage:
  python dr_engine/tools/calc.py eval --dir research/<slug> \\
      --label "Net payout after 20% split and 10% tax" \\
      --expr "gross * (1 - split) * (1 - tax)" \\
      --var gross=10000 --var split=0.20 --var tax=0.10 \\
      --cites E001,E002 --unit USD

  python dr_engine/tools/calc.py decision --dir research/<slug> \\
      --title "Prop Account Slot Allocation" \\
      --cost 540 --tax-rate 0.10 --haircut 0.20 --friction 25 \\
      --base-prob 0.42 --base-payoff 4000 \\
      --bear-prob 0.25 --bear-payoff 2500 \\
      --stress-prob 0.10 --stress-payoff 1500 \\
      --cites E001,E002,E004

  python dr_engine/tools/calc.py verify --dir research/<slug>
  python dr_engine/tools/calc.py show --dir research/<slug>

Stdlib only.
"""

from __future__ import annotations

import argparse
import ast
import datetime as dt
import hashlib
import json
import math
import operator
import re
import statistics
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import units  # noqa: E402

EID_TOKEN_RE = re.compile(r"^E\d{3}$")
CID_TOKEN_RE = re.compile(r"^C\d{3}$")


# ---------------------------------------------------------------------------
# Quantitative & Statistical Helper Functions (Available inside expressions)
# ---------------------------------------------------------------------------

def norm_cdf(x: float) -> float:
  """Standard normal cumulative distribution function Phi(x)."""
  return 0.5 * (1.0 + math.erf(float(x) / math.sqrt(2.0)))


def norm_pdf(x: float) -> float:
  """Standard normal probability density function phi(x)."""
  return math.exp(-0.5 * float(x) ** 2) / math.sqrt(2.0 * math.pi)


def wilson_lower(k: float, n: float, z: float = 1.96) -> float:
  """Lower bound of the Wilson score confidence interval for binomial proportion k/n."""
  if n <= 0:
    raise ValueError("n must be > 0")
  p = k / n
  denom = 1.0 + (z * z) / n
  center = p + (z * z) / (2.0 * n)
  spread = z * math.sqrt((p * (1.0 - p) + (z * z) / (4.0 * n)) / n)
  return max(0.0, (center - spread) / denom)


def wilson_upper(k: float, n: float, z: float = 1.96) -> float:
  """Upper bound of the Wilson score confidence interval for binomial proportion k/n."""
  if n <= 0:
    raise ValueError("n must be > 0")
  p = k / n
  denom = 1.0 + (z * z) / n
  center = p + (z * z) / (2.0 * n)
  spread = z * math.sqrt((p * (1.0 - p) + (z * z) / (4.0 * n)) / n)
  return min(1.0, (center + spread) / denom)


def se_prop(p: float, n: float) -> float:
  """Standard error of a proportion sqrt(p*(1-p)/n)."""
  if n <= 0 or p < 0 or p > 1:
    raise ValueError("Require 0 <= p <= 1 and n > 0")
  return math.sqrt(p * (1.0 - p) / n)


def ev_binary(p: float, win_net: float, loss_net: float) -> float:
  """Expected value of a binary outcome: p * win_net - (1 - p) * loss_net."""
  return p * win_net - (1.0 - p) * loss_net


def ev_sunk_fee(
    p: float,
    gross_payoff: float,
    fee_sunk: float,
    friction: float = 0.0,
    tax_rate: float = 0.0,
    haircut: float = 0.0,
) -> float:
  """Net EV where fee_sunk and friction are incurred upfront and payoff is haircut & taxed."""
  net_payoff = gross_payoff * (1.0 - haircut) * (1.0 - tax_rate)
  return p * net_payoff - fee_sunk - friction


def breakeven_prob(net_payoff: float, fee_sunk: float, friction: float = 0.0) -> float:
  """Win probability p* required for ev_sunk_fee == 0."""
  if net_payoff <= 0:
    return 1.0
  return (fee_sunk + friction) / net_payoff


def kelly(p: float, b: float) -> float:
  """Full Kelly fraction (p*b - (1-p)) / b for win prob p and net odds b = W/L."""
  if b <= 0:
    raise ValueError("Payoff odds b must be > 0")
  return (p * b - (1.0 - p)) / b


def half_kelly(p: float, b: float) -> float:
  """Conservative Half-Kelly clipped at 0."""
  return 0.5 * max(0.0, kelly(p, b))


def sharpe(mean_ret: float, std_ret: float, periods_per_year: float = 252.0) -> float:
  """Annualized Sharpe ratio from per-period mean and standard deviation."""
  if std_ret <= 0:
    raise ValueError("std_ret must be > 0")
  return (mean_ret / std_ret) * math.sqrt(periods_per_year)


def ann_vol(period_vol: float, periods_per_year: float = 252.0) -> float:
  """Annualized volatility from per-period volatility."""
  return period_vol * math.sqrt(periods_per_year)


def cagr(start_val: float, end_val: float, years: float) -> float:
  """Compound annual growth rate."""
  if start_val <= 0 or end_val <= 0 or years <= 0:
    raise ValueError("start_val, end_val, and years must be > 0")
  return (end_val / start_val) ** (1.0 / years) - 1.0


def npv(rate: float, cashflows: list[float] | tuple[float, ...]) -> float:
  """Net present value of a sequence of cashflows [CF_0, CF_1, ...] at discount rate."""
  return sum(float(cf) / ((1.0 + rate) ** t) for t, cf in enumerate(cashflows))


def after_tax(gross: float, tax_rate: float, social_contrib: float = 0.0) -> float:
  """Net amount after social contribution deduction and income/corporate tax rate."""
  return gross * (1.0 - social_contrib) * (1.0 - tax_rate)


SAFE_CONSTS: dict[str, float] = {
    "pi": math.pi,
    "e": math.e,
}

SAFE_FUNCS: dict[str, Any] = {
    "sqrt": math.sqrt,
    "exp": math.exp,
    "log": math.log,
    "ln": math.log,
    "log10": math.log10,
    "log2": math.log2,
    "abs": abs,
    "min": min,
    "max": max,
    "round": round,
    "pow": pow,
    "ceil": math.ceil,
    "floor": math.floor,
    "mean": statistics.fmean,
    "median": statistics.median,
    "stdev": statistics.stdev,
    "pstdev": statistics.pstdev,
    "sum": sum,
    "norm_cdf": norm_cdf,
    "norm_pdf": norm_pdf,
    "wilson_lower": wilson_lower,
    "wilson_upper": wilson_upper,
    "se_prop": se_prop,
    "ev": ev_binary,
    "ev_binary": ev_binary,
    "ev_sunk_fee": ev_sunk_fee,
    "breakeven_prob": breakeven_prob,
    "kelly": kelly,
    "half_kelly": half_kelly,
    "sharpe": sharpe,
    "ann_vol": ann_vol,
    "cagr": cagr,
    "npv": npv,
    "after_tax": after_tax,
    # unit conversions (units.py): bp/%, RT/per-side, bp->R, annual->daily, holding cost,
    # long/short net financing
    **units.CALC_FUNCS,
}

_BIN_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
}

_UNARY_OPS = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}


def safe_eval(expr: str, variables: dict[str, float] | None = None) -> float:
  """Safely evaluates a mathematical expression via AST whitelist without eval()."""
  env: dict[str, float] = dict(SAFE_CONSTS)
  if variables:
    for k, v in variables.items():
      if not re.match(r"^[A-Za-z_]\w*$", k):
        raise ValueError(f"Invalid variable identifier: {k!r}")
      env[k] = float(v)

  tree = ast.parse(expr.strip(), mode="eval")

  def _eval_node(node: ast.AST) -> Any:
    if isinstance(node, ast.Expression):
      return _eval_node(node.body)
    if isinstance(node, ast.Constant):
      if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
        raise ValueError(f"Unsupported literal: {node.value!r}")
      return float(node.value)
    if isinstance(node, ast.Name):
      if node.id in env:
        return env[node.id]
      raise ValueError(f"Unknown variable: {node.id!r}")
    if isinstance(node, ast.UnaryOp):
      op_fn = _UNARY_OPS.get(type(node.op))
      if not op_fn:
        raise ValueError(f"Unsupported unary operator: {type(node.op).__name__}")
      return float(op_fn(_eval_node(node.operand)))
    if isinstance(node, ast.BinOp):
      left = float(_eval_node(node.left))
      right = float(_eval_node(node.right))
      if isinstance(node.op, ast.Pow):
        if abs(right) > 1000:
          raise ValueError(f"Exponent {right} exceeds safety cap 1000")
        return float(left ** right)
      op_fn = _BIN_OPS.get(type(node.op))
      if not op_fn:
        raise ValueError(f"Unsupported binary operator: {type(node.op).__name__}")
      return float(op_fn(left, right))
    if isinstance(node, (ast.List, ast.Tuple)):
      return [float(_eval_node(elt)) for elt in node.elts]
    if isinstance(node, ast.Call):
      if not isinstance(node.func, ast.Name) or node.func.id not in SAFE_FUNCS:
        fn_name = getattr(node.func, "id", repr(node.func))
        raise ValueError(f"Disallowed function call: {fn_name}")
      if node.keywords:
        raise ValueError("Keyword arguments are not supported in expressions; use positional args")
      args = [_eval_node(a) for a in node.args]
      return float(SAFE_FUNCS[node.func.id](*args))
    raise ValueError(f"Disallowed AST construct: {type(node).__name__}")

  val = float(_eval_node(tree))
  if math.isnan(val) or math.isinf(val):
    raise ValueError(f"Expression evaluated to non-finite value: {val}")
  return val


# ---------------------------------------------------------------------------
# JSONL Persistence, Number Binding & Integrity Verification
# ---------------------------------------------------------------------------

def _read_jsonl(path: Path) -> list[dict]:
  if not path.exists():
    return []
  return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _append_jsonl(path: Path, rec: dict) -> None:
  path.parent.mkdir(parents=True, exist_ok=True)
  with path.open("a", encoding="utf-8") as f:
    f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def _next_calc_id(records: list[dict]) -> str:
  nums = [int(r["id"][1:]) for r in records if CID_TOKEN_RE.match(r.get("id", ""))]
  return f"C{(max(nums) + 1) if nums else 1:03d}"


def canonical_calc_sha256(expr: str, variables: dict[str, float], result: float, cited_eids: list[str]) -> str:
  """Computes canonical SHA-256 over the formula, inputs, cited evidence IDs, and result."""
  payload = json.dumps(
      {
          "expr": expr.strip(),
          "variables": {k: round(float(v), 9) for k, v in sorted(variables.items())},
          "cited_eids": sorted(cited_eids),
          "result": round(float(result), 9),
      },
      sort_keys=True,
      separators=(",", ":"),
  )
  return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _expand_numeric_forms(val: float, unit: str = "") -> set[float]:
  """Generates exact and standard rounded representations (and % / bps scales when applicable)
  so prose references to [C###] bind deterministically in gate.py R3."""
  out: set[float] = set()
  for v in (val, abs(val)):
    for k in (0, 1, 2, 3, 4, 6):
      out.add(round(v, k))
    # Support decimal <-> percentage representation when value is a rate/probability or unit is %
    u_low = (unit or "").strip().lower()
    if u_low in ("%", "pct", "percent", "prob", "probability", "ratio", "") and 0.0 <= abs(val) <= 2.0:
      for k in (0, 1, 2, 3, 4):
        out.add(round(v * 100.0, k))
    if u_low in ("bps", "bp") and 0.0 <= abs(val) <= 1.0:
      for k in (0, 1, 2):
        out.add(round(v * 10000.0, k))
  return out


def bound_numbers_for_record(rec: dict) -> set[float]:
  """Returns all numeric values (outputs + input variables) bound by a verified [C###] record."""
  unit = rec.get("unit", "")
  nums = _expand_numeric_forms(float(rec["result"]), unit=unit)
  for v in (rec.get("variables") or {}).values():
    nums |= _expand_numeric_forms(float(v), unit="")
  return nums


def record_calculation(
    study_dir: Path,
    label: str,
    expr: str,
    variables: dict[str, float] | None = None,
    cited_eids: list[str] | None = None,
    unit: str = "",
) -> dict:
  """Evaluates an expression and appends a verified [C###] record to calculations.jsonl."""
  vars_clean = {k: float(v) for k, v in (variables or {}).items()}
  cites_clean = sorted({c.strip().upper() for c in (cited_eids or []) if c.strip()})
  for eid in cites_clean:
    if not EID_TOKEN_RE.match(eid):
      raise ValueError(f"Invalid evidence ID {eid!r}; expected E### (e.g. E001)")

  result = safe_eval(expr, vars_clean)
  calc_path = study_dir / "calculations.jsonl"
  records = _read_jsonl(calc_path)
  cid = _next_calc_id(records)
  digest = canonical_calc_sha256(expr, vars_clean, result, cites_clean)

  rec = {
      "id": cid,
      "ts": dt.datetime.now().isoformat(timespec="seconds"),
      "label": label.strip(),
      "expr": expr.strip(),
      "variables": vars_clean,
      "cited_eids": cites_clean,
      "result": round(result, 9),
      "unit": unit.strip(),
      "sha256": digest,
  }
  _append_jsonl(calc_path, rec)
  return rec


def load_calculations(study_dir: Path) -> dict[str, dict]:
  """Loads calculations.jsonl into an {id: record} dictionary."""
  return {r["id"]: r for r in _read_jsonl(study_dir / "calculations.jsonl")
          if "id" in r and not r.get("retracted")}


def verify_calculations(study_dir: Path, known_evidence_ids: set[str] | None = None) -> list[str]:
  """Re-evaluates every record in calculations.jsonl and checks SHA-256 and evidence links.
  Returns a list of human-readable failure messages (empty list = all valid)."""
  calc_path = study_dir / "calculations.jsonl"
  if not calc_path.exists():
    return []
  errors: list[str] = []
  seen_ids: set[str] = set()
  for idx, rec in enumerate(_read_jsonl(calc_path), 1):
    cid = rec.get("id", f"row#{idx}")
    if not CID_TOKEN_RE.match(cid):
      errors.append(f"{cid}: invalid calculation ID format (expected C###)")
      continue
    if cid in seen_ids:
      errors.append(f"{cid}: duplicate calculation ID in calculations.jsonl")
    seen_ids.add(cid)

    expr = rec.get("expr", "")
    variables = rec.get("variables") or {}
    cited_eids = rec.get("cited_eids") or []
    stored_res = rec.get("result")
    stored_sha = rec.get("sha256", "")

    if not isinstance(stored_res, (int, float)):
      errors.append(f"{cid}: missing numeric result")
      continue
    try:
      recomputed = safe_eval(expr, {k: float(v) for k, v in variables.items()})
    except Exception as exc:
      errors.append(f"{cid}: expression {expr!r} failed re-evaluation ({exc})")
      continue

    if not math.isclose(recomputed, float(stored_res), rel_tol=1e-7, abs_tol=1e-7):
      errors.append(f"{cid}: stored result {stored_res} != recomputed {recomputed:.9g}")
      continue

    expected_sha = canonical_calc_sha256(
        expr,
        {k: float(v) for k, v in variables.items()},
        recomputed,
        [str(c).upper() for c in cited_eids],
    )
    if stored_sha != expected_sha:
      errors.append(f"{cid}: sha256 mismatch (record edited by hand after evaluation)")

    if rec.get("retracted"):  # withdrawn (e.g. its evidence was retracted): kept, not cited
      continue
    for eid in cited_eids:
      if not EID_TOKEN_RE.match(str(eid)):
        errors.append(f"{cid}: invalid cited_eid {eid!r}")
      elif known_evidence_ids is not None and eid not in known_evidence_ids:
        errors.append(f"{cid}: cites unknown evidence ID {eid} not in evidence.jsonl")
  return errors


# ---------------------------------------------------------------------------
# Decision & Sensitivity Matrix Builder (Base / Bear / Stress + Flip Triggers)
# ---------------------------------------------------------------------------

def build_decision_matrix(
    study_dir: Path,
    title: str,
    cost: float,
    base_prob: float,
    base_payoff: float,
    bear_prob: float,
    bear_payoff: float,
    stress_prob: float,
    stress_payoff: float,
    friction: float = 0.0,
    tax_rate: float = 0.0,
    haircut: float = 0.0,
    cited_eids: list[str] | None = None,
    unit: str = "USD",
    mode: str = "sunk",
) -> dict[str, Any]:
  """Evaluates Base/Bear/Stress scenarios + exact Breakeven Flip Thresholds, logs [C###]
  records in calculations.jsonl, and returns structured results + Markdown table."""
  cites = cited_eids or []
  if mode not in ("sunk", "binary"):
    raise ValueError("mode must be 'sunk' (upfront fee paid regardless) or 'binary' (cost lost only on failure)")

  scenarios = [
      ("Base", base_prob, base_payoff),
      ("Bear", bear_prob, bear_payoff),
      ("Stress", stress_prob, stress_payoff),
  ]
  scen_records: dict[str, dict] = {}
  for name, prob, payoff in scenarios:
    if mode == "sunk":
      expr = "ev_sunk_fee(p, payoff, cost, friction, tax, haircut)"
    else:
      expr = "p * (payoff * (1 - haircut) * (1 - tax) - friction) - (1 - p) * (cost + friction)"
    rec = record_calculation(
        study_dir=study_dir,
        label=f"{title} — {name} Scenario Net EV",
        expr=expr,
        variables={
            "p": prob,
            "payoff": payoff,
            "cost": cost,
            "friction": friction,
            "tax": tax_rate,
            "haircut": haircut,
        },
        cited_eids=cites,
        unit=unit,
    )
    scen_records[name] = rec

  # Regime-weighted composite EV (0.50 Base + 0.35 Bear + 0.15 Stress)
  comp_rec = record_calculation(
      study_dir=study_dir,
      label=f"{title} — Regime-Weighted Expected Value (50/35/15)",
      expr="0.50 * ev_base + 0.35 * ev_bear + 0.15 * ev_stress",
      variables={
          "ev_base": scen_records["Base"]["result"],
          "ev_bear": scen_records["Bear"]["result"],
          "ev_stress": scen_records["Stress"]["result"],
      },
      cited_eids=cites,
      unit=unit,
  )

  # Flip Threshold 1: Breakeven Win Probability p* in Base scenario
  if mode == "sunk":
    be_prob_expr = "breakeven_prob(payoff * (1 - haircut) * (1 - tax), cost, friction)"
  else:
    be_prob_expr = "(cost + friction) / ((payoff * (1 - haircut) * (1 - tax)) + cost)"
  be_prob_rec = record_calculation(
      study_dir=study_dir,
      label=f"{title} — Base Breakeven Win Probability p*",
      expr=be_prob_expr,
      variables={
          "payoff": base_payoff,
          "cost": cost,
          "friction": friction,
          "tax": tax_rate,
          "haircut": haircut,
      },
      cited_eids=cites,
      unit="%",
  )

  # Flip Threshold 2: Max Tolerable Cost / Fee C* before Base Net EV <= 0
  if mode == "sunk":
    max_cost_expr = "p * payoff * (1 - haircut) * (1 - tax) - friction"
  else:
    max_cost_expr = "(p * (payoff * (1 - haircut) * (1 - tax) - friction) - (1 - p) * friction) / max(1e-9, 1 - p)"
  max_cost_rec = record_calculation(
      study_dir=study_dir,
      label=f"{title} — Base Max Tolerable Upfront Cost C*",
      expr=max_cost_expr,
      variables={
          "p": base_prob,
          "payoff": base_payoff,
          "friction": friction,
          "tax": tax_rate,
          "haircut": haircut,
      },
      cited_eids=cites,
      unit=unit,
  )

  cite_str = ", ".join(cites)
  def _ref(cid: str) -> str:
    return f"[{cite_str}, {cid}]" if cite_str else f"[{cid}]"

  md_lines = [
      f"### Decision & Sensitivity Matrix: {title}",
      "",
      "| Scenario / Metric | Win Prob ($p$) | Gross Payoff | Cost + Friction | Net EV / Threshold | Verified Ref |",
      "| :-- | :-- | :-- | :-- | :-- | :-- |",
      f"| **Base** (50% wt) | {base_prob * 100:.1f}% | {base_payoff:,.2f} {unit} | {cost + friction:,.2f} {unit} | **{scen_records['Base']['result']:,.2f} {unit}** | {_ref(scen_records['Base']['id'])} |",
      f"| **Bear** (35% wt) | {bear_prob * 100:.1f}% | {bear_payoff:,.2f} {unit} | {cost + friction:,.2f} {unit} | **{scen_records['Bear']['result']:,.2f} {unit}** | {_ref(scen_records['Bear']['id'])} |",
      f"| **Stress** (15% wt) | {stress_prob * 100:.1f}% | {stress_payoff:,.2f} {unit} | {cost + friction:,.2f} {unit} | **{scen_records['Stress']['result']:,.2f} {unit}** | {_ref(scen_records['Stress']['id'])} |",
      f"| **Regime-Weighted EV** | — | — | — | **{comp_rec['result']:,.2f} {unit}** | {_ref(comp_rec['id'])} |",
      f"| **Flip Trigger: Min Win Prob ($p^*$)** | **{be_prob_rec['result'] * 100:.2f}%** | {base_payoff:,.2f} {unit} | {cost + friction:,.2f} {unit} | Net EV = 0 {unit} | {_ref(be_prob_rec['id'])} |",
      f"| **Flip Trigger: Max Cost ($C^*$)** | {base_prob * 100:.1f}% | {base_payoff:,.2f} {unit} | **{max_cost_rec['result']:,.2f} {unit}** | Net EV = 0 {unit} | {_ref(max_cost_rec['id'])} |",
  ]
  return {
      "scenarios": scen_records,
      "composite": comp_rec,
      "breakeven_prob": be_prob_rec,
      "max_cost": max_cost_rec,
      "markdown": "\n".join(md_lines),
  }


# ---------------------------------------------------------------------------
# CLI Entrypoints
# ---------------------------------------------------------------------------

def _parse_vars(var_list: list[str] | None) -> dict[str, float]:
  out: dict[str, float] = {}
  for item in var_list or []:
    if "=" not in item:
      raise ValueError(f"--var must be NAME=VALUE, got {item!r}")
    k, v = item.split("=", 1)
    out[k.strip()] = float(v.strip())
  return out


def _parse_cites(cites_str: str | None) -> list[str]:
  if not cites_str:
    return []
  return [c.strip().upper() for c in cites_str.split(",") if c.strip()]


def cmd_eval(args: argparse.Namespace) -> int:
  try:
    rec = record_calculation(
        study_dir=Path(args.dir),
        label=args.label,
        expr=args.expr,
        variables=_parse_vars(args.var),
        cited_eids=_parse_cites(args.cites),
        unit=args.unit or "",
    )
  except Exception as exc:
    print(f"REFUSED: {exc}", file=sys.stderr)
    return 1
  cites = ", ".join(rec["cited_eids"])
  cite_hint = f"[{cites}, {rec['id']}]" if cites else f"[{rec['id']}]"
  unit_sfx = f" {rec['unit']}" if rec["unit"] else ""
  print(f"{rec['id']}  = {rec['result']:g}{unit_sfx}  ({rec['label']})  cite as {cite_hint}")
  return 0


def cmd_decision(args: argparse.Namespace) -> int:
  try:
    res = build_decision_matrix(
        study_dir=Path(args.dir),
        title=args.title,
        cost=args.cost,
        base_prob=args.base_prob,
        base_payoff=args.base_payoff,
        bear_prob=args.bear_prob,
        bear_payoff=args.bear_payoff,
        stress_prob=args.stress_prob,
        stress_payoff=args.stress_payoff,
        friction=args.friction,
        tax_rate=args.tax_rate,
        haircut=args.haircut,
        cited_eids=_parse_cites(args.cites),
        unit=args.unit,
        mode=args.mode,
    )
  except Exception as exc:
    print(f"REFUSED: {exc}", file=sys.stderr)
    return 1
  print(res["markdown"])
  return 0


def cmd_verify(args: argparse.Namespace) -> int:
  d = Path(args.dir)
  ev_path = d / "evidence.jsonl"
  known_eids = ({r["id"] for r in _read_jsonl(ev_path) if "id" in r and not r.get("retracted")}
                if ev_path.exists() else None)
  errors = verify_calculations(d, known_evidence_ids=known_eids)
  calcs = load_calculations(d)
  if errors:
    print(f"[FAIL] {d}/calculations.jsonl ({len(errors)} error(s) across {len(calcs)} record(s)):")
    for err in errors:
      print(f"  - {err}")
    return 1
  print(f"[PASS] {d}/calculations.jsonl ({len(calcs)} deterministic calculation(s) verified)")
  return 0


def cmd_retract(args: argparse.Namespace) -> int:
  """Withdraw a calculation (wrong input, or it cites a retracted E###). The record stays in
  the file, marked; gate.py stops checking it and a report citing it fails R2."""
  d = Path(args.dir)
  path = d / "calculations.jsonl"
  records = _read_jsonl(path) if path.exists() else []
  if not (args.reason or "").strip():
    print("REFUSED: --reason is required (e.g. 'input E001 retracted, replaced by C008')")
    return 1
  target = next((r for r in records if r.get("id") == args.id), None)
  if target is None or target.get("retracted"):
    print(f"REFUSED: {args.id} is not an active calculation in {path}")
    return 1
  target["retracted"] = {"ts": dt.datetime.now().isoformat(timespec="seconds"), "reason": args.reason.strip()}
  with path.open("w", encoding="utf-8", newline="\n") as f:
    for r in records:
      f.write(json.dumps(r, ensure_ascii=False) + "\n")
  print(f"{args.id}  retracted  ({args.reason.strip()}) - re-run calc.py eval with corrected inputs if needed")
  return 0


def cmd_show(args: argparse.Namespace) -> int:
  d = Path(args.dir)
  records = _read_jsonl(d / "calculations.jsonl")
  if not records:
    print("(no calculations logged in calculations.jsonl)")
    return 0
  for r in records:
    unit_sfx = f" {r.get('unit')}" if r.get("unit") else ""
    cites = ",".join(r.get("cited_eids") or [])
    print(f"{r['id']}  {r['result']:>12g}{unit_sfx:<5}  cites=[{cites}]  {r['label']}  ::  {r['expr']}")
  return 0


def main(argv: list[str] | None = None) -> int:
  if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
  ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
  sub = ap.add_subparsers(dest="cmd", required=True)

  p_eval = sub.add_parser("eval", help="evaluate expression and log [C###] in calculations.jsonl")
  p_eval.add_argument("--dir", required=True)
  p_eval.add_argument("--label", required=True)
  p_eval.add_argument("--expr", required=True)
  p_eval.add_argument("--var", action="append", help="variable assignment NAME=VALUE (repeatable)")
  p_eval.add_argument("--cites", default="", help="comma-separated evidence IDs, e.g. E001,E002")
  p_eval.add_argument("--unit", default="", help="unit label, e.g. USD, EUR, %%, bps")
  p_eval.set_defaults(fn=cmd_eval)

  p_dec = sub.add_parser("decision", help="compute Base/Bear/Stress EV + breakeven flip thresholds")
  p_dec.add_argument("--dir", required=True)
  p_dec.add_argument("--title", required=True)
  p_dec.add_argument("--cost", type=float, required=True)
  p_dec.add_argument("--base-prob", type=float, required=True)
  p_dec.add_argument("--base-payoff", type=float, required=True)
  p_dec.add_argument("--bear-prob", type=float, required=True)
  p_dec.add_argument("--bear-payoff", type=float, required=True)
  p_dec.add_argument("--stress-prob", type=float, required=True)
  p_dec.add_argument("--stress-payoff", type=float, required=True)
  p_dec.add_argument("--friction", type=float, default=0.0)
  p_dec.add_argument("--tax-rate", type=float, default=0.0)
  p_dec.add_argument("--haircut", type=float, default=0.0)
  p_dec.add_argument("--cites", default="", help="comma-separated evidence IDs")
  p_dec.add_argument("--unit", default="USD")
  p_dec.add_argument("--mode", choices=("sunk", "binary"), default="sunk")
  p_dec.set_defaults(fn=cmd_decision)

  p_ver = sub.add_parser("verify", help="re-evaluate and verify all [C###] SHA-256 digests")
  p_ver.add_argument("--dir", required=True)
  p_ver.set_defaults(fn=cmd_verify)

  p_ret = sub.add_parser("retract", help="withdraw a [C###] record (kept in the file, marked)")
  p_ret.add_argument("--dir", required=True)
  p_ret.add_argument("--id", required=True)
  p_ret.add_argument("--reason", required=True)
  p_ret.set_defaults(fn=cmd_retract)
  p_show = sub.add_parser("show", help="print all logged [C###] calculations")
  p_show.add_argument("--dir", required=True)
  p_show.set_defaults(fn=cmd_show)

  args = ap.parse_args(argv)
  return args.fn(args)


if __name__ == "__main__":
  sys.exit(main())
