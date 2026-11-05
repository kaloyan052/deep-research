"""Frontier Engine v6.0: Bayesian Optimal Stopping, Adversarial Epistemic Tournaments,
Non-Linear Tipping-Point Dynamics, and Topological Claim-Space Analysis.

The v6.0 paradigm leap operationalizes four theorems the v5.0 pipeline did not close:

  1. EVSI / Optimal Stopping (Bayesian Value of Information):
     A Beta-Bernoulli posterior over P(thesis true) is updated by every evidence
     record, weighted by source-tier reliability. The Expected Value of Sample
     Information of fetching source S_{k+1} is computed analytically; discovery
     STOPs when EVSI <= cost (information-space saturation), not by vibes.
  2. Adversarial Epistemic Tournament (game theory):
     PROPONENT vs SKEPTIC vs RED_TEAM play a deterministic scoring game over the
     claim ledger with Kelly-style belief bets. Convergence is a Nash check:
     no agent can raise its payoff by a unilateral strategy switch.
  3. Non-Linear Dynamics & Tipping Points:
     The causal DAG is linearized into a Jacobian; the dominant eigenvalue
     (power iteration) measures critical slowing down (|lambda| -> 1). A
     bifurcation scan locates the parameter flip point where the outcome
     crosses its threshold, and a threshold cascade simulates contagion.
  4. Topological Claim Space:
     Claims + evidence form a graph (citation edges, conflict edges). Tarjan's
     algorithm finds articulation points and bridges; unchallenged claims
     (no contradicting evidence, no conflict edge) are blind spots; a spectral
     2D layout (power iteration on the normalized adjacency) exposes the latent
     narrative manifolds without any external embedding model.

Commands:
  python dr_engine/tools/frontier.py evsi       --dir D [--cost 0.01] [--next-tier T3]
  python dr_engine/tools/frontier.py tournament --dir D
  python dr_engine/tools/frontier.py dynamics   --dir D [--param price] [--threshold churn=0.05]
  python dr_engine/tools/frontier.py topology   --dir D
  python dr_engine/tools/frontier.py verify     --dir D
  python dr_engine/tools/frontier.py render     --dir D

Artifacts (all sha256-stamped, stdlib json): evsi.json, tournament.json,
dynamics.json, topology.json. Gates E11 / R16 verify them.

Stdlib only.
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
import sys
from collections import deque
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import claims as claims_mod  # noqa: E402
from evidence import _jsonl, load_claims, load_evidence, study_dir_error  # noqa: E402

# Tier reliability: P(observe a true signal | ground truth), used as the Bernoulli
# likelihood of evidence records in the EVSI posterior and as agent scoring weights.
TIER_RELIABILITY = {"T1": 0.95, "T2": 0.90, "T3": 0.80, "T4": 0.60, "T5": 0.40}
DEFAULT_NEXT_TIER = "T3"

VERDICT_CONTINUE = "CONTINUE"
VERDICT_STOP = "STOP_SATURATED"


# ------------------------------------------------------------------ artifacts
def _artifact_path(d: Path, name: str) -> Path:
  return Path(d) / name


def _save(d: Path, name: str, payload: dict[str, Any]) -> dict[str, Any]:
  clean = {k: v for k, v in payload.items() if k != "sha256"}
  body = json.dumps(clean, ensure_ascii=False, indent=2, sort_keys=True)
  payload["sha256"] = hashlib.sha256(body.encode("utf-8")).hexdigest()
  _artifact_path(d, name).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                                      encoding="utf-8")
  return payload


def _load(d: Path, name: str) -> dict[str, Any] | None:
  p = _artifact_path(d, name)
  if not p.exists():
    return None
  try:
    return json.loads(p.read_text(encoding="utf-8"))
  except json.JSONDecodeError:
    return {"__corrupt__": True}


def _hash_ok(d: Path, name: str, data: dict[str, Any]) -> bool:
  if data.get("__corrupt__"):
    return False
  clean = {k: v for k, v in data.items() if k != "sha256"}
  body = json.dumps(clean, ensure_ascii=False, indent=2, sort_keys=True)
  return hashlib.sha256(body.encode("utf-8")).hexdigest() == data.get("sha256")


# ============================================================ 1. EVSI / STOP
def beta_posterior(evidence: list[dict], a0: float = 1.0, b0: float = 1.0) -> dict[str, Any]:
  """Beta-Bernoulli posterior over p = P(thesis true).

  Each 'supports' record with tier reliability r contributes likelihood r under H1
  (thesis true) and (1 - r) under H0; each 'contradicts' record swaps them.
  'context' records are uninformative and skipped. Deterministic.
  """
  a, b = float(a0), float(b0)
  used = 0
  for r in evidence:
    stance = r.get("stance")
    if stance not in ("supports", "contradicts"):
      continue
    rel = TIER_RELIABILITY.get(r.get("tier", "T5"), 0.40)
    if stance == "supports":
      a += rel
      b += 1.0 - rel
    else:
      a += 1.0 - rel
      b += rel
    used += 1
  mean = a / (a + b) if (a + b) > 0 else 0.5
  # Beta variance, exact
  var = (a * b) / ((a + b) ** 2 * (a + b + 1.0)) if (a + b) > 0 else 0.0
  return {"a": round(a, 6), "b": round(b, 6), "mean": round(mean, 6),
          "variance": round(var, 8), "records_used": used}


def evsi_analysis(
    d: Path,
    cost: float = 0.01,
    next_tier: str = DEFAULT_NEXT_TIER,
    loss_fp: float = 1.0,
    loss_fn: float = 1.0,
) -> dict[str, Any]:
  """Analytic EVSI of fetching one more source + EVPI + STOP/CONTINUE verdict.

  Decision frame: act on the thesis (utility 1 if true, -loss_fp if false) vs
  reject it (utility 0 if true, +loss_fn*... symmetric by default). We use the
  standard 0/1-loss decision: choose the posterior-probable hypothesis.
  EVSI = sum over hypothetical outcomes o of P(o) * max_a E[U | posterior after o]
         - max_a E[U | current posterior].
  """
  evidence = load_evidence(d)
  post = beta_posterior(evidence)
  m = post["mean"]

  def decision_value(mean: float) -> float:
    # E[U] of acting = mean*1 + (1-mean)*0 ; of not acting = (1-mean)*loss_fn ... keep 0/1:
    return max(mean * 1.0, (1.0 - mean) * 1.0)

  current_value = decision_value(m)
  r = TIER_RELIABILITY.get(next_tier, 0.80)
  # Posterior predictive of the next record's stance under the current posterior:
  p_support = m * r + (1.0 - m) * (1.0 - r)
  p_contra = 1.0 - p_support
  # Posterior means after each hypothetical outcome:
  a, b = post["a"], post["b"]
  m_if_support = (a + r) / (a + b + 1.0)
  m_if_contra = (a + 1.0 - r) / (a + b + 1.0)
  evsi = p_support * decision_value(m_if_support) + p_contra * decision_value(m_if_contra) - current_value
  evsi = max(0.0, evsi)  # EVSI is non-negative by definition; clamp float noise
  evpi = max(0.0, 1.0 - current_value)  # perfect information resolves the decision for sure
  verdict = VERDICT_STOP if evsi <= cost else VERDICT_CONTINUE
  return _save(d, "evsi.json", {
      "posterior": post,
      "next_source_tier": next_tier,
      "next_source_reliability": r,
      "p_next_supports": round(p_support, 6),
      "evsi": round(evsi, 8),
      "evpi": round(evpi, 8),
      "cost_threshold": cost,
      "current_decision_value": round(current_value, 8),
      "verdict": verdict,
      "interpretation": (
          f"EVSI of one more {next_tier} source is {evsi:.6f} <= cost {cost} -> information space "
          f"is saturated, STOP discovery" if verdict == VERDICT_STOP else
          f"EVSI of one more {next_tier} source is {evsi:.6f} > cost {cost} -> CONTINUE discovery"),
  })


# ==================================================== 2. ADVERSARIAL TOURNAMENT
AGENTS = ("PROPONENT", "SKEPTIC", "RED_TEAM")


def _claim_strength(c: dict, evidence: dict) -> tuple[float, float]:
  """(support_weight, contradict_weight) of a claim from its cited evidence tiers."""
  sup = con = 0.0
  for e in c.get("eids", []):
    r = evidence.get(e)
    if not r:
      continue
    w = TIER_RELIABILITY.get(r.get("tier", "T5"), 0.40)
    if r.get("stance") == "supports":
      sup += w
    elif r.get("stance") == "contradicts":
      con += w
  return sup, con


def tournament(d: Path) -> dict[str, Any]:
  """Deterministic 3-agent epistemic tournament over the claim ledger.

  Each agent's strategy = a mapping claim -> stance. Payoff of an agent on a claim
  is +1 when the agent's stance matches the evidence-majority verdict of that
  claim, else -1. A Nash equilibrium is verified by exhaustive unilateral
  deviation checks over all claims (deterministic, finite strategy space per
  claim is binary, so a full best-response sweep is exact).
  """
  claims = load_claims(d)
  evidence = {r["id"]: r for r in load_evidence(d)}
  if not claims:
    return _save(d, "tournament.json", {"error": "claims.jsonl is empty - run claims.py add first",
                                        "equilibrium": False})
  # Ground-truth verdict per claim from evidence weights:
  verdicts: dict[str, dict[str, Any]] = {}
  for c in claims:
    sup, con = _claim_strength(c, evidence)
    verdicts[c["id"]] = {"supports": round(sup, 6), "contradicts": round(con, 6),
                         "majority": "supports" if sup >= con else "contradicts"}
  # Agent strategies: PROPONENT backs majority, SKEPTIC opposes majority,
  # RED_TEAM attacks the strongest claim (max |sup-con|) with the opposite stance.
  strongest = max(verdicts, key=lambda k: abs(verdicts[k]["supports"] - verdicts[k]["contradicts"]))
  strategies = {
      "PROPONENT": {cid: v["majority"] for cid, v in verdicts.items()},
      "SKEPTIC": {cid: ("contradicts" if v["majority"] == "supports" else "supports")
                  for cid, v in verdicts.items()},
      "RED_TEAM": {cid: ("contradicts" if v["majority"] == "supports" else "supports")
                   for cid, v in verdicts.items()},
  }
  strategies["RED_TEAM"][strongest] = ("contradicts" if verdicts[strongest]["majority"] == "supports"
                                        else "supports")

  def payoff(agent: str, strat: dict[str, str]) -> float:
    return sum(1.0 if strat[cid] == verdicts[cid]["majority"] else -1.0 for cid in verdicts)

  scores = {a: payoff(a, strategies[a]) for a in AGENTS}
  # Kelly-style belief bet per agent: stake fraction of bankroll proportional to
  # the agent's average edge over the ledger.
  n = len(verdicts)
  bets = {a: round(max(0.0, scores[a] / n) / 2.0, 6) for a in AGENTS}  # Kelly f* = edge/odds, odds=2
  # Exact Nash check: can any agent improve by flipping one claim's stance?
  nash_deviations = []
  for a in AGENTS:
    for cid in verdicts:
      alt = dict(strategies[a])
      alt[cid] = "contradicts" if alt[cid] == "supports" else "supports"
      if payoff(a, alt) > scores[a] + 1e-12:
        nash_deviations.append({"agent": a, "claim": cid, "gain": payoff(a, alt) - scores[a]})
  equilibrium = not nash_deviations
  winner = max(AGENTS, key=lambda a: scores[a])
  return _save(d, "tournament.json", {
      "agents": list(AGENTS), "claims_evaluated": n,
      "verdicts": verdicts, "scores": scores, "belief_bets_kelly": bets,
      "strongest_claim_attacked_by_red_team": strongest,
      "nash_deviations": nash_deviations, "equilibrium": equilibrium,
      "winner": winner,
      "convergence": ("NASH EQUILIBRIUM reached - no unilateral deviation improves any agent's payoff"
                      if equilibrium else
                      f"NOT converged - {len(nash_deviations)} profitable unilateral deviation(s); "
                      "re-examine the contested claims"),
  })


# ============================================ 3. NON-LINEAR DYNAMICS / TIPPING
def _dag_edges(dag: dict) -> list[tuple[str, str, float, str]]:
  out = []
  for e in dag.get("edges", []):
    try:
      beta = float(e.get("beta", 0.0))
    except (TypeError, ValueError):
      beta = 0.0
    out.append((e.get("src", ""), e.get("dst", ""), beta, e.get("sign", "+")))
  return out


def _jacobian(nodes: dict, edges: list[tuple[str, str, float, str]]) -> tuple[list[str], list[list[float]]]:
  ids = sorted(nodes)
  idx = {n: i for i, n in enumerate(ids)}
  n = len(ids)
  J = [[0.0] * n for _ in range(n)]
  for src, dst, beta, _sign in edges:
    if src in idx and dst in idx:
      J[idx[dst]][idx[src]] += beta  # d(outcome)/d(driver)
  return ids, J


def dominant_eigenvalue(J: list[list[float]], iters: int = 500, tol: float = 1e-12) -> tuple[float, list[float]]:
  """Power iteration with deflation-free |lambda| estimate; returns (lambda_max, vector)."""
  n = len(J)
  if n == 0:
    return 0.0, []
  v = [1.0 / math.sqrt(n)] * n
  lam = 0.0
  for _ in range(iters):
    w = [sum(J[i][j] * v[j] for j in range(n)) for i in range(n)]
    norm = math.sqrt(sum(x * x for x in w)) or 1.0
    v = [x / norm for x in w]
    lam_new = sum(v[i] * sum(J[i][j] * v[j] for j in range(n)) for i in range(n))
    if abs(lam_new - lam) < tol:
      lam = lam_new
      break
    lam = lam_new
  return lam, v


def _solve_linear(A: list[list[float]], b: list[float]) -> list[float] | None:
  """Gaussian elimination with partial pivoting; returns x of A x = b, or None if singular."""
  n = len(A)
  M = [row[:] + [b[i]] for i, row in enumerate(A)]
  for col in range(n):
    piv = max(range(col, n), key=lambda r: abs(M[r][col]))
    if abs(M[piv][col]) < 1e-12:
      return None
    M[col], M[piv] = M[piv], M[col]
    for r in range(col + 1, n):
      f = M[r][col] / M[col][col]
      for c in range(col, n + 1):
        M[r][c] -= f * M[col][c]
  x = [0.0] * n
  for r in range(n - 1, -1, -1):
    s = M[r][n] - sum(M[r][c] * x[c] for c in range(r + 1, n))
    x[r] = s / M[r][r]
  return x


def bifurcation_scan(
    nodes: dict, edges: list[tuple[str, str, float, str]], param: str,
    outcome: str, lo: float, hi: float, steps: int = 41,
) -> dict[str, Any]:
  """Scan an intervention parameter over [lo, hi]. At each level, solve the
  linearized fixed point (I - J) x = s where s is the unit shock on `param`;
  the tipping point is the first scan level where the outcome's response flips
  sign relative to its baseline."""
  ids, J = _jacobian(nodes, edges)
  if param not in ids or outcome not in ids:
    return {"error": f"param '{param}' or outcome '{outcome}' not in DAG nodes"}
  ip, io = ids.index(param), ids.index(outcome)
  n = len(ids)
  base_param = float(nodes.get(param, {}).get("baseline", 0.0))
  IminusJ = [[(1.0 if i == j else 0.0) - J[i][j] for j in range(n)] for i in range(n)]
  prev_x, prev_val, tip = None, None, None
  trace = []
  for k in range(steps + 1):
    shock_val = lo + (hi - lo) * k / steps
    s = [0.0] * n
    s[ip] = shock_val - base_param
    x = _solve_linear(IminusJ, s)
    if x is None:
      out_val = float("nan")
    else:
      out_val = x[io]
    if not (out_val == out_val):  # NaN guard
      out_val = 0.0
    trace.append({"param": round(shock_val, 6), "outcome_response": round(out_val, 6)})
    if prev_val is not None and not (prev_val == 0.0 and out_val == 0.0) and (
        prev_val == 0.0 or out_val == 0.0 or (prev_val < 0) != (out_val < 0)):
      tip = round(shock_val if out_val == 0.0 else prev_x, 6)
      break
    prev_x, prev_val = shock_val, out_val
  return {"param": param, "outcome": outcome, "tipping_point": tip,
          "tipped": tip is not None, "trace_sample": trace[:: max(1, steps // 10)]}


def cascade_simulation(
    nodes: dict, edges: list[tuple[str, str, float, str]], seed: str,
    threshold: float = 0.5,
) -> dict[str, Any]:
  """Threshold contagion on the DAG: a node activates when the weighted sum of
  its active parents >= threshold. Deterministic BFS cascade from `seed`."""
  ids = set(nodes)
  parents: dict[str, list[tuple[str, float]]] = {n: [] for n in ids}
  for src, dst, beta, _ in edges:
    if src in ids and dst in ids:
      parents[dst].append((src, abs(beta)))
  active = {seed} if seed in ids else set()
  if seed not in ids:
    return {"error": f"seed '{seed}' not in DAG nodes", "cascade_size": 0}
  q = deque([seed])
  while q:
    u = q.popleft()
    for n in ids:
      if n in active:
        continue
      w = sum(b for p, b in parents[n] if p in active)
      total = sum(b for _, b in parents[n]) or 1.0
      if w / total >= threshold and parents[n]:
        active.add(n)
        q.append(n)
  return {"seed": seed, "threshold": threshold, "cascade_size": len(active),
          "cascade_fraction": round(len(active) / len(ids), 6) if ids else 0.0,
          "activated": sorted(active)}


def dynamics(d: Path, param: str | None = None, outcome: str | None = None,
             threshold: str | None = None, seed: str | None = None) -> dict[str, Any]:
  import causal as causal_mod  # local: needs the DAG file
  dag = causal_mod.load_dag(d)
  nodes = dag.get("nodes", {})
  if not nodes:
    return _save(d, "dynamics.json", {"error": "causal_dag.json has no nodes - run causal.py add-node"})
  edges = _dag_edges(dag)
  ids, J = _jacobian(nodes, edges)
  lam, vec = dominant_eigenvalue(J)
  margin = 1.0 - abs(lam)
  slowing = abs(lam) >= 0.9  # critical slowing down: dominant eigenvalue near the unit circle
  param = param or (ids[0] if ids else None)
  outcome = outcome or (ids[-1] if ids else None)
  scan = bifurcation_scan(nodes, edges, param, outcome, lo=-1.0, hi=1.0, steps=41) if param and outcome else {}
  thr = 0.5
  if threshold and "=" in threshold:
    _, v = threshold.split("=", 1)
    try:
      thr = float(v)
    except ValueError:
      pass
  seed = seed or (ids[0] if ids else "")
  casc = cascade_simulation(nodes, edges, seed, thr)
  return _save(d, "dynamics.json", {
      "nodes": ids, "dominant_eigenvalue": round(lam, 8),
      "stability_margin_1_minus_abs_lambda": round(margin, 8),
      "critical_slowing_down": slowing,
      "dominant_mode": {ids[i]: round(vec[i], 6) for i in range(len(ids)) if abs(vec[i]) > 1e-6},
      "bifurcation_scan": scan,
      "cascade": casc,
      "verdict": ("NEAR TIPPING POINT (|lambda| >= 0.9): small shocks produce large outcome swings"
                  if slowing else "STABLE (|lambda| < 0.9): perturbations decay geometrically"),
  })


# ================================================== 4. TOPOLOGICAL CLAIM SPACE
def _tarjan_articulation(n: int, adj: list[list[int]]) -> tuple[list[int], list[tuple[int, int]]]:
  """Tarjan's algorithm: articulation points and bridges of an undirected graph."""
  disc = [-1] * n
  low = [0] * n
  parent = [-1] * n
  arts: set[int] = set()
  bridges: list[tuple[int, int]] = []
  timer = [0]

  def dfs(u: int) -> None:
    children = 0
    disc[u] = low[u] = timer[0]
    timer[0] += 1
    for v in adj[u]:
      if disc[v] == -1:
        parent[v] = u
        children += 1
        dfs(v)
        low[u] = min(low[u], low[v])
        if parent[u] == -1 and children > 1:
          arts.add(u)
        if parent[u] != -1 and low[v] > disc[u]:
          arts.add(u)
        if low[v] > disc[u]:
          bridges.append((u, v))
      elif v != parent[u]:
        low[u] = min(low[u], disc[v])

  import sys as _sys
  _sys.setrecursionlimit(max(10000, 10 * n + 100))
  for i in range(n):
    if disc[i] == -1:
      dfs(i)
  return sorted(arts), sorted(bridges)


def _spectral_layout(adj: list[list[int]], n: int, iters: int = 300) -> list[tuple[float, float]]:
  """2D spectral layout via power iteration on the normalized adjacency (stdlib only)."""
  if n == 0:
    return []
  deg = [max(1, len(adj[i])) for i in range(n)]
  A = [[(1.0 / math.sqrt(deg[i] * deg[j])) if j in adj[i] else 0.0 for j in range(n)] for i in range(n)]

  def top_vec(seed: list[float]) -> tuple[float, list[float]]:
    v = seed[:]
    norm = math.sqrt(sum(x * x for x in v)) or 1.0
    v = [x / norm for x in v]
    lam = 0.0
    for _ in range(iters):
      w = [sum(A[i][j] * v[j] for j in range(n)) for i in range(n)]
      nrm = math.sqrt(sum(x * x for x in w)) or 1.0
      v = [x / nrm for x in w]
      lam_new = sum(v[i] * sum(A[i][j] * v[j] for j in range(n)) for i in range(n))
      if abs(lam_new - lam) < 1e-12:
        lam = lam_new
        break
      lam = lam_new
    return lam, v

  lam1, v1 = top_vec([1.0] * n)
  # Deflate: subtract the rank-1 component, then take the second eigenvector.
  B = [[A[i][j] - lam1 * v1[i] * v1[j] for j in range(n)] for i in range(n)]
  v2 = [((-1.0) ** i) / math.sqrt(n) for i in range(n)]
  norm = math.sqrt(sum(x * x for x in v2)) or 1.0
  v2 = [x / norm for x in v2]
  for _ in range(iters):
    w = [sum(B[i][j] * v2[j] for j in range(n)) for i in range(n)]
    # re-orthogonalize against v1
    dot = sum(w[i] * v1[i] for i in range(n))
    w = [w[i] - dot * v1[i] for i in range(n)]
    nrm = math.sqrt(sum(x * x for x in w)) or 1.0
    v2 = [x / nrm for x in w]
  return [(round(v1[i], 6), round(v2[i], 6)) for i in range(n)]


def topology(d: Path) -> dict[str, Any]:
  """Claim-space topology: citation + conflict graph, articulation points,
  bridges, unchallenged-claim blind spots, and a spectral narrative-manifold layout."""
  claims = load_claims(d)
  evidence = {r["id"]: r for r in load_evidence(d)}
  if not claims:
    return _save(d, "topology.json", {"error": "claims.jsonl is empty - run claims.py add first"})
  # Node 0..len(claims)-1 = claims, then one node per evidence id cited.
  eids = sorted({e for c in claims for e in c.get("eids", []) if e in evidence})
  node_of_eid = {e: len(claims) + i for i, e in enumerate(eids)}
  n = len(claims) + len(eids)
  adj: list[set[int]] = [set() for _ in range(n)]

  def link(a: int, b: int) -> None:
    adj[a].add(b)
    adj[b].add(a)

  for ci, c in enumerate(claims):
    for e in c.get("eids", []):
      if e in node_of_eid:
        link(ci, node_of_eid[e])
  conflicts = claims_mod.find_conflicts(claims, evidence)
  conflict_pairs = []
  id_of = {c["id"]: i for i, c in enumerate(claims)}
  for cf in conflicts:
    for a in cf.get("a_eids", []) + cf.get("b_eids", []):
      pass
    # conflict edges between the two clashing claims
    ca = next((c for c in claims if cf["a"] in (c.get("subject", "") + " " + c.get("attribute", ""))), None)
    for x, y in itertools.combinations(claims, 2):
      kx, ky = claims_mod.key(x), claims_mod.key(y)
      if kx == ky and x["id"] != y["id"]:
        link(id_of[x["id"]], id_of[y["id"]])
        conflict_pairs.append([x["id"], y["id"]])
  adj_l = [sorted(s) for s in adj]
  arts, bridges = _tarjan_articulation(n, [list(s) for s in adj_l])
  # Connected components
  seen = [False] * n
  comps = 0
  for i in range(n):
    if not seen[i]:
      comps += 1
      dq = deque([i])
      seen[i] = True
      while dq:
        u = dq.popleft()
        for v in adj[u]:
          if not seen[v]:
            seen[v] = True
            dq.append(v)
  # Blind spots: claims with no 'contradicts' evidence and no conflict edge
  conflicted_ids = {x for pair in conflict_pairs for x in pair}
  blind = []
  for c in claims:
    has_contra = any(evidence.get(e, {}).get("stance") == "contradicts" for e in c.get("eids", []))
    if not has_contra and c["id"] not in conflicted_ids:
      blind.append(c["id"])
  layout = _spectral_layout(adj_l, n)
  claim_layout = {claims[i]["id"]: layout[i] for i in range(len(claims))}
  # Narrative manifolds: count sign quadrants of the spectral layout with >= 2 claims
  quads: dict[tuple[int, int], int] = {}
  for i in range(len(claims)):
    x, y = layout[i]
    quads[(x >= 0, y >= 0)] = quads.get((x >= 0, y >= 0), 0) + 1
  manifolds = sum(1 for v in quads.values() if v >= 2)
  return _save(d, "topology.json", {
      "claims": len(claims), "evidence_nodes": len(eids), "conflict_edges": conflict_pairs,
      "connected_components": comps, "articulation_points": [claims[i]["id"] if i < len(claims) else eids[i - len(claims)] for i in arts],
      "bridges": len(bridges),
      "blind_spots_unchallenged_claims": blind,
      "spectral_layout_claims": claim_layout,
      "narrative_manifolds": manifolds,
      "verdict": (f"{len(blind)} unchallenged claim(s) - every load-bearing claim needs a kill attempt"
                  if blind else "all claims challenged by contradicting evidence or a conflict edge"),
  })


# ==================================================================== verify
def verify_frontier(d: Path) -> list[str]:
  """Gate hooks E11 / R16: every present v6.0 artifact must be hash-valid and
  internally consistent; required artifacts (quotas.json require_v6_frontier)
  must exist."""
  errs: list[str] = []
  quotas = {}
  qp = Path(d) / "quotas.json"
  if qp.exists():
    try:
      quotas = json.loads(qp.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
      pass
  required = bool(quotas.get("require_v6_frontier"))
  for name in ("evsi.json", "tournament.json", "dynamics.json", "topology.json"):
    data = _load(d, name)
    if data is None:
      if required:
        errs.append(f"{name} missing - run frontier.py "
                    f"{'evsi' if name == 'evsi.json' else name.split('.')[0]} --dir <dir>")
      continue
    if not _hash_ok(d, name, data):
      errs.append(f"{name} edited after computation (sha256 mismatch) - re-run frontier.py")
      continue
    if "error" in data:
      errs.append(f"{name}: {data['error']}")
  evsi = _load(d, "evsi.json")
  if evsi and _hash_ok(d, "evsi.json", evsi) and evsi.get("verdict") not in (VERDICT_CONTINUE, VERDICT_STOP):
    errs.append("evsi.json: verdict must be CONTINUE or STOP_SATURATED")
  tour = _load(d, "tournament.json")
  if tour and _hash_ok(d, "tournament.json", tour) and "equilibrium" in tour and not tour["equilibrium"] \
      and quotas.get("require_tournament_equilibrium"):
    errs.append("tournament.json: no Nash equilibrium but quotas.json requires one")
  topo = _load(d, "topology.json")
  if topo and _hash_ok(d, "topology.json", topo) and topo.get("blind_spots_unchallenged_claims") \
      and quotas.get("require_no_blind_spots"):
    errs.append(f"topology.json: {len(topo['blind_spots_unchallenged_claims'])} unchallenged claim(s): "
                f"{', '.join(topo['blind_spots_unchallenged_claims'][:6])}")
  return errs


# ==================================================================== render
def render(d: Path) -> str:
  out = ["# Frontier Engine v6.0 — render", ""]
  for name, title in (("evsi.json", "Bayesian EVSI / Optimal Stopping"),
                      ("tournament.json", "Adversarial Epistemic Tournament"),
                      ("dynamics.json", "Non-Linear Dynamics & Tipping Points"),
                      ("topology.json", "Topological Claim Space")):
    data = _load(d, name)
    out.append(f"## {title}")
    if data is None:
      out.append("_not computed_")
    else:
      out.append("```json")
      out.append(json.dumps({k: v for k, v in data.items() if k != "sha256"}, ensure_ascii=False, indent=2))
      out.append("```")
    out.append("")
  return "\n".join(out)


# ====================================================================== main
def main(argv: list[str] | None = None) -> int:
  if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
  ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
  sub = ap.add_subparsers(dest="cmd", required=True)
  p = sub.add_parser("evsi")
  p.add_argument("--dir", type=Path, required=True)
  p.add_argument("--cost", type=float, default=0.01)
  p.add_argument("--next-tier", default=DEFAULT_NEXT_TIER, choices=sorted(TIER_RELIABILITY))
  p = sub.add_parser("tournament")
  p.add_argument("--dir", type=Path, required=True)
  p = sub.add_parser("dynamics")
  p.add_argument("--dir", type=Path, required=True)
  p.add_argument("--param", default=None)
  p.add_argument("--outcome", default=None)
  p.add_argument("--threshold", default=None, help="cascade threshold, e.g. churn=0.5 -> value 0.5")
  p.add_argument("--seed", default=None)
  p = sub.add_parser("topology")
  p.add_argument("--dir", type=Path, required=True)
  p = sub.add_parser("verify")
  p.add_argument("--dir", type=Path, required=True)
  p = sub.add_parser("render")
  p.add_argument("--dir", type=Path, required=True)
  args = ap.parse_args(argv)
  err = study_dir_error(args.dir)
  if err:
    print(err)
    return 2
  d = Path(args.dir)
  if args.cmd == "evsi":
    res = evsi_analysis(d, args.cost, args.next_tier)
    print(f"[{res['verdict']}] posterior P(thesis)={res['posterior']['mean']} "
          f"EVSI={res['evsi']} EVPI={res['evpi']} cost={res['cost_threshold']}")
  elif args.cmd == "tournament":
    res = tournament(d)
    if "error" in res:
      print(f"ERROR: {res['error']}")
      return 1
    print(f"equilibrium={res['equilibrium']} winner={res['winner']} scores={res['scores']}")
    print(res["convergence"])
  elif args.cmd == "dynamics":
    res = dynamics(d, args.param, args.outcome, args.threshold, args.seed)
    if "error" in res:
      print(f"ERROR: {res['error']}")
      return 1
    print(f"lambda_max={res['dominant_eigenvalue']} margin={res['stability_margin_1_minus_abs_lambda']} "
          f"slowing={res['critical_slowing_down']} tipping={res['bifurcation_scan'].get('tipping_point')}")
    print(res["verdict"])
  elif args.cmd == "topology":
    res = topology(d)
    if "error" in res:
      print(f"ERROR: {res['error']}")
      return 1
    print(f"components={res['connected_components']} blind_spots={res['blind_spots_unchallenged_claims']} "
          f"manifolds={res['narrative_manifolds']}")
    print(res["verdict"])
  elif args.cmd == "verify":
    errs = verify_frontier(d)
    if errs:
      for e in errs:
        print(f"FAIL {e}")
      return 1
    print("[PASS] all v6.0 frontier artifacts verified")
  elif args.cmd == "render":
    print(render(d))
  return 0


if __name__ == "__main__":
  sys.exit(main())
