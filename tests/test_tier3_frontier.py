from dataclasses import replace
import unittest

try:
    import pytest
except ImportError:
    raise unittest.SkipTest("pytest is not installed in the active environment")

from dr_engine.core.causal_dag import CausalCitationDAG
from dr_engine.core.credibility import SourceRecord
from dr_engine.core.engine import DeepResearchEngine
from dr_engine.core.hypergraph import EvidenceHypergraph
from dr_engine.core.hypothesis_ledger import HypothesisLedger, HypothesisRecord
from dr_engine.core.models import ExtractedLearning, ResearchReport, SearchResult
from dr_engine.ingestion.table_extractor import TableExtractor
from dr_engine.providers.llm import MockLLMProvider
from dr_engine.reporting.frontier_synthesizer import FrontierSynthesizer
from dr_engine.verification.sandbox import EmpiricalSandbox


def make_ledger() -> HypothesisLedger:
    return HypothesisLedger([
        HypothesisRecord("H1", "The proposed result is numerically reproducible.", 0.55, ["Independent calculations disagree."]),
        HypothesisRecord("H2", "The proposed result is not numerically reproducible.", 0.45, ["Independent calculations agree."]),
    ])


def test_sandbox_verifies_and_refutes_deliberate_arithmetic_errors():
    sandbox = EmpiricalSandbox()

    refuted = sandbox.verify_text("The paper states that 2 + 2 = 5.")[0]
    verified = sandbox.verify_text("The paper states that 2 + 2 = 4.")[0]
    syntax_error = sandbox.execute("claimed_value = ", claimed_value=1.0)
    unsafe = sandbox.execute("import socket\nclaimed_value = 1\ncomputed_value = 1", claimed_value=1.0)

    assert refuted.status == "refuted"
    assert refuted.computed_value == 4.0
    assert refuted.discrepancy_delta == 1.0
    assert refuted.verification_scope == "numerical_consistency"
    assert verified.status == "verified"
    assert verified.discrepancy_delta == 0.0
    assert syntax_error.status == "syntax_error"
    assert unsafe.status == "unsafe_code"
    assert sandbox.verify_text("The proposed method is 18.2% higher than the baseline.") == []


def test_empirical_refutation_updates_ledger_once_as_hard_evidence():
    sandbox = EmpiricalSandbox()
    claim = replace(sandbox.detector.detect("H1 check: 2 + 2 = 5.")[0], hypothesis_id="H1")
    proof = sandbox.verify(claim)
    ledger = make_ledger()
    prior = ledger.mean_probabilities["H1"]

    assert ledger.apply_empirical_proof(proof)
    posterior = ledger.mean_probabilities["H1"]
    history_size = len(ledger.evidence_history)
    assert ledger.apply_empirical_proof(proof)

    assert proof.status == "refuted"
    assert posterior < prior
    assert ledger.leading_hypothesis.hid == "H2"
    assert len(ledger.evidence_history) == history_size
    event = ledger.evidence_history[-1]
    assert event["kind"] == "empirical_refuted"
    assert event["likelihood_scores"]["H1"] == 0.02
    assert event["information_nats"] > 0


def test_four_node_citation_ring_collapses_to_one_unit_of_evidence():
    graph = CausalCitationDAG()
    for name in "ABCD":
        graph.add_source(SourceRecord(source_id=name, url=f"https://example.org/{name}", tier="paper"))
    for citing, cited in zip("ABCD", "BCDA"):
        graph.add_citation(citing, cited)

    condensation = graph.condense()
    collapse = graph.collapse(intrinsic_weights={name: 1.0 for name in "ABCD"})

    assert len(condensation.components) == 1
    assert condensation.edges == frozenset()
    assert collapse.neff == pytest.approx(1.0)
    assert collapse.independent_root_count == 1
    assert len(collapse.cartels) == 1
    assert collapse.roots[0].representative_id == "A"
    assert sorted(collapse.independence_weights.values()) == [0.0, 0.0, 0.0, 1.0]


def test_only_validated_derivation_edges_collapses_linear_cascades():
    raw = CausalCitationDAG()
    derived = CausalCitationDAG()
    for name in "ABC":
        source = SourceRecord(source_id=name, url=f"https://example.org/{name}", tier="paper")
        raw.add_source(source)
        derived.add_source(source)
    for citing, cited in (("A", "B"), ("B", "C")):
        raw.add_citation(citing, cited)
        derived.add_derivation(citing, cited)
    weights = {name: 1.0 for name in "ABC"}

    assert raw.collapse(intrinsic_weights=weights).neff == pytest.approx(3.0)
    collapsed = derived.collapse(intrinsic_weights=weights)
    assert collapsed.neff == pytest.approx(1.0)
    assert collapsed.roots[0].representative_id == "C"
    assert collapsed.root_provenance["A"] == ("C",)


def test_markdown_tables_preserve_coordinates_units_and_emit_idempotently():
    content = """Table 2: Matched benchmark
| Method | Latency (ms) | Accuracy |
| --- | --- | --- |
| Baseline | 0.12 s | 66.0% |
| Proposed | 100 | <0.1% |
| malformed | 1 |
"""
    extractor = TableExtractor()
    table = extractor.extract(content, "markdown")[0]

    assert table.rows[0]["Latency (ms)"] == pytest.approx(120.0)
    assert table.rows[0]["Accuracy"] == pytest.approx(66.0)
    assert table.rows[1]["Accuracy"] == "<0.1%"
    assert table.cell_provenance[(0, "Latency (ms)")].raw_value == "0.12 s"
    assert table.cell_provenance[(0, "Latency (ms)")].normalized_unit == "ms"
    assert table.cell_provenance[(1, "Accuracy")].value_kind == "bound"
    assert table.parse_warnings
    assert len(table.comparative_axes) == 2

    hypergraph = EvidenceHypergraph(":memory:")
    source_id = hypergraph.upsert_source("https://example.org/benchmark", tier="bench")
    first = extractor.emit_to_hypergraph(table, hypergraph, source_id)
    assertion_count = hypergraph.conn.execute("SELECT COUNT(*) FROM assertions").fetchone()[0]
    second = extractor.emit_to_hypergraph(table, hypergraph, source_id)

    assert len(first.cell_claim_ids) == 3
    assert len(first.comparison_claim_ids) == 1
    assert second.assertion_ids == first.assertion_ids
    assert hypergraph.conn.execute("SELECT COUNT(*) FROM assertions").fetchone()[0] == assertion_count
    comparison = hypergraph.conn.execute(
        "SELECT value, unit FROM claims WHERE id=?", (first.comparison_claim_ids[0],)
    ).fetchone()
    assert comparison["value"] == pytest.approx(-20.0)
    assert comparison["unit"] == "ms"


def test_html_table_expands_rowspan_without_losing_cell_provenance():
    html = """
    <table><caption>Ablation</caption>
    <tr><th>Method</th><th>Dataset</th><th>Score</th></tr>
    <tr><td rowspan="2">Baseline</td><td>A</td><td>10</td></tr>
    <tr><td>B</td><td>11</td></tr>
    </table>
    """
    table = TableExtractor().extract(html, "html")[0]

    assert table.caption == "Ablation"
    assert table.rows[1]["Method"] == "Baseline"
    assert table.rows[1]["Dataset"] == "B"
    assert table.cell_provenance[(1, "Method")].row_index == 1
    assert table.cell_provenance[(1, "Method")].column == "Method"


def test_frontier_report_renders_real_epistemic_and_provenance_state():
    hypergraph = EvidenceHypergraph(":memory:")
    source_a = hypergraph.upsert_source("https://example.org/a", tier="paper", reproducible=True)
    source_b = hypergraph.upsert_source("https://example.org/b", tier="paper", reproducible=True)
    hypergraph.upsert_source("https://example.org/retracted", tier="paper", retracted=True)
    claim_id = hypergraph.add_claim(
        "score", "Matched benchmark score", value=84.2, unit="%", uncertainty_lo=83.8, uncertainty_hi=84.6
    )
    hypergraph.add_assertion(claim_id, source_a, "84.2%", 0.95)
    hypergraph.add_assertion(claim_id, source_b, "84.2%", 0.95)
    graph = CausalCitationDAG.from_hypergraph(hypergraph)
    graph.add_derivation(source_a, source_b)
    hypergraph.citation_dag = graph

    ledger = make_ledger()
    initial_entropy = ledger.epistemic_uncertainty_nats
    sandbox = EmpiricalSandbox()
    quantitative = replace(
        sandbox.detector.detect("H1 check: mean of [2, 4, 6] is 4.")[0],
        hypothesis_id="H1",
        source_url="https://example.org/b",
    )
    proof = sandbox.verify(quantitative)
    assert ledger.apply_empirical_proof(proof)

    report = ResearchReport(
        title="Frontier Test",
        executive_summary="Existing synthesis.",
        markdown_content="# Frontier Test\n\nExisting synthesis.",
    )
    enhanced = FrontierSynthesizer().enhance_report(
        report,
        "Evaluate numerical reproducibility",
        ledger,
        hypergraph,
        [proof],
        graph,
        initial_entropy,
    )
    markdown = enhanced.markdown_content

    for heading in (
        "Executive Epistemic Abstract",
        "Evidence Triangulation Matrix",
        "Mermaid Epistemic Decision DAG",
        "Empirical Verification Appendix",
        "Consolidated Primary Bibliography",
    ):
        assert heading in markdown
    assert "P(H^*)" in markdown
    assert r"\bar{p}_t" in markdown
    assert "$I^2$" in markdown
    assert "$n_{eff}$" in markdown
    assert "https://example.org/b" in markdown
    assert "RETRACTED" in markdown
    assert "independence weight" in markdown
    assert "Absolute discrepancy" in markdown
    assert enhanced.metadata["tier3_frontier"]["empirical_proofs"] == 1
    assert enhanced.metadata["tier3_frontier"]["retracted_sources"] == 1
    assert enhanced.metadata["tier3_frontier"]["total_evidence_nats"] > 0
    assert enhanced.mermaid_diagrams[-1].startswith("flowchart TD")
    assert enhanced.key_findings_matrix[-1]["metrics"].startswith("n_eff=")


class OneSourceSearch:
    def search(self, query: str, category: str = "web", max_results: int = 3):
        return [SearchResult(
            title="Tier 3 integration fixture",
            url="https://example.org/integration",
            snippet="Arithmetic and tabular evidence",
        )]


class OneSourceReader:
    def read(self, target: str):
        return {
            "source": target,
            "title": "Tier 3 integration fixture",
            "text": "[H1] arithmetic check: 2 + 2 = 5.\n\n## References\nhttps://example.org/root\n",
            "tables_html": "<table><caption>Results</caption><tr><th>Method</th><th>Latency (ms)</th></tr><tr><td>Baseline</td><td>0.12 s</td></tr><tr><td>Proposed</td><td>100</td></tr></table>",
            "format": "html",
        }


def test_engine_wires_tables_citations_proofs_and_frontier_reporting():
    engine = DeepResearchEngine(llm=MockLLMProvider(), search_aggregator=OneSourceSearch(), reader=OneSourceReader())
    engine.extractor.extract_from_source = lambda query, source: [
        ExtractedLearning(
            learning="[H1] arithmetic check: 2 + 2 = 5.",
            entities=["H1"],
            metrics=["2 + 2 = 5"],
            source_url=source.url,
            confidence=1.0,
        ),
        ExtractedLearning(
            learning="H1 receptor calculation: 3 + 3 = 6.",
            entities=["H1 receptor"],
            metrics=["3 + 3 = 6"],
            source_url=source.url,
            confidence=1.0,
        ),
    ]
    engine.cove.verify_and_patch = lambda markdown: {"corrections_made": 0, "verified_text": markdown}

    report = engine.run("Check Tier 3 integration", breadth=1, depth=0)

    verification = report.metadata["empirical_verification"]
    assert verification["ledger_updates"] == 1
    assert verification["proofs"][0]["status"] == "refuted"
    assert verification["proofs"][0]["discrepancy_delta"] == 1.0
    assert verification["proofs"][1]["status"] == "verified"
    assert verification["proofs"][1]["hypothesis_id"] is None
    assert report.metadata["table_extraction"] == {"tables": 1, "assertions": 3}
    assert report.metadata["citation_dag"]["edges"][0]["cited"] == "https://example.org/root"
    assert report.metadata["tier3_frontier"]["empirical_refutations"] == 1
    assert "Empirical Verification Appendix" in report.markdown_content
    assert "Evidence Triangulation Matrix" in report.markdown_content


def test_dynamic_derivative_detection_discounts_judge_sensitivities():
    def make_local_ledger():
        return HypothesisLedger([
            HypothesisRecord("H1", "Target proposition holds.", 0.50, ["falsifier1"]),
            HypothesisRecord("H2", "Baseline proposition holds.", 0.50, ["falsifier2"]),
        ])

    l1 = make_local_ledger()
    l1.update_with_document_findings(
        doc_url="https://example.org/independent",
        learnings=["MCTS achieves 84.2% accuracy outperforming beam search."],
        is_derivative=False,
    )
    p1_indep = l1.mean_probabilities["H1"]

    l2 = make_local_ledger()
    l2.update_with_document_findings(
        doc_url="https://example.org/derivative_copy",
        learnings=["MCTS achieves 84.2% accuracy outperforming beam search."],
        is_derivative=True,
    )
    p1_deriv = l2.mean_probabilities["H1"]

    assert p1_indep > p1_deriv > 0.50


def test_conflict_detection_with_citation_cartel_and_k_guard():
    h = EvidenceHypergraph(":memory:")
    s1 = h.upsert_source("https://example.org/study1", tier="paper")
    s2 = h.upsert_source("https://example.org/study2_clone", tier="paper", upstream_refs=["https://example.org/study1"])

    c1 = h.add_claim("throughput", "Throughput is 100 tps", value=100.0, unit="tps")
    c2 = h.add_claim("throughput", "Throughput is 110 tps", value=110.0, unit="tps")
    h.add_assertion(c1, s1, "100 tps", 0.95)
    h.add_assertion(c2, s2, "110 tps", 0.95)

    dag = CausalCitationDAG.from_hypergraph(h)
    dag.add_derivation(s2, s1)
    h.citation_dag = dag

    conflicts = h.detect_conflicts()
    assert len(conflicts) == 1
    # 10% relative difference <= 20% guard threshold -> consensus, not regime split
    assert conflicts[0]["status"] == "crh_consensus"
    assert conflicts[0]["truth_estimate"] == pytest.approx(100.09, abs=0.5)

    # Disparate values (>20% relative diff) trigger regime split
    c3 = h.add_claim("throughput", "Throughput is 250 tps", value=250.0, unit="tps")
    h.add_assertion(c3, s1, "250 tps", 0.95)
    conflicts_split = h.detect_conflicts()
    assert any(c["status"] == "regime_split_required" for c in conflicts_split)
