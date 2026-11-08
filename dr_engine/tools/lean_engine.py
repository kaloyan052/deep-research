#!/usr/bin/env python3

"""Deep Research Engine v8.0 LEAN FRONTIER — Unified 3-Stage Compiler & Verifier.



Collapses 10+ bureaucratic CLI scripts into a single, zero-dependency, high-speed

engine with three subcommands:

  1. `ingest`: Concurrent multi-source fetching, SHA-256 snapshotting, hierarchical

               table flattening, and one-shot Okapi BM25 passage compilation.

  2. `verify`: Single-pass vectorized verification of `report.md` (with embedded or

               external `manifest.json` and `python:model` AST blocks), Depth-1

               Algebraic Closure number binding, DerSimonian-Laird I^2 pooling,

               Shingle-Jaccard N_eff independence, and Counterparty Friction auditing.

  3. `selftest`: Zero-mock end-to-end verification of all v8.0 mechanisms (< 50 ms).



Pure Python stdlib. Windows cp1252-safe.

"""



from __future__ import annotations



import argparse

import ast

import concurrent.futures

import datetime as dt

import hashlib

import html

import json

import math

import operator

import re

import sys

import tempfile

import urllib.error

import urllib.parse

import urllib.request

from dataclasses import dataclass, field

from pathlib import Path

from typing import Any

# Ensure workspace root is in sys.path so dr_engine modules can always be imported
_workspace_root = Path(__file__).resolve().parent.parent.parent
if str(_workspace_root) not in sys.path:
  sys.path.insert(0, str(_workspace_root))

# v10.0: polyglot ranking, resilient transport, fail-closed epistemic gate.
from dr_engine.tools.context_ranker import rank_passages as _v10_rank_passages  # noqa: E402
# v13.0: Multi-hop deep digging, anti-truncation R19, Claim-Link-Quote R20, R21 & B12.
from dr_engine.tools.deep_digger import (  # noqa: E402
  canonicalize_crawl_url,
  extract_high_value_sublinks,
  fetch_document_snapshot,
  html_to_structured_snapshot,
)
from dr_engine.tools.depth_and_ledger_gate import (  # noqa: E402
  ATTESTATION_MARKER_RE,
  audit_deliverables_directory,
  export_verified_report,
  is_v13_protocol,
  render_claim_ledger_scaffold,
  run_v13_gates_fail_closed,
  version_at_least,
  write_verification_receipt,
)
# v12.0: Epistemic Alpha Delta (R18), Active Dethroning (B11), fail-closed wrapper.
from dr_engine.tools.ead_gate import (  # noqa: E402
  PROTOCOL_VERSION as V12_PROTOCOL_VERSION, is_v12_protocol,
  run_v12_gates_fail_closed,
)
from dr_engine.tools.epistemic_guard import (  # noqa: E402
  NEGATIVE_VERDICTS, is_mitigated_locally, normalize_verdict, safe_int,
  safe_number, unmitigated_spans, run_filters_fail_closed,
)
from dr_engine.tools.http_resilience import resilient_fetch  # noqa: E402



# ---------------------------------------------------------------------------

# Constants, Whitelists & Microstructure Priors

# ---------------------------------------------------------------------------

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (DR-Lean/8.0)"

TIER_WEIGHTS = {"T1": 1.00, "T2": 0.90, "T3": 0.80, "T4": 0.45, "T5": 0.20}



DECAYED_TEXTBOOK_TRAPS = {

    "london 4pm fix reversal": "Refuted in lab (t = -11.09, P31/FXFIX01); post-2015 window widening killed edge.",

    "naive turn of the month": "Decayed post-2018 due to front-running institutional pension rebalance flows.",

    "unfiltered retail rsi": "Negative net expectancy after spread and slippage on M15/H1.",

}



# Structural, calendar, timeframe, and statistical tokens exempt from empirical quote binding

EXEMPT_TOKEN_PATTERNS = (

    re.compile(r"https?://[^\s)>\]\"'|]+", re.I),  # URLs (verified independently by R20)

    re.compile(r"\b(?:19|20)\d{2}-\d{2}-\d{2}\b"),  # ISO dates 2026-11-05

    re.compile(r"\b(?:SQ|K|E|C|S|R|CL|D|P|T|H|M|W)\d{1,3}[a-z]?\b", re.I),  # IDs & timeframes (M15, H1, E001)

    re.compile(r"\b[0-5]DTE\b", re.I),  # 0DTE, 1DTE options

    re.compile(r"\b24\s*/\s*7\b"),

    re.compile(r"\b\d+(?:\.\d+)?\s*(?:★|⭐)\b"),

    re.compile(r"\b\d+(?:\.\d+)?\s*/\s*(?:5|10|100)\b"),

    re.compile(r"\b(?:90|95|99)(?:\.0)?%\s*(?:CI|confidence|interval|bound|доверителен)", re.I),

    re.compile(r"\bp\s*[<≤=]\s*0\.0[015]\b", re.I),

    re.compile(r"\b(?:section|секция|step|стъпка|phase|фаза|table|таблица|row|ред)\s+#?\d+(?:\.\d+)*\b", re.I),

)



# Standard domain constants (trading days, calendar days, hours, standard normal z-scores)

DOMAIN_CONSTANTS = {

    0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0,

    12.0, 14.0, 15.0, 20.0, 24.0, 30.0, 50.0, 60.0, 90.0, 95.0, 99.0, 100.0,

    180.0, 250.0, 252.0, 260.0, 360.0, 365.0, 500.0, 1000.0, 10000.0,

    1.645, 1.96, 2.326, 2.576,

}



EXEMPT_COL_HEADER_RE = re.compile(

    r"^(?:#|id|rank|tier|kind|status|verdict|sq|kill|parameter|param|horizon|window|"

    r"timeframe|scenario|score|weight|assumption|spec|code|variable|axis|role|"

    r"url|link|source|източник|линк|връзка)\b",

    re.I,

)



SPEC_LINE_RE = re.compile(

    r"(\[(?:SPEC|PARAM|MODEL|I|EST|ASSUMPTION)\]|"

    r"\b(?:Hyperparameter|Specification|Model\s+Assumption|Backtest\s+Config)\s*:)",

    re.I,

)



# Max characters an `...` ellipsis may span inside a verbatim quote.
MAX_ELLIPSIS_GAP = 500
MAX_TOTAL_ELLIPSIS_GAP = 1000

# v14.1 — hard floors for an admissible verbatim quote (fail-closed).
MIN_QUOTE_CHARS = 20
MIN_QUOTE_WORDS = 4
MIN_FRAGMENT_CHARS = 8
MIN_FRAGMENT_WORDS = 2
MAX_ELLIPSIS_FRAGMENTS = 6

EID_RE = re.compile(r"\bE\d{3}\b")

CID_RE = re.compile(r"\bC\d{3}\b")

SID_RE = re.compile(r"\bS\d{3}\b")



NUM_EXTRACT_RE = re.compile(

    r"(?<![\w.])([$€£¥])?\s*"

    r"([-+]?\d[\d,]*(?:\.\d+)?)"

    r"(?:[\s-]*(%|‰|bps\b|bp\b|k\b|m\b|mn\b|bn\b|million\b|billion\b))?",

    re.I,

)



STOPWORDS = {

    "the", "and", "for", "that", "with", "from", "this", "are", "was", "were",

    "have", "has", "not", "but", "what", "all", "when", "can", "more", "than",

    "into", "only", "other", "such", "their", "which", "would", "about", "there",

    "или", "при", "като", "това", "която", "които", "след", "през", "към", "със",

}





def sha256_text(text: str) -> str:

  return hashlib.sha256(text.encode("utf-8")).hexdigest()





def normalise_ws(text: str) -> str:

  text = text.replace("\u00a0", " ").replace("−", "-").replace("–", "-").replace("—", "-")

  text = re.sub(r"['’‘`]", "'", text)

  text = re.sub(r'[“”"]', '"', text)

  return re.sub(r"\s+", " ", text).strip()





# ---------------------------------------------------------------------------

# 1. Sandboxed AST Math & Model Evaluator (Replaces CLI calc.py loops)

# ---------------------------------------------------------------------------

SAFE_OPS = {

    ast.Add: operator.add,

    ast.Sub: operator.sub,

    ast.Mult: operator.mul,

    ast.Div: operator.truediv,

    ast.FloorDiv: operator.floordiv,

    ast.Mod: operator.mod,

    ast.Pow: operator.pow,

    ast.USub: operator.neg,

    ast.UAdd: operator.pos,

}



SAFE_FUNCS = {

    "abs": abs,

    "min": min,

    "max": max,

    "round": round,

    "sum": sum,

    "sqrt": math.sqrt,

    "log": math.log,

    "log10": math.log10,

    "exp": math.exp,

    # Built-in quantitative finance & microstructure helpers

    "hold_cost_bp": lambda spread_bp, nights, annual_swap_bp: spread_bp + nights * (annual_swap_bp / 365.0),

    "net_edge_bp": lambda gross_bp, spread_bp, slippage_bp, comm_bp=0.0: gross_bp - (spread_bp + slippage_bp + comm_bp),

    "sharpe_annual": lambda mean_ret, std_ret, periods=252.0: (mean_ret / std_ret) * math.sqrt(periods) if std_ret > 0 else 0.0,

    "kelly_half": lambda win_prob, payoff_ratio: 0.5 * (win_prob - (1.0 - win_prob) / payoff_ratio) if payoff_ratio > 0 else 0.0,

    "wilson_lower_95": lambda k, n: (

        (k / n + (1.96**2) / (2 * n) - 1.96 * math.sqrt((k / n * (1 - k / n) + (1.96**2) / (4 * n)) / n))

        / (1 + (1.96**2) / n)

    ) if n > 0 else 0.0,

}





def _eval_ast_node(node: ast.AST, env: dict[str, Any]) -> Any:

  if isinstance(node, ast.Constant):

    if isinstance(node.value, (int, float, str, bool)):

      return node.value

    raise ValueError(f"Unsupported constant: {node.value!r}")

  if isinstance(node, ast.Name):

    if node.id in env:

      return env[node.id]

    if node.id in SAFE_FUNCS:

      return SAFE_FUNCS[node.id]

    raise ValueError(f"Undefined variable in model: {node.id!r}")

  if isinstance(node, ast.BinOp) and type(node.op) in SAFE_OPS:

    left = _eval_ast_node(node.left, env)

    right = _eval_ast_node(node.right, env)

    # v10.0 deterministic resource budget. `2 ** 100000000` in a python:model
    # block used to hang verification indefinitely; string/list multiplication
    # could exhaust memory. All bounds are generous for real research models.
    if isinstance(node.op, ast.Pow) and isinstance(right, (int, float)) and not isinstance(right, bool):
      if abs(float(right)) > 64.0:
        raise ValueError("model exponent exceeds deterministic budget (|e| <= 64)")
    if isinstance(node.op, ast.Mult) and isinstance(right, int) and not isinstance(right, bool):
      if abs(right) > 10000:
        raise ValueError("model repetition exceeds deterministic budget (<= 10000)")
    result = SAFE_OPS[type(node.op)](left, right)
    if isinstance(result, int) and abs(result) > 10 ** 15:
      raise ValueError("model integer exceeds deterministic numeric budget (<= 1e15)")
    if isinstance(result, float) and not math.isfinite(result):
      raise ValueError("model produced a non-finite value (NaN/Inf)")
    if isinstance(result, (str, list)) and len(result) > 10000:
      raise ValueError("model container exceeds deterministic size budget")
    return result

  if isinstance(node, ast.UnaryOp) and type(node.op) in SAFE_OPS:

    return SAFE_OPS[type(node.op)](_eval_ast_node(node.operand, env))

  if isinstance(node, ast.Tuple) or isinstance(node, ast.List):

    return [_eval_ast_node(elt, env) for elt in node.elts]

  if isinstance(node, ast.Call):

    fn = _eval_ast_node(node.func, env)

    if fn not in SAFE_FUNCS.values():

      raise ValueError(f"Disallowed function call in model: {ast.dump(node.func)}")

    args = [_eval_ast_node(a, env) for a in node.args]

    kwargs = {kw.arg: _eval_ast_node(kw.value, env) for kw in node.keywords if kw.arg}

    return fn(*args, **kwargs)

  raise ValueError(f"Disallowed AST construct in deterministic model: {type(node).__name__}")





def execute_model_block(code_str: str, initial_env: dict[str, float] | None = None) -> dict[str, float]:

  """Executes a declarative `python:model` block of variable assignments via safe AST evaluation."""

  tree = ast.parse(code_str, mode="exec")

  env: dict[str, Any] = dict(initial_env or {})

  emitted: dict[str, float] = {}

  for stmt in tree.body:

    if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1 and isinstance(stmt.targets[0], ast.Name):

      var_name = stmt.targets[0].id

      val = _eval_ast_node(stmt.value, env)

      if isinstance(val, (int, float)) and not isinstance(val, bool):

        fval = round(float(val), 6)

        env[var_name] = fval

        emitted[var_name] = fval

      else:

        env[var_name] = val

    elif isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant) and isinstance(stmt.value.value, str):

      continue  # Allow docstrings/comments

    else:

      raise ValueError(f"Model blocks only allow deterministic assignments (`var = expr`), got: {type(stmt).__name__}")

  return emitted





# ---------------------------------------------------------------------------

# 2. Number Extraction & Depth-1 Algebraic Closure (Eliminates Gate R3 Friction)

# ---------------------------------------------------------------------------

def extract_numbers(text: str, strip_exempt: bool = True) -> set[float]:

  """Extracts material numeric values while stripping structural tokens, dates, and code."""

  cleaned = re.sub(r"https?://\S+", " ", text)

  cleaned = re.sub(r"`[^`]+`", " ", cleaned)  # Inline code parameters are exempt

  if strip_exempt:

    cleaned = re.sub(r"^\s*\|\s*#?\d{1,3}\s*(?=\|)", "| ", cleaned)  # Leading table index

    for pat in EXEMPT_TOKEN_PATTERNS:

      cleaned = pat.sub(" ", cleaned)



  out: set[float] = set()

  for m in NUM_EXTRACT_RE.finditer(cleaned):

    raw = m.group(2).rstrip(",.")

    suffix = (m.group(3) or "").lower()

    if re.fullmatch(r"[-+]?\d{1,3}(,\d{3})+(\.\d+)?", raw):

      raw = raw.replace(",", "")

    else:

      raw = raw.replace(",", ".")

    try:

      val = float(raw)

    except ValueError:

      continue

    mult = {

        "k": 1e3, "m": 1e6, "mn": 1e6, "million": 1e6, "bn": 1e9, "billion": 1e9

    }.get(suffix, 1.0)

    fval = round(val * mult, 6)

    if strip_exempt:

      if abs(fval) in DOMAIN_CONSTANTS:

        continue

      if 1990 <= fval <= 2035 and fval.is_integer():

        continue  # Calendar years are context, not unbound material floats

    out.add(fval)

  return out





def algebraic_closure(base_nums: set[float]) -> set[float]:

  """Computes the Depth-1 Algebraic Closure C_1(B) over a set of bound numbers B.

  Includes unit/scale morphisms (%, bps, RT=2x, annual/daily), complements (100-x),

  pairwise arithmetic (+, -, *, /, % change), and standard rounding.

  """

  closure: set[float] = set(DOMAIN_CONSTANTS)

  active = [x for x in base_nums if math.isfinite(x)]



  # Step 1: Unary morphisms & rounding

  expanded: set[float] = set()

  for x in active:

    for candidate in (

        x, abs(x), -x,

        x * 100.0, x / 100.0,        # decimal <-> %

        x * 10000.0, x / 10000.0,    # decimal <-> bps

        x * 1000.0, x / 1000.0,      # k <-> raw

        x * 2.0, x / 2.0,            # per-side <-> round-turn (RT)

        100.0 - x, 1.0 - x,          # complements (e.g., 87% fail -> 13% survive)

        x * 252.0, x / 252.0,        # daily <-> trading annual

        x * 365.0, x / 365.0,        # daily <-> calendar annual

    ):

      if math.isfinite(candidate):

        expanded.add(round(candidate, 6))

        expanded.add(round(candidate, 2))

        expanded.add(round(candidate, 1))

        expanded.add(round(candidate, 0))



  closure |= expanded

  # Step 2: Pairwise combinations over the core numbers (capped at 40 to keep O(1) speed)

  core_list = sorted(set(round(x, 6) for x in active))[:40]

  for i, a in enumerate(core_list):

    for b in core_list[i:]:

      pairs = [a + b, a - b, b - a, a * b, (a * b) / 100.0]

      if abs(b) > 1e-9:

        pairs.extend([a / b, (a / b) * 100.0, ((a - b) / b) * 100.0])

      if abs(a) > 1e-9:

        pairs.extend([b / a, (b / a) * 100.0, ((b - a) / a) * 100.0])

      for p in pairs:

        if math.isfinite(p):

          closure.add(round(p, 6))

          closure.add(round(p, 2))

          closure.add(round(p, 1))

          closure.add(round(p, 0))

  return closure





def is_number_bound(target: float, closure: set[float], rel_tol: float = 0.005) -> bool:

  """Checks if `target` is in `closure` within 0.5% relative tolerance or rounding."""

  if target in closure or abs(target) in DOMAIN_CONSTANTS:

    return True

  for d in (0, 1, 2, 3, 4):

    if round(target, d) in closure:

      return True

  for c in closure:

    denom = max(abs(target), abs(c), 1e-9)

    if abs(target - c) / denom <= rel_tol:

      return True

  return False





# ---------------------------------------------------------------------------

# 3. Verbatim Quote Matcher, Shingle-Jaccard N_eff & DerSimonian-Laird I^2

# ---------------------------------------------------------------------------

def quote_matches_snapshot(quote: str, snapshot: str) -> bool:
  """Verify `quote` verbatim against `snapshot`, allowing bounded `...` gaps.

  v14.1: a quote is admissible only if it is a non-empty string with a
  minimum character/word count; every ellipsis fragment is independently
  admissible; the fragment count is bounded; and **every** gap — including
  the punctuation-tolerant fallback branch — is bounded by
  MAX_ELLIPSIS_GAP in the coordinate system of the NORMALISED snapshot.
  """
  if not isinstance(quote, str) or not isinstance(snapshot, str):
    return False

  q = normalise_ws(quote).casefold()
  if len(q) < MIN_QUOTE_CHARS:
    return False
  if len(re.findall(r"\w+", q)) < MIN_QUOTE_WORDS:
    return False

  fragments = [f.strip() for f in re.split(r"\.\.\.|\u2026", q) if f.strip()]
  if not fragments or len(fragments) > MAX_ELLIPSIS_FRAGMENTS:
    return False
  for frag in fragments:
    words = re.findall(r"\w+", frag)
    if (len(frag) < MIN_FRAGMENT_CHARS
        or len(words) < MIN_FRAGMENT_WORDS
        or not any(ch.isalnum() for ch in frag)):
      return False

  snap_norm = normalise_ws(snapshot).casefold()
  if not snap_norm:
    return False

  pos = 0
  total_gap = 0
  for i, frag in enumerate(fragments):
    idx = snap_norm.find(frag, pos)
    if idx >= 0:
      if i > 0:
        gap = idx - pos
        if gap > MAX_ELLIPSIS_GAP:
          return False
        total_gap += gap
        if total_gap > MAX_TOTAL_ELLIPSIS_GAP:
          return False
      pos = idx + len(frag)
      continue

    # Punctuation-tolerant fallback. Restrict the separator class: `\\W+`
    # previously allowed arbitrary characters (including newlines) to be
    # spliced between words, and skipped the gap check entirely.
    pat = re.compile(r"[\s\-,;:]{0,4}".join(map(re.escape, re.findall(r"\w+", frag))))
    m = pat.search(snap_norm, min(pos, len(snap_norm)))
    if not m:
      return False
    if i > 0:
      gap = m.start() - pos
      if gap > MAX_ELLIPSIS_GAP:
        return False
      total_gap += gap
      if total_gap > MAX_TOTAL_ELLIPSIS_GAP:
        return False
    pos = m.end()
  return True





def _shingles(text: str, k: int = 3) -> set[tuple[str, ...]]:

  words = [w for w in re.findall(r"[a-zа-я0-9]{3,}", text.lower()) if w not in STOPWORDS]

  if len(words) < k:

    return {tuple(words)} if words else set()

  return {tuple(words[i:i + k]) for i in range(len(words) - k + 1)}





def compute_neff_and_entropy(evidence: list[dict], sources: dict[str, dict]) -> dict[str, Any]:

  """Computes Shingle-Jaccard independence clustering and Inverse-HHI N_eff."""

  if not evidence:

    return {"raw_sources": 0, "independent_clusters": 0, "n_eff": 0.0, "echo_multiplier": 1.0}



  by_src: dict[str, dict[str, Any]] = {}

  for r in evidence:

    sid = r.get("source", "S000")

    smeta = sources.get(sid, {})

    url = r.get("url") or smeta.get("url", "")

    host = urllib.parse.urlparse(url).hostname or sid

    host = host[4:] if host.startswith("www.") else host

    entry = by_src.setdefault(sid, {"host": host, "shingles": set(), "count": 0})

    entry["shingles"] |= _shingles(r.get("quote", ""), k=3)

    entry["count"] += 1



  sids = sorted(by_src.keys())

  parent = {s: s for s in sids}



  def find(x: str) -> str:

    while parent[x] != x:

      parent[x] = parent[parent[x]]

      x = parent[x]

    return x



  for i in range(len(sids)):

    for j in range(i + 1, len(sids)):

      s1, s2 = sids[i], sids[j]

      d1, d2 = by_src[s1], by_src[s2]

      if d1["host"] == d2["host"]:

        parent[find(s2)] = find(s1)

        continue

      sh1, sh2 = d1["shingles"], d2["shingles"]

      jacc = (len(sh1 & sh2) / len(sh1 | sh2)) if (sh1 and sh2) else 0.0

      if jacc >= 0.28:

        parent[find(s2)] = find(s1)



  clusters: dict[str, int] = {}

  for s in sids:

    root = find(s)

    clusters[root] = clusters.get(root, 0) + by_src[s]["count"]



  total = sum(clusters.values())

  hhi = sum((c / total) ** 2 for c in clusters.values()) if total else 1.0

  n_eff = round(1.0 / hhi, 2) if hhi > 0 else 0.0

  n_clusters = len(clusters)

  raw_domains = len({by_src[s]["host"] for s in sids})

  indep_ratio = n_clusters / max(1, raw_domains)

  mult = round(0.65 + 0.35 * min(1.0, indep_ratio), 3)

  return {

      "raw_sources": len(sids),

      "raw_domains": raw_domains,

      "independent_clusters": n_clusters,

      "n_eff": n_eff,

      "echo_multiplier": mult,

  }





def dersimonian_laird_pool(claims: list[dict[str, Any]]) -> list[dict[str, Any]]:

  """Groups quantitative claims by (subject, metric, unit, scope) and runs DL random-effects pooling."""

  groups: dict[tuple[str, str, str, str], list[dict[str, Any]]] = {}

  for c in claims:

    if isinstance(c.get("value"), (int, float)):

      key = (

          str(c.get("subject", "")).lower().strip(),

          str(c.get("metric", "")).lower().strip(),

          str(c.get("unit", "")).lower().strip(),

          str(c.get("scope", "general")).lower().strip(),

      )

      groups.setdefault(key, []).append(c)



  results: list[dict[str, Any]] = []

  for (subj, metric, unit, scope), c_list in groups.items():

    if len(c_list) < 2:

      continue

    vals = [float(c["value"]) for c in c_list]

    k = len(vals)

    scale = sum(abs(v) for v in vals) / k

    if scale == 0:

      continue

    ses = [max(1e-6, float(c.get("se") or 0.10 * scale)) for c in c_list]

    w_fe = [1.0 / (s ** 2) for s in ses]

    sum_w = sum(w_fe)

    fe_mean = sum(w * v for w, v in zip(w_fe, vals)) / sum_w

    q_stat = sum(w * ((v - fe_mean) ** 2) for w, v in zip(w_fe, vals))

    df = k - 1

    c_den = sum_w - (sum(w ** 2 for w in w_fe) / sum_w)

    tau2 = max(0.0, (q_stat - df) / c_den) if c_den > 0 else 0.0

    i2 = max(0.0, min(99.9, ((q_stat - df) / q_stat) * 100.0)) if q_stat > df else 0.0

    w_re = [1.0 / ((s ** 2) + tau2) for s in ses]

    re_mean = sum(w * v for w, v in zip(w_re, vals)) / sum(w_re)

    results.append({

        "subject": subj, "metric": metric, "unit": unit, "scope": scope,

        "k": k, "values": vals, "re_estimate": round(re_mean, 4),

        "q_stat": round(q_stat, 2), "i2_pct": round(i2, 1),

        "regime_split_required": i2 > 50.0,

    })

  return results





# ---------------------------------------------------------------------------

# 4. Stage 1 (`ingest`): Concurrent Fetching + Auto-BM25 Context Packager

# ---------------------------------------------------------------------------

def _strip_html(raw_html: str) -> str:
  return html_to_structured_snapshot(raw_html)


def _fetch_single_url(
    url: str,
    timeout: float = 20.0,
    community_kind: str = "all",
    min_score: int = 1,
) -> dict[str, Any]:
  """v13.0 community-, PDF-, and table-aware provenance-carrying source fetch."""
  community_error = ""
  try:
    from dr_engine.tools.community_engine import detect_community_platform, fetch_community_url
    if detect_community_platform(url) is not None:
      comm_res = fetch_community_url(
          url, min_score=min_score, target_kind=community_kind, timeout=timeout,
      )
      if comm_res.get("ok"):
        text = str(comm_res.get("text") or "")
        return {
            "ok": len(text) >= 200, "url": url, "text": text, "raw_html": "",
            "status": comm_res.get("status"), "error": str(comm_res.get("error") or ""),
            "via": "community_engine", "charset": "utf-8",
            "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "bot_wall": False, "warnings": [],
        }
  except Exception as exc:
    # Fail-loud: record the parser failure, then fall through to direct HTTP.
    community_error = f"community parser failed: {type(exc).__name__}: {exc}"[:200]

  # v13.0: handle linked PDF documents (e.g. General Terms & Conditions PDFs, papers)
  if str(url or "").lower().split("?")[0].endswith(".pdf"):
    pdf_doc = fetch_document_snapshot(url, timeout=timeout)
    if pdf_doc.ok and pdf_doc.text:
      warns = list(pdf_doc.warnings)
      if community_error:
        warns.append(community_error)
      return {
          "ok": True, "url": url, "text": pdf_doc.text, "raw_html": "",
          "status": pdf_doc.status, "error": "", "via": pdf_doc.via,
          "charset": "utf-8", "sha256": pdf_doc.sha256, "bot_wall": False,
          "warnings": warns, "evidence_class": pdf_doc.evidence_class,
          "source_url": url, "fallback_chain": [],
      }

  result = resilient_fetch(url, timeout=timeout, max_bytes=2_500_000, retries=2)
  raw_body = result.text if result.ok else ""
  structured_text = html_to_structured_snapshot(raw_body) if raw_body else ""
  final_text = structured_text if len(structured_text) >= 40 else raw_body
  payload = {
      "ok": bool(result.ok and final_text.strip()),
      "url": url,
      "text": final_text,
      "raw_html": raw_body if ("<" in raw_body and ">" in raw_body) else "",
      "status": result.status,
      "error": result.error,
      "via": result.via,
      "charset": result.charset,
      "sha256": hashlib.sha256(final_text.encode("utf-8")).hexdigest() if final_text else result.sha256,
      "bot_wall": result.bot_wall,
      "warnings": list(result.warnings),
      "evidence_class": result.evidence_class,
      "source_url": result.source_url or url,
      "fallback_chain": list(result.fallback_chain),
  }
  if community_error:
    payload["warnings"].append(community_error)
  return payload




def rank_bm25_passages(
    sources: dict[str, str], queries: dict[str, str], top_k_per_query: int = 6
) -> list[dict[str, Any]]:
  """v10.0 delegation to :mod:`context_ranker` (return shape unchanged).

  v9.0 used ``[a-zа-я0-9]{3,}`` (discarding CJK, Hangul and accented Latin),
  hard-truncated every paragraph at 800 characters, repeated identical spans
  across queries, and applied no diversity cap or context budget. The v10.0
  ranker adds overlapping windows, script-aware tokens, a bounded
  number-density prior, shingle-Jaccard syndication suppression, per-source
  diversity caps, cross-query deduplication and a hard character budget.
  """
  return _v10_rank_passages(sources, queries, top_k_per_query=top_k_per_query)




def cmd_ingest(args: argparse.Namespace) -> int:

  d = Path(args.dir)

  src_dir = d / "sources"

  src_dir.mkdir(parents=True, exist_ok=True)

  spec_path = Path(args.spec) if args.spec else (d / "study_spec.json")

  if not spec_path.exists():

    print(f"ERROR: spec file not found: {spec_path}")

    return 2



  spec = json.loads(spec_path.read_text(encoding="utf-8"))

  urls: list[str] = spec.get("urls", [])

  local_sources: dict[str, str] = spec.get("inline_sources", {})

  # v10.0: URLs the spec declares as unverified bundled offline seeds (e.g.
  # the hardcoded benchmark leaderboard). They can be snapshotted for context,
  # but must never be treated as measured Tier-2 evidence for Rule B9.
  unverified_urls: set[str] = set(spec.get("unverified_inline_sources", []))



  index: list[dict[str, Any]] = []

  snap_texts: dict[str, str] = {}



  # 1. Ingest any inline/local sources provided in spec

  for idx, (url, text) in enumerate(local_sources.items(), 1):

    sid = f"S{idx:03d}"

    (src_dir / f"{sid}.txt").write_text(text, encoding="utf-8")

    rec = {

        "id": sid, "url": url, "fetched_at": dt.date.today().isoformat(),

        "chars": len(text), "sha256": sha256_text(text),

        "via": "inline_seed", "charset": "utf-8", "bot_wall": False,

        "unverified_bundled": url in unverified_urls,

        "evidence_class": "primary_fetched", "secondary_transcription": False,

        "source_url": url, "fallback_chain": [],

    }

    index.append(rec)

    snap_texts[sid] = text



  # 2. Fetch remote URLs concurrently (up to 16 workers) + v13 Multi-Hop Subpage Digging
  if urls:
    comm_kind = str(spec.get("community_kind", "all"))
    comm_min_score = int(spec.get("community_min_score", 1))
    seen_canon = {canonicalize_crawl_url(r["url"]) for r in index if r.get("url")}
    seen_shas = {str(r["sha256"]) for r in index if r.get("sha256")}
    frontier_html: list[tuple[str, str]] = []

    workers = min(16, len(urls))
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
      futs = {
          ex.submit(_fetch_single_url, u, 20.0, comm_kind, comm_min_score): u
          for u in urls
      }

      for fut in concurrent.futures.as_completed(futs):
        res = fut.result()
        if not res["ok"]:
          print(f"  WARN  Failed fetch {res['url']}: {res['error']}")
          continue
        sha = sha256_text(res["text"])
        c_url = canonicalize_crawl_url(res["url"])
        if sha in seen_shas:
          continue
        seen_shas.add(sha)
        if c_url:
          seen_canon.add(c_url)

        sid = f"S{len(index) + 1:03d}"
        (src_dir / f"{sid}.txt").write_text(res["text"], encoding="utf-8")
        rec = {
            "id": sid, "url": res["url"], "fetched_at": dt.date.today().isoformat(),
            "chars": len(res["text"]), "sha256": sha,
            "via": res.get("via", "unknown"), "charset": res.get("charset", ""),
            "bot_wall": bool(res.get("bot_wall", False)),
            "fetch_warnings": list(res.get("warnings", [])),
            "evidence_class": res.get("evidence_class", "primary_fetched"),
            "secondary_transcription": res.get("evidence_class", "primary_fetched") != "primary_fetched",
            "source_url": res.get("source_url", res["url"]),
            "fallback_chain": list(res.get("fallback_chain", [])),
            "hop_depth": 0,
        }
        index.append(rec)
        snap_texts[sid] = res["text"]
        if res.get("raw_html"):
          frontier_html.append((res["url"], str(res["raw_html"])))

    # v13.0 Multi-Hop Subpage / Help-Center / Legal / PDF Spider
    dig_cfg = spec.get("deep_digging") if isinstance(spec.get("deep_digging"), dict) else {}
    deep_enabled = bool(getattr(args, "deep", False)) or bool(dig_cfg.get("enabled", False))
    arg_subpages = getattr(args, "max_subpages", None)
    subpage_budget = int(arg_subpages if arg_subpages is not None else dig_cfg.get("max_subpages", 12))
    max_depth = int(dig_cfg.get("max_depth", 2))
    focus_q = str(spec.get("study_title") or " ".join(spec.get("entities") or []))

    hop = 1
    while deep_enabled and subpage_budget > 0 and hop <= max_depth and frontier_html:
      cand_by_url: dict[str, Any] = {}
      for parent_url, raw_h in frontier_html:
        for cand in extract_high_value_sublinks(raw_h, parent_url, focus_query=focus_q, max_links=max(8, subpage_budget)):
          if cand.url in seen_canon:
            continue
          prev = cand_by_url.get(cand.url)
          if prev is None or cand.score > prev.score:
            cand_by_url[cand.url] = cand

      if not cand_by_url:
        break

      batch = sorted(cand_by_url.values(), key=lambda c: (-c.score, c.url))[:subpage_budget]
      for c in batch:
        seen_canon.add(c.url)

      next_frontier: list[tuple[str, str]] = []
      with concurrent.futures.ThreadPoolExecutor(max_workers=min(8, len(batch))) as ex:
        sub_futs = {
            ex.submit(_fetch_single_url, c.url, 16.0, comm_kind, comm_min_score): c
            for c in batch
        }
        for sfut in concurrent.futures.as_completed(sub_futs):
          cand = sub_futs[sfut]
          sres = sfut.result()
          if not sres.get("ok") or not sres.get("text"):
            continue
          ssha = sha256_text(sres["text"])
          if ssha in seen_shas:
            continue
          seen_shas.add(ssha)
          sid = f"S{len(index) + 1:03d}"
          (src_dir / f"{sid}.txt").write_text(sres["text"], encoding="utf-8")
          srec = {
              "id": sid, "url": sres["url"], "fetched_at": dt.date.today().isoformat(),
              "chars": len(sres["text"]), "sha256": ssha,
              "via": sres.get("via", "unknown"), "charset": sres.get("charset", ""),
              "bot_wall": bool(sres.get("bot_wall", False)),
              "fetch_warnings": list(sres.get("warnings", [])),
              "evidence_class": sres.get("evidence_class", "primary_fetched"),
              "secondary_transcription": sres.get("evidence_class", "primary_fetched") != "primary_fetched",
              "source_url": sres.get("source_url", sres["url"]),
              "fallback_chain": list(sres.get("fallback_chain", [])),
              "hop_depth": hop,
              "parent_url": cand.parent_url,
              "link_reason": cand.reason,
          }
          index.append(srec)
          snap_texts[sid] = sres["text"]
          subpage_budget -= 1
          if sres.get("raw_html"):
            next_frontier.append((sres["url"], str(sres["raw_html"])))
          if subpage_budget <= 0:
            break
      frontier_html = next_frontier
      hop += 1



  with (src_dir / "index.jsonl").open("w", encoding="utf-8") as f:

    for r in index:

      f.write(json.dumps(r, ensure_ascii=False) + "\n")



  # 3. Auto-compile ranked BM25 passages across all SQs and Kills into `context_pack.md`

  queries = {}

  for sq_id, sq_q in spec.get("sub_questions", {}).items():

    queries[sq_id] = sq_q

  for k_id, k_q in spec.get("kill_hypotheses", {}).items():

    queries[k_id] = k_q if isinstance(k_q, str) else k_q.get("query", "")

  # v12.0 Frontier 1: the Active Dethroning vectors become real BM25 queries,
  # so an upset recorded in a snapshot is compiled into the context pack
  # instead of sitting unused in study_spec.json.
  dethrone_spec = spec.get("dethroning") or {}
  dethrone_vectors = dethrone_spec.get("vectors") or []
  if isinstance(dethrone_vectors, list):
    for vec in dethrone_vectors[:6]:
      if not isinstance(vec, dict):
        continue
      vid = str(vec.get("vector_id") or "DTH")
      qtext = str(vec.get("query") or "")
      if qtext:
        queries[vid] = qtext

  is_v13 = version_at_least(spec.get("protocol_version"), 13, 0)
  ranked = rank_bm25_passages(snap_texts, queries, top_k_per_query=(10 if is_v13 else 5))

  pack_lines = [

      f"# Compiled Evidence & Passage Pack (`{d.name}`)",

      f"Sources fetched: {len(index)} | Ranked passages: {len(ranked)}",

      "",

      "## Source Index",

  ]

  for r in index:

    pack_lines.append(f"- **{r['id']}** ({r['chars']} chars, sha256 `{r['sha256'][:12]}...`): {r['url']}")

  pack_lines.append("\n## Top BM25 Verbatim Spans (Copy exact substrings into `manifest.evidence`)")

  for item in ranked:

    prior = float(item.get("insider_prior", 1.0) or 1.0)

    nugget_tag = (
        f" [GOLDEN NUGGET prior=x{prior:.1f} langs={','.join(item.get('insider_languages', []))}]"
        if prior > 1.0 else ""
    )

    also = item.get("also_matches") or []
    also_tag = f" also={','.join(str(x) for x in also)}" if also else ""

    pack_lines.append(
        f"### [{item['query_id']}] {item['locator']} (BM25={item['score']})"
        f"{nugget_tag}{also_tag}"
    )

    if item.get("reserved_slot"):
      pack_lines.append("> Reserved O_dethrone / insider slot: surfaced despite low lexical overlap.")

    pack_lines.append(f"> {item['quote_span']}\n")

  # v12.0+ Frontier 3: put the mandatory EAD scaffold directly in the pack the
  # synthesis step reads, so the report author cannot forget the alpha delta.
  if version_at_least(spec.get("protocol_version"), 12, 0):
    pack_lines.append("\n## Mandatory Report Section (Rule R18)")
    pack_lines.append(
        "The final report.md MUST contain a `## Epistemic Alpha Delta` section "
        "with Superficial Consensus, Trench Ground-Truth (The Alpha) citing a "
        "snapshot-verified [E###] NOT cited in the consensus, and Delta Impact "
        "naming the financial / operational / strategic loss.\n"
    )
    pack_lines.append(str(spec.get("ead_scaffold") or ""))
    if dethrone_vectors:
      compiled_ids = [
        str(v.get("vector_id") or "DTH") for v in dethrone_vectors[:6]
        if isinstance(v, dict)
      ]
      pack_lines.append("\n### Compiled O_dethrone Query IDs")
      pack_lines.append(", ".join(compiled_ids))
      pack_lines.append(
          f"\nO_dethrone: {len(dethrone_vectors)} adversarial 30/90-day vectors were "
          "compiled above. Rule B11 requires a `manifest.dethroning[]` record "
          "(status intact|dethroned, vectors_run >= 8, checked_at within 30 days, "
          "recency_verified=true, snapshot-verified evidence_ids) before any "
          "world-record / leading-model claim can be certified."
      )

  # v13.0: Anti-Truncation Depth (R19), Claim-Link-Quote Ledger (R20) & B12 Checklist
  if is_v13:
    quotas = spec.get("depth_quotas") or {}
    pack_lines.append("\n## Mandatory v13.0 Deep-Digging & Claim-Link-Quote Gates (R19 / R20 / R21 / B12)")
    pack_lines.append(
        f"- **R19 (Anti-Truncation):** >= {quotas.get('min_words', 1000)} prose words, "
        f">= {quotas.get('min_sources', 5)} snapshotted sources, "
        f">= {quotas.get('min_evidence', 8)} verified `[E###]` quotes, "
        f">= {quotas.get('min_tables', 2)} structured Markdown tables, "
        f">= {quotas.get('min_sections', 5)} `## ` sections, "
        f">= {quotas.get('min_model_vars', 4)} `python:model` variables.\n"
        "- **R20 (Claim-Link-Quote Ledger):** Include the table below with >= "
        f"{quotas.get('min_ledger_rows', 8)} rows mapping Claim -> Primary URL -> Verbatim Quote -> `[E###]`.\n"
        "- **B12 (Anti-Hallucination):** NEVER write `MAXIMUM CONVICTION GO`, uncalculated `Nx` multipliers, "
        "or unbacked `~N occurrences/year` guesses.\n"
        "- **R21 (Deliverable Guard):** Export ONLY via `python dr_engine/tools/lean_engine.py export --dir <study> --out reports/<NAME>.md`.\n"
    )
    pack_lines.append(str(spec.get("claim_ledger_scaffold") or render_claim_ledger_scaffold()))

  (d / "context_pack.md").write_text("\n".join(pack_lines) + "\n", encoding="utf-8")

  print(f"[INGEST OK] {len(index)} sources snapshotted -> {d / 'context_pack.md'}")

  return 0





# ---------------------------------------------------------------------------

# 5. Stage 2 (`verify`): Single-Pass Compiler, Algebraic Closure & Audit Gate

# ---------------------------------------------------------------------------

@dataclass

class VerificationReport:

  study_dir: str

  passed: bool = False

  epistemic_index: float = 0.0

  information_density_index: float = 0.0

  max_confidence: str = "Low"

  n_sources: int = 0

  n_evidence: int = 0

  n_models: int = 0

  n_eff_clusters: float = 0.0

  bound_units: int = 0

  total_claim_units: int = 0

  dl_meta_analyses: list[dict[str, Any]] = field(default_factory=list)

  # v11.0: B10 Dialectical Reconciliation Matrix and R17 density diagnostics.
  dialectical_arbitration: dict[str, Any] = field(default_factory=dict)

  empirical_density_per_100w: float = 0.0

  boilerplate_hits: list[str] = field(default_factory=list)

  # v12.0: EAD / dethroning gate diagnostics.
  v12_protocol_active: bool = False

  ead_diagnostics: dict[str, Any] = field(default_factory=dict)

  dethroning_diagnostics: dict[str, Any] = field(default_factory=dict)

  # v13.0: Deep-Digging R19, Claim-Link-Quote Ledger R20 & B12 diagnostics.
  v13_protocol_active: bool = False

  depth_diagnostics: dict[str, Any] = field(default_factory=dict)

  ledger_diagnostics: dict[str, Any] = field(default_factory=dict)

  failures: list[str] = field(default_factory=list)

  warnings: list[str] = field(default_factory=list)





def _extract_embedded_blocks(report_text: str) -> tuple[dict[str, Any], list[tuple[str, str]], str]:

  """Extracts ` ```json:manifest ` and ` ```python:model ` blocks from report.md,

  returning (manifest_dict, [(model_id, code_str)], prose_only_text)."""

  manifest: dict[str, Any] = {}

  models: list[tuple[str, str]] = []



  for m in re.finditer(r"```json:manifest\s*\n(.*?)```", report_text, re.S):

    manifest = json.loads(m.group(1).strip())



  for idx, m in enumerate(re.finditer(r"```python:model(?:\s+(\w+))?\s*\n(.*?)```", report_text, re.S), 1):

    mid = m.group(1) or f"C{idx:03d}"

    models.append((mid, m.group(2).strip()))



  # Strip attestation footers, fenced code blocks, and math blocks from prose before auditing sentences
  clean_rep = ATTESTATION_MARKER_RE.sub("", report_text)

  prose = re.sub(r"```.*?```", "\n", clean_rep, flags=re.S)

  prose = re.sub(r"\$\$.*?\$\$", "\n", prose, flags=re.S)

  return manifest, models, prose





def verify_study(d: Path, force_v12: bool = False, force_v13: bool = False, force_v14: bool = False) -> VerificationReport:

  """Verify one study. ``force_v12`` / ``force_v13`` / ``force_v14`` activate v12/v13/v14 gates
  even on legacy specs (``verify --strict-v12`` / ``--strict-v13`` / ``--strict-v14``)."""
  force_v13 = bool(force_v13 or force_v14)
  force_v12 = bool(force_v12 or force_v13)

  res = VerificationReport(study_dir=str(d))

  src_dir = d / "sources"

  idx_path = src_dir / "index.jsonl"

  rep_path = d / "report.md"



  if not idx_path.exists():

    res.failures.append("E1: sources/index.jsonl missing (run `lean_engine.py ingest` first)")

    return res

  if not rep_path.exists():

    res.failures.append("R1: report.md missing")

    return res



  sources = {

      r["id"]: r for r in (json.loads(l) for l in idx_path.read_text(encoding="utf-8").splitlines() if l.strip())

  }

  snaps: dict[str, str] = {}

  for sid, srec in sources.items():

    p = src_dir / f"{sid}.txt"

    if not p.exists():

      res.failures.append(f"E1: snapshot {sid}.txt missing")

      continue

    txt = p.read_text(encoding="utf-8")

    if sha256_text(txt) != srec.get("sha256"):

      res.failures.append(f"E1: snapshot {sid}.txt SHA-256 mismatch (hand-edited)")

    snaps[sid] = txt



  res.n_sources = len(snaps)

  # v11.0: mirror-rescued sources are secondary transcriptions. Recording the
  # downgrade here prevents a Wayback copy or a search snippet from being
  # silently treated as an independent primary T1 observation.
  secondary_sources = [
      sid for sid, srec in sources.items() if srec.get("secondary_transcription")
  ]
  if secondary_sources:
    res.warnings.append(
        f"W_SECONDARY_TRANSCRIPTION: {sorted(secondary_sources)} are archival / "
        "syndicated / search-cache copies, not primary snapshots. Cap these at "
        "T3, never use one as sole triangulation, and re-fetch a primary page "
        "before quoting them as ground truth"
    )

  raw_report = rep_path.read_text(encoding="utf-8")



  # Extract embedded manifest & executable AST models (or fallback to manifest.json file)

  try:

    manifest, model_blocks, prose_text = _extract_embedded_blocks(raw_report)

  except Exception as e:

    res.failures.append(f"M1: malformed embedded block in report.md: {e}")

    return res



  if not manifest and (d / "manifest.json").exists():

    manifest = json.loads((d / "manifest.json").read_text(encoding="utf-8"))



  evidence_list: list[dict[str, Any]] = manifest.get("evidence", [])
  if not isinstance(evidence_list, list):
    res.failures.append("M1: manifest.evidence must be a list")
    evidence_list = []

  kill_list: list[dict[str, Any]] = manifest.get("kills", [])

  claims_list: list[dict[str, Any]] = manifest.get("claims", [])

  counterparty: dict[str, Any] = manifest.get("counterparty_physics", {})



  # 1. Verify Evidence Quotes Verbatim against Snapshots

  ev_by_id: dict[str, dict[str, Any]] = {}

  ev_numbers: dict[str, set[float]] = {}

  all_evidence_base_nums: set[float] = set()



  for ev in evidence_list:

    eid = ev.get("id", "")

    sid = ev.get("source", "")
    if not sid and "source_url" in ev:
      for s_candidate_id, s_data in sources.items():
        if s_data.get("url") == ev.get("source_url"):
          sid = s_candidate_id
          break

    quote = ev.get("quote", "")
    if not isinstance(quote, str):
      res.failures.append(f"E2: {eid} quote is not a string ({type(quote).__name__})")
      continue
    if len(normalise_ws(quote)) < 20:
      res.failures.append(f"E2: {eid} quote is too short to be a verbatim excerpt")
      continue

    if sid not in snaps:

      res.failures.append(f"E2: {eid} references unfetched source {sid!r}")

      continue

    if not quote_matches_snapshot(quote, snaps[sid]):

      res.failures.append(f"E2: {eid} quote not found verbatim in {sid}.txt: {quote[:80]!r}")

      continue

    ev_by_id[eid] = ev

    q_nums = extract_numbers(quote, strip_exempt=False)

    ev_numbers[eid] = q_nums

    all_evidence_base_nums |= q_nums



  res.n_evidence = len(ev_by_id)

  if res.n_evidence < 3:

    res.failures.append(f"E2: only {res.n_evidence} verified evidence records; need >= 3")

  # v14.1 Rule B14: bind report.md to the pre-synthesis evidence locker.
  # Enforced whenever the report cites [E###] or a ledger exists (independent of protocol version).
  if EID_RE.search(raw_report) or (d / "evidence_ledger.json").exists():
    from dr_engine.tools.evidence_locker import verify_report_against_ledger
    res.failures.extend(verify_report_against_ledger(d, manifest, raw_report))



  # 2. Execute Sandboxed AST Models (`python:model` blocks & manifest models)

  calc_by_id: dict[str, set[float]] = {}

  global_model_env: dict[str, float] = {}

  for mid, code_str in model_blocks:

    try:

      emitted = execute_model_block(code_str, initial_env=global_model_env)

      global_model_env.update(emitted)

      calc_by_id[mid] = set(emitted.values()) | extract_numbers(code_str, strip_exempt=False)

    except Exception as e:

      res.failures.append(f"E8: AST model {mid} failed execution: {e}")



  for m_spec in manifest.get("models", []):

    mid = m_spec.get("id", f"C{len(calc_by_id)+1:03d}")

    try:

      emitted = execute_model_block(m_spec.get("code", ""), initial_env=global_model_env)

      global_model_env.update(emitted)

      calc_by_id[mid] = set(emitted.values()) | extract_numbers(m_spec.get("code", ""), strip_exempt=False)

    except Exception as e:

      res.failures.append(f"E8: manifest model {mid} failed execution: {e}")



  res.n_models = len(calc_by_id)



  # 3. Verify Pre-Registered Kill Hypotheses (Popperian Disconfirmation)

  if len(kill_list) < 3:

    res.failures.append(f"E3: manifest has {len(kill_list)} kill hypotheses; need >= 3")

  for k in kill_list:

    kid = k.get("id", "K?")

    verdict = str(k.get("verdict", "")).lower()

    keids = [e for e in k.get("eids", []) if e in ev_by_id]

    if verdict not in ("refuted", "confirmed", "unresolved"):

      res.failures.append(f"E3: kill hypothesis {kid} has invalid verdict {verdict!r}")

    if verdict in ("refuted", "confirmed") and not keids:

      res.failures.append(f"E5: kill hypothesis {kid} is {verdict!r} but cites no verified [E###]")



  # 4. Anti-Textbook Alpha & Counterparty Friction Check

  low_rep = raw_report.lower()

  for trap_phrase, refutation in DECAYED_TEXTBOOK_TRAPS.items():

    # v10.0: a single "refuted" in an unrelated appendix no longer
    # disarms every trap. Each mention needs its own local refutation.
    hits = unmitigated_spans(

        raw_report, re.compile(re.escape(trap_phrase), re.I),

        terms=("refuted", "decayed", "dead", "killed", "invalidated", "опроверган"),

        window=220,

    )

    if hits:

      res.failures.append(

          f"R8 (Alpha Trap): report proposes known decayed edge {trap_phrase!r} "

          f"without locally refuting it ({refutation})"

      )

  # v14.1 Rule B13 — fail-closed (AGENTS.md Rule B0).
  try:
    from dr_engine.tools.desk_memory import scan_text_against_desk_graveyard
    from dr_engine.tools.traps import check_known_traps_in_text
    desk_violations = scan_text_against_desk_graveyard(raw_report)
    trap_violations = check_known_traps_in_text(raw_report)
  except Exception as e:
    res.failures.append(f"FAIL B13 (Gate Error, fail-closed): {type(e).__name__}: {e}")
  else:
    for dv in desk_violations:
      res.failures.append(
          f"FAIL B13 (Desk Graveyard): proposes killed edge '{dv['name']}' "
          f"without refutation. {dv['description']}")
    for tv in trap_violations:
      res.failures.append(
          f"FAIL B13 (Known Trap): violates {tv.get('id', 'TRAP')} "
          f"({tv.get('name', '')}). {tv.get('description', '')}")



  if counterparty:

    if not counterparty.get("forced_actor"):

      res.failures.append("R8: counterparty_physics is missing 'forced_actor' (who is forced to trade/pay)")

    gross_bp = safe_number(counterparty.get("gross_edge_bp"), 0.0) or 0.0

    fric_bp = safe_number(counterparty.get("friction_cost_bp"), 0.0) or 0.0

    canon_verdict = normalize_verdict(manifest.get("verdict", ""))

    # v10.0: the verdict is read from the manifest, not guessed from a
    # stray "kill"/"no-go" token anywhere in the prose.
    if gross_bp > 0 and (gross_bp - fric_bp) <= 0 and canon_verdict not in NEGATIVE_VERDICTS:

      res.failures.append(

          f"R8: net edge after friction is non-positive ({gross_bp} - {fric_bp} = {gross_bp - fric_bp:.2f} bp) "

          f"without a NO-GO / KILL verdict"

      )

    # v10.0: v9.0 defaulted a MISSING sample period to 2026, silently
    # fabricating recency. A missing or malformed period is now explicit.
    raw_end = counterparty.get("sample_end_year")

    sample_end = safe_int(raw_end) if raw_end is not None else None

    if raw_end is None:

      res.warnings.append("W_DECAY: counterparty_physics.sample_end_year not declared; recency unverified")

    elif sample_end is None:

      res.failures.append(f"R8 (Malformed Sample Period): sample_end_year={raw_end!r} is not an integer year")

    elif sample_end < 2022:

      res.warnings.append(f"W_DECAY: primary empirical sample ends in {sample_end} (< 2022); high alpha decay risk")



  # 5. Column-Aware & Algebraic-Closure Semantic Grounding Check (Replaces Naive Regex R3)

  global_model_closure = algebraic_closure(set(global_model_env.values()))

  in_table = False

  exempt_col_indices: set[int] = set()



  units: list[tuple[int, str, bool]] = []
  cur_para: list[str] = []
  cur_line = 0

  def flush_para():
    nonlocal cur_para, cur_line
    if cur_para:
      units.append((cur_line, " ".join(cur_para), False))
      cur_para = []

  for l_no, raw_line in enumerate(prose_text.splitlines(), 1):
    s_line = raw_line.strip()
    if not s_line or s_line.startswith("#") or re.fullmatch(r"[-*_]{3,}", s_line):
      flush_para()
      continue
    if SPEC_LINE_RE.search(s_line):
      flush_para()
      continue
    if s_line.startswith("|"):
      flush_para()
      units.append((l_no, s_line, True))
      continue
    if re.match(r"^([-*+]|\d+[.)])\s+", s_line):
      flush_para()
      units.append((l_no, s_line, False))
      continue
    if not cur_para:
      cur_line = l_no
    cur_para.append(s_line)
  flush_para()

  in_table = False
  exempt_col_indices: set[int] = set()

  for line_no, s, is_row in units:
    if is_row:
      if re.fullmatch(r"\|?[\s:|-]+\|?", s) and "-" in s:
        continue
      cells = [c.strip() for c in s.strip("|").split("|")]
      if not in_table:
        in_table = True
        exempt_col_indices = {
            idx for idx, col_name in enumerate(cells)
            if EXEMPT_COL_HEADER_RE.search(col_name) or "[I]" in col_name
        }
        continue
      empirical_text = " | ".join(
          c for idx, c in enumerate(cells) if idx not in exempt_col_indices and "[I]" not in c
      )
      target_nums = extract_numbers(empirical_text, strip_exempt=True)
    else:
      in_table = False
      target_nums = extract_numbers(s, strip_exempt=True)



    if not target_nums:

      continue



    res.total_claim_units += 1

    cited_eids = [e for e in EID_RE.findall(s) if e in ev_by_id]

    cited_cids = [c for c in CID_RE.findall(s) if c in calc_by_id]



    if not cited_eids and not cited_cids:

      # Check if all numbers on this line are already exported by the study's AST models

      if all(is_number_bound(n, global_model_closure) for n in target_nums):

        res.bound_units += 1

        continue

      res.failures.append(f"R2 (L{line_no}): quantitative claim has no [E###] or [C###]: {s[:100]}")

      continue



    unit_base_nums: set[float] = set(global_model_env.values())

    for e in cited_eids:

      unit_base_nums |= ev_numbers[e]

    for c in cited_cids:

      unit_base_nums |= calc_by_id[c]



    unit_closure = algebraic_closure(unit_base_nums)

    unbound = [n for n in sorted(target_nums) if not is_number_bound(n, unit_closure)]

    if not unbound:

      res.bound_units += 1

    else:

      res.failures.append(

          f"R3 (L{line_no}): number(s) {unbound[:4]} not in Algebraic Closure of {cited_eids + cited_cids}"

      )



  def _regime_split_discussed(report: str, dl: dict, mf: dict) -> bool:

    """v10.0: require a regime discussion attached to the heterogeneous

    subject, or an explicit structured declaration -- not a stray word.

    """

    declared = bool((mf.get("heterogeneity") or {}).get("regime_split_discussed"))

    if declared:

      return True

    subject_pos = report.lower().find(str(dl.get("subject", "")).lower())

    if subject_pos < 0:

      return False

    return is_mitigated_locally(

        report, subject_pos,

        terms=("regime", "split", "partition", "scope", "subperiod", "heterogeneity"),

        window=400, max_sentence_gaps=3,

    )



  # 6. DerSimonian-Laird I^2 Pooling & N_eff Independence Scoring

  res.dl_meta_analyses = dersimonian_laird_pool(claims_list)

  for dl in res.dl_meta_analyses:

    if dl["regime_split_required"] and not _regime_split_discussed(raw_report, dl, manifest):

      res.failures.append(

          f"R11: high heterogeneity (I^2={dl['i2_pct']}%) on {dl['subject']}.{dl['metric']} "

          f"requires explicit regime splitting in report prose"

      )



  ent = compute_neff_and_entropy(list(ev_by_id.values()), sources)

  res.n_eff_clusters = ent["n_eff"]



  # 6.5. v10.0 FAIL-CLOSED epistemic filters (B0-B9).
  # v9.0 wrapped this in `except Exception -> warnings.append(...)`; since
  # `res.passed = len(failures) == 0`, any exception silently certified the
  # study with NO B1-B9 evaluation. An unevaluable filter is now a B0 hard
  # failure, and B9 receives only quotes already verified against snapshots.
  # Evidence from an unverified bundled offline seed is snapshot-verifiable
  # but is NOT an independent measured observation. Exclude it from B9's
  # Tier-2 grounding set so a hardcoded leaderboard cannot certify a SOTA claim.
  trusted_evidence_ids = {
      eid for eid, ev in ev_by_id.items()
      if not sources.get(str(ev.get("source", "")), {}).get("unverified_bundled", False)
  }
  excluded = set(ev_by_id) - trusted_evidence_ids
  if excluded:
    res.warnings.append(
        f"W_UNVERIFIED_SEED: {sorted(excluded)} cite unverified bundled offline "
        "sources and cannot ground comparative SOTA claims"
    )
  # v11.0 B10: de_jure/de_facto arbitration + confidence cap.
  arbitration: dict[str, Any] = {}
  b_fails, b_warns = run_filters_fail_closed(
      raw_report, manifest, global_model_env,
      verified_evidence_ids=trusted_evidence_ids,
      arbitration_out=arbitration,
      pooled_subjects=[str(dl.get("subject", "")) for dl in res.dl_meta_analyses],
  )
  res.dialectical_arbitration = arbitration
  res.failures.extend(b_fails)
  res.warnings.extend(b_warns)

  # 6.6. v12.0 FRONTIERS 1 & 3 — Rule R18 (Epistemic Alpha Delta) and
  # Rule B11 (Active Dethroning), behind a fail-closed wrapper so any
  # unevaluable v12 gate is a B0 hard failure, never a warning.
  #
  # Versioning: studies generated by auto_spec v12 declare
  # protocol_version="12.0" and MUST carry the EAD section plus (where a
  # superlative is asserted) a verified manifest.dethroning record. Pre-v12
  # studies stay on the v11 gate stack and get an explicit legacy warning,
  # which keeps the 322-test regression invariant intact without letting any
  # NEW study skip the alpha gate.
  v12_active = is_v12_protocol(d, manifest, force=bool(force_v12 or force_v13))
  v12_fail, v12_warn, v12_diag = run_v12_gates_fail_closed(
      prose_text, manifest, trusted_evidence_ids,
      protocol_active=v12_active,
  )
  res.v12_protocol_active = bool(v12_active)
  res.ead_diagnostics = dict(v12_diag.get("ead") or {})
  res.dethroning_diagnostics = dict(v12_diag.get("dethroning") or {})
  res.failures.extend(v12_fail)
  res.warnings.extend(v12_warn)
  if v12_active and not v12_fail:
    res.warnings.append(
        f"W_EAD_PASS: Epistemic Alpha Delta contrast verified "
        f"(Jaccard={res.ead_diagnostics.get('contrast_jaccard')}, "
        f"trench evidence={res.ead_diagnostics.get('verified_trench_evidence')}); "
        f"O_dethrone claims={res.dethroning_diagnostics.get('claims_detected', 0)}"
    )

  # 6.7. v13.0 FRONTIERS — Rule R19 (Anti-Truncation Depth), Rule R20
  # (Mandatory Claim -> URL -> Verbatim Quote Ledger) & Rule B12
  # (Hyperbolic Verdict, Fake Multiplier & Frequency Guess Ban), fail-closed.
  v13_active = is_v13_protocol(d, manifest, force=bool(force_v13))
  v13_fail, v13_warn, v13_diag = run_v13_gates_fail_closed(
      raw_report,
      study_dir=d,
      manifest=manifest,
      sources_index=sources,
      source_texts=snaps,
      verified_evidence_ids=trusted_evidence_ids,
      model_env=global_model_env,
      protocol_active=v13_active,
  )
  res.v13_protocol_active = bool(v13_active)
  _v = str(manifest.get("protocol_version", "")).split(".")
  res.v14_protocol_active = bool(
      force_v14
      or (len(_v) >= 1 and _v[0].isdigit() and int(_v[0]) >= 14)
      or (d / "evidence_ledger.json").exists()
  )
  res.depth_diagnostics = dict(v13_diag.get("depth") or {})
  res.ledger_diagnostics = dict(v13_diag.get("ledger") or {})
  res.failures.extend(v13_fail)
  res.warnings.extend(v13_warn)

  # 7. Epistemic Index (EI) & Information Density Index (IDI)

  if res.n_evidence > 0:

    a_e = sum(TIER_WEIGHTS.get(r.get("tier", "T5"), 0.20) for r in ev_by_id.values()) / res.n_evidence

  else:

    a_e = 0.0

  t_d = min(1.0, res.n_eff_clusters / 4.0) * ent["echo_multiplier"]

  resolved_kills = sum(1 for k in kill_list if str(k.get("verdict", "")).lower() in ("refuted", "confirmed"))

  s_k = (resolved_kills / max(3, len(kill_list))) if kill_list else 0.0

  v_q = (res.bound_units / res.total_claim_units) if res.total_claim_units > 0 else 1.0



  res.epistemic_index = round(100.0 * (0.35 * a_e + 0.25 * t_d + 0.20 * s_k + 0.20 * v_q), 1)



  from dr_engine.tools.density_gate import evaluate_r17_gate, strip_fenced_code
  prose_no_code = strip_fenced_code(prose_text)
  # Exclude R20 evidence-ledger table rows (already counted via n_evidence) and Markdown pipe borders
  # so quoting complete primary clauses in the ledger never artificially dilutes prose density.
  narrative_lines = [
      ln for ln in prose_no_code.splitlines()
      if not (
          ln.lstrip().startswith("|")
          and (
              re.fullmatch(r"[\s|:\-]+", ln.strip())
              or ("http" in ln.lower() and re.search(r"\bE\d{3}\b", ln))
          )
      )
  ]
  narrative_prose = re.sub(r"(?:https?://\S+|\|+)", " ", "\n".join(narrative_lines))
  word_count = max(1, len(re.findall(r"\S+", narrative_prose)))

  code_funcs = len(re.findall(r"\bdef\s+\w+\s*\(", raw_report))

  res.information_density_index = round(
      (1000.0 / word_count)
      * (
          2.0 * res.n_evidence
          + 5.0 * res.n_models
          + 2.5 * len(global_model_env)
          + 2.0 * res.bound_units
          + 8.0 * code_funcs
      ),
      1,
  )

  # 8. v11.0 R17: Anti-Fluff Information Density Gate (mechanical, hard).
  # v10.0 computed IDI but never enforced it, and had no boilerplate defence.
  r17_failures, r17_diag = evaluate_r17_gate(
      narrative_prose,
      idi=res.information_density_index,
      n_evidence=res.n_evidence,
      n_models=res.n_models,
      bound_units=res.bound_units,
      word_count=word_count,
  )
  res.empirical_density_per_100w = r17_diag["empirical_density_per_100w"]
  res.boilerplate_hits = r17_diag["boilerplate"]["distinct"]
  res.failures.extend(r17_failures)
  if not r17_failures:
    res.warnings.append(
        f"W_R17: IDI={r17_diag['idi']} >= {r17_diag['idi_min']:.0f}, "
        f"empirical density={r17_diag['empirical_density_per_100w']}/100w, "
        f"boilerplate hits={len(res.boilerplate_hits)}"
    )



  if res.epistemic_index >= 75.0 and not res.failures and res.n_eff_clusters >= 2.5:

    res.max_confidence = "High"

  elif res.epistemic_index >= 55.0 and not res.failures:

    res.max_confidence = "Medium"

  else:

    res.max_confidence = "Low"

  # v11.0 B10: a de_jure/de_facto contradiction may not be declared High
  # confidence until an explicit verification record exists. Process metrics
  # (EI) measure rigour, not truth -- this cap is a separate truth constraint.
  if res.dialectical_arbitration.get("confidence_cap") == "Medium" and res.max_confidence == "High":
    res.max_confidence = "Medium"
    res.warnings.append(
        "W_B10_CONFIDENCE_CAP: unresolved de_jure/de_facto contradiction; "
        "overall confidence mechanically capped at Medium (EI unchanged)"
    )



  res.passed = len(res.failures) == 0
  if res.passed:
    try:
      write_verification_receipt(
          d,
          raw_report,
          {
              "passed": True,
              "protocol_version": "14.1" if res.v14_protocol_active else ("13.0" if res.v13_protocol_active else ("12.0" if res.v12_protocol_active else "legacy")),
              "ei_score": res.epistemic_index,
              "idi_score": res.information_density_index,
              "max_confidence": res.max_confidence,
              "n_sources": res.n_sources,
              "n_evidence": res.n_evidence,
              "neff": res.n_eff_clusters,
          },
      )
    except OSError:
      pass

  return res





def cmd_verify(args: argparse.Namespace) -> int:

  d = Path(args.dir)

  rep = verify_study(
      d,
      force_v12=bool(getattr(args, "strict_v12", False) or getattr(args, "strict_v13", False) or getattr(args, "strict_v14", False)),
      force_v13=bool(getattr(args, "strict_v13", False) or getattr(args, "strict_v14", False)),
      force_v14=bool(getattr(args, "strict_v14", False)),
  )

  if args.json:

    print(json.dumps(rep.__dict__, ensure_ascii=False, indent=2))

  else:

    status = "PASS" if rep.passed else "FAIL"

    print(

        f"[{status}] {rep.study_dir} | EI={rep.epistemic_index}/100 | IDI={rep.information_density_index} | "

        f"Density={rep.empirical_density_per_100w}/100w | "

        f"MaxConf={rep.max_confidence} | N_eff={rep.n_eff_clusters} | "

        f"Ground={rep.bound_units}/{rep.total_claim_units} | "

        f"B10_conflicts={rep.dialectical_arbitration.get('conflicts_detected', 0)} | "
        f"v12={'ON' if rep.v12_protocol_active else 'legacy'} | "
        f"v13={'ON' if rep.v13_protocol_active else 'legacy'} | "
        f"EAD={'PASS' if rep.ead_diagnostics.get('passed') else 'n/a'} | "
        f"Ledger={'PASS' if rep.ledger_diagnostics.get('passed') else 'n/a'} | "
        f"O_dethrone_claims={rep.dethroning_diagnostics.get('claims_detected', 0)}"

    )

    for f in rep.failures:

      print(f"  FAIL  {f}")

    for w in rep.warnings:

      print(f"  WARN  {w}")

  return 0 if rep.passed else 1


def cmd_preflight(args: argparse.Namespace) -> int:
    """Pre-flight check against desk memory graveyard and basic invariants."""
    from dr_engine.tools.desk_memory import scan_text_against_desk_graveyard
    from dr_engine.tools.traps import check_known_traps_in_text
    study_path = Path(args.dir)

    # If a prompt is explicitly provided, evaluate it independently first
    if getattr(args, "prompt", None):
        prompt_violations = scan_text_against_desk_graveyard(args.prompt)
        prompt_traps = check_known_traps_in_text(args.prompt)
        if prompt_violations or prompt_traps:
            print(f"[PREFLIGHT BLOCKED] Violations detected in prompt:")
            for v in prompt_violations:
                print(f"  [GRAVEYARD] {v['name']}: {v['description']}")
                print(f"     Matched snippet: {v['matched_snippet']!r}")
            for t in prompt_traps:
                print(f"  [KNOWN TRAP] {t.get('id', 'TRAP')} ({t.get('name', '')}): {t.get('description', '')}")
            print("\nDo not proceed with research until these refuted hypotheses are removed or explicitly framed as refutations.")
            return 1

    text_to_check = ""
    if (study_path / "plan.md").exists():
        text_to_check += (study_path / "plan.md").read_text(encoding="utf-8") + "\n"
    if (study_path / "study_spec.json").exists():
        text_to_check += (study_path / "study_spec.json").read_text(encoding="utf-8") + "\n"
    if (study_path / "report.md").exists():
        text_to_check += (study_path / "report.md").read_text(encoding="utf-8") + "\n"

    violations = scan_text_against_desk_graveyard(text_to_check)
    traps = check_known_traps_in_text(text_to_check)
    if violations or traps:
        print(f"[PREFLIGHT BLOCKED] Violations detected in study files:")
        for v in violations:
            print(f"  [GRAVEYARD] {v['name']}: {v['description']}")
            print(f"     Matched snippet: {v['matched_snippet']!r}")
        for t in traps:
            print(f"  [KNOWN TRAP] {t.get('id', 'TRAP')} ({t.get('name', '')}): {t.get('description', '')}")
        print("\nDo not proceed with research until these refuted hypotheses are removed or explicitly framed as refutations.")
        return 1

    print(f"[PREFLIGHT PASS] Study `{args.dir}` passed desk memory graveyard pre-flight check. Zero violations.")
    return 0


def cmd_lock_evidence(args: argparse.Namespace) -> int:
    """Locks verified evidence quotes from snapshots into immutable evidence_ledger.json."""
    from dr_engine.tools.evidence_locker import lock_evidence
    study_path = Path(args.dir)
    ev_items = []
    rep_path = study_path / "report.md"
    if rep_path.exists():
        m = re.search(r"```json:manifest\s*\n(.*?)```", rep_path.read_text(encoding="utf-8"), re.S)
        if m:
            try:
                ev_items = json.loads(m.group(1)).get("evidence", [])
            except Exception:
                pass
    if not ev_items and (study_path / "manifest.json").exists():
        try:
            ev_items = json.loads((study_path / "manifest.json").read_text(encoding="utf-8")).get("evidence", [])
        except Exception:
            pass

    if not ev_items:
        print(f"[LOCK-EVIDENCE REFUSED] No evidence list found in `{args.dir}/report.md` manifest or `manifest.json`.")
        return 1

    locked, errs = lock_evidence(study_path, ev_items)
    if errs:
        print(f"[LOCK-EVIDENCE FAILED] {len(errs)} quote(s) failed snapshot verification:")
        for e in errs:
            print(f"  FAIL  {e}")
        return 1

    print(f"[LOCK-EVIDENCE OK] Locked {len(locked)} verified quotes -> {study_path / 'evidence_ledger.json'}")
    return 0


def cmd_colab(args: argparse.Namespace) -> int:
    """Exports AST models and statistical battery to executable Google Colab notebook."""
    from dr_engine.tools.colab_exporter import export_colab_notebook
    study_path = Path(args.dir)
    out_p = Path(args.out) if getattr(args, "out", None) else None
    try:
        nb_path = export_colab_notebook(study_path, out_p)
        print(f"[COLAB OK] Executable Jupyter notebook written -> {nb_path}")
        return 0
    except Exception as e:
        print(f"[COLAB FAILED] Could not export notebook: {e}")
        return 1


def cmd_colab_verify(args: argparse.Namespace) -> int:
    """Headlessly executes research_notebook.ipynb and writes notebook_execution_receipt.json."""
    from dr_engine.tools.notebook_verifier import verify_notebook
    study_path = Path(args.dir)
    nb_path = study_path / "research_notebook.ipynb"
    if not nb_path.exists():
        print(f"[COLAB-VERIFY REFUSED] {nb_path} does not exist. Run `lean_engine.py colab` first.")
        return 1
    receipt_p = Path(getattr(args, "receipt", None) or (study_path / "notebook_execution_receipt.json"))
    receipt = verify_notebook(nb_path, timeout=getattr(args, "timeout", 300))
    receipt_p.parent.mkdir(parents=True, exist_ok=True)
    receipt_p.write_text(json.dumps(receipt, indent=2, ensure_ascii=False), encoding="utf-8")
    if receipt.get("passed"):
        print(f"[COLAB-VERIFY OK] Notebook executed headlessly with 0 errors -> {receipt_p}")
        return 0
    else:
        print(f"[COLAB-VERIFY FAIL] Notebook execution errors: {receipt.get('cell_errors') or receipt.get('error')}")
        return 1


def cmd_export(args: argparse.Namespace) -> int:
  """Rule R21 gated deliverable exporter: verifies study before writing to `reports/`."""
  sdir = Path(args.dir)
  nb_p = sdir / "research_notebook.ipynb"
  if nb_p.exists():
      rc_p = sdir / "notebook_execution_receipt.json"
      if not rc_p.exists():
          print(f"[EXPORT REFUSED] {nb_p} exists but notebook_execution_receipt.json missing. Run `lean_engine.py colab-verify --dir {args.dir}` first.")
          return 1
      try:
          rec = json.loads(rc_p.read_text(encoding="utf-8"))
          if not rec.get("passed"):
              print(f"[EXPORT REFUSED] Notebook execution receipt has errors: {rec.get('cell_errors')}")
              return 1
          current_nb_hash = hashlib.sha256(nb_p.read_bytes()).hexdigest()
          receipt_nb_hash = rec.get("notebook_sha256")
          if not receipt_nb_hash or current_nb_hash != receipt_nb_hash:
              print(f"[EXPORT REFUSED] Notebook bytes do not match verified receipt ({current_nb_hash[:12]} != {str(receipt_nb_hash)[:12]}). Run `colab-verify`.")
              return 1
      except Exception as e:
          print(f"[EXPORT REFUSED] Unreadable notebook_execution_receipt.json: {e}")
          return 1

  strict14 = bool(getattr(args, "strict_v14", False))
  strict13 = bool(getattr(args, "strict_v13", False)) or strict14
  strict12 = bool(getattr(args, "strict_v12", False)) or strict13
  ok, fails, dest = export_verified_report(
      args.dir,
      args.out,
      verify_fn=lambda p: verify_study(p, force_v12=strict12, force_v13=strict13, force_v14=strict14),
  )
  if not ok:
    print(f"[EXPORT REFUSED] Study `{args.dir}` failed verification ({len(fails)} error(s)):")
    for f in fails:
      print(f"  FAIL  {f}")
    return 1
  print(f"[EXPORT OK] Verified & attested deliverable written -> {dest}")
  return 0


def cmd_audit_deliverables(args: argparse.Namespace) -> int:
  """Rule R21 scanner: reject unverified standalone `.md` files in `reports/`."""
  res = audit_deliverables_directory(
      args.reports_dir,
      args.research_root,
      since_date=args.since,
      check_all=bool(args.all),
  )
  status = "PASS" if res["passed"] else "FAIL"
  print(
      f"[DELIVERABLES AUDIT {status}] checked={res['checked']} | "
      f"verified={len(res['verified'])} | violations={len(res['violations'])} | "
      f"skipped_legacy={len(res['skipped_legacy'])}"
  )
  for v in res["violations"]:
    print(f"  FAIL  {v['file']}: {v['reason']}")
  return 0 if res["passed"] else 1

def cmd_selftest(_args: argparse.Namespace) -> int:
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp) / "2026-11-05-0dte-gex-study"
        d.mkdir(parents=True, exist_ok=True)

        spec = {
            "sub_questions": {
                "SQ1": "0DTE dealer gamma hedging intraday momentum and reversal regimes",
                "SQ2": "Execution spread and slippage friction on US index futures M15",
            },
            "kill_hypotheses": {
                "K1": "Exchange fee and M15 bid-ask spread exceed gross intraday displacement alpha",
                "K2": "Dealer GEX flip signal decayed post-2024 as market makers internalized flow",
                "K3": "Overnight swap charges invalidate multi-day holding periods",
            },
            "inline_sources": {
                "https://cboe.com/microstructure/0dte-gamma-2025": (
                    "CBOE Empirical Market Structure Report (2024-2025): Across 500 trading sessions, "
                    "when net dealer 0DTE gamma exposure falls below -2.5 billion USD, 15-minute index "
                    "displacement exhibits a gross return of 8.4 bps per trade with a 58% win rate. "
                    "Conversely, positive gamma regimes above +3.0 billion USD compress realized volatility by 34%."
                ),
                "https://cmegroup.com/nq-liquidity-friction-2025": (
                    "CME Microstructure Execution Benchmark 2025: Top-of-book effective spread on US100 (NQ) "
                    "during regular trading hours averages 1.2 bps, with institutional market-order slippage "
                    "adding 0.9 bps per side (1.8 bps round-turn). Total round-turn execution friction is 3.0 bps."
                ),
                "https://bis.org/publ/work1190-fx-equity-auctions": (
                    "BIS Working Paper 1190 (2025): European and US cash close auctions account for 28% of "
                    "daily equity volume, creating predictable hedging pressure in the final 30 minutes."
                ),
            },
        }
        spec_file = d / "study_spec.json"
        spec_file.write_text(json.dumps(spec, indent=2), encoding="utf-8")

        # Stage 1: Ingest & Auto-BM25 Context Pack
        rc_ing = cmd_ingest(argparse.Namespace(dir=str(d), spec=str(spec_file)))
        assert rc_ing == 0, "Ingest failed"
        assert (d / "context_pack.md").exists(), "context_pack.md not generated"

        # Stage 2: Single-turn synthesized report with embedded manifest, AST model, and inline algebra
        report_md = """# Intraday 0DTE Gamma Imbalance & Dealer Hedging Flow (As of 2026-11-05)

## Executive Synthesis & Microstructure Physics
When net dealer 0DTE gamma drops below -2.5 billion USD, market makers must hedge in the direction
of price movement, generating 8.4 bps gross return per trade with a 58% win rate (and a 42% loss rate)
across 500 sessions [E001]. In positive gamma regimes above +3.0 billion USD, volatility drops by 34% [E001].
On US100 M15 bars across 252 trading days (95% CI), effective spread is 1.2 bps and slippage is 0.9 bps
per side, or 1.8 bps round-turn, yielding 3.0 bps total round-turn friction [E002]. Net alpha after
friction is 5.4 bps per trade (`C001`), while closing auctions drive 28% of daily volume [E003].

| # | Parameter / Regime | Horizon | Gross Alpha (bps) | Friction (bps) | Net Edge (bps) | Score [I] | Evidence |
| :- | :-- | :-- | :-- | :-- | :-- | :-- | :-- |
| 1 | Negative GEX (< -2.5B) | M15 | 8.4 | 3.0 | 5.4 | 4.8/5 | [E001, E002, C001] |

```python:model C001
gross_bp = 8.4
spread_bp = 1.2
slippage_rt_bp = 2 * 0.9
total_friction_bp = spread_bp + slippage_rt_bp
net_alpha_bp = net_edge_bp(gross_bp, spread_bp, slippage_rt_bp)
expected_annual_bps = net_alpha_bp * 252
```

```python
def compute_gex_displacement_signal(gex_bn: float, atr_15m: float) -> float:
    if gex_bn < -2.5:
        return 1.5 * atr_15m
    return 0.0
```

```json:manifest
{
  "counterparty_physics": {
    "forced_actor": "Short-gamma options market makers forced to delta-hedge into momentum",
    "sample_end_year": 2025,
    "gross_edge_bp": 8.4,
    "friction_cost_bp": 3.0
  },
  "evidence": [
    {
      "id": "E001",
      "source": "S001",
      "tier": "T1",
      "stance": "supports",
      "quote": "when net dealer 0DTE gamma exposure falls below -2.5 billion USD, 15-minute index displacement exhibits a gross return of 8.4 bps per trade with a 58% win rate. Conversely, positive gamma regimes above +3.0 billion USD compress realized volatility by 34%."
    },
    {
      "id": "E002",
      "source": "S002",
      "tier": "T1",
      "stance": "supports",
      "quote": "Top-of-book effective spread on US100 (NQ) during regular trading hours averages 1.2 bps, with institutional market-order slippage adding 0.9 bps per side (1.8 bps round-turn). Total round-turn execution friction is 3.0 bps."
    },
    {
      "id": "E003",
      "source": "S003",
      "tier": "T1",
      "stance": "supports",
      "quote": "European and US cash close auctions account for 28% of daily equity volume"
    }
  ],
  "kills": [
    {"id": "K1", "verdict": "refuted", "eids": ["E001", "E002"]},
    {"id": "K2", "verdict": "refuted", "eids": ["E001"]},
    {"id": "K3", "verdict": "refuted", "eids": ["E003"]}
  ],
  "claims": [
    {"id": "CL01", "subject": "us100_0dte", "metric": "net_edge", "value": 5.4, "unit": "bps", "scope": "neg_gex", "eids": ["E001", "E002"]}
  ]
}
```
"""
        (d / "report.md").write_text(report_md, encoding="utf-8")
        cmd_lock_evidence(argparse.Namespace(dir=str(d)))

        rep = verify_study(d)
        assert rep.passed, f"Expected PASS, got failures: {rep.failures}"
        assert rep.bound_units == rep.total_claim_units, "Not all claim units bound"
        assert rep.n_eff_clusters == 3.0, f"Expected N_eff=3.0, got {rep.n_eff_clusters}"
        print(
            f"[SELFTEST PASS] LEAN Engine v12.0 verified in single pass: "
            f"EI={rep.epistemic_index}/100, IDI={rep.information_density_index}, "
            f"MaxConf={rep.max_confidence}, N_eff={rep.n_eff_clusters}"
        )
        return 0


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_ing = sub.add_parser("ingest")
    p_ing.add_argument("--dir", required=True)
    p_ing.add_argument("--spec", help="Path to study_spec.json (default: <dir>/study_spec.json)")
    p_ing.add_argument("--deep", action="store_true", help="Spider high-value T&C/FAQ/Rules/PDF subpages")
    p_ing.add_argument("--max-subpages", type=int, default=None, help="Override max subpages to spider")
    p_ing.set_defaults(fn=cmd_ingest)

    p_ver = sub.add_parser("verify")
    p_ver.add_argument("--dir", required=True)
    p_ver.add_argument("--json", action="store_true")
    p_ver.add_argument("--strict-v12", action="store_true",
                        help="Force the mandatory EAD (R18) and dethroning (B11) "
                             "gates even on a study whose spec predates v12")
    p_ver.add_argument("--strict-v13", action="store_true",
                        help="Force v13 Deep-Digging (R19), Claim-Link-Quote Ledger (R20) "
                             "& Anti-Hallucination (B12) gates on any study")
    p_ver.add_argument("--strict-v14", action="store_true",
                        help="Force v14 Evidence Locker (B14) & strict pre-synthesis gates on any study")
    p_ver.set_defaults(fn=cmd_verify)

    p_exp = sub.add_parser("export", help="Verify study and export attested report to reports/")
    p_exp.add_argument("--dir", required=True, help="Verified research/<slug> directory")
    p_exp.add_argument("--out", required=True, help="Destination path in reports/<NAME>.md")
    p_exp.add_argument("--strict-v12", action="store_true")
    p_exp.add_argument("--strict-v13", action="store_true")
    p_exp.add_argument("--strict-v14", action="store_true")
    p_exp.set_defaults(fn=cmd_export)

    p_pref = sub.add_parser("preflight", help="Check study against desk memory graveyard and invariants")
    p_pref.add_argument("--dir", required=True)
    p_pref.add_argument("--prompt", help="Optional user prompt to check before study init")
    p_pref.set_defaults(fn=cmd_preflight)

    p_lock = sub.add_parser("lock-evidence", help="Lock verified evidence quotes into evidence_ledger.json")
    p_lock.add_argument("--dir", required=True)
    p_lock.set_defaults(fn=cmd_lock_evidence)

    p_col = sub.add_parser("colab", help="Compile AST models into executable Google Colab notebook")
    p_col.add_argument("--dir", required=True)
    p_col.add_argument("--out", help="Optional output notebook path")
    p_col.set_defaults(fn=cmd_colab)

    p_col_ver = sub.add_parser("colab-verify", help="Execute notebook headlessly and write execution receipt")
    p_col_ver.add_argument("--dir", required=True)
    p_col_ver.add_argument("--receipt", help="Optional output receipt path")
    p_col_ver.add_argument("--timeout", type=int, default=300)
    p_col_ver.set_defaults(fn=cmd_colab_verify)

    p_aud = sub.add_parser("audit-deliverables", help="Audit reports/ against unverified standalone stubs")
    p_aud.add_argument("--reports-dir", default="reports")
    p_aud.add_argument("--research-root", default="research")
    p_aud.add_argument("--since", default="2026-11-07", help="ISO cutoff date for mandatory R21 attestation")
    p_aud.add_argument("--all", action="store_true", help="Audit all historical reports regardless of mtime")
    p_aud.set_defaults(fn=cmd_audit_deliverables)

    p_st = sub.add_parser("selftest")
    p_st.set_defaults(fn=cmd_selftest)

    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
