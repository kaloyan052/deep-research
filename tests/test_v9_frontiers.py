#!/usr/bin/env python3
"""Tests for Deep Research Engine v9.0 Turn 0 (auto_spec) and Turn 3 (decision_card)."""

from __future__ import annotations

import unittest
from pathlib import Path
from dr_engine.tools.auto_spec import (
    classify_prompt_domain,
    extract_core_entities,
    build_adversarial_spec_skeleton,
    optimize_lead_diversity,
    CandidateLead,
)
from dr_engine.tools.decision_card import (
    compile_models_for_decision_card,
)


class TestV9Frontiers(unittest.TestCase):
    def test_domain_classification(self):
        self.assertEqual(classify_prompt_domain("US100 M15 gamma imbalance alpha"), "quant")
        self.assertEqual(classify_prompt_domain("B2B SaaS churn and Stripe webhook integration"), "saas")
        self.assertEqual(classify_prompt_domain("GLP-1 receptor Phase 3 trial clinical endpoint"), "biotech")
        self.assertEqual(classify_prompt_domain("Bulgarian tax law ЗДДФЛ and corporate tax ЗКПО"), "legal")
        self.assertEqual(classify_prompt_domain("Solid state battery Carnot efficiency Wh/kg BOM"), "deeptech")

    def test_skeptic_swarm_kill_hypotheses(self):
        skeleton = build_adversarial_spec_skeleton("0DTE SPX dealer gamma momentum")
        self.assertEqual(skeleton["domain"], "quant")
        self.assertIn("K1", skeleton["kill_hypotheses"])
        self.assertIn("K2", skeleton["kill_hypotheses"])
        self.assertIn("K3", skeleton["kill_hypotheses"])
        self.assertIn("3.0%", skeleton["kill_hypotheses"]["K1"]["hypothesis"])

    def test_inverse_hhi_diversity(self):
        leads = [
            CandidateLead("L1", "https://openalex.org/1", "openalex.org", "academic", score=50),
            CandidateLead("L2", "https://openalex.org/2", "openalex.org", "academic", score=40),
            CandidateLead("L3", "https://openalex.org/3", "openalex.org", "academic", score=30),  # must be dropped (max 2 per host)
            CandidateLead("L4", "https://arxiv.org/1", "arxiv.org", "preprint", score=45),
            CandidateLead("L5", "https://reddit.com/r/1", "reddit.com", "community", score=35),
            CandidateLead("L6", "https://news.ycombinator.com/1", "news.ycombinator.com", "community", score=25),
        ]
        kept, neff = optimize_lead_diversity(leads, max_per_host=2, max_total=6)
        self.assertEqual(len(kept), 5)
        self.assertEqual(sum(1 for c in kept if c.host == "openalex.org"), 2)
        self.assertGreaterEqual(neff, 3.5)

    def test_decision_card_model_compilation(self):
        code = """
gross_bp = 10.0
spread_bp = 2.0
slip_bp = 1.0
net_bp = gross_bp - (spread_bp + 2.0 * slip_bp)
"""
        inputs, metrics, _ = compile_models_for_decision_card([("M01", code.strip())])
        self.assertEqual(len(inputs), 3)
        self.assertEqual(len(metrics), 1)
        self.assertEqual(metrics[0].name, "net_bp")
        self.assertEqual(metrics[0].baseline_val, 6.0)
        # Breakeven for gross_bp where net_bp == 0 is 4.0
        self.assertAlmostEqual(metrics[0].breakeven_bounds["gross_bp"], 4.0, places=3)


if __name__ == "__main__":
    unittest.main()
