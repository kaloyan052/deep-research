"""Unit tests for Frontier Engine v6.0 (dr_engine/tools/frontier.py) & Gates E11/R16.

Stdlib only. Tests:
  1. test_beta_posterior_math
  2. test_evsi_evpi_bounds
  3. test_evsi_saturation_stopping
  4. test_tournament_nash_equilibrium
  5. test_dominant_eigenvalue_power_iteration
  6. test_critical_slowing_down_flag
  7. test_bifurcation_scan_tipping_point
  8. test_cascade_simulation
  9. test_tarjan_articulation_and_bridges
  10. test_topology_blind_spots
  11. test_spectral_layout
  12. test_sha256_tamper_detection
  13. test_gate_e11_and_r16_integration
"""

import json
import math
import shutil
import tempfile
import unittest
from pathlib import Path

import dr_engine.tools.frontier as frontier
import dr_engine.tools.gate as gate_mod


class TestFrontierEngineV6(unittest.TestCase):

  def setUp(self):
    self.tmp = tempfile.mkdtemp(prefix="dr_test_v6_")
    self.d = Path(self.tmp)
    self.sources_dir = self.d / "sources"
    self.sources_dir.mkdir(parents=True, exist_ok=True)
    # create minimal plan.md
    (self.d / "plan.md").write_text("# Plan\n\nQuestion: Test\nDecision: Test\n", encoding="utf-8")
    # minimal source index
    (self.sources_dir / "index.jsonl").write_text("", encoding="utf-8")
    # minimal evidence
    (self.d / "evidence.jsonl").write_text("", encoding="utf-8")
    (self.d / "claims.jsonl").write_text("", encoding="utf-8")

  def tearDown(self):
    shutil.rmtree(self.tmp, ignore_errors=True)

  def test_beta_posterior_math(self):
    evidence = [
        {"id": "E001", "stance": "supports", "tier": "T1"},       # rel=0.95 -> a+=0.95, b+=0.05
        {"id": "E002", "stance": "contradicts", "tier": "T3"},    # rel=0.80 -> a+=0.20, b+=0.80
        {"id": "E003", "stance": "context", "tier": "T2"},        # skipped
    ]
    post = frontier.beta_posterior(evidence, a0=1.0, b0=1.0)
    self.assertEqual(post["records_used"], 2)
    self.assertAlmostEqual(post["a"], 1.0 + 0.95 + 0.20, places=5)
    self.assertAlmostEqual(post["b"], 1.0 + 0.05 + 0.80, places=5)
    expected_mean = post["a"] / (post["a"] + post["b"])
    self.assertAlmostEqual(post["mean"], expected_mean, places=5)
    self.assertGreater(post["variance"], 0.0)

  def test_evsi_evpi_bounds(self):
    # Non-empty evidence to test EVSI >= 0 and EVSI <= EVPI
    ev_records = [
        {"id": "E001", "source": "S001", "sq": "SQ1", "tier": "T2", "stance": "supports",
         "quote": "q1", "claim": "c1"},
        {"id": "E002", "source": "S001", "sq": "SQ1", "tier": "T2", "stance": "supports",
         "quote": "q2", "claim": "c2"},
    ]
    (self.d / "evidence.jsonl").write_text("\n".join(json.dumps(r) for r in ev_records) + "\n", encoding="utf-8")
    res = frontier.evsi_analysis(self.d, cost=0.01, next_tier="T3")
    self.assertGreaterEqual(res["evsi"], 0.0)
    self.assertGreaterEqual(res["evpi"], 0.0)
    self.assertLessEqual(res["evsi"], res["evpi"] + 1e-6)
    self.assertIn(res["verdict"], (frontier.VERDICT_CONTINUE, frontier.VERDICT_STOP))

  def test_evsi_saturation_stopping(self):
    # Strong overwhelming evidence should saturate the information space (EVSI <= cost)
    records = []
    for i in range(25):
      records.append({"id": f"E{i:03d}", "source": "S001", "sq": "SQ1", "tier": "T1",
                      "stance": "supports", "quote": f"quote {i}", "claim": f"claim {i}"})
    (self.d / "evidence.jsonl").write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")
    res = frontier.evsi_analysis(self.d, cost=0.01, next_tier="T3")
    self.assertEqual(res["verdict"], frontier.VERDICT_STOP)
    self.assertLessEqual(res["evsi"], 0.01)

  def test_tournament_nash_equilibrium(self):
    ev = [
        {"id": "E001", "source": "S001", "sq": "SQ1", "tier": "T1", "stance": "supports", "quote": "q1", "claim": "c1"},
        {"id": "E002", "source": "S001", "sq": "SQ1", "tier": "T2", "stance": "supports", "quote": "q2", "claim": "c2"},
    ]
    cl = [
        {"id": "CLM01", "subject": "pricing", "attribute": "churn", "value": "low", "eids": ["E001"]},
        {"id": "CLM02", "subject": "retention", "attribute": "ltv", "value": "high", "eids": ["E002"]},
    ]
    (self.d / "evidence.jsonl").write_text("\n".join(json.dumps(r) for r in ev) + "\n", encoding="utf-8")
    (self.d / "claims.jsonl").write_text("\n".join(json.dumps(c) for c in cl) + "\n", encoding="utf-8")

    res = frontier.tournament(self.d)
    self.assertEqual(res["claims_evaluated"], 2)
    self.assertIn(res["winner"], frontier.AGENTS)
    self.assertIn("PROPONENT", res["scores"])
    self.assertIn("SKEPTIC", res["scores"])
    self.assertIn("RED_TEAM", res["scores"])
    self.assertIsInstance(res["equilibrium"], bool)
    self.assertTrue((self.d / "tournament.json").exists())

  def test_dominant_eigenvalue_power_iteration(self):
    # Diagonal matrix with known dominant eigenvalue 0.8
    J = [[0.8, 0.0], [0.0, 0.3]]
    lam, vec = frontier.dominant_eigenvalue(J)
    self.assertAlmostEqual(lam, 0.8, places=5)
    self.assertAlmostEqual(vec[0], 1.0, places=3)
    self.assertAlmostEqual(vec[1], 0.0, places=3)

  def test_critical_slowing_down_flag(self):
    nodes = {"a": {"baseline": 1.0}, "b": {"baseline": 0.5}}
    # Near unit circle eigenvalue (0.95)
    edges_unstable = [("a", "b", 0.95, "+"), ("b", "a", 0.95, "+")]
    _, J_unstable = frontier._jacobian(nodes, edges_unstable)
    lam_unstable, _ = frontier.dominant_eigenvalue(J_unstable)
    self.assertGreaterEqual(abs(lam_unstable), 0.9)

    # Stable system (0.4)
    edges_stable = [("a", "b", 0.4, "+")]
    _, J_stable = frontier._jacobian(nodes, edges_stable)
    lam_stable, _ = frontier.dominant_eigenvalue(J_stable)
    self.assertLess(abs(lam_stable), 0.9)

  def test_bifurcation_scan_tipping_point(self):
    nodes = {"x": {"baseline": 0.0}, "y": {"baseline": 0.0}}
    edges = [("x", "y", -0.5, "-")]
    scan = frontier.bifurcation_scan(nodes, edges, param="x", outcome="y", lo=-2.0, hi=2.0, steps=20)
    self.assertIn("tipping_point", scan)
    self.assertIn("trace_sample", scan)

  def test_cascade_simulation(self):
    nodes = {"n1": {}, "n2": {}, "n3": {}}
    edges = [("n1", "n2", 1.0, "+"), ("n2", "n3", 1.0, "+")]
    casc = frontier.cascade_simulation(nodes, edges, seed="n1", threshold=0.5)
    self.assertEqual(casc["cascade_size"], 3)
    self.assertEqual(casc["cascade_fraction"], 1.0)
    self.assertEqual(casc["activated"], ["n1", "n2", "n3"])

  def test_tarjan_articulation_and_bridges(self):
    # Graph: 0 - 1 - 2 (node 1 is articulation point, edges (0,1) and (1,2) are bridges)
    adj = [[1], [0, 2], [1]]
    arts, bridges = frontier._tarjan_articulation(3, adj)
    self.assertIn(1, arts)
    self.assertEqual(len(bridges), 2)

  def test_topology_blind_spots(self):
    ev = [{"id": "E001", "source": "S001", "sq": "SQ1", "tier": "T1", "stance": "supports", "quote": "q1", "claim": "c1"}]
    cl = [{"id": "CLM01", "subject": "pricing", "attribute": "churn", "value": "low", "eids": ["E001"]}]
    (self.d / "evidence.jsonl").write_text("\n".join(json.dumps(r) for r in ev) + "\n", encoding="utf-8")
    (self.d / "claims.jsonl").write_text("\n".join(json.dumps(c) for c in cl) + "\n", encoding="utf-8")

    topo = frontier.topology(self.d)
    # CLM01 has only supporting evidence and no conflict -> blind spot
    self.assertIn("CLM01", topo["blind_spots_unchallenged_claims"])

    # Now add contradicting evidence to CLM01
    ev.append({"id": "E002", "source": "S002", "sq": "SQ1", "tier": "T2", "stance": "contradicts", "quote": "q2", "claim": "c2"})
    cl[0]["eids"].append("E002")
    (self.d / "evidence.jsonl").write_text("\n".join(json.dumps(r) for r in ev) + "\n", encoding="utf-8")
    (self.d / "claims.jsonl").write_text("\n".join(json.dumps(c) for c in cl) + "\n", encoding="utf-8")

    topo2 = frontier.topology(self.d)
    self.assertNotIn("CLM01", topo2["blind_spots_unchallenged_claims"])

  def test_spectral_layout(self):
    adj = [[1, 2], [0, 2], [0, 1]]
    coords = frontier._spectral_layout(adj, 3)
    self.assertEqual(len(coords), 3)
    for x, y in coords:
      self.assertIsInstance(x, float)
      self.assertIsInstance(y, float)

  def test_sha256_tamper_detection(self):
    ev = [{"id": "E001", "source": "S001", "sq": "SQ1", "tier": "T1", "stance": "supports", "quote": "q1", "claim": "c1"}]
    (self.d / "evidence.jsonl").write_text("\n".join(json.dumps(r) for r in ev) + "\n", encoding="utf-8")
    frontier.evsi_analysis(self.d, cost=0.01)

    # Valid before edit
    errs = frontier.verify_frontier(self.d)
    self.assertEqual(errs, [])

    # Tamper with evsi.json
    p = self.d / "evsi.json"
    data = json.loads(p.read_text(encoding="utf-8"))
    data["evsi"] = 999.0
    p.write_text(json.dumps(data), encoding="utf-8")

    errs2 = frontier.verify_frontier(self.d)
    self.assertTrue(any("sha256 mismatch" in e for e in errs2))

  def test_gate_e11_and_r16_integration(self):
    # E11: evsi says STOP_SATURATED after only 5 searches (< 12) -> should fail E11
    gate = gate_mod.Gate(self.d)
    evsi_payload = {"verdict": frontier.VERDICT_STOP, "evsi": 0.001, "cost_threshold": 0.01}
    frontier._save(self.d, "evsi.json", evsi_payload)
    gate._frontier_evidence_check(self.d, n_searches=5)
    self.assertTrue(any("E11" in f and "contradicts the E4 search floor" in f for f in gate.fail))


if __name__ == "__main__":
  unittest.main()
