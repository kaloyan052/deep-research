"""Deterministic Epistemic Index (EI) and Mechanical Confidence Ceiling for Deep Research.

Computes an objective, non-gameable epistemic scorecard from a research study folder:
  EI = 100 * (0.35 * A_E + 0.25 * T_D + 0.20 * S_K + 0.20 * V_Q)

Components:
  A_E  Authority Score        (tier-weighted T1=1.0, T2=0.90, T3=0.80, T4=0.45, T5=0.15; manual 0.75x)
  T_D  Triangulation Score    (independent T1-T4 domains + SQ primary coverage + multi-source SQ share)
  S_K  Kill-Survival Score    (disconfirmation depth across K1..Kn + addressed 'contradicts' evidence)
  V_Q  Quantitative Grounding (share of claim units bound to verbatim [E###] quotes or verified [C###])

Also computes the Mechanical Confidence Ceiling (High / Medium / Low) and checks whether
report.md over-claims confidence beyond what the evidence mathematically supports (Gate R10).

Usage:
  python dr_engine/tools/formula.py research/<dir>
  python dr_engine/tools/formula.py research/<dir> --markdown
  python dr_engine/tools/formula.py research/<dir> --json

Stdlib only.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
import calc  # noqa: E402
import check_report as cr  # noqa: E402
from evidence import _jsonl, load_evidence  # noqa: E402
from traps import (  # noqa: E402
    FORMAL_CALC_RE,
    SAMPLE_SIZE_RE,
    is_community_domain,
    is_tertiary_encyclopedia,
    is_unofficial_github,
)

TIER_WEIGHTS: dict[str, float] = {
    "T1": 1.00,
    "T2": 0.90,
    "T3": 0.80,
    "T4": 0.45,
    "T5": 0.15,
}

CONF_RANK: dict[str, int] = {
    "Low": 1,
    "Medium": 2,
    "High": 3,
}

EID_RE = re.compile(r"\bE\d{3}\b")
CID_RE = re.compile(r"\bC\d{3}\b")
CONF_SECTION_RE = re.compile(r"^#{1,3}\s*(confidence|certainty|увереност|степен на сигурност)\b", re.I)

# Matches explicit overall confidence metadata lines in title block / Executive Decision Card
OVERALL_CONF_META_RE = re.compile(
    r"^\s*(?:[-*+]\s+|\|\s*)?\*{0,2}"
    r"(?:Overall\s+Confidence|Mechanical\s+Confidence|Confidence\s+Level|Confidence|"
    r"Обща\s+увереност|Механична\s+увереност|Степен\s+на\s+сигурност|Увереност|Доверие)"
    r"\*{0,2}\s*(?::|\|)\*{0,2}\s*\*{0,2}"
    r"(High|Medium|Moderate|Low|Висока|Високо|Средна|Средно|Умерена|Ниска|Ниско)\b",
    re.I,
)

# Matches leading confidence declaration at start of ## Confidence section
SECTION_CONF_DECL_RE = re.compile(
    r"^\s*(?:[-*+]\s+)?\*{0,2}"
    r"(?:(?:Overall|Обща|Общо|Ниво)\s*[:\-–]\s*\*{0,2})?"
    r"(High|Medium|Moderate|Low|Висока|Високо|Средна|Средно|Умерена|Ниска|Ниско)\b"
    r"(?:\*{0,2})\s*(?:[.—\-–:(]|$)",
    re.I,
)

VERDICTS = ("confirmed", "refuted", "unresolved")


def _canonical_conf(token: str) -> str | None:
  t = token.strip().lower()
  if t in ("high", "висока", "високо"):
    return "High"
  if t in ("medium", "moderate", "средна", "средно", "умерена"):
    return "Medium"
  if t in ("low", "ниска", "ниско"):
    return "Low"
  return None


def extract_declared_confidence(report_text: str) -> tuple[str | None, int | None, str]:
  """Extracts an explicit overall report confidence level if declared in metadata or ## Confidence.

  Returns (canonical_level, line_number, matched_line) or (None, None, "").
  """
  lines = report_text.splitlines()
  # 1. Check metadata / Executive Decision Card in the first 50 lines
  for idx, line in enumerate(lines[:50], 1):
    m = OVERALL_CONF_META_RE.match(line)
    if m:
      canon = _canonical_conf(m.group(1))
      if canon:
        return canon, idx, line.strip()

  # 2. Check the opening declaration of ## Confidence / ## Увереност section
  in_conf_sec = False
  checked_in_sec = 0
  for idx, line in enumerate(lines, 1):
    s = line.strip()
    if s.startswith("#"):
      if CONF_SECTION_RE.match(s):
        in_conf_sec = True
        checked_in_sec = 0
        continue
      if in_conf_sec:
        break
    if in_conf_sec and s:
      checked_in_sec += 1
      m = OVERALL_CONF_META_RE.match(s) or SECTION_CONF_DECL_RE.match(s)
      if m:
        canon = _canonical_conf(m.group(1))
        if canon:
          return canon, idx, s
      if checked_in_sec >= 2:
        break
  return None, None, ""


def _parse_plan(plan_text: str) -> tuple[list[str], dict[str, dict]]:
  sqs: list[str] = []
  kills: dict[str, dict] = {}
  for line in plan_text.splitlines():
    s = line.strip()
    m_sq = re.match(r"^\|\s*(SQ\d+)\s*\|", s)
    if m_sq:
      sqs.append(m_sq.group(1))
    m_k = re.match(r"^\|\s*(K\d+)\s*\|", s)
    if m_k:
      low = s.lower()
      verdict = next((v for v in VERDICTS if re.search(rf"\b{v}\b", low)), "pending")
      kills[m_k.group(1)] = {"verdict": verdict, "evidence": EID_RE.findall(s)}
  return sqs, kills


def _host(url: str) -> str:
  try:
    h = (urlparse(url).hostname or "").lower()
    return h[4:] if h.startswith("www.") else h
  except Exception:
    return ""


def _effective_tier(raw_tier: str, url: str, publisher: str = "") -> str:
  """Downgrades inflated source tiers to their true epistemic tier (T5 community, T4 encyclopedia)."""
  t = (raw_tier or "T5").upper()
  if is_community_domain(url) or is_unofficial_github(url, publisher=publisher)[0]:
    return "T5"
  if is_tertiary_encyclopedia(url) and t in ("T1", "T2", "T3"):
    return "T4"
  return t if t in TIER_WEIGHTS else "T5"


def compute_epistemic_score(study_dir: Path, report_path: Path | None = None) -> dict[str, Any]:
  """Computes the deterministic Epistemic Index (EI) and Mechanical Confidence Ceiling."""
  d = Path(study_dir)
  index = {r["id"]: r for r in _jsonl(d / "sources" / "index.jsonl") if "id" in r}
  evidence = {r["id"]: r for r in load_evidence(d) if "id" in r}
  searches = _jsonl(d / "searches.jsonl")
  calcs = calc.load_calculations(d)

  plan_path = d / "plan.md"
  sqs, kills = _parse_plan(plan_path.read_text(encoding="utf-8")) if plan_path.exists() else ([], {})

  # 1. Authority Score (A_E) using inflation-corrected effective tiers
  tier_counts = {t: 0 for t in ("T1", "T2", "T3", "T4", "T5")}
  eff_tiers: dict[str, str] = {}
  weighted_sum = 0.0
  manual_count = 0
  non_t5_domains: set[str] = set()
  all_domains: set[str] = set()

  for eid, r in evidence.items():
    src = index.get(r.get("source", ""), {})
    url = r.get("url") or src.get("url", "")
    pub = r.get("publisher", "") or src.get("publisher", "")
    t = _effective_tier(r.get("tier", "T5"), url, publisher=pub)
    eff_tiers[eid] = t
    tier_counts[t] += 1
    w = TIER_WEIGHTS.get(t, 0.15)
    if src.get("via") == "manual":
      w *= 0.75
      manual_count += 1
    weighted_sum += w
    h = _host(url)
    if h:
      all_domains.add(h)
      if t != "T5":
        non_t5_domains.add(h)

  n_ev = len(evidence)
  a_e = (weighted_sum / n_ev) if n_ev > 0 else 0.0
  primary_count = tier_counts["T1"] + tier_counts["T2"] + tier_counts["T3"]
  primary_share = (primary_count / n_ev) if n_ev > 0 else 0.0
  manual_share = (manual_count / n_ev) if n_ev > 0 else 0.0

  # 2. Triangulation & Coverage Score (T_D)
  domain_factor = min(1.0, len(non_t5_domains) / 5.0)
  by_sq_records: dict[str, list[dict]] = {}
  for r in evidence.values():
    by_sq_records.setdefault(r.get("sq", ""), []).append(r)

  if sqs:
    sq_primary = sum(
        1 for sq in sqs
        if any(eff_tiers.get(r.get("id", "")) in ("T1", "T2", "T3") for r in by_sq_records.get(sq, []))
    ) / len(sqs)
    sq_multi = sum(
        1 for sq in sqs
        if len({r.get("source") for r in by_sq_records.get(sq, [])}) >= 2
        or len(by_sq_records.get(sq, [])) >= 2
    ) / len(sqs)
  else:
    sq_primary = primary_share
    sq_multi = 1.0 if len(non_t5_domains) >= 2 else 0.0

  t_d = 0.45 * domain_factor + 0.35 * sq_primary + 0.20 * sq_multi

  # 3. Disconfirmation & Kill-Survival Score (S_K)
  per_purpose_searches: dict[str, int] = {}
  for s in searches:
    p = s.get("purpose", "")
    per_purpose_searches[p] = per_purpose_searches.get(p, 0) + 1

  n_kills = len(kills)
  unresolved_kills = 0
  pending_kills = 0
  if n_kills >= 3:
    k_scores: list[float] = []
    for kid, kinfo in kills.items():
      v = kinfo["verdict"]
      k_recs = by_sq_records.get(kid, []) + [evidence[e] for e in kinfo["evidence"] if e in evidence]
      has_primary_k = any(eff_tiers.get(r.get("id", "")) in ("T1", "T2", "T3") for r in k_recs)
      if v == "refuted":
        k_scores.append(1.00 if has_primary_k else (0.70 if k_recs else 0.20))
      elif v == "confirmed":
        k_scores.append(0.90 if k_recs else 0.30)
      elif v == "unresolved":
        unresolved_kills += 1
        k_scores.append(0.45 if per_purpose_searches.get(kid, 0) >= 3 else 0.15)
      else:
        pending_kills += 1
        k_scores.append(0.0)
    kill_mean = sum(k_scores) / n_kills
  else:
    pending_kills = max(1, 3 - n_kills)
    kill_mean = 0.0

  has_contradicts = any(r.get("stance") == "contradicts" for r in evidence.values())
  contradicts_factor = 1.0 if has_contradicts else 0.60
  s_k = 0.80 * kill_mean + 0.20 * contradicts_factor

  # 4. Quantitative Grounding Score (V_Q)
  rep = report_path or (d / "report.md")
  total_claim_units = 0
  direct_bound_units = 0
  inline_calc_units = 0
  declared_conf, declared_line, declared_raw = None, None, ""

  if rep.exists():
    # Lazy import gate.numbers / gate.material to avoid circular top-level import
    import gate as gate_mod  # noqa: E402
    text = rep.read_text(encoding="utf-8", errors="replace")
    declared_conf, declared_line, declared_raw = extract_declared_confidence(text)
    units = cr._units(cr._strip_non_prose(text.splitlines()))
    quotes = {eid: r.get("quote", "") for eid, r in evidence.items()}
    calc_nums = {cid: calc.bound_numbers_for_record(crec) for cid, crec in calcs.items()}

    exempt = False
    for u in units:
      if u.kind == "heading":
        exempt = cr.heading_exempt(u.text, exempt)
        continue
      if exempt:
        continue
      if not cr._is_claim(u.text) or cr.SOURCE_LINE_RE.match(u.text):
        continue
      total_claim_units += 1
      eids = [e for e in EID_RE.findall(u.text) if e in evidence]
      cids = [c for c in CID_RE.findall(u.text) if c in calcs]
      for c in cids:
        for ce in calcs[c].get("cited_eids", []):
          if ce in evidence and ce not in eids:
            eids.append(ce)
      if not eids:
        continue
      bound: set = set()
      for e in eids:
        bound |= gate_mod.numbers(quotes[e])
      for c in cids:
        bound |= calc_nums[c]
      missing = gate_mod.material(gate_mod.numbers(u.text)) - bound
      if not missing:
        direct_bound_units += 1
      elif FORMAL_CALC_RE.search(u.text) or (
          re.search(r"\b(Estimate|Оценка)\b", u.text, re.I) and SAMPLE_SIZE_RE.search(u.text)
      ):
        inline_calc_units += 1

    if total_claim_units > 0:
      v_q = (direct_bound_units + 0.65 * inline_calc_units) / total_claim_units
    else:
      v_q = 1.0 if n_ev > 0 else 0.0
  else:
    v_q = primary_share

  inline_calc_share = (inline_calc_units / total_claim_units) if total_claim_units > 0 else 0.0

  # Composite Epistemic Index (0..100)
  ei = round(100.0 * (0.35 * a_e + 0.25 * t_d + 0.20 * s_k + 0.20 * v_q), 1)

  # 5. Mechanical Confidence Ceiling & Limiting Factors
  max_conf = "High"
  limiting_factors: list[str] = []

  def _cap_at(level: str, reason: str) -> None:
    nonlocal max_conf
    limiting_factors.append(reason)
    if CONF_RANK[level] < CONF_RANK[max_conf]:
      max_conf = level

  if n_ev == 0:
    _cap_at("Low", "no verified evidence records logged")
  if ei < 50.0:
    _cap_at("Low", f"Epistemic Index EI={ei} < 50.0")
  elif ei < 72.0:
    _cap_at("Medium", f"Epistemic Index EI={ei} < 72.0 (need >= 72.0 for High)")

  if primary_share < 0.35:
    _cap_at("Low", f"T1-T3 primary/peer-reviewed share is {primary_share:.0%} (< 35%)")
  elif primary_share < 0.60:
    _cap_at("Medium", f"T1-T3 primary/peer-reviewed share is {primary_share:.0%} (< 60% required for High)")

  if pending_kills > 0 or n_kills < 3:
    _cap_at("Low", f"{pending_kills} kill hypothesis verdict(s) still pending or < 3 kills")
  elif n_kills > 0 and (unresolved_kills / n_kills) > 0.50:
    _cap_at("Low", f"{unresolved_kills}/{n_kills} kill hypotheses are unresolved (> 50%)")
  elif unresolved_kills >= 1:
    _cap_at("Medium", f"{unresolved_kills} kill hypothesis remains unresolved")

  if len(non_t5_domains) < 2 and n_ev >= 4:
    _cap_at("Low", f"only {len(non_t5_domains)} non-community domain(s) (< 2)")
  elif len(non_t5_domains) < 3:
    _cap_at("Medium", f"only {len(non_t5_domains)} independent non-community domain(s) (< 3 required for High)")

  if manual_share > 0.25:
    _cap_at("Medium", f"manual snapshots account for {manual_share:.0%} of evidence (> 25%)")

  if total_claim_units > 0:
    if v_q < 0.50:
      _cap_at("Low", f"quantitative grounding V_Q={v_q:.2f} < 0.50 ({direct_bound_units}/{total_claim_units} claim units bound)")
    elif v_q < 0.80:
      _cap_at("Medium", f"quantitative grounding V_Q={v_q:.2f} < 0.80 ({direct_bound_units}/{total_claim_units} claim units bound)")

  if total_claim_units >= 5 and inline_calc_share > 0.25:
    _cap_at("Medium", f"unverified inline Calculation: units are {inline_calc_share:.0%} (> 25%; use calc.py [C###])")

  overclaimed = False
  if declared_conf and CONF_RANK[declared_conf] > CONF_RANK[max_conf]:
    overclaimed = True

  return {
      "study_dir": str(d),
      "epistemic_index": ei,
      "max_confidence": max_conf,
      "declared_confidence": declared_conf,
      "declared_confidence_line": declared_line,
      "declared_confidence_raw": declared_raw,
      "confidence_overclaimed": overclaimed,
      "components": {
          "authority_A_E": round(a_e, 3),
          "triangulation_T_D": round(t_d, 3),
          "kill_survival_S_K": round(s_k, 3),
          "quant_grounding_V_Q": round(v_q, 3),
      },
      "metrics": {
          "evidence_count": n_ev,
          "tier_counts": tier_counts,
          "primary_t1_t3_share": round(primary_share, 3),
          "non_t5_domains": len(non_t5_domains),
          "all_domains": len(all_domains),
          "searches_count": len(searches),
          "calculations_count": len(calcs),
          "kills_total": n_kills,
          "kills_unresolved": unresolved_kills,
          "claim_units_total": total_claim_units,
          "claim_units_direct_bound": direct_bound_units,
          "claim_units_inline_calc": inline_calc_units,
          "inline_calc_share": round(inline_calc_share, 3),
      },
      "limiting_factors": limiting_factors,
  }


def format_scorecard_markdown(score: dict[str, Any]) -> str:
  """Renders a paste-ready Markdown Epistemic Scorecard for report.md ## Verification."""
  c = score["components"]
  m = score["metrics"]
  tc = m["tier_counts"]
  lim = "; ".join(score["limiting_factors"]) if score["limiting_factors"] else "None (all High-confidence thresholds met)"
  lines = [
      "### Epistemic Scorecard (`formula.py`)",
      "",
      f"- **Epistemic Index (EI):** **{score['epistemic_index']:.1f} / 100** "
      f"($A_E={c['authority_A_E']:.2f}$, $T_D={c['triangulation_T_D']:.2f}$, "
      f"$S_K={c['kill_survival_S_K']:.2f}$, $V_Q={c['quant_grounding_V_Q']:.2f}$)",
      f"- **Mechanical Confidence Ceiling:** **{score['max_confidence']}**",
      f"- **Source Tier Distribution:** T1={tc['T1']}, T2={tc['T2']}, T3={tc['T3']}, T4={tc['T4']}, T5={tc['T5']} "
      f"(Primary/Peer-Reviewed T1–T3 = {m['primary_t1_t3_share']:.0%} across {m['non_t5_domains']} independent domains)",
      f"- **Verified Calculations (`[C###]`):** {m['calculations_count']} deterministic record(s); "
      f"direct quote/calc binding = {m['claim_units_direct_bound']}/{m['claim_units_total']} claim units",
      f"- **Limiting Factors:** {lim}",
  ]
  return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
  if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
  ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
  ap.add_argument("dir", type=Path)
  ap.add_argument("--report", type=Path, help="default: <dir>/report.md")
  ap.add_argument("--markdown", action="store_true", help="output Markdown block for ## Verification")
  ap.add_argument("--json", action="store_true", help="output JSON")
  args = ap.parse_args(argv)

  score = compute_epistemic_score(args.dir, args.report)
  if args.json:
    print(json.dumps(score, ensure_ascii=False, indent=2))
  elif args.markdown:
    print(format_scorecard_markdown(score))
  else:
    c = score["components"]
    m = score["metrics"]
    print(f"[SCORECARD] {score['study_dir']}")
    print(f"  Epistemic Index (EI) : {score['epistemic_index']:.1f} / 100")
    print(f"  Max Confidence Cap   : {score['max_confidence']}"
          + (f"  (declared: {score['declared_confidence']})" if score["declared_confidence"] else ""))
    print(f"  Components           : A_E={c['authority_A_E']:.2f}  T_D={c['triangulation_T_D']:.2f}  "
          f"S_K={c['kill_survival_S_K']:.2f}  V_Q={c['quant_grounding_V_Q']:.2f}")
    print(f"  Primary T1-T3 Share  : {m['primary_t1_t3_share']:.0%}  ({m['evidence_count']} evidence items, "
          f"{m['non_t5_domains']} non-T5 domains, {m['calculations_count']} [C###] calcs)")
    if score["limiting_factors"]:
      print("  Limiting Factors     :")
      for lf in score["limiting_factors"]:
        print(f"    - {lf}")
    if score["confidence_overclaimed"]:
      print(f"  [FAIL R10] Declared confidence '{score['declared_confidence']}' exceeds ceiling '{score['max_confidence']}'")
      return 1
  return 0


if __name__ == "__main__":
  sys.exit(main())
