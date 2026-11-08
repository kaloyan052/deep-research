#!/usr/bin/env python3
"""v11.0 Unfair Epistemic Dominance — exhaustive adversarial regression suite.

Covers the four frontiers:
  1. keyless censorship / bot-wall evasion (Wayback CDX, Memento, FxTwitter,
     PullPush, Redlib, DDG Lite, SearXNG) + measured coverage;
  2. correlated Monte Carlo (Cholesky), macro regimes, VaR99 / CVaR99;
  3. B10 de_jure vs de_facto Dialectical Reconciliation Matrix;
  4. R17 anti-fluff Information Density Gate.

All network access is mocked. No API keys, no external services, no flakiness.
"""

from __future__ import annotations

import argparse
import io
import json
import math
import os
import tempfile
import unittest
import urllib.error
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from dr_engine.tools import (
    decision_card, density_gate, dialectical_arbitration, epistemic_guard,
    http_resilience, lean_engine, risk_engine, trench_miner,
    v9_bullshit_filters,
)
from dr_engine.tools.http_resilience import FetchResult


def _fetch(ok, text="", via="direct", cls="primary_fetched", url="https://x.test",
           status=200, error="", chain=None):
    return FetchResult(
        ok=ok, url=url, text=text, status=status if ok else (status if error else 403),
        via=via, charset="utf-8", sha256="", attempts=1, error=error,
        bot_wall=not ok, elapsed_ms=0.0, truncated=False, lossy=False,
        evidence_class=cls, fallback_chain=chain or [], source_url=url,
    )


class _Resp:
    def __init__(self, body: bytes, status: int = 200, headers: dict | None = None):
        self._body, self.status, self.headers = body, status, headers or {}

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self, n: int = -1) -> bytes:
        return self._body if n < 0 else self._body[:n]


# ===========================================================================
# FRONTIER 1 — keyless multi-path fallback & coverage
# ===========================================================================
class TestKeylessFallback(unittest.TestCase):
    def test_declared_path_order_and_authority_downgrades(self):
        self.assertEqual(http_resilience.FALLBACK_PATH_ORDER,
                         ("memento", "wayback_cdx", "syndication", "search_cache"))
        classes = http_resilience.EVIDENCE_CLASS_BY_PATH
        self.assertEqual(classes["direct"], "primary_fetched")
        self.assertEqual(classes["wayback_cdx"], "archival_copy")
        self.assertEqual(classes["memento"], "archival_copy")
        self.assertEqual(classes["syndication"], "syndicated_transcription")
        self.assertEqual(classes["search_cache"], "search_snippet")
        self.assertFalse(_fetch(True, cls="archival_copy").is_primary)
        self.assertTrue(_fetch(True).is_primary)

    @mock.patch("dr_engine.tools.http_resilience._raw_get")
    def test_memento_availability_recovers_closest_snapshot(self, raw_get):
        snap_url = "https://web.archive.org/web/20260101000000/https://blocked.test/thread"
        raw_get.side_effect = [
            _fetch(True, json.dumps({"archived_snapshots": {"closest": {
                "url": snap_url, "timestamp": "20260101000000", "status": "200"}}}),
                via="direct", url="https://archive.org/wayback/available"),
            _fetch(True, "RECOVERED THREAD BODY: " + "spread widened 4.2 bps. " * 8,
                   via="direct", url=snap_url),
        ]
        result, record = http_resilience._fallback_memento(
            "https://blocked.test/thread", 3.0, 100000)
        self.assertIsNotNone(result) and self.assertTrue(result.ok)
        self.assertEqual(result.via, "memento")
        self.assertEqual(result.evidence_class, "archival_copy")
        self.assertEqual(result.source_url, snap_url)
        self.assertIn("SECONDARY SOURCE", " ".join(result.warnings))
        self.assertTrue(record["ok"] and record["timestamp"] == "20260101000000")

    @mock.patch("dr_engine.tools.http_resilience._raw_get")
    def test_cdx_selects_newest_capture_not_first(self, raw_get):
        rows = [
            ["timestamp", "original", "statuscode", "digest"],
            ["20230101000000", "https://blocked.test/t", "200", "AAA"],
            ["20251115000000", "https://blocked.test/t", "200", "BBB"],
            ["20240101000000", "https://blocked.test/t", "200", "CCC"],
        ]
        raw_get.side_effect = [
            _fetch(True, json.dumps(rows), via="direct"),
            _fetch(True, "ARCHIVED PRACTITIONER POSTMORTEM: " + "latency spike. " * 10,
                   via="direct"),
        ]
        result, record = http_resilience._fallback_wayback_cdx(
            "https://blocked.test/t", 3.0, 100000)
        self.assertTrue(result.ok)
        self.assertEqual(record["timestamp"], "20251115000000")
        self.assertIn("20251115000000", result.source_url)
        self.assertEqual(result.evidence_class, "archival_copy")

    @mock.patch("dr_engine.tools.http_resilience._raw_get")
    def test_fxtwitter_syndication(self, raw_get):
        raw_get.return_value = _fetch(True, json.dumps({
            "tweet": {"text": "Production fill rate collapsed after the venue changed queue priority.",
                      "created_at": "2026-10-01", "author": {"screen_name": "quant_dev"}}
        }), via="direct")
        result, record = http_resilience._fallback_syndication(
            "https://x.com/quant_dev/status/1234567890", 3.0, 100000)
        self.assertTrue(result.ok and result.via == "syndication")
        self.assertEqual(result.evidence_class, "syndicated_transcription")
        self.assertIn("FxTwitter", result.text)
        self.assertEqual(record["via"], "fxtwitter")

    @mock.patch("dr_engine.tools.http_resilience._raw_get")
    def test_pullpush_recovers_deleted_reddit_comments(self, raw_get):
        raw_get.return_value = _fetch(True, json.dumps({"data": [
            {"body": "In production the slippage ate the entire edge after 3 weeks."},
            {"body": "[deleted]"},
            {"body": "We measured 4.2 bps of extra spread during the open, not in the backtest."},
        ]}), via="direct")
        result, record = http_resilience._fallback_syndication(
            "https://www.reddit.com/r/algotrading/comments/abc123/0dte_postmortem",
            3.0, 100000)
        self.assertTrue(result.ok)
        self.assertEqual(record["comments"], 2)
        self.assertIn("[COMMENT 1]", result.text)
        self.assertNotIn("[deleted]", result.text)
        self.assertEqual(result.evidence_class, "syndicated_transcription")

    @mock.patch("dr_engine.tools.http_resilience._raw_get")
    def test_redlib_used_when_pullpush_empty(self, raw_get):
        raw_get.side_effect = [
            _fetch(True, json.dumps({"data": []}), via="direct"),
            _fetch(True, "<html><body>Recovered Reddit thread: "
                   + "the maker queue priority changed. " * 6 + "</body></html>", via="direct"),
        ]
        result, record = http_resilience._fallback_syndication(
            "https://reddit.com/r/algotrading/comments/abc123/x", 3.0, 100000)
        self.assertTrue(result.ok and record["via"] == "redlib")
        self.assertIn("Recovered Reddit thread", result.text)

    @mock.patch("dr_engine.tools.http_resilience._raw_get")
    def test_ddg_lite_cache_is_leads_only_never_evidence(self, raw_get):
        html = (
            '<a href="https://mirror.test/thread" class="result-link">Cached thread title</a>'
            '<a href="https://other.test/post">Another cached snippet about slippage</a>'
        )
        raw_get.return_value = _fetch(True, html, via="direct")
        result, record = http_resilience._fallback_search_cache(
            "https://www.reddit.com/r/algotrading/comments/abc123/x", 3.0, 100000)
        self.assertTrue(result.ok)
        self.assertEqual(result.evidence_class, "search_snippet")
        self.assertFalse(result.is_primary)
        self.assertIn("NOT VERBATIM EVIDENCE", result.text)
        self.assertIn("leads, never evidence", result.text)
        self.assertEqual(record["leads"], 2)

    @mock.patch("dr_engine.tools.http_resilience._raw_get")
    def test_searxng_json_used_when_ddg_blocked(self, raw_get):
        raw_get.side_effect = [
            _fetch(False, "", error="HTTP 403"),
            _fetch(True, json.dumps({"results": [
                {"url": "https://cached.test/a", "content": "Spread widened 4.2 bps."},
            ]}), via="direct"),
        ]
        result, record = http_resilience._fallback_search_cache(
            "https://blocked.test/thread/slippage", 3.0, 100000)
        self.assertTrue(result.ok and record["leads"] == 1)
        self.assertEqual(record["via"], "ddg_lite_or_searxng")

    @mock.patch("dr_engine.tools.http_resilience.resilient_fetch")
    @mock.patch("dr_engine.tools.http_resilience._fallback_memento")
    def test_direct_success_short_circuits_all_mirrors(self, memento, direct):
        direct.return_value = _fetch(True, "PRIMARY PAGE BODY " * 6, via="direct")
        result = http_resilience.fetch_with_fallbacks("https://open.test/page")
        self.assertTrue(result.ok and result.is_primary)
        self.assertEqual(len(result.fallback_chain), 1)
        memento.assert_not_called()

    @mock.patch("dr_engine.tools.http_resilience.resilient_fetch")
    @mock.patch("dr_engine.tools.http_resilience._fallback_memento")
    @mock.patch("dr_engine.tools.http_resilience._fallback_wayback_cdx")
    @mock.patch("dr_engine.tools.http_resilience._fallback_syndication")
    @mock.patch("dr_engine.tools.http_resilience._fallback_search_cache")
    def test_full_chain_is_audited_and_last_path_recovers(
            self, search, synd, cdx, memento, direct):
        direct.return_value = _fetch(False, "", via="none", cls="none", error="HTTP 403")
        memento.return_value = (None, {"path": "memento", "ok": False, "error": "no snapshot"})
        cdx.return_value = (None, {"path": "wayback_cdx", "ok": False, "error": "no captures"})
        synd.return_value = (None, {"path": "syndication", "ok": False, "error": "unsupported"})
        search.return_value = (
            _fetch(True, "CACHED LEADS " * 20, via="search_cache", cls="search_snippet"),
            {"path": "search_cache", "ok": True, "leads": 3},
        )
        result = http_resilience.fetch_with_fallbacks("https://blocked.test/thread")
        self.assertTrue(result.ok)
        self.assertEqual([c["path"] for c in result.fallback_chain],
                         ["direct", "memento", "wayback_cdx", "syndication", "search_cache"])
        self.assertEqual(result.evidence_class, "search_snippet")
        self.assertIn("direct path failed", " ".join(result.warnings))

    @mock.patch("dr_engine.tools.http_resilience.resilient_fetch")
    @mock.patch("dr_engine.tools.http_resilience._fallback_memento")
    def test_env_disable_mirrors_prevents_third_party_contact(self, memento, direct):
        direct.return_value = _fetch(False, "", via="none", cls="none", error="HTTP 403")
        with mock.patch.dict(os.environ, {"DR_DISABLE_MIRRORS": "1"}):
            result = http_resilience.fetch_with_fallbacks("https://blocked.test/thread")
        self.assertFalse(result.ok)
        memento.assert_not_called()
        self.assertIn("disabled", " ".join(result.warnings))

    def test_coverage_benchmark_95_percent_target(self):
        results = [_fetch(True)] * 19 + [_fetch(False, cls="none", error="403")]
        cov = http_resilience.benchmark_fallback_coverage(results)
        self.assertEqual(cov["coverage_pct"], 95.0)
        self.assertTrue(cov["meets_95pct_target"])
        self.assertEqual(cov["secondary_recoveries"], 0)
        worse = http_resilience.benchmark_fallback_coverage(
            [_fetch(True)] * 18 + [_fetch(False, cls="none", error="403")] * 2)
        self.assertFalse(worse["meets_95pct_target"])
        secondary = http_resilience.benchmark_fallback_coverage(
            [_fetch(True)] * 17 + [
                _fetch(True, cls="archival_copy", via="wayback_cdx") for _ in range(3)])
        self.assertEqual(secondary["coverage_pct"], 100.0)
        self.assertEqual(secondary["secondary_recoveries"], 3)
        self.assertIn("archival_copy", secondary["evidence_classes"])

    def test_mirror_rescue_item_is_downgraded(self):
        item = trench_miner.TrenchEvidenceItem(
            "MirrorRescue", "wayback_cdx", "archive", "Recovered thread",
            "https://reddit.com/r/x/comments/abc", "unknown", 5,
            "In production the spread widened to 4.2 bps and the edge died.",
            date_known=False, fetch_via="wayback_cdx", evidence_class="archival_copy",
        )
        self.assertFalse(item.is_primary)
        self.assertIn("class=archival_copy", item.render_snapshot_block())

    def test_ingest_records_secondary_transcription_and_verifier_warns(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp) / "study"
            d.mkdir()
            spec = {
                "urls": ["https://blocked.test/thread"],
                "inline_sources": {
                    "https://cboe.com/report":
                        "CBOE empirical report: effective spread 1.2 bps in 2026. " * 5,
                },
                "sub_questions": {"SQ1": "spread friction"},
                "kill_hypotheses": {"K1": "spread exceeds gross edge"},
            }
            (d / "study_spec.json").write_text(json.dumps(spec), encoding="utf-8")
            secondary = {
                "ok": True, "url": "https://blocked.test/thread",
                "text": "RECOVERED: In production the spread widened 4.2 bps. " * 6,
                "status": 200, "error": "", "via": "wayback_cdx",
                "charset": "utf-8", "sha256": "",
                "evidence_class": "archival_copy", "bot_wall": False,
                "source_url": "https://web.archive.org/web/2026id_/https://blocked.test/thread",
                "fallback_chain": [{"path": "direct", "ok": False},
                                   {"path": "wayback_cdx", "ok": True}],
                "warnings": ["SECONDARY SOURCE via wayback_cdx"],
            }
            with mock.patch("dr_engine.tools.lean_engine._fetch_single_url",
                            return_value=secondary):
                rc = lean_engine.cmd_ingest(argparse.Namespace(
                    dir=str(d), spec=str(d / "study_spec.json")))
            self.assertEqual(rc, 0)
            rows = [json.loads(l) for l in (d / "sources" / "index.jsonl").read_text(
                encoding="utf-8").splitlines() if l.strip()]
            mirror = next(r for r in rows if "blocked.test" in r["url"])
            self.assertTrue(mirror["secondary_transcription"])
            self.assertEqual(mirror["evidence_class"], "archival_copy")
            self.assertEqual(len(mirror["fallback_chain"]), 2)
            inline = next(r for r in rows if "cboe.com" in r["url"])
            self.assertFalse(inline["secondary_transcription"])


# ===========================================================================
# FRONTIER 2 — correlated Monte Carlo, regimes, VaR / CVaR
# ===========================================================================
MODEL_CODE = """
gross_bp = 8.4
spread_bp = 1.2
slippage_rt_bp = 1.8
stop_1r_bp = 100.0
total_friction_bp = spread_bp + slippage_rt_bp
friction_share_of_1r = total_friction_bp / stop_1r_bp
net_alpha_bp = net_edge_bp(gross_bp, spread_bp, slippage_rt_bp)
""".strip()


class TestCorrelatedRisk(unittest.TestCase):
    def test_cholesky_reconstructs_correlation_matrix(self):
        sigma = [[1.0, 0.8, 0.3], [0.8, 1.0, 0.5], [0.3, 0.5, 1.0]]
        L, info = risk_engine.cholesky(sigma)
        self.assertIsNotNone(L) and self.assertTrue(info["positive_definite"])
        self.assertFalse(info["repaired"])
        for i in range(3):
            for j in range(3):
                recon = sum(L[i][k] * L[j][k] for k in range(3))
                self.assertAlmostEqual(recon, sigma[i][j], places=9)

    def test_indefinite_matrix_is_repaired_with_reported_shrinkage(self):
        bad = [[1.0, 0.99, -0.99], [0.99, 1.0, 0.99], [-0.99, 0.99, 1.0]]
        L, info = risk_engine.cholesky(bad)
        self.assertIsNotNone(L)
        self.assertEqual(info["repair"], "identity_shrinkage")
        self.assertGreater(info["shrinkage"], 0.0)
        L2, info2 = risk_engine.cholesky(bad, jitter=False)
        self.assertIsNone(L2) and self.assertFalse(info2["positive_definite"])

    def test_correlation_specs_all_forms(self):
        names = ["a", "b", "c"]
        m1, _ = risk_engine.build_correlation_matrix(names, {("a", "b"): 0.7})
        self.assertEqual(m1[0][1], 0.7) and self.assertEqual(m1[1][0], 0.7)
        m2, meta = risk_engine.build_correlation_matrix(
            names, {"groups": [(["a", "b", "c"], 0.6)]})
        self.assertTrue(all(abs(m2[i][j] - 0.6) < 1e-9
                            for i in range(3) for j in range(3) if i != j))
        self.assertEqual(meta["pairs"], 3)
        m3, _ = risk_engine.build_correlation_matrix(
            names, {"matrix": [[1, 0.4, 0], [0.4, 1, 0], [0, 0, 1]], "order": names})
        self.assertEqual(m3[0][1], 0.4)
        m4, _ = risk_engine.build_correlation_matrix(names, {"a|b": 0.55})
        self.assertEqual(m4[0][1], 0.55)
        ident, _ = risk_engine.build_correlation_matrix(names, None)
        self.assertEqual(ident[0][1], 0.0)

    def test_correlated_shocks_couple_inputs(self):
        L, _ = risk_engine.cholesky([[1.0, 0.9], [0.9, 1.0]])
        zc = risk_engine.correlated_shocks(L, [1.0, 0.0])
        self.assertAlmostEqual(zc[0], 1.0)
        self.assertGreater(zc[1], 0.5)
        self.assertLessEqual(risk_engine.correlated_shocks(
            L, [99.0, -99.0], clamp=2.0)[0], 2.0)

    def test_regime_mean_shifts_longest_pattern_wins(self):
        names = ["spread_bp", "slippage_bp", "fee_bp", "volume", "volatility"]
        shifts = risk_engine.regime_mean_shifts(names, "Liquidity Crunch")
        self.assertEqual(shifts[0], 1.6)
        self.assertEqual(shifts[3], -1.2)   # "volume", not generic "vol"
        self.assertEqual(shifts[4], 1.3)   # "volatility"
        self.assertEqual(risk_engine.regime_mean_shifts(names, "Baseline"), [0.0] * 5)
        self.assertEqual(risk_engine.regime_mean_shifts(names, "no-such-regime"), [0.0] * 5)

    def test_regime_and_structural_correlation_specs(self):
        names = ["spread_bp", "slippage_bp", "fee_bp", "volume"]
        spec = risk_engine.regime_correlation_spec(names, "Liquidity Crunch")
        self.assertEqual(spec["groups"][0][1], 0.85)
        self.assertIn("spread_bp", spec["groups"][0][0])
        self.assertTrue(risk_engine.structural_correlation_spec(names)["groups"])
        self.assertEqual(risk_engine.regime_correlation_spec(names, "Baseline"), {})

    def test_all_three_regimes_are_declared(self):
        for name in ("Liquidity Crunch", "High-Inflation Squeeze", "Latency Breakdown"):
            spec = risk_engine.MACRO_REGIMES[name]
            self.assertGreater(spec["group_rho"], 0.0)
            self.assertGreater(spec["sigma_multiplier"], 1.0)
            self.assertTrue(spec["mean_shock_patterns"])

    def test_var_cvar_conventions_and_shortfall_inequality(self):
        vals = [-10.0] + [float(i) for i in range(1, 100)]
        r = risk_engine.empirical_var_cvar(vals)
        self.assertTrue(r["cvar_ge_var"])
        self.assertGreaterEqual(r["cvar_99"], r["var_99"])
        self.assertEqual(r["n"], 100) and self.assertGreaterEqual(r["tail_n"], 1)
        positive = risk_engine.empirical_var_cvar([float(i) for i in range(1, 101)])
        self.assertTrue(positive["var_negative_means_no_loss"])
        self.assertEqual(risk_engine.quantile([1.0, 2.0, 3.0, 4.0], 0.5), 3.0)
        summary = risk_engine.risk_summary(vals)
        self.assertEqual(summary["p50"], 50.0)

    def test_correlated_monte_carlo_reports_var_cvar_and_provenance(self):
        inputs, metrics, code = decision_card.compile_models_for_decision_card(
            [("C001", MODEL_CODE)])
        mc = decision_card.compute_monte_carlo(
            code, inputs, metrics, n_samples=400, seed=11, regime="Liquidity Crunch")
        self.assertEqual(mc["regime"], "Liquidity Crunch")
        self.assertTrue(mc["correlation"]["cholesky"]["positive_definite"])
        self.assertEqual(mc["correlation"]["mean_shifts"]["spread_bp"], 1.6)
        self.assertGreater(mc["effective_sigma_frac"], mc["sigma_frac"])
        for name, d in mc["metrics"].items():
            self.assertIsNotNone(d["var_99"]) and self.assertIsNotNone(d["cvar_99"])
            self.assertGreaterEqual(d["cvar_99"], d["var_99"] - 1e-6)
            self.assertLessEqual(d["hist_lo"], d["hist_hi"])
            self.assertEqual(len(d["histogram"]), 18)
        again = decision_card.compute_monte_carlo(
            code, inputs, metrics, n_samples=400, seed=11, regime="Liquidity Crunch")
        self.assertEqual(mc, again, "correlated Monte Carlo must be reproducible")

    def test_v10_default_mc_path_is_preserved(self):
        inputs, metrics, code = decision_card.compile_models_for_decision_card(
            [("C001", MODEL_CODE)])
        a = decision_card.compute_monte_carlo(code, inputs, metrics, n_samples=200, seed=42)
        b = decision_card.compute_monte_carlo(code, inputs, metrics, n_samples=200, seed=42)
        self.assertEqual(a, b)
        self.assertIsNone(a["correlation"])
        self.assertIsNone(a["regime"])
        self.assertEqual(a["effective_sigma_frac"], a["sigma_frac"])
        self.assertIn("risk_convention", a)

    def test_risk_svg_has_var_cvar_markers(self):
        inputs, metrics, code = decision_card.compile_models_for_decision_card(
            [("C001", MODEL_CODE)])
        mc = decision_card.compute_monte_carlo(
            code, inputs, metrics, n_samples=300, seed=5, regime="Liquidity Crunch")
        svg = decision_card.render_risk_svg(mc["metrics"]["net_alpha_bp"])
        self.assertIn("<svg", svg) and self.assertIn("<rect", svg)
        self.assertIn("VaR99", svg) and self.assertIn("CVaR", svg)
        self.assertIn("#ef4444", svg)

    def test_regime_stress_scenarios_are_deterministic_and_baseline_matches(self):
        inputs, metrics, code = decision_card.compile_models_for_decision_card(
            [("C001", MODEL_CODE)])
        rows = decision_card.compute_regime_stress_scenarios(code, inputs, metrics)
        self.assertEqual([r["regime"] for r in rows], [
            "Baseline", "Liquidity Crunch", "High-Inflation Squeeze", "Latency Breakdown"])
        baseline = rows[0]["values"]["net_alpha_bp"]
        self.assertAlmostEqual(baseline, 5.4, places=3)
        self.assertIn("spread_bp", rows[1]["shocked_inputs"])
        self.assertLess(rows[1]["values"]["net_alpha_bp"], baseline)

    def test_decision_card_html_contains_regime_and_tail_risk_panels(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp) / "study"
            src = d / "sources"
            src.mkdir(parents=True)
            body = "CBOE report: effective spread 1.2 bps, net alpha 5.4 bps in 2026. " * 4
            (src / "S001.txt").write_text(body, encoding="utf-8")
            (src / "index.jsonl").write_text(json.dumps({
                "id": "S001", "url": "https://cboe.com/x",
                "sha256": lean_engine.sha256_text(body), "chars": len(body),
            }) + "\n", encoding="utf-8")
            manifest = {"domain": "quant", "verdict": "GO",
                        "evidence": [{"id": "E001", "source": "S001", "tier": "T1",
                                      "quote": "effective spread 1.2 bps"}], "kills": []}
            report = ("# Correlated Risk Study\n\n"
                      "```json:manifest\n" + json.dumps(manifest) + "\n```\n\n"
                      "```python:model C001\n" + MODEL_CODE + "\n```\n")
            (d / "report.md").write_text(report, encoding="utf-8")
            fake = SimpleNamespace(passed=True, max_confidence="High",
                                   epistemic_index=88.0, information_density_index=140.0,
                                   n_eff_clusters=3.0, bound_units=1,
                                   total_claim_units=1, n_evidence=1)
            out = decision_card.render_decision_card_html(d, verification=fake)
            for needle in ("Correlated Regime Stress", "Empirical Tail Risk",
                           "VaR99", "CVaR", "Declared Macro Stress Regimes",
                           "Liquidity Crunch", "Cholesky"):
                self.assertIn(needle, out)


# ===========================================================================
# FRONTIER 3 — B10 dialectical arbitration
# ===========================================================================
def _conflict_manifest(**overrides):
    manifest = {
        "domain": "quant", "verdict": "GO",
        "evidence": [
            {"id": "E001", "tier": "T1", "kind": "academic", "stance": "supports",
             "subject": "gamma_edge", "epistemic_mode": "de_jure",
             "quote": "Theoretical model predicts positive expectancy under frictionless execution."},
            {"id": "E002", "tier": "T5", "kind": "practitioner_postmortem",
             "stance": "contradicts", "subject": "gamma_edge",
             "epistemic_mode": "de_facto",
             "quote": "In production the spread widened and slippage ate the edge; fill rate collapsed."},
        ],
        "dialectics": [{
            "subject": "gamma_edge",
            "axis": "undisclosed_microstructure_friction",
            "resolution": "Re-run with measured round-turn friction.",
            "verification": {"status": "pending"},
        }],
    }
    manifest.update(overrides)
    return manifest


CLEAN_REPORT = "We reject the frictionless theoretical result [E001] given measured execution [E002]."


class TestDialecticalArbitration(unittest.TestCase):
    def test_epistemic_mode_requires_tier_and_semantics(self):
        self.assertEqual(dialectical_arbitration.epistemic_mode(
            {"tier": "T1", "kind": "academic"}), "de_jure")
        self.assertEqual(dialectical_arbitration.epistemic_mode(
            {"tier": "T5", "kind": "practitioner_postmortem"}), "de_facto")
        self.assertIsNone(dialectical_arbitration.epistemic_mode(
            {"tier": "T1", "kind": "context"}))
        self.assertEqual(dialectical_arbitration.epistemic_mode(
            {"tier": "T5", "epistemic_mode": "de_jure"}), "de_jure")

    def test_conflict_detection_and_subject_scoping(self):
        conflicts = dialectical_arbitration.detect_dejure_defacto_conflicts(
            _conflict_manifest()["evidence"])
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0]["de_jure_ids"], ["E001"])
        self.assertEqual(conflicts[0]["de_facto_ids"], ["E002"])
        ev = _conflict_manifest()["evidence"]
        ev[1]["subject"] = "unrelated_topic"
        self.assertEqual(dialectical_arbitration.detect_dejure_defacto_conflicts(ev), [])

    def test_three_delta_axes_are_classifiable(self):
        cases = [
            ("The deployment crashed with a latency timeout and an off-by-one bug.",
             "implementation_drag"),
            ("The spread and slippage ate the edge; queue priority and hidden fees dominated.",
             "undisclosed_microstructure_friction"),
            ("The regulator never enforced the guidance; a discretionary exemption applies in practice.",
             "regulatory_enforcement_asymmetry"),
        ]
        for quote, expected in cases:
            conflict = {"subject": "x", "de_jure_quotes": [""], "de_facto_quotes": [quote]}
            self.assertEqual(dialectical_arbitration.classify_delta(
                conflict, "Neutral prose.")["axis"], expected)

    def test_averaging_across_tiers_is_a_hard_failure(self):
        fails, _, _ = dialectical_arbitration.run_b10_dialectical_arbitration(
            "On average the edge is mildly positive, pooling [E001] and [E002].",
            _conflict_manifest())
        self.assertTrue(any("B10 (Forbidden Averaging)" in f for f in fails))

    def test_pooled_estimator_is_a_hard_failure(self):
        fails, _, _ = dialectical_arbitration.run_b10_dialectical_arbitration(
            CLEAN_REPORT, _conflict_manifest(), pooled_subjects=["gamma_edge"])
        self.assertTrue(any("B10 (Forbidden Averaging)" in f for f in fails))

    def test_unreconciled_and_unclassified_deltas_fail(self):
        m = _conflict_manifest()
        m.pop("dialectics")
        fails, _, _ = dialectical_arbitration.run_b10_dialectical_arbitration(CLEAN_REPORT, m)
        self.assertTrue(any("B10 (Unreconciled" in f for f in fails))
        m2 = _conflict_manifest(dialectics=[{
            "subject": "gamma_edge", "axis": "made_up_axis", "resolution": "x"}])
        # Strip every axis marker from both quotes and the prose so the engine
        # has NO lexical basis to guess an axis -> must refuse, not invent one.
        m2["evidence"][0]["quote"] = "The model predicts a positive outcome."
        m2["evidence"][1]["quote"] = "The observed outcome differed."
        fails2, _, _ = dialectical_arbitration.run_b10_dialectical_arbitration(
            "Two records disagree [E001, E002].", m2)
        self.assertTrue(any("B10 (Unclassified" in f for f in fails2),
                        f"expected unclassified delta, got {fails2}")

    def test_classified_reconciled_conflict_caps_at_medium(self):
        fails, warns, matrix = dialectical_arbitration.run_b10_dialectical_arbitration(
            CLEAN_REPORT, _conflict_manifest())
        self.assertFalse(fails)
        self.assertEqual(matrix["confidence_cap"], "Medium")
        self.assertTrue(matrix["verification_required"])
        self.assertEqual(matrix["rows"][0]["axis"], "undisclosed_microstructure_friction")
        self.assertTrue(any("W_B10" in w for w in warns))

    def test_verified_conflict_lifts_the_cap(self):
        m = _conflict_manifest(dialectics=[{
            "subject": "gamma_edge",
            "axis": "undisclosed_microstructure_friction",
            "resolution": "Re-measured on live venue data.",
            "verification": {"status": "verified", "method": "14-day live A/B"},
        }])
        fails, _, matrix = dialectical_arbitration.run_b10_dialectical_arbitration(
            CLEAN_REPORT, m)
        self.assertFalse(fails)
        self.assertIsNone(matrix["confidence_cap"])
        self.assertFalse(matrix["verification_required"])

    def test_unverified_evidence_ids_cannot_manufacture_a_conflict(self):
        _, _, matrix = dialectical_arbitration.run_b10_dialectical_arbitration(
            CLEAN_REPORT, _conflict_manifest(), verified_evidence_ids={"E001"})
        self.assertEqual(matrix["conflicts_detected"], 0)

    def test_b10_is_reachable_through_the_fail_closed_wrapper(self):
        arb: dict = {}
        fails, warns = epistemic_guard.run_filters_fail_closed(
            CLEAN_REPORT, _conflict_manifest(), {}, arbitration_out=arb)
        self.assertFalse(any("B0" in f for f in fails))
        self.assertEqual(arb.get("confidence_cap"), "Medium")
        self.assertTrue(any("W_B10" in w for w in warns))
        direct = v9_bullshit_filters.run_b10_dialectical_filter(
            CLEAN_REPORT, _conflict_manifest())[0]
        self.assertFalse(direct)

    def test_verify_study_caps_high_confidence_on_dialectical_conflict(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp) / "study"
            src = d / "sources"
            src.mkdir(parents=True)
            quotes = [
                "Theoretical model predicts positive expectancy under frictionless execution with 1.2 bps spread.",
                "In production the spread widened and slippage ate the edge; fill rate collapsed at 4.2 bps.",
                "CBOE benchmark reports effective spread 1.2 bps across 500 sessions.",
            ]
            fillers = [
                "Appendix A of the working paper derives the estimator under a frictionless limit and states the formal assumptions. ",
                "Operator log from a live venue shows queue priority changes and a measurable latency spike during the opening auction. ",
                "Exchange statistical release tabulates session counts, closing auction volume and effective spreads by instrument class. ",
            ]
            bodies = []
            for i, q in enumerate(quotes, 1):
                body = q + " " + fillers[i - 1] * 3
                bodies.append(body)
                (src / f"S{i:03d}.txt").write_text(body, encoding="utf-8")
            # Distinct hosts: the N_eff independence clustering correctly
            # merges sources that share a hostname, which would hide a High
            # confidence verdict and make the B10 cap untestable.
            hosts = ["paper.test", "operator.test", "exchange.test"]
            rows = [{
                "id": f"S{i:03d}", "url": f"https://{hosts[i-1]}/report{i}",
                "sha256": lean_engine.sha256_text(bodies[i - 1]),
                "chars": len(bodies[i - 1]),
            } for i in (1, 2, 3)]
            (src / "index.jsonl").write_text(
                "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
            manifest = {
                "domain": "general", "verdict": "GO",
                "evidence": [
                    {"id": "E001", "source": "S001", "tier": "T1", "kind": "academic",
                     "stance": "supports", "subject": "gamma_edge",
                     "epistemic_mode": "de_jure", "quote": quotes[0]},
                    {"id": "E002", "source": "S002", "tier": "T5",
                     "kind": "practitioner_postmortem", "stance": "contradicts",
                     "subject": "gamma_edge", "epistemic_mode": "de_facto",
                     "quote": quotes[1]},
                    {"id": "E003", "source": "S003", "tier": "T1", "kind": "context",
                     "stance": "supports", "quote": quotes[2]},
                ],
                "dialectics": [{
                    "subject": "gamma_edge",
                    "axis": "undisclosed_microstructure_friction",
                    "resolution": "Re-measure with round-turn friction.",
                    "verification": {"status": "pending"},
                }],
                "kills": [
                    {"id": "K1", "verdict": "confirmed", "eids": ["E001"]},
                    {"id": "K2", "verdict": "refuted", "eids": ["E002"]},
                    {"id": "K3", "verdict": "unresolved", "eids": []},
                ],
            }
            report = (
                "# De Jure vs De Facto Arbitration\n\n"
                "Effective spread is 1.2 bps [E003].\n\n"
                "```json:manifest\n" + json.dumps(manifest) + "\n```\n\n"
                "```python:model C001\nspread_bp = 1.2\nnet_alpha_bp = 5.4\n```\n"
            )
            (d / "report.md").write_text(report, encoding="utf-8")
            from dr_engine.tools.evidence_locker import lock_evidence
            lock_evidence(d, manifest["evidence"])

            rep = lean_engine.verify_study(d)
            self.assertEqual(rep.dialectical_arbitration.get("conflicts_detected"), 1)
            self.assertEqual(rep.dialectical_arbitration.get("confidence_cap"), "Medium")
            self.assertEqual(rep.max_confidence, "Medium")
            self.assertTrue(any("W_B10_CONFIDENCE_CAP" in w for w in rep.warnings))


# ===========================================================================
# FRONTIER 4 — R17 anti-fluff IDI gate
# ===========================================================================
class TestAntiFluffGate(unittest.TestCase):
    def test_dense_verified_prose_passes(self):
        good = ("Effective spread is 1.2 bps across 500 sessions [E001]. "
                "Net alpha is 5.4 bps [E001, C001]. Total friction is 3.0 bps [E002].")
        fails, diag = density_gate.evaluate_r17_gate(
            good, idi=140.0, n_evidence=3, n_models=1, bound_units=6)
        self.assertFalse(fails)
        self.assertTrue(diag["passed"])
        self.assertGreaterEqual(diag["empirical_density_per_100w"], 3.0)

    def test_low_idi_fails_with_measured_numbers(self):
        fails, _ = density_gate.evaluate_r17_gate(
            "A short dense sentence [E001].", idi=42.0,
            n_evidence=1, n_models=0, bound_units=1)
        self.assertTrue(any("R17 (Information Density Gate)" in f for f in fails))
        self.assertTrue(any("IDI=42.0" in f for f in fails))

    def test_word_padding_destroys_empirical_density(self):
        padded = ("The microstructure of modern electronic markets is a broad and "
                  "complex subject with many interacting components. " * 120)
        fails, diag = density_gate.evaluate_r17_gate(
            padded, idi=500.0, n_evidence=1, n_models=0, bound_units=0)
        self.assertTrue(any("R17 (Empirical Entity Density)" in f for f in fails))
        self.assertLess(diag["empirical_density_per_100w"], 3.0)

    def test_hard_boilerplate_single_occurrence_fails(self):
        for phrase in ("This paves the way for future work.",
                       "We now delve into the mechanics.",
                       "It is a testament to the method.",
                       "We take a multifaceted approach."):
            fails, _ = density_gate.evaluate_r17_gate(
                "Effective spread 1.2 bps [E001]. " + phrase, idi=200.0,
                n_evidence=3, n_models=1, bound_units=5)
            self.assertTrue(any("Hard Boilerplate" in f for f in fails), phrase)

    def test_soft_boilerplate_cluster_fails_but_single_is_allowed(self):
        base = "Effective spread 1.2 bps [E001]. "
        single, _ = density_gate.evaluate_r17_gate(
            base + "In conclusion, the edge holds.", idi=200.0,
            n_evidence=3, n_models=1, bound_units=5)
        self.assertFalse(any("Boilerplate Cluster" in f for f in single))
        cluster, diag = density_gate.evaluate_r17_gate(
            base + "In conclusion, it is important to remember that overall this holds. "
                   "Needless to say, a wide range of factors plays a crucial role.",
            idi=200.0, n_evidence=3, n_models=1, bound_units=5)
        self.assertTrue(any("Boilerplate Cluster" in f for f in cluster))
        self.assertGreater(diag["boilerplate"]["soft_count"], 1)

    def test_fenced_code_is_never_prose(self):
        prose = density_gate.strip_fenced_code(
            "Real prose.\n```python\nIn conclusion: paves the way\nx = 1\n```\nMore prose.")
        self.assertNotIn("paves the way", prose)
        self.assertNotIn("x = 1", prose)
        self.assertEqual(density_gate.detect_boilerplate(
            "```python\npaves the way\n```")["hard"], [])

    def test_empirical_density_formula(self):
        self.assertEqual(density_gate.empirical_density(100, 3, 1, 6), 17.0)
        self.assertEqual(density_gate.empirical_density(1000, 3, 1, 6), 1.7)
        self.assertEqual(density_gate.DENSITY_MIN_PER_100, 3.0)
        self.assertEqual(density_gate.IDI_MIN, 100.0)

    def test_verify_study_rejects_fluff_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp) / "study"
            src = d / "sources"
            src.mkdir(parents=True)
            body = "CBOE report: effective spread 1.2 bps across 500 sessions in 2026. " * 4
            for i in (1, 2, 3):
                (src / f"S{i:03d}.txt").write_text(body, encoding="utf-8")
            rows = [{"id": f"S{i:03d}", "url": f"https://cboe.test/{i}",
                     "sha256": lean_engine.sha256_text(body), "chars": len(body)}
                    for i in (1, 2, 3)]
            (src / "index.jsonl").write_text(
                "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
            manifest = {
                "domain": "general", "verdict": "GO",
                "evidence": [{"id": f"E{i:03d}", "source": f"S{i:03d}", "tier": "T1",
                              "quote": "effective spread 1.2 bps"} for i in (1, 2, 3)],
                "kills": [{"id": f"K{i}", "verdict": "unresolved", "eids": []}
                          for i in (1, 2, 3)],
            }
            fluff = (
                "# A Broad Overview\n\n"
                "It is important to remember that this is a multifaceted approach. "
                "In conclusion, it is worth noting that the landscape is complex. "
                "Overall, a wide range of factors plays a crucial role and paves the way. "
                "Effective spread is 1.2 bps [E001]. " * 25
            )
            report = ("# A Broad Overview\n\n" + fluff + "\n\n"
                      "```json:manifest\n" + json.dumps(manifest) + "\n```\n")
            (d / "report.md").write_text(report, encoding="utf-8")
            from dr_engine.tools.evidence_locker import lock_evidence
            lock_evidence(d, manifest["evidence"])

            rep = lean_engine.verify_study(d)
            self.assertFalse(rep.passed)
            self.assertTrue(any("R17 (Anti-Fluff" in f for f in rep.failures))
            self.assertTrue(any("R17 (Information Density Gate)" in f for f in rep.failures)
                            or any("R17 (Empirical Entity Density)" in f for f in rep.failures))
            self.assertTrue(rep.boilerplate_hits)

    def test_verify_study_records_r17_diagnostics_on_a_dense_report(self):
        # Reuse the lean engine's own verified selftest study shape.
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp) / "study"
            src = d / "sources"
            src.mkdir(parents=True)
            body = "CBOE report: effective spread 1.2 bps across 500 sessions in 2026. " * 6
            for i in (1, 2, 3):
                (src / f"S{i:03d}.txt").write_text(body, encoding="utf-8")
            rows = [{"id": f"S{i:03d}", "url": f"https://cboe.test/{i}",
                     "sha256": lean_engine.sha256_text(body), "chars": len(body)}
                    for i in (1, 2, 3)]
            (src / "index.jsonl").write_text(
                "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
            manifest = {
                "domain": "general", "verdict": "GO",
                "evidence": [{"id": f"E{i:03d}", "source": f"S{i:03d}", "tier": "T1",
                              "quote": "effective spread 1.2 bps"} for i in (1, 2, 3)],
                "kills": [{"id": f"K{i}", "verdict": "unresolved", "eids": []}
                          for i in (1, 2, 3)],
            }
            report = ("# Execution Friction\n\n"
                      "Effective spread is 1.2 bps [E001, E002, E003].\n\n"
                      "```json:manifest\n" + json.dumps(manifest) + "\n```\n\n"
                      "```python:model C001\nspread_bp = 1.2\nnet_alpha_bp = 5.4\n```\n")
            (d / "report.md").write_text(report, encoding="utf-8")
            from dr_engine.tools.evidence_locker import lock_evidence
            lock_evidence(d, manifest["evidence"])

            rep = lean_engine.verify_study(d)
            self.assertGreater(rep.empirical_density_per_100w, 0.0)
            self.assertFalse(any("R17" in f for f in rep.failures),
                             f"dense report should pass R17: {rep.failures}")
            self.assertTrue(any("W_R17" in w for w in rep.warnings))


if __name__ == "__main__":
    unittest.main()
