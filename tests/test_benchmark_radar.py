#!/usr/bin/env python3
"""Unit tests for dr_engine/tools/benchmark_radar.py (Deep Research v9.0)."""

from __future__ import annotations

import unittest
from dr_engine.tools.benchmark_radar import BenchmarkRadar


class TestBenchmarkRadar(unittest.TestCase):
    def test_finance_snapshot_contains_top_models(self):
        snapshot = BenchmarkRadar.render_snapshot("finance")
        self.assertIn("Artificial Analysis Finance & Accounting Index", snapshot)
        self.assertIn("Rank 1: Gemini 4 Carbon (high) - Overall Score: 63", snapshot)
        self.assertIn("Rank 2: Claude Opus 5.5 (max) - Overall Score: 59", snapshot)
        self.assertIn("Non-Hallucination: 93", snapshot)
        self.assertIn("Reasoning: 68", snapshot)

    def test_coding_snapshot_contains_swe_bench(self):
        snapshot = BenchmarkRadar.render_snapshot("coding")
        self.assertIn("Artificial Analysis Coding & Software Engineering Index", snapshot)
        self.assertIn("Gemini 4 Carbon (high)", snapshot)
        self.assertIn("Claude Opus 5.5 (max)", snapshot)
        self.assertIn("SWE-bench", snapshot)

    def test_leader_metrics(self):
        # Overall leader in finance: Gemini 4 Carbon (high)
        overall_leader = BenchmarkRadar.get_leader("finance", "overall")
        self.assertEqual(overall_leader["model"], "Gemini 4 Carbon (high)")
        self.assertEqual(overall_leader["overall_score"], 63)

        # Non-hallucination leader in top 5: Gemini 4 Carbon (high) with 93
        nh_leader = BenchmarkRadar.get_leader("finance", "non_hallucination", top_n=5)
        self.assertEqual(nh_leader["model"], "Gemini 4 Carbon (high)")
        self.assertEqual(nh_leader["non_hallucination"], 93)

        # Pure reasoning leader in top 5: Claude Opus 5.5 (max) with 68
        reasoning_leader = BenchmarkRadar.get_leader("finance", "reasoning", top_n=5)
        self.assertEqual(reasoning_leader["model"], "Claude Opus 5.5 (max)")
        self.assertEqual(reasoning_leader["reasoning"], 68)

        # Business knowledge leader in top 5: GPT-6.1 Sol (max) with 54
        biz_leader = BenchmarkRadar.get_leader("finance", "business_knowledge", top_n=5)
        self.assertEqual(biz_leader["model"], "GPT-6.1 Sol (max)")
        self.assertEqual(biz_leader["business_knowledge"], 54)


if __name__ == "__main__":
    unittest.main()
