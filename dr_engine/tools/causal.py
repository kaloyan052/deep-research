"""Deterministic Causal DAG, Pearl d-Separation & Counterfactual Engine (v5.0).

Forces the research agent to move beyond descriptive correlations by building a
verified Directed Acyclic Graph (DAG) of the underlying mechanism, checking Pearl's
Backdoor Criterion (d-separation across chains, forks, and colliders + M-bias
descendant checks), and running deterministic do-calculus counterfactual shocks.

Commands:
  python dr_engine/tools/causal.py init --dir D
  python dr_engine/tools/causal.py add-node --dir D --id price --label "Monthly Price" --baseline 15 --unit EUR --eids E001
  python dr_engine/tools/causal.py add-edge --dir D --src price --dst churn --sign - --beta -0.45 --kind causal --mechanism "..." --eids E002
  python dr_engine/tools/causal.py check-backdoor --dir D --treatment price --outcome churn [--condition seg,size]
  python dr_engine/tools/causal.py simulate --dir D --intervene price=49 --target churn
  python dr_engine/tools/causal.py verify --dir D
  python dr_engine/tools/causal.py render --dir D

Stdlib only.
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import itertools
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import calc  # noqa: E402
from evidence import load_evidence, study_dir_error  # noqa: E402

EDGE_KINDS = ("causal", "confounder", "mediator", "collider", "moderation")
SIGNS = ("+", "-", "non_monotonic")


def _dag_path(d: Path) -> Path:
  return Path(d) / "causal_dag.json"


def load_dag(d: Path) -> dict[str, Any]:
  p = _dag_path(d)
  if not p.exists():
    return {"nodes": {}, "edges": [], "simulations": []}
  return json.loads(p.read_text(encoding="utf-8"))


def save_dag(d: Path, dag: dict[str, Any]) -> None:
  clean = {k: v for k, v in dag.items() if k != "sha256"}
  payload = json.dumps(clean, ensure_ascii=False, indent=2, sort_keys=True)
  dag["sha256"] = hashlib.sha256(payload.encode("utf-8")).hexdigest()
  _dag_path(d).write_text(json.dumps(dag, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def find_cycles(nodes: dict[str, Any], edges: list[dict[str, Any]]) -> list[list[str]]:
  """DFS cycle detection to guarantee the causal graph is a strict DAG."""
  adj: dict[str, list[str]] = {n: [] for n in nodes}
  for e in edges:
    if e.get("src") in adj and e.get("dst") in adj:
      adj[e["src"]].append(e["dst"])

  visited: dict[str, int] = {n: 0 for n in nodes}  # 0=unvisited, 1=visiting, 2=done
  stack: list[str] = []
  cycles: list[list[str]] = []

  def dfs(u: str) -> None:
    visited[u] = 1
    stack.append(u)
    for v in adj.get(u, []):
      if visited.get(v, 0) == 1:
        idx = stack.index(v)
        cycles.append(stack[idx:] + [v])
      elif visited.get(v, 0) == 0:
        dfs(v)
    stack.pop()
    visited[u] = 2

  for n in nodes:
    if visited[n] == 0:
      dfs(n)
  return cycles


def get_descendants(nodes: dict[str, Any], edges: list[dict[str, Any]], start: str) -> set[str]:
  """Returns all strict directed descendants of `start` (excluding `start` itself)."""
  adj: dict[str, list[str]] = {n: [] for n in nodes}
  for e in edges:
    if e.get("src") in adj:
      adj[e["src"]].append(e["dst"])
  desc: set[str] = set()
  q = collections.deque(adj.get(start, []))
  while q:
    curr = q.popleft()
    if curr not in desc and curr != start:
      desc.add(curr)
      q.extend(adj.get(curr, []))
  return desc


def analyze_paths(dag: dict[str, Any]) -> dict[str, Any]:
  """Identifies root drivers, terminal outcomes, confounders (forks), colliders, and mediators."""
  nodes = dag.get("nodes", {})
  edges = dag.get("edges", [])
  in_deg: dict[str, list[dict]] = {n: [] for n in nodes}
  out_deg: dict[str, list[dict]] = {n: [] for n in nodes}

  for e in edges:
    if e.get("src") in out_deg:
      out_deg[e["src"]].append(e)
    if e.get("dst") in in_deg:
      in_deg[e["dst"]].append(e)

  roots = [n for n in nodes if not in_deg[n]]
  outcomes = [n for n in nodes if not out_deg[n]]
  confounders = [
      n for n in nodes
      if len(out_deg[n]) >= 2 or any(e.get("kind") == "confounder" for e in out_deg[n])
  ]
  colliders = [
      n for n in nodes
      if len(in_deg[n]) >= 2 or any(e.get("kind") == "collider" for e in in_deg[n])
  ]
  mediators = [
      n for n in nodes
      if in_deg[n] and out_deg[n] and any(e.get("kind") == "mediator" for e in in_deg[n] + out_deg[n])
  ]

  return {
      "roots": roots,
      "outcomes": outcomes,
      "confounders": confounders,
      "colliders": colliders,
      "mediators": mediators,
  }


# ------------------------------------------------ Pearl d-Separation & Backdoor
def _enumerate_undirected_paths(
    nodes: dict[str, Any], edges: list[dict[str, Any]], source: str, target: str
) -> list[list[tuple[str, str, str]]]:
  """Enumerates all simple undirected paths between `source` and `target`.
  Each step in a path is a tuple (u, v, direction) where direction is:
    '->' if the directed edge in G is u -> v
    '<-' if the directed edge in G is v -> u
  """
  adj: dict[str, list[tuple[str, str]]] = {n: [] for n in nodes}
  for e in edges:
    u, v = e.get("src", ""), e.get("dst", "")
    if u in adj and v in adj:
      adj[u].append((v, "->"))
      adj[v].append((u, "<-"))

  results: list[list[tuple[str, str, str]]] = []

  def dfs(curr: str, visited: set[str], path: list[tuple[str, str, str]]) -> None:
    if curr == target:
      results.append(list(path))
      return
    for nxt, direction in adj.get(curr, []):
      if nxt not in visited:
        visited.add(nxt)
        path.append((curr, nxt, direction))
        dfs(nxt, visited, path)
        path.pop()
        visited.remove(nxt)

  if source in nodes and target in nodes and source != target:
    dfs(source, {source}, [])
  return results


def _format_path(path: list[tuple[str, str, str]]) -> str:
  if not path:
    return ""
  out = [path[0][0]]
  for _, nxt, direction in path:
    out.append(f"{direction} {nxt}")
  return " ".join(out)


def is_path_d_separated(
    nodes: dict[str, Any],
    edges: list[dict[str, Any]],
    path: list[tuple[str, str, str]],
    conditioning_set: set[str],
    descendants_map: dict[str, set[str]] | None = None,
) -> tuple[bool, str]:
  """Checks whether a single path is blocked (d-separated) by `conditioning_set`.
  Returns (is_blocked, reason).
  Pearl's d-separation rules at every interior node `m` along `u (dir1) m (dir2) w`:
    1. Chain (`u -> m -> w` or `u <- m <- w`) or Fork/Confounder (`u <- m -> w`):
       Blocked iff `m in conditioning_set`.
    2. Collider (`u -> m <- w`):
       Blocked iff `m not in conditioning_set` AND no descendant of `m` is in `conditioning_set`.
  """
  if len(path) <= 1:
    return False, "direct edge cannot be blocked without severing"

  if descendants_map is None:
    descendants_map = {n: get_descendants(nodes, edges, n) for n in nodes}

  for i in range(len(path) - 1):
    _, m, dir1 = path[i]
    _, _, dir2 = path[i + 1]
    is_collider = (dir1 == "->" and dir2 == "<-")
    if is_collider:
      active_desc = ({m} | descendants_map.get(m, set())) & conditioning_set
      if not active_desc:
        return True, f"collider {m!r} is unconditioned"
    else:
      if m in conditioning_set:
        role = "fork/confounder" if (dir1 == "<-" and dir2 == "->") else "chain/mediator"
        return True, f"{role} {m!r} is conditioned on"

  return False, "all interior nodes are active"


def check_backdoor_criterion(
    dag: dict[str, Any],
    treatment: str,
    outcome: str,
    conditioning_set: set[str] | list[str] | None = None,
    compute_minimal_sets: bool = True,
) -> dict[str, Any]:
  """Evaluates Pearl's Backdoor Criterion for estimating P(outcome | do(treatment))
  given `conditioning_set` Z:
    Rule 1: No node in Z is a descendant of `treatment`.
    Rule 2: Z blocks (d-separates) every backdoor path between `treatment` and `outcome`
            (i.e. every path starting with `treatment <- ...`).
  """
  nodes = dag.get("nodes", {})
  edges = dag.get("edges", [])
  z_set = set(conditioning_set or []) - {treatment, outcome}

  if treatment not in nodes or outcome not in nodes:
    raise ValueError(f"Unknown treatment ({treatment}) or outcome ({outcome}) in DAG")

  desc_map = {n: get_descendants(nodes, edges, n) for n in nodes}
  treatment_descendants = desc_map.get(treatment, set())
  invalid_z_descendants = sorted(z_set & treatment_descendants)

  all_paths = _enumerate_undirected_paths(nodes, edges, treatment, outcome)
  open_backdoor: list[str] = []
  blocked_backdoor: list[str] = []
  open_causal: list[str] = []
  blocked_causal: list[str] = []
  open_other_noncausal: list[str] = []

  for p in all_paths:
    p_str = _format_path(p)
    is_directed_causal = all(step[2] == "->" for step in p)
    is_backdoor = (p[0][2] == "<-")
    blocked, _ = is_path_d_separated(nodes, edges, p, z_set, desc_map)

    if is_directed_causal:
      if blocked:
        blocked_causal.append(p_str)
      else:
        open_causal.append(p_str)
    elif is_backdoor:
      if blocked:
        blocked_backdoor.append(p_str)
      else:
        open_backdoor.append(p_str)
    else:
      # Path starts with `treatment -> ...` but contains a collider `<-` later (e.g. M-bias / selection)
      if not blocked:
        open_other_noncausal.append(p_str)

  backdoor_satisfied = (
      len(invalid_z_descendants) == 0
      and len(open_backdoor) == 0
      and len(open_other_noncausal) == 0
  )

  minimal_sets: list[list[str]] = []
  if compute_minimal_sets:
    candidates = sorted(set(nodes.keys()) - {treatment, outcome} - treatment_descendants)
    max_k = min(4, len(candidates))
    for k in range(0, max_k + 1):
      for combo in itertools.combinations(candidates, k):
        c_set = set(combo)
        if any(set(prev) <= c_set for prev in minimal_sets):
          continue
        res_c = check_backdoor_criterion(
            dag, treatment, outcome, c_set, compute_minimal_sets=False
        )
        if res_c["valid"]:
          minimal_sets.append(list(combo))

  return {
      "treatment": treatment,
      "outcome": outcome,
      "conditioning_set": sorted(z_set),
      "valid": backdoor_satisfied,
      "d_separated_backdoor": len(open_backdoor) == 0 and len(open_other_noncausal) == 0,
      "z_descendants_of_x": invalid_z_descendants,
      "open_backdoor_paths": open_backdoor,
      "blocked_backdoor_paths": blocked_backdoor,
      "open_noncausal_collider_paths": open_other_noncausal,
      "open_causal_paths": open_causal,
      "blocked_causal_paths": blocked_causal,
      "minimal_adjustment_sets": minimal_sets,
  }


def simulate_do_intervention(
    d: Path,
    interventions: dict[str, float],
    target: str,
    conditioning_set: list[str] | None = None,
) -> dict[str, Any]:
  """Executes Pearl's do(X=x) operator: severs incoming edges to intervened nodes and
  propagates linear sensitivity betas along topological order."""
  dag = load_dag(d)
  nodes = dag["nodes"]
  edges = dag["edges"]

  for k in interventions:
    if k not in nodes:
      raise ValueError(f"Unknown intervention node: {k}")
  if target not in nodes:
    raise ValueError(f"Unknown target node: {target}")

  cycles = find_cycles(nodes, edges)
  if cycles:
    raise ValueError(f"Cannot simulate on a cyclic graph: {' -> '.join(cycles[0])}")

  primary_x = next(iter(interventions.keys()))
  bd = check_backdoor_criterion(dag, primary_x, target, conditioning_set=conditioning_set)

  # Topological sort on mutilated graph G_{\overline{X}} (all incoming edges to X removed)
  in_deg = {n: 0 for n in nodes}
  adj: dict[str, list[dict]] = {n: [] for n in nodes}
  for e in edges:
    if e["dst"] in interventions:
      continue  # Pearl's graph surgery: cut incoming arrows into do(X)
    in_deg[e["dst"]] += 1
    adj[e["src"]].append(e)

  q = collections.deque([n for n, deg in in_deg.items() if deg == 0])
  order: list[str] = []
  while q:
    u = q.popleft()
    order.append(u)
    for e in adj[u]:
      v = e["dst"]
      in_deg[v] -= 1
      if in_deg[v] == 0:
        q.append(v)

  delta_pct: dict[str, float] = {n: 0.0 for n in nodes}
  abs_values: dict[str, float] = {n: float(nodes[n].get("baseline", 1.0)) for n in nodes}

  for k, val in interventions.items():
    base = float(nodes[k].get("baseline", 1.0))
    abs_values[k] = val
    delta_pct[k] = ((val - base) / base) if base != 0 else 0.0

  for u in order:
    for e in adj[u]:
      v = e["dst"]
      beta = float(e.get("beta", 0.0))
      delta_pct[v] += beta * delta_pct[u]

  for n in nodes:
    if n not in interventions:
      base = float(nodes[n].get("baseline", 1.0))
      abs_values[n] = round(base * (1.0 + delta_pct[n]), 4)

  sim_rec = {
      "interventions": interventions,
      "target": target,
      "conditioning_set": bd["conditioning_set"] if conditioning_set is not None else (
          bd["minimal_adjustment_sets"][0] if bd["minimal_adjustment_sets"] else []
      ),
      "backdoor_valid": bd["valid"] or bool(bd["minimal_adjustment_sets"]),
      "minimal_adjustment_sets": bd["minimal_adjustment_sets"],
      "target_baseline": float(nodes[target].get("baseline", 1.0)),
      "target_counterfactual": abs_values[target],
      "target_delta_pct": round(delta_pct[target] * 100.0, 2),
      "node_states": abs_values,
  }
  dag.setdefault("simulations", []).append(sim_rec)
  save_dag(d, dag)
  return sim_rec


def verify_dag(d: Path) -> list[str]:
  """Verifies structural DAG integrity and Pearl Backdoor identifiability for Gate E10."""
  dag = load_dag(d)
  errors: list[str] = []
  nodes = dag.get("nodes", {})
  edges = dag.get("edges", [])

  if len(nodes) < 4:
    errors.append(f"causal_dag.json has {len(nodes)} nodes; need >= 4 (root cause, mediator, confounder/collider, outcome)")
  if len(edges) < 3:
    errors.append(f"causal_dag.json has {len(edges)} edges; need >= 3 causal/confounder links")

  ev_ids = {r["id"] for r in load_evidence(d)}
  calc_ids = set(calc.load_calculations(d).keys())
  valid_refs = ev_ids | calc_ids

  for nid, ninfo in nodes.items():
    refs = ninfo.get("eids", [])
    if not refs or not (set(refs) <= valid_refs):
      errors.append(f"DAG node {nid!r} cites invalid or empty refs {refs}")

  for idx, e in enumerate(edges, 1):
    if e.get("src") not in nodes or e.get("dst") not in nodes:
      errors.append(f"DAG edge #{idx} references unknown node ({e.get('src')} -> {e.get('dst')})")
    if e.get("kind") not in EDGE_KINDS:
      errors.append(f"DAG edge #{idx} has invalid kind {e.get('kind')!r}")
    refs = e.get("eids", [])
    if not refs or not (set(refs) <= valid_refs):
      errors.append(f"DAG edge {e.get('src')}->{e.get('dst')} lacks valid [E###]/[C###] backing: {refs}")
    if not (e.get("mechanism") or "").strip():
      errors.append(f"DAG edge {e.get('src')}->{e.get('dst')} is missing physical/economic mechanism description")

  if errors:
    return errors

  cycles = find_cycles(nodes, edges)
  if cycles:
    errors.append(f"causal_dag.json contains cycle(s): {' -> '.join(cycles[0])} (must be a strict DAG)")
    return errors

  topo = analyze_paths(dag)
  if not topo["confounders"] and not topo["colliders"]:
    errors.append("causal_dag.json identifies 0 confounders or colliders (naive correlation trap: "
                  "explicitly model at least 1 confounder fork or selection/survivorship collider)")

  sims = dag.get("simulations", [])
  if not sims:
    errors.append("causal_dag.json has 0 counterfactual simulations; run `causal.py simulate`")
  else:
    for idx, s in enumerate(sims, 1):
      interventions = s.get("interventions", {})
      target = s.get("target", "")
      cond = s.get("conditioning_set")
      if interventions and target in nodes:
        px = next(iter(interventions.keys()))
        if px in nodes:
          bd = check_backdoor_criterion(dag, px, target, conditioning_set=cond)
          if cond is not None and not bd["valid"]:
            errors.append(
                f"Simulation #{idx} ({px} -> {target}) has unblocked backdoor path(s) "
                f"{bd['open_backdoor_paths']} or invalid descendant conditioning {bd['z_descendants_of_x']}"
            )
  return errors


def render_markdown(d: Path) -> str:
  dag = load_dag(d)
  nodes = dag.get("nodes", {})
  edges = dag.get("edges", [])
  topo = analyze_paths(dag)
  lines = [
      "### Structural Causal Model (DAG) & Counterfactual Physics",
      "",
      "| Causal Link ($X \\to Y$) | Role / Axis | Sign & Elasticity ($\\beta$) | Physical / Counterparty Mechanism | Backing |",
      "| :-- | :-- | :-- | :-- | :-- |",
  ]
  for e in edges:
    src_lbl = nodes.get(e["src"], {}).get("label", e["src"])
    dst_lbl = nodes.get(e["dst"], {}).get("label", e["dst"])
    refs = ", ".join(e.get("eids", []))
    beta_s = f"{e.get('sign', '+')} (β={e.get('beta', 0.0):+.2f})"
    lines.append(f"| **{src_lbl}** → **{dst_lbl}** | `{e['kind']}` | {beta_s} | {e['mechanism']} | [{refs}] |")

  lines.extend([
      "",
      f"- **Identified Confounders (Backdoor Forks):** {', '.join(topo['confounders']) or 'None'}",
      f"- **Selection / Survivorship Colliders:** {', '.join(topo['colliders']) or 'None'}",
  ])
  if dag.get("simulations"):
    lines.extend([
        "",
        "#### Counterfactual `do(X)` Simulations",
        "",
        "| Intervention `do(X = x')` | Adjustment Set $Z$ | Target Outcome | Baseline | Counterfactual | Net Shift (%) |",
        "| :-- | :-- | :-- | :-- | :-- | :-- |",
    ])
    for s in dag["simulations"]:
      int_str = ", ".join(f"{k}={v}" for k, v in s["interventions"].items())
      z_str = ", ".join(s.get("conditioning_set") or []) or "∅"
      lines.append(
          f"| `do({int_str})` | `{z_str}` | **{s['target']}** | {s['target_baseline']} | "
          f"**{s['target_counterfactual']}** | {s['target_delta_pct']:+.2f}% |"
      )
  return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
  if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
  ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
  sub = ap.add_subparsers(dest="cmd", required=True)

  p = sub.add_parser("init"); p.add_argument("--dir", required=True)
  p = sub.add_parser("add-node"); p.add_argument("--dir", required=True)
  p.add_argument("--id", required=True); p.add_argument("--label", required=True)
  p.add_argument("--baseline", type=float, required=True); p.add_argument("--unit", default="")
  p.add_argument("--eids", required=True, help="Comma-separated E###/C###")

  p = sub.add_parser("add-edge"); p.add_argument("--dir", required=True)
  p.add_argument("--src", required=True); p.add_argument("--dst", required=True)
  p.add_argument("--sign", choices=SIGNS, default="+")
  p.add_argument("--beta", type=float, required=True)
  p.add_argument("--kind", choices=EDGE_KINDS, default="causal")
  p.add_argument("--mechanism", required=True); p.add_argument("--eids", required=True)

  p = sub.add_parser("check-backdoor"); p.add_argument("--dir", required=True)
  p.add_argument("--treatment", required=True); p.add_argument("--outcome", required=True)
  p.add_argument("--condition", default="", help="Comma-separated conditioning node IDs")

  p = sub.add_parser("simulate"); p.add_argument("--dir", required=True)
  p.add_argument("--intervene", nargs="+", required=True, help="node=value pairs")
  p.add_argument("--target", required=True)
  p.add_argument("--condition", default="", help="Optional comma-separated conditioning node IDs")

  p = sub.add_parser("verify"); p.add_argument("--dir", required=True)
  p = sub.add_parser("render"); p.add_argument("--dir", required=True)

  args = ap.parse_args(argv)
  d = Path(args.dir)
  err = study_dir_error(d)
  if err:
    print(err)
    return 2

  if args.cmd == "init":
    save_dag(d, {"nodes": {}, "edges": [], "simulations": []})
    print(f"Initialized causal_dag.json in {d}")
    return 0
  if args.cmd == "add-node":
    dag = load_dag(d)
    dag["nodes"][args.id] = {
        "label": args.label, "baseline": args.baseline, "unit": args.unit,
        "eids": [x.strip() for x in args.eids.split(",") if x.strip()],
    }
    save_dag(d, dag)
    print(f"Node '{args.id}' added.")
    return 0
  if args.cmd == "add-edge":
    dag = load_dag(d)
    dag["edges"].append({
        "src": args.src, "dst": args.dst, "sign": args.sign, "beta": args.beta,
        "kind": args.kind, "mechanism": args.mechanism,
        "eids": [x.strip() for x in args.eids.split(",") if x.strip()],
    })
    save_dag(d, dag)
    print(f"Edge {args.src} -> {args.dst} ({args.kind}, beta={args.beta}) added.")
    return 0
  if args.cmd == "check-backdoor":
    dag = load_dag(d)
    cond = [x.strip() for x in args.condition.split(",") if x.strip()]
    res = check_backdoor_criterion(dag, args.treatment, args.outcome, cond)
    print(json.dumps(res, ensure_ascii=False, indent=2))
    return 0 if res["valid"] else 1
  if args.cmd == "simulate":
    interventions = {}
    for pair in args.intervene:
      k, v = pair.split("=", 1)
      interventions[k.strip()] = float(v)
    cond = [x.strip() for x in args.condition.split(",") if x.strip()] if args.condition else None
    res = simulate_do_intervention(d, interventions, args.target, conditioning_set=cond)
    print(json.dumps(res, ensure_ascii=False, indent=2))
    return 0
  if args.cmd == "verify":
    errs = verify_dag(d)
    if errs:
      for e in errs:
        print(f"  FAIL  {e}")
      return 1
    print(f"[PASS] causal_dag.json verified ({len(load_dag(d)['nodes'])} nodes, {len(load_dag(d)['edges'])} edges)")
    return 0
  if args.cmd == "render":
    print(render_markdown(d))
    return 0
  return 0


if __name__ == "__main__":
  sys.exit(main())
