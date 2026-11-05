"""Exhaustive test suite for Deep Research Engine v5.0 (Frontier Level).

Covers:
  1. test_causal_dag: cycle detection, missing confounder/collider trap, Pearl do(X)
     graph surgery & elasticity propagation, and [E###]/[C###] reference validation.
  2. test_causal_backdoor_criterion: exact d-separation across chains, forks, and
     colliders (including M-bias / Berkson's paradox when conditioning on a collider
     or descendant of treatment) and automatic minimal adjustment set discovery.
  3. test_dialectics_heterogeneity: Cochran's Q, DerSimonian-Laird tau^2 and I^2,
     rejection of naive averaging when I^2 > 50%, and regime-partitioning verification.
  4. test_swarm_sharding: multi-agent packet emission, isolated shard writing, and
     atomic collision-free batch merging into evidence.jsonl.
  5. test_parse_pdf_hierarchical: multi-level nested headers with horizontal forward-fill,
     section group spanners, unit inheritance, and regression t-stat sub-row merging.
  6. test_formula_v5_entropy: Shingle Jaccard & rare-number syndication clustering,
     Inverse-HHI effective cluster count N_eff, and echo-chamber penalty enforcement.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "dr_engine" / "tools"
if str(TOOLS) not in sys.path:
  sys.path.insert(0, str(TOOLS))

import causal  # noqa: E402
import dialectics  # noqa: E402
import evidence as ev_mod  # noqa: E402
import formula  # noqa: E402
import parse_pdf  # noqa: E402
import swarm  # noqa: E402


def _bootstrap_study(tmp_path: Path) -> Path:
  """Creates a valid self-contained study folder with fetched snapshots and verified evidence."""
  d = tmp_path / "2026-11-05-v5-test"
  (d / "sources").mkdir(parents=True, exist_ok=True)
  plan = """# Study Plan
| ID | Sub-question |
| :-- | :-- |
| SQ1 | What drives churn and pricing elasticity in micro-SaaS? |
| SQ2 | How do AI coding tools affect developer productivity across seniority? |

| ID | Kill hypothesis | Verdict |
| :-- | :-- | :-- |
| K1 | Low barrier to entry causes both wrapper flood and 87% failure rate | refuted [E001] |
| K2 | Switching costs lock out new entrants | refuted [E002] |
| K3 | Platform bundling makes the niche free | refuted [E003] |
"""
  (d / "plan.md").write_text(plan, encoding="utf-8")
  (d / "study.json").write_text(json.dumps({"created": "2026-11-05", "protocol": "5.0"}) + "\n", encoding="utf-8")

  s1_text = (
      "Empirical SaaS Benchmark 2024-2025: Micro-SaaS plans priced at 15 EUR per month experience "
      "a monthly churn rate of 7.8% across 4,250 tracked firms. Raising price to 49 EUR filters out "
      "low-commitment hobbyists and reduces churn to 2.9%. Meanwhile, 87% of micro-SaaS products "
      "fail within 18 months due to low barrier to entry."
  )
  s2_text = (
      "Randomized Controlled Trial on AI Developer Productivity (2025-2026): Experienced developers "
      "working on complex legacy repositories took 19% longer (-19% productivity shift) due to context "
      "verification overhead. Conversely, junior developers completing routine boilerplate tasks "
      "achieved a +26% productivity gain across 1,800 pull requests."
  )
  (d / "sources" / "S001.txt").write_text(s1_text, encoding="utf-8")
  (d / "sources" / "S002.txt").write_text(s2_text, encoding="utf-8")

  idx_records = [
      {
          "id": "S001", "url": "https://research.stripe.com/saas-benchmarks-2025",
          "final_url": "https://research.stripe.com/saas-benchmarks-2025",
          "http_status": 200, "content_type": "text/html", "via": "direct",
          "fetched_at": "2026-11-05T10:00:00", "chars": len(s1_text),
          "sha256": ev_mod.sha256_text(s1_text),
      },
      {
          "id": "S002", "url": "https://metr.org/ai-productivity-rct-2026",
          "final_url": "https://metr.org/ai-productivity-rct-2026",
          "http_status": 200, "content_type": "text/html", "via": "direct",
          "fetched_at": "2026-11-05T10:01:00", "chars": len(s2_text),
          "sha256": ev_mod.sha256_text(s2_text),
      },
  ]
  with (d / "sources" / "index.jsonl").open("w", encoding="utf-8") as f:
    for r in idx_records:
      f.write(json.dumps(r) + "\n")

  ev_records = [
      {
          "id": "E001", "source": "S001", "url": idx_records[0]["url"],
          "sq": "SQ1", "tier": "T1", "kind": "empirical", "stance": "supports",
          "quote": "Micro-SaaS plans priced at 15 EUR per month experience a monthly churn rate of 7.8% across 4,250 tracked firms.",
          "claim": "Baseline price of 15 EUR has 7.8% monthly churn.",
          "sample_period": "2024-2025", "accessed": "2026-11-05",
          "snapshot_sha256": idx_records[0]["sha256"],
      },
      {
          "id": "E002", "source": "S001", "url": idx_records[0]["url"],
          "sq": "K1", "tier": "T1", "kind": "empirical", "stance": "supports",
          "quote": "Raising price to 49 EUR filters out low-commitment hobbyists and reduces churn to 2.9%.",
          "claim": "Higher price filters out hobbyists and lowers churn to 2.9%.",
          "sample_period": "2024-2025", "accessed": "2026-11-05",
          "snapshot_sha256": idx_records[0]["sha256"],
      },
      {
          "id": "E003", "source": "S002", "url": idx_records[1]["url"],
          "sq": "SQ2", "tier": "T1", "kind": "empirical", "stance": "contradicts",
          "quote": "Experienced developers working on complex legacy repositories took 19% longer (-19% productivity shift) due to context verification overhead.",
          "claim": "AI tools reduce productivity by -19% on complex legacy tasks.",
          "sample_period": "2025-2026", "accessed": "2026-11-05",
          "snapshot_sha256": idx_records[1]["sha256"],
      },
  ]
  with (d / "evidence.jsonl").open("w", encoding="utf-8") as f:
    for r in ev_records:
      f.write(json.dumps(r) + "\n")

  (d / "searches.jsonl").touch()
  (d / "calculations.jsonl").touch()
  return d


class TestV5Frontier(unittest.TestCase):

  def test_causal_dag(self) -> None:
    """Tests cycle rejection, missing confounder trap, citation checks, and Pearl do(X) simulation."""
    with tempfile.TemporaryDirectory() as tmp:
      d = _bootstrap_study(Path(tmp))
      causal.save_dag(d, {"nodes": {}, "edges": [], "simulations": []})

      # 1. Cycle detection must catch A -> B -> C -> A
      cyclic_nodes = {
          "A": {"label": "A", "baseline": 10.0, "eids": ["E001"]},
          "B": {"label": "B", "baseline": 20.0, "eids": ["E001"]},
          "C": {"label": "C", "baseline": 30.0, "eids": ["E002"]},
          "D": {"label": "D", "baseline": 40.0, "eids": ["E002"]},
      }
      cyclic_edges = [
          {"src": "A", "dst": "B", "sign": "+", "beta": 0.5, "kind": "causal", "mechanism": "m1", "eids": ["E001"]},
          {"src": "B", "dst": "C", "sign": "+", "beta": 0.5, "kind": "causal", "mechanism": "m2", "eids": ["E001"]},
          {"src": "C", "dst": "A", "sign": "+", "beta": 0.5, "kind": "causal", "mechanism": "m3", "eids": ["E002"]},
      ]
      cycles = causal.find_cycles(cyclic_nodes, cyclic_edges)
      self.assertTrue(len(cycles) >= 1, "Failed to detect directed cycle A -> B -> C -> A")

      # 2. Pure chain without confounder/collider must fail verify_dag (naive correlation trap)
      chain_edges = [
          {"src": "A", "dst": "B", "sign": "+", "beta": 0.5, "kind": "causal", "mechanism": "m1", "eids": ["E001"]},
          {"src": "B", "dst": "C", "sign": "+", "beta": 0.5, "kind": "causal", "mechanism": "m2", "eids": ["E001"]},
          {"src": "C", "dst": "D", "sign": "+", "beta": 0.5, "kind": "causal", "mechanism": "m3", "eids": ["E002"]},
      ]
      causal.save_dag(d, {"nodes": cyclic_nodes, "edges": chain_edges, "simulations": []})
      errs = causal.verify_dag(d)
      self.assertTrue(any("0 confounders or colliders" in e for e in errs))

      # 3. Invalid citation [E999] must fail verify_dag
      bad_nodes = dict(cyclic_nodes)
      bad_nodes["A"] = {"label": "A", "baseline": 10.0, "eids": ["E999"]}
      causal.save_dag(d, {"nodes": bad_nodes, "edges": chain_edges, "simulations": []})
      errs_bad = causal.verify_dag(d)
      self.assertTrue(any("E999" in e for e in errs_bad))

      # 4. Valid DAG with confounder (`segment` -> `price` and `segment` -> `churn`) + mediator (`quality`)
      valid_dag = {
          "nodes": {
              "segment": {"label": "Customer Segment Quality", "baseline": 1.0, "unit": "idx", "eids": ["E001"]},
              "price": {"label": "Monthly Subscription Price", "baseline": 15.0, "unit": "EUR", "eids": ["E001"]},
              "buyer_commitment": {"label": "Buyer Switching Commitment", "baseline": 1.0, "unit": "idx", "eids": ["E002"]},
              "churn": {"label": "Monthly Churn Rate", "baseline": 7.8, "unit": "%", "eids": ["E001", "E002"]},
          },
          "edges": [
              {"src": "segment", "dst": "price", "sign": "+", "beta": 0.40, "kind": "confounder",
               "mechanism": "Enterprise segments tolerate higher baseline prices", "eids": ["E001"]},
              {"src": "segment", "dst": "churn", "sign": "-", "beta": -0.30, "kind": "confounder",
               "mechanism": "Enterprise segments have lower structural churn", "eids": ["E001"]},
              {"src": "price", "dst": "buyer_commitment", "sign": "+", "beta": 0.50, "kind": "mediator",
               "mechanism": "Higher price filters out casual impulse signups", "eids": ["E002"]},
              {"src": "buyer_commitment", "dst": "churn", "sign": "-", "beta": -0.55, "kind": "causal",
               "mechanism": "Committed buyers integrate workflow and churn less", "eids": ["E002"]},
          ],
          "simulations": [],
      }
      causal.save_dag(d, valid_dag)

      # Run Pearl do(price = 49.0):
      # Relative change in price = (49 - 15) / 15 = +2.266667 (+226.67%)
      # Incoming edge segment -> price is SEVERED by do(price=49).
      # Path price -> buyer_commitment (beta=0.50) -> churn (beta=-0.55)
      # Total elasticity on churn = 0.50 * (-0.55) = -0.275
      # Expected delta_pct on churn = -0.275 * 2.266667 = -62.33% -> counterfactual churn = 7.8 * (1 - 0.623333) = 2.938%
      sim = causal.simulate_do_intervention(d, {"price": 49.0}, "churn", conditioning_set=["segment"])
      self.assertAlmostEqual(sim["target_counterfactual"], 2.938, places=2)
      self.assertEqual(sim["target_delta_pct"], -62.33)
      self.assertEqual(causal.verify_dag(d), [])

  def test_causal_backdoor_criterion(self) -> None:
    """Tests Pearl's d-separation across forks, chains, and M-bias colliders."""
    dag = {
        "nodes": {
            "X": {"label": "Treatment", "baseline": 1.0, "eids": ["E001"]},
            "Y": {"label": "Outcome", "baseline": 1.0, "eids": ["E001"]},
            "Z_conf": {"label": "Confounder Fork", "baseline": 1.0, "eids": ["E001"]},
            "M_med": {"label": "Mediator", "baseline": 1.0, "eids": ["E001"]},
            "U1": {"label": "Latent 1", "baseline": 1.0, "eids": ["E001"]},
            "U2": {"label": "Latent 2", "baseline": 1.0, "eids": ["E001"]},
            "C_coll": {"label": "M-Bias Collider", "baseline": 1.0, "eids": ["E001"]},
        },
        "edges": [
            # Directed causal path: X -> M_med -> Y
            {"src": "X", "dst": "M_med", "sign": "+", "beta": 0.5, "kind": "mediator", "mechanism": "m", "eids": ["E001"]},
            {"src": "M_med", "dst": "Y", "sign": "+", "beta": 0.5, "kind": "causal", "mechanism": "m", "eids": ["E001"]},
            # Classical backdoor fork: X <- Z_conf -> Y
            {"src": "Z_conf", "dst": "X", "sign": "+", "beta": 0.3, "kind": "confounder", "mechanism": "c", "eids": ["E001"]},
            {"src": "Z_conf", "dst": "Y", "sign": "+", "beta": 0.3, "kind": "confounder", "mechanism": "c", "eids": ["E001"]},
            # M-bias collider path: X <- U1 -> C_coll <- U2 -> Y
            {"src": "U1", "dst": "X", "sign": "+", "beta": 0.2, "kind": "confounder", "mechanism": "u1", "eids": ["E001"]},
            {"src": "U1", "dst": "C_coll", "sign": "+", "beta": 0.2, "kind": "collider", "mechanism": "u1c", "eids": ["E001"]},
            {"src": "U2", "dst": "C_coll", "sign": "+", "beta": 0.2, "kind": "collider", "mechanism": "u2c", "eids": ["E001"]},
            {"src": "U2", "dst": "Y", "sign": "+", "beta": 0.2, "kind": "confounder", "mechanism": "u2", "eids": ["E001"]},
        ],
    }

    # Case 1: Empty conditioning set Z = {} leaves X <- Z_conf -> Y open!
    # Note that X <- U1 -> C_coll <- U2 -> Y is naturally BLOCKED by the unconditioned collider C_coll.
    res_empty = causal.check_backdoor_criterion(dag, "X", "Y", conditioning_set=[])
    self.assertFalse(res_empty["valid"])
    self.assertEqual(len(res_empty["open_backdoor_paths"]), 1)
    self.assertIn("X <- Z_conf -> Y", res_empty["open_backdoor_paths"][0])

    # Case 2: Conditioning on Z = {"Z_conf"} blocks the fork and leaves collider C_coll untouched -> VALID!
    res_valid = causal.check_backdoor_criterion(dag, "X", "Y", conditioning_set=["Z_conf"])
    self.assertTrue(res_valid["valid"])
    self.assertEqual(res_valid["open_backdoor_paths"], [])
    self.assertIn(["Z_conf"], res_valid["minimal_adjustment_sets"])

    # Case 3: Conditioning on {"Z_conf", "C_coll"} OPENS the M-bias collider path X <- U1 -> C_coll <- U2 -> Y!
    res_mbias = causal.check_backdoor_criterion(dag, "X", "Y", conditioning_set=["Z_conf", "C_coll"])
    self.assertFalse(res_mbias["valid"])
    self.assertEqual(len(res_mbias["open_backdoor_paths"]), 1)
    self.assertIn("C_coll", res_mbias["open_backdoor_paths"][0])

    # Case 4: Conditioning on {"Z_conf", "M_med"} violates Rule 1 (M_med is a descendant of X)
    res_desc = causal.check_backdoor_criterion(dag, "X", "Y", conditioning_set=["Z_conf", "M_med"])
    self.assertFalse(res_desc["valid"])
    self.assertEqual(res_desc["z_descendants_of_x"], ["M_med"])

  def test_dialectics_heterogeneity(self) -> None:
    """Tests Cochran's Q, DerSimonian-Laird I^2, anti-pooling enforcement, and regime partitioning."""
    with tempfile.TemporaryDirectory() as tmp:
      d = _bootstrap_study(Path(tmp))

      # Direct math test: METR (-19%, SE=4.0) vs Microsoft (+26%, SE=3.5)
      dl = dialectics.dersimonian_laird([-19.0, 26.0], [4.0, 3.5])
      self.assertGreater(dl["q_stat"], 70.0)
      self.assertGreater(dl["i2_pct"], 95.0)
      self.assertGreater(dl["tau2"], 900.0)
      self.assertFalse(dl["pooling_allowed"])

      # Create conflicting claims in claims.jsonl
      claims_data = [
          {
              "id": "CL001", "subject": "ai_coding_assistant", "attribute": "productivity_delta",
              "value": -19.0, "unit": "%", "scope": "senior_devs_complex_legacy_repo",
              "time": "2026", "eids": ["E003"], "load_bearing": True,
          },
          {
              "id": "CL002", "subject": "ai_coding_assistant", "attribute": "productivity_delta",
              "value": 26.0, "unit": "%", "scope": "junior_devs_routine_boilerplate",
              "time": "2026", "eids": ["E003"], "load_bearing": True,
          },
      ]
      with (d / "claims.jsonl").open("w", encoding="utf-8") as f:
        for c in claims_data:
          f.write(json.dumps(c) + "\n")

      recs = dialectics.build_dialectics(d)
      self.assertEqual(len(recs), 1)
      self.assertEqual(recs[0]["id"], "D001")
      self.assertIn("scope", recs[0]["axes"])
      self.assertGreater(recs[0]["heterogeneity"]["i2_pct"], 90.0)

      # Attempting to resolve without a partition_rule or with naive averaging must be REFUSED
      ok1, msg1 = dialectics.resolve_dialectic(d, "D001", "Both studies show mixed results.", partition_rule="")
      self.assertFalse(ok1)
      self.assertIn("REFUSED", msg1)

      ok2, msg2 = dialectics.resolve_dialectic(
          d, "D001", "The pooled average of the two studies is +3.5%.", partition_rule="Split by complexity"
      )
      self.assertFalse(ok2)
      self.assertIn("REFUSED", msg2)

      # Valid regime-partitioning synthesis must succeed and pass verify_dialectics
      ok3, _ = dialectics.resolve_dialectic(
          d,
          "D001",
          "Negative shift (-19%) occurs in high-entropy legacy architectures; positive shift (+26%) holds in greenfield boilerplate.",
          partition_rule="Apply -19% penalty when cyclomatic complexity > 25; apply +26% gain on standard CRUD modules.",
      )
      self.assertTrue(ok3)
      self.assertEqual(dialectics.verify_dialectics(d), [])

  def test_swarm_sharding(self) -> None:
    """Tests packet emission, isolated shard writing, and collision-free atomic merge."""
    with tempfile.TemporaryDirectory() as tmp:
      d = _bootstrap_study(Path(tmp))
      swarm._swarm_dir(d)
      pkts = swarm.emit_scout_packets(d)
      self.assertEqual(len(pkts), 5)  # SQ1, SQ2, K1, K2, K3

      # Write two independent shards concurrently
      shard_sq1 = d / "swarm" / "shards" / "scout_SQ1.jsonl"
      shard_k2 = d / "swarm" / "shards" / "scout_K2.jsonl"

      shard_sq1.write_text(json.dumps({
          "source": "S001", "sq": "SQ1", "tier": "T1", "kind": "empirical", "stance": "supports",
          "quote": "87% of micro-SaaS products fail within 18 months due to low barrier to entry.",
          "claim": "87% of micro-SaaS products fail within 18 months.", "sample_period": "2024-2025",
      }) + "\n", encoding="utf-8")

      shard_k2.write_text(json.dumps({
          "source": "S002", "sq": "K2", "tier": "T1", "kind": "empirical", "stance": "supports",
          "quote": "junior developers completing routine boilerplate tasks achieved a +26% productivity gain across 1,800 pull requests.",
          "claim": "Junior developers gained +26% productivity across 1,800 PRs.", "sample_period": "2025-2026",
      }) + "\n", encoding="utf-8")

      rc = swarm.merge_shards(d)
      self.assertEqual(rc, 0)

      all_ev = ev_mod.load_evidence(d)
      self.assertEqual(len(all_ev), 5)  # E001..E003 + 2 merged records (E004, E005)
      ids = [r["id"] for r in all_ev]
      self.assertEqual(ids, ["E001", "E002", "E003", "E004", "E005"])

  def test_parse_pdf_hierarchical(self) -> None:
    """Tests multi-level nested header forward-fill, section spanners, and t-stat sub-row attachment."""
    raw_grid = [
        ["Variable", "Panel A: Europe", "", "Panel B: US", ""],
        ["", "In-Sample", "Out-of-Sample", "In-Sample", "Out-of-Sample"],
        ["Momentum Factors:", "", "", "", ""],
        ["3-Bar Displacement", "0.042***", "0.038**", "0.051***", "0.044**"],
        ["", "(3.41)", "(2.89)", "(4.12)", "(3.05)"],
    ]
    above_text = "Table 4: Cross-Market Factor Performance (all figures in bps per day)"
    lines = parse_pdf.format_hierarchical_table(raw_grid, page_num=7, table_idx=2, surrounding_text_above=above_text)
    joined = "\n".join(lines)

    self.assertIn("[TABLE p7.t2]", joined)
    self.assertIn("p7.t2 units: all figures in bps per day", joined)
    self.assertIn(
        "p7.t2 header: Variable | Panel A: Europe / In-Sample | Panel A: Europe / Out-of-Sample | "
        "Panel B: US / In-Sample | Panel B: US / Out-of-Sample",
        joined,
    )
    self.assertIn(
        "p7.t2 r1: Momentum Factors > 3-Bar Displacement [all figures in bps per day] | "
        "Panel A: Europe / In-Sample: 0.042*** (3.41) | "
        "Panel A: Europe / Out-of-Sample: 0.038** (2.89) | "
        "Panel B: US / In-Sample: 0.051*** (4.12) | "
        "Panel B: US / Out-of-Sample: 0.044** (3.05)",
        joined,
    )

  def test_formula_v5_entropy(self) -> None:
    """Tests Shingle Jaccard & rare-number syndication detection vs genuine multi-domain independence."""
    syndicated_quote = (
        "According to the annual survey of 453,691 non-financial micro-enterprises, "
        "exact cloud adoption reached 19.42% with an average spend of 1,284 EUR."
    )
    echo_ev = {}
    echo_idx = {}
    for i in range(1, 7):
      sid = f"S00{i}"
      eid = f"E00{i}"
      url = f"https://syndicated-host-{i}.com/report"
      echo_idx[sid] = {"id": sid, "url": url, "publisher": f"Pub {i}"}
      echo_ev[eid] = {"id": eid, "source": sid, "url": url, "tier": "T2", "quote": syndicated_quote}

    ent_echo = formula.compute_entropy_and_independence(echo_ev, echo_idx)
    self.assertEqual(ent_echo["raw_domains"], 6)
    self.assertEqual(ent_echo["independent_clusters"], 1)
    self.assertEqual(ent_echo["effective_clusters_N_eff"], 1.0)
    self.assertLess(ent_echo["echo_chamber_multiplier"], 0.70)
    self.assertTrue(len(ent_echo["syndicated_pairs"]) >= 5)

    # Orthogonal independent sources
    distinct_quotes = [
        "Eurostat structural business registry logs 24.1 million active SMEs across the European Union.",
        "US Census Bureau SUSB dataset records 6,140,000 employer firms with fewer than 20 employees.",
        "Bank for International Settlements triennial FX survey measures daily turnover at 7.5 trillion USD.",
        "European Central Bank SAFE survey shows bank loan rejection rates rose to 8.4% in Q3.",
        "OECD TiVA database estimates domestic value added in software exports at 89.2% across member states.",
        "World Bank Global Findex report indicates digital merchant payment adoption reached 64.7%.",
    ]
    indep_ev = {}
    indep_idx = {}
    for i, q in enumerate(distinct_quotes, 1):
      sid = f"S00{i}"
      eid = f"E00{i}"
      url = f"https://institution-{i}.org/data"
      indep_idx[sid] = {"id": sid, "url": url, "publisher": f"Inst {i}"}
      indep_ev[eid] = {"id": eid, "source": sid, "url": url, "tier": "T1", "quote": q}

    ent_indep = formula.compute_entropy_and_independence(indep_ev, indep_idx)
    self.assertEqual(ent_indep["independent_clusters"], 6)
    self.assertEqual(ent_indep["effective_clusters_N_eff"], 6.0)
    self.assertEqual(ent_indep["syndicated_pairs"], [])
    self.assertGreaterEqual(ent_indep["echo_chamber_multiplier"], 0.98)


if __name__ == "__main__":
  unittest.main()
