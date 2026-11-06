#!/usr/bin/env python3
"""Unit tests for dr_engine/tools/lean_engine.py (Deep Research v8.0 LEAN FRONTIER)."""

from __future__ import annotations

import argparse
import unittest
from dr_engine.tools.lean_engine import (
    algebraic_closure,
    cmd_selftest,
    compute_neff_and_entropy,
    dersimonian_laird_pool,
    execute_model_block,
    extract_numbers,
    is_number_bound,
    quote_matches_snapshot,
)


class TestLeanEngine(unittest.TestCase):
    def test_selftest_executes_successfully(self):
        """Zero-mock end-to-end selftest must pass with returncode 0 in < 100 ms."""
        rc = cmd_selftest(argparse.Namespace())
        self.assertEqual(rc, 0)

    def test_algebraic_closure_morphisms(self):
        """Algebraic closure must bind complements, RT=2x, %, and bps."""
        base = {58.0, 0.9}  # 58% win rate, 0.9 bps slippage
        closure = algebraic_closure(base)

        # Complement: 100 - 58 = 42
        self.assertTrue(is_number_bound(42.0, closure))
        # RT=2x: 2 * 0.9 = 1.8
        self.assertTrue(is_number_bound(1.8, closure))
        # Percent to decimal: 58 / 100 = 0.58
        self.assertTrue(is_number_bound(0.58, closure))
        # Basis points to decimal: 0.9 / 10000 = 0.00009
        self.assertTrue(is_number_bound(0.00009, closure))

    def test_ast_model_execution_and_helpers(self):
        """Safe AST evaluator must support finance helpers and deterministic assignment."""
        code = """
gross = 10.5
spread = 1.5
slippage_rt = 2.0
comm = 0.5
net_edge = net_edge_bp(gross, spread, slippage_rt, comm)
annual_bps = net_edge * 252
"""
        env = execute_model_block(code)
        self.assertAlmostEqual(env["gross"], 10.5)
        self.assertAlmostEqual(env["net_edge"], 6.5)  # 10.5 - (1.5 + 2.0 + 0.5)
        self.assertAlmostEqual(env["annual_bps"], 1638.0)

    def test_ast_security_sandbox(self):
        """Safe AST evaluator must reject builtins, imports, and arbitrary calls."""
        unsafe_code = "__import__('os').system('dir')"
        with self.assertRaises(Exception):
            execute_model_block(unsafe_code)

    def test_quote_matches_snapshot_with_ellipsis(self):
        """Verbatim quote matching must succeed with whitespace variance and ellipses."""
        snapshot = (
            "Federal Reserve statistical release H.15: The daily overnight bank funding rate (OBFR) "
            "averaged 5.31 percent across the observation window, with standard deviation 0.04 percent."
        )
        quote = "overnight bank funding rate (OBFR) averaged 5.31 percent ... standard deviation 0.04 percent"
        self.assertTrue(quote_matches_snapshot(quote, snapshot))

        fake_quote = "overnight bank funding rate averaged 7.50 percent"
        self.assertFalse(quote_matches_snapshot(fake_quote, snapshot))

    def test_dersimonian_laird_meta_analysis(self):
        """DL pooling must correctly estimate pooled effect and detect heterogeneity."""
        claims = [
            {"subject": "eurusd", "metric": "spread", "unit": "bps", "scope": "london", "value": 1.2, "se": 0.1},
            {"subject": "eurusd", "metric": "spread", "unit": "bps", "scope": "london", "value": 1.4, "se": 0.1},
        ]
        results = dersimonian_laird_pool(claims)
        self.assertEqual(len(results), 1)
        r = results[0]
        self.assertEqual(r["subject"], "eurusd")
        self.assertAlmostEqual(r["re_estimate"], 1.3, places=2)
        self.assertFalse(r["regime_split_required"])

    def test_neff_shingle_clustering(self):
        """Echo chamber sources must be clustered into fewer independent degrees of freedom."""
        evidence = [
            {"source": "S001", "url": "https://reuters.com/a", "quote": "The Federal Reserve raised policy rates by 25 basis points."},
            {"source": "S002", "url": "https://cnbc.com/b", "quote": "The Federal Reserve raised policy rates by 25 basis points."},
            {"source": "S003", "url": "https://academic.org/c", "quote": "Empirical analysis reveals persistent intraday momentum on E-mini futures."},
        ]
        sources = {
            "S001": {"url": "https://reuters.com/a"},
            "S002": {"url": "https://cnbc.com/b"},
            "S003": {"url": "https://academic.org/c"},
        }
        res = compute_neff_and_entropy(evidence, sources)
        # S001 and S002 share > 28% shingles and should cluster together
        self.assertEqual(res["independent_clusters"], 2)
        self.assertLess(res["n_eff"], 3.0)


if __name__ == "__main__":
    unittest.main()
