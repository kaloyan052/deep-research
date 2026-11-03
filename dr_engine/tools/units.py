"""Units and dimensions for finance and science claims.

Two jobs:

1. Parse the unit of a claim ("3 USD per side", "6 USD RT", "6% p.a.", "1.64 bp/day",
   "1.5 bp per trade", "0.07 R") into a dimension and a factor to a canonical base, so
   `claims.py` can tell equal quantities written differently from real conflicts:
     3 USD per side  ==  6 USD per lot RT            (same quantity, no conflict)
     6% p.a.         ==  1.64 bp/day                 (same quantity at ACT/365)
     6% p.a.         vs  1.5 bp per trade            (different dimensions: axis `unit` -
                                                      a holding period is needed, trap G9)
2. Deterministic converters for the errors the audits keep finding:
     - annual swap / financing rate -> cost per day and per holding period. Never compare
       an annual rate with a per-trade hurdle; C_hold = spread + nights x daily rate.
     - long/short book financing: the long leg pays its rate, the short leg receives its
       rate (and pays when that rate is negative). On equal notionals the benchmark cancels
       and the net cost is the sum of the two markups - not a flat rate on both legs.
     - bp <-> %, round-turn <-> per-side, bp of price <-> R (risk units: cost / stop).
   The float versions are registered in calc.py, so a conversion can be logged as [C###]:
     calc.py eval --expr "hold_cost_bp(3, 600, 1.5)" ...

  python dr_engine/tools/units.py parse "USD per side"
  python dr_engine/tools/units.py convert 3 "USD per side" "USD per lot RT"
  python dr_engine/tools/units.py hold --nights 3 --annual-bp 600 [--spread-bp 1.5] [--day-count 365]
  python dr_engine/tools/units.py ls --long-pct 8.5 --short-pct 2.5 [--long-notional 1e6 --short-notional 1e6]
  python dr_engine/tools/units.py r --cost-bp 0.7 --stop-bp 10

Canonical bases: ratios in bp (1% = 100 bp), rates per year (a day is 1/day_count of a
year, default 365), per-trade and per-lot costs round-turn, money per currency (no FX
conversion - different currencies are different dimensions). Stdlib only.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass

DAY_COUNT = 365

CURRENCIES = {"usd": "USD", "$": "USD", "eur": "EUR", "€": "EUR", "gbp": "GBP", "£": "GBP",
              "jpy": "JPY", "¥": "JPY", "chf": "CHF", "aud": "AUD", "cad": "CAD", "nzd": "NZD",
              "bgn": "BGN", "лв": "BGN", "лева": "BGN"}
CURRENCY_RE = re.compile(r"(?<![a-zа-я])(usd|eur|gbp|jpy|chf|aud|cad|nzd|bgn|лева|лв)(?![a-zа-я])|[$€£¥]")
SIDE_RT_RE = re.compile(r"(?<![a-z])(rt|r/t|round[- ]?turn|round[- ]?trip)(?![a-z])")
SIDE_ONE_RE = re.compile(r"(?<![a-z])(per[- ]side|a side|each[- ]way|one[- ]way|single[- ]side|"
                         r"half[- ]turn|на страна)(?![a-z])")
YEAR_RE = re.compile(r"(?<![a-z])p\.?\s?a\.?(?![a-z])|per annum|annuali[sz]ed|annual(?:ly)?|"
                     r"/\s*y(?:ea)?r|per y(?:ea)?r|a year|годишно|на година")
DAY_RE = re.compile(r"/\s*(?:day|night|d)(?![a-z])|per (?:day|night)|daily|nightly|a day|на ден|дневно")
MONTH_RE = re.compile(r"/\s*month|per month|monthly|a month|месечно")
TRADE_RE = re.compile(r"/\s*trade|per trade|a trade|на сделка")
LOT_RE = re.compile(r"/\s*lot|per lot|a lot|на лот|(?<![a-z])lots?(?![a-z])")
CONTRACT_RE = re.compile(r"/\s*contract|per contract|(?<![a-z])contracts?(?![a-z])")
PCT_RE = re.compile(r"%|(?<![a-z])(percent|pct|процента?)(?![a-z])")
BP_RE = re.compile(r"(?<![a-z])(bps?|basis points?|б\.?т\.?)(?![a-z])")
PIP_RE = re.compile(r"(?<![a-z])pips?(?![a-z])")
POINT_RE = re.compile(r"(?<![a-z])(pts?|points?|пункта?|пункт)(?![a-z])")
R_RE = re.compile(r"(?<![a-z])r(?![a-z])")
DAYS_RE = re.compile(r"(?<![a-z])(days?|nights?|дни|ден)(?![a-z])")
YEARS_RE = re.compile(r"(?<![a-z])(years?|yrs?|години|година)(?![a-z])")


@dataclass(frozen=True)
class Unit:
  dim: str       # canonical dimension, e.g. "USD/lot", "bp/year", "bp/trade", "bp", "R", "days"
  factor: float  # multiply a value in this unit by factor to get the canonical base
  label: str     # human label of the canonical base


@dataclass(frozen=True)
class Quantity:
  value: float
  dim: str
  label: str

  def __str__(self) -> str:
    return f"{self.value:g} {self.label}"


def parse(unit: str, day_count: int = DAY_COUNT) -> Unit | None:
  """Unit string -> canonical dimension and factor, or None when the unit is unknown."""
  s = (unit or "").strip().lower()
  if not s:
    return None
  side = 1.0
  side_given = False
  if SIDE_ONE_RE.search(s):
    side, side_given = 2.0, True
    s = SIDE_ONE_RE.sub(" ", s)
  elif SIDE_RT_RE.search(s):
    side_given = True
    s = SIDE_RT_RE.sub(" ", s)
  per, per_factor = "", 1.0
  for rx, name, f in ((YEAR_RE, "year", 1.0), (DAY_RE, "year", float(day_count)),
                      (MONTH_RE, "year", 12.0), (TRADE_RE, "trade", 1.0),
                      (CONTRACT_RE, "contract", 1.0), (LOT_RE, "lot", 1.0)):
    if rx.search(s):
      per, per_factor = name, f
      s = rx.sub(" ", s)
      break
  m = CURRENCY_RE.search(s)
  if m:
    base, base_label, factor = CURRENCIES[m.group(1) or m.group(0)], None, 1.0
    base_label = base
  elif PCT_RE.search(s):
    base, base_label, factor = "bp", "bp", 100.0
  elif BP_RE.search(s):
    base, base_label, factor = "bp", "bp", 1.0
  elif PIP_RE.search(s):
    base, base_label, factor = "pips", "pips", 1.0
  elif POINT_RE.search(s):
    base, base_label, factor = "points", "points", 1.0
  elif R_RE.search(s):
    return Unit("R", 1.0, "R")  # risk units are per trade by definition
  elif not per and DAYS_RE.search(s):
    return Unit("days", 1.0, "days")
  elif not per and YEARS_RE.search(s):
    return Unit("days", float(day_count), "days")
  else:
    return None
  if side_given and not per:
    per = "lot" if base not in ("bp", "pips", "points") else "trade"
  if per == "year":
    side = 1.0  # a side qualifier means nothing for a rate per unit of time
  dim = f"{base}/{per}" if per else base
  label = f"{base_label}/{per}" if per == "year" else base_label
  if per in ("lot", "trade", "contract"):
    if side_given:
      label = f"{base_label} per {per} RT"
    else:
      # "3 USD per lot" may be per side or round-turn: comparing it with an explicit RT or
      # per-side figure is a unit question (a 2x error hides here), not a value conflict.
      dim, label = dim + "?", f"{base_label} per {per} (side unspecified)"
  return Unit(dim, factor * per_factor * side, label)


def quantity(value: float, unit: str, day_count: int = DAY_COUNT) -> Quantity | None:
  u = parse(unit, day_count)
  return Quantity(value * u.factor, u.dim, u.label) if u else None


def convert(value: float, from_unit: str, to_unit: str, day_count: int = DAY_COUNT) -> float:
  a, b = parse(from_unit, day_count), parse(to_unit, day_count)
  if not a or not b:
    raise ValueError(f"unknown unit: {from_unit if not a else to_unit!r}")
  if a.dim != b.dim:
    raise ValueError(f"cannot convert {a.dim} to {b.dim} without more inputs "
                     f"(an annual rate needs a holding period; bp of price needs a stop for R)")
  return value * a.factor / b.factor


def same_quantity(va: float, ua: str, vb: float, ub: str, tol: float = 0.05) -> bool | None:
  """True/False when both units parse to the same dimension; None when not comparable."""
  qa, qb = quantity(va, ua), quantity(vb, ub)
  if not qa or not qb or qa.dim != qb.dim:
    return None
  denom = max(abs(qa.value), abs(qb.value)) or 1.0
  return abs(qa.value - qb.value) / denom <= tol


# ---------------------------------------------------------------- converters
def bp_to_pct(bp: float) -> float:
  return bp / 100.0


def pct_to_bp(pct: float) -> float:
  return pct * 100.0


def side_to_rt(per_side: float) -> float:
  return 2.0 * per_side


def rt_to_side(rt: float) -> float:
  return rt / 2.0


def bp_to_r(cost_bp: float, stop_bp: float) -> float:
  """Cost in R (risk units) when both cost and stop distance are in bp of price."""
  if stop_bp <= 0:
    raise ValueError("stop distance must be positive")
  return cost_bp / stop_bp


def r_to_bp(r: float, stop_bp: float) -> float:
  return r * stop_bp


def money_to_r(cost: float, risk: float) -> float:
  if risk <= 0:
    raise ValueError("risk per trade must be positive")
  return cost / risk


def daily_bp(annual_bp: float, day_count: int = DAY_COUNT) -> float:
  """Annual rate in bp -> bp per calendar day (financing accrues every night, weekends
  included; FX brokers book the weekend as a triple charge on one night)."""
  return annual_bp / day_count


def hold_cost_bp(nights: float, annual_bp: float, spread_bp: float = 0.0,
                 day_count: int = DAY_COUNT) -> float:
  """Cost of one trade in bp of notional: spread + nights x daily financing (trap G9)."""
  return spread_bp + nights * annual_bp / day_count


def ls_financing(long_pct: float, short_pct: float, long_notional: float = 1.0,
                 short_notional: float = 1.0, day_count: int = DAY_COUNT) -> dict:
  """Long/short book financing per year and per day.

  The long leg PAYS long_pct on its notional; the short leg RECEIVES short_pct on its
  notional (when short_pct is negative the short leg pays too). With a benchmark B and
  markups mL, mS: long_pct = B + mL, short_pct = B - mS, so on equal notionals the net
  is mL + mS and B cancels. Charging long_pct on both legs is the classic error.
  """
  long_cost = long_notional * long_pct / 100.0
  short_income = short_notional * short_pct / 100.0
  net = long_cost - short_income
  gross = long_notional
  net_pct = 100.0 * net / gross if gross else 0.0
  return {"long_cost_per_year": long_cost, "short_income_per_year": short_income,
          "net_cost_per_year": net, "net_cost_per_day": net / day_count,
          "net_pct_pa_of_long_notional": net_pct,
          "net_bp_per_day_of_long_notional": pct_to_bp(net_pct) / day_count,
          "wrong_flat_cost_per_year": (long_notional + short_notional) * long_pct / 100.0}


def ls_net_pct(long_pct: float, short_pct: float) -> float:
  """Net financing in % p.a. of a dollar-neutral book: long pays, short receives."""
  return long_pct - short_pct


def ls_net_bp_day(long_pct: float, short_pct: float, day_count: int = DAY_COUNT) -> float:
  return pct_to_bp(long_pct - short_pct) / day_count


CALC_FUNCS = {
    "bp_to_pct": bp_to_pct, "pct_to_bp": pct_to_bp, "side_to_rt": side_to_rt,
    "rt_to_side": rt_to_side, "bp_to_r": bp_to_r, "r_to_bp": r_to_bp, "money_to_r": money_to_r,
    "daily_bp": daily_bp, "hold_cost_bp": hold_cost_bp, "ls_net_pct": ls_net_pct,
    "ls_net_bp_day": ls_net_bp_day,
}


# ----------------------------------------------------------------------- CLI
def main(argv: list[str] | None = None) -> int:
  if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
  ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
  sub = ap.add_subparsers(dest="cmd", required=True)
  p = sub.add_parser("parse")
  p.add_argument("unit")
  p = sub.add_parser("convert")
  p.add_argument("value", type=float)
  p.add_argument("from_unit")
  p.add_argument("to_unit")
  p = sub.add_parser("hold", help="spread + nights x daily financing, in bp")
  p.add_argument("--nights", type=float, required=True)
  p.add_argument("--annual-bp", type=float, required=True)
  p.add_argument("--spread-bp", type=float, default=0.0)
  p.add_argument("--day-count", type=int, default=DAY_COUNT)
  p = sub.add_parser("ls", help="long/short net financing")
  p.add_argument("--long-pct", type=float, required=True)
  p.add_argument("--short-pct", type=float, required=True)
  p.add_argument("--long-notional", type=float, default=1.0)
  p.add_argument("--short-notional", type=float, default=1.0)
  p.add_argument("--day-count", type=int, default=DAY_COUNT)
  p = sub.add_parser("r", help="cost in R = cost_bp / stop_bp")
  p.add_argument("--cost-bp", type=float, required=True)
  p.add_argument("--stop-bp", type=float, required=True)
  args = ap.parse_args(argv)
  try:
    if args.cmd == "parse":
      u = parse(args.unit)
      print(json.dumps(u.__dict__ if u else None, ensure_ascii=False))
    elif args.cmd == "convert":
      print(f"{convert(args.value, args.from_unit, args.to_unit):g} {args.to_unit}")
    elif args.cmd == "hold":
      d = daily_bp(args.annual_bp, args.day_count)
      total = hold_cost_bp(args.nights, args.annual_bp, args.spread_bp, args.day_count)
      print(f"daily financing {d:.4f} bp; {args.nights:g} nights -> {args.nights * d:.4f} bp; "
            f"with spread {args.spread_bp:g} bp -> {total:.4f} bp per trade")
    elif args.cmd == "ls":
      print(json.dumps(ls_financing(args.long_pct, args.short_pct, args.long_notional,
                                    args.short_notional, args.day_count), indent=2))
    elif args.cmd == "r":
      print(f"{bp_to_r(args.cost_bp, args.stop_bp):.4f} R")
  except ValueError as e:
    print(f"ERROR: {e}")
    return 1
  return 0


if __name__ == "__main__":
  sys.exit(main())
