"""
End-to-End Integration Test Suite.
Verifies that the entire Deep Research pipeline runs from query to final publication report
without crashing, with token tracking, MCTS control, claim resolution, and budget enforcement.
"""

import sys
import os
import re
import unittest
from typing import List

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from dr_engine.core.engine import DeepResearchEngine
from dr_engine.core.models import SearchResult, ResearchReport
from dr_engine.providers.llm import MockLLMProvider
from dr_engine.core.universal_reader import UniversalReader


class MockSearchAggregator:
    def __init__(self):
        self.call_count = 0

    def search(self, query: str, category: str = "web", max_results: int = 3) -> List[SearchResult]:
        self.call_count += 1
        q_slug = re.sub(r"\W+", "_", query.lower())[:25].strip("_")
        return [
            SearchResult(
                title=f"Empirical Evaluation {query}",
                url=f"https://arxiv.org/abs/2408.0{self.call_count}_{q_slug}",
                snippet="MCTS achieves 18.2% higher pass@1 on MATH-500 compared to beam search.",
                source="arxiv",
            ),
            SearchResult(
                title=f"Latency Constraints {query}",
                url=f"https://github.com/google-deepmind/bench_{self.call_count}_{q_slug}",
                snippet="Benchmarks demonstrate that naive beam search achieves lower latency but fails to solve non-convex problems.",
                source="github",
            ),
        ]


class MockReader:
    def read(self, target: str):
        return {
            "source": target,
            "title": "MCTS vs Beam Search Study",
            "text": """
# Empirical Evaluation of Test-Time Search
MCTS achieves 18.2% higher pass@1 on MATH-500 compared to beam search.
Under high-load benchmarks, latency was reduced by 12% across distributed shards.
Conversely, baseline beam search fails to match MCTS under non-convex reasoning landscapes.
| Model | Accuracy (Pass@1) | Latency (ms) |
| --- | --- | --- |
| MCTS Agent | 84.2% | 120 |
| Beam Search | 66.0% | 85 |
""",
            "format": "markdown",
        }


class TestDeepResearchPipeline(unittest.TestCase):
    def test_pipeline_runs_to_completion(self):
        mock_llm = MockLLMProvider()
        mock_search = MockSearchAggregator()
        mock_reader = MockReader()

        engine = DeepResearchEngine(
            llm=mock_llm,
            search_aggregator=mock_search,
            reader=mock_reader,
        )

        stages_recorded = []

        def on_progress(stage: str, data: dict):
            stages_recorded.append(stage)

        report = engine.run(
            query="Evaluate MCTS vs Beam Search in Reasoning Agents",
            depth=2,
            breadth=2,
            on_progress=on_progress,
        )

        # 1. Assert Report Identity & Non-empty Fields
        self.assertIsInstance(report, ResearchReport)
        self.assertTrue(len(report.title) > 5)
        self.assertTrue(len(report.executive_summary) > 20)
        self.assertTrue(len(report.sections) >= 2)
        self.assertTrue(len(report.markdown_content) > 100)

        # 2. P0 Verification: Metadata must exist and not raise AttributeError
        self.assertIsNotNone(report.metadata)
        self.assertIn("budget_governor", report.metadata)
        self.assertIn("hypothesis_ledger", report.metadata)

        # 3. P1 Verification: Tokens must be non-zero
        budget_meta = report.metadata["budget_governor"]
        self.assertGreater(budget_meta["total_tokens"], 0, "Total tokens must be > 0 (tracked across LLM calls)")
        self.assertGreater(budget_meta["total_fetches"], 0, "Total fetches must be recorded")
        self.assertGreaterEqual(budget_meta["total_tokens"], 3250, "All LLM calls including triage (69+ tokens) must be credited")
        self.assertGreater(budget_meta["nats_reduced_per_ktoken"], 0.0, "Epistemic entropy must reduce over ktoken spent")

        # 4. P1 Verification: Hypothesis Ledger & Directional Bayesian Beliefs
        hyp_meta = report.metadata["hypothesis_ledger"]
        self.assertEqual(hyp_meta["leading_hypothesis"], "H1", "Confirming evidence must establish H1 as leading hypothesis")
        self.assertIn("H1", hyp_meta["distribution"])
        self.assertIn("H2", hyp_meta["distribution"])
        self.assertGreater(hyp_meta["distribution"]["H1"], 0.70, "H1 posterior must reflect confirming evidence (P(H1) > 0.70)")

        # 5. Pipeline Stages & Multi-Round MCTS VoI Execution
        self.assertIn("triage_start", stages_recorded)
        self.assertIn("planning_start", stages_recorded)
        self.assertIn("depth_iteration", stages_recorded)
        self.assertIn("mcts_actions_recommended", stages_recorded, "MCTS controller must clear and recommend frontier actions")
        self.assertGreaterEqual(stages_recorded.count("depth_iteration"), 2, "Search must execute multiple rounds via MCTS VoI gate (depth > 0)")
        self.assertGreaterEqual(mock_search.call_count, 3, "Multiple search rounds must be executed across depths")
        self.assertIn("triangulation_start", stages_recorded)
        self.assertIn("synthesis_start", stages_recorded)
        self.assertIn("research_completed", stages_recorded)

        print("\n=======================================================")
        print("[OK] FULL END-TO-END PIPELINE VERIFICATION PASSED CODE 0")
        print("=======================================================")
        print(f"Report Title: {report.title}")
        print(f"Tokens Spent: {budget_meta['total_tokens']}")
        print(f"Leading Hypothesis: {hyp_meta['leading_hypothesis']} (P={hyp_meta['distribution'].get(hyp_meta['leading_hypothesis'])})")
        print(f"Stages Executed: {len(stages_recorded)}")


if __name__ == "__main__":
    unittest.main()
