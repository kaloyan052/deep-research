#!/usr/bin/env python3
"""Unit tests for dr_engine/tools/v9_bullshit_filters.py (Deep Research v9.0)."""

from __future__ import annotations

import unittest
from dr_engine.tools.v9_bullshit_filters import (
    extract_fenced_python_code,
    run_v9_bullshit_filters,
    verify_runnable_code_blocks,
)


class TestV9BullshitFilters(unittest.TestCase):
    def test_b1_fake_ev_is_rejected(self):
        """Subjective scenario weights (Base 50%, Bear 35%) without empirical sample size must FAIL."""
        report = "We estimate an Expected Value using Base 50% / Bear 35% / Stress 15%."
        manifest = {"domain": "quant", "verdict": "GO"}
        fails, _ = run_v9_bullshit_filters(report, manifest, {})
        self.assertTrue(any("B1 (No Fake EV)" in f for f in fails))

    def test_b1_saas_requires_unit_breakeven_variables(self):
        """SaaS models must compute required_clients_breakeven and monthly_churn_replacements."""
        report = "Valid SaaS analysis."
        manifest = {
            "domain": "saas",
            "verdict": "CONDITIONAL_GO",
            "architecture_mode": "preflight_validator",
            "chatgpt_falsification": {
                "mechanism": "statutory_xsd_ast_validator",
                "why_raw_llm_fails": "ChatGPT cannot validate large XML files against strict official government XSD schemas.",
            },
            "demand_test_14d": {"protocol": "Landing page card pre-orders", "pass_threshold_count": 5},
        }
        # Missing model_env vars
        fails, _ = run_v9_bullshit_filters(report, manifest, {})
        self.assertTrue(any("B1 (Unit Breakeven)" in f for f in fails))

        # With model_env vars -> passes B1
        env = {"required_clients_breakeven": 345.0, "monthly_churn_replacements": 17.2}
        fails_ok, _ = run_v9_bullshit_filters(report, manifest, env)
        self.assertFalse(any("B1" in f for f in fails_ok))

    def test_b2_zero_liability_solo_physics(self):
        """Mutating 2-way real-time write-syncs must fail for solo founders."""
        report = "We will deploy a two-way real-time sync across multi-channel stores."
        manifest = {
            "domain": "saas",
            "verdict": "GO",
            "architecture_mode": "mutating_write_sync",
        }
        fails, _ = run_v9_bullshit_filters(report, manifest, {})
        self.assertTrue(any("B2 (Operational Physics)" in f for f in fails))

    def test_b3_quant_friction_and_anti_decay(self):
        """Quant models must be modern (>=2023) and survive Jacobian friction tipping point (<=3.0% of 1R)."""
        report = "Quant analysis with 5% friction."
        manifest = {
            "domain": "quant",
            "verdict": "GO",
            "counterparty_physics": {
                "forced_actor": "Options dealers delta-hedging",
                "sample_end_year": 2020,  # Old sample!
                "gross_edge_bp": 10.0,
                "friction_cost_bp": 5.0,
            },
        }
        env = {"friction_share_of_1r": 0.05}  # 5% > 3% tipping point!
        fails, _ = run_v9_bullshit_filters(report, manifest, env)
        self.assertTrue(any("B3 (Anti-Textbook Decay)" in f for f in fails))
        self.assertTrue(any("B3 (Jacobian Friction Gate)" in f for f in fails))

    def test_b3_code_verification_catches_stubs(self):
        """Runnable Python code blocks must not have empty pass or ellipsis stubs."""
        stub_code = """
class BadEngine:
    def execute(self):
        pass
"""
        errs = verify_runnable_code_blocks([stub_code], min_loc=5)
        self.assertTrue(any("empty `pass` stub" in e for e in errs))

    def test_b4_chatgpt_falsification_test(self):
        """SaaS products must prove structural defense against standard LLM prompt wrappers."""
        report = "Simple SaaS tool."
        manifest = {
            "domain": "product",
            "verdict": "CONDITIONAL_GO",
            "architecture_mode": "read_only_diff",
            "chatgpt_falsification": {
                "mechanism": "invalid_mechanism",
                "why_raw_llm_fails": "Too short",
            },
            "demand_test_14d": {"protocol": "Pre-orders", "pass_threshold_count": 3},
        }
        env = {"required_clients_breakeven": 100.0, "monthly_churn_replacements": 5.0}
        fails, _ = run_v9_bullshit_filters(report, manifest, env)
        self.assertTrue(any("B4 (ChatGPT Falsification)" in f for f in fails))

    def test_b5_wtp_vs_complaint_separation(self):
        """Complaints cannot be declared as proof of willingness to pay a newcomer."""
        report = "Customer complaint analysis."
        manifest = {
            "domain": "product",
            "verdict": "CONDITIONAL_GO",
            "architecture_mode": "preflight_validator",
            "chatgpt_falsification": {
                "mechanism": "in_browser_wasm_large_file",
                "why_raw_llm_fails": "Cannot process 100MB files in browser memory without server data custody.",
            },
            "demand_test_14d": {"protocol": "Card pre-order", "pass_threshold_count": 5},
            "evidence": [
                {
                    "id": "E001",
                    "kind": "review_pain",
                    "proves": "willingness_to_pay_new_entrant",  # ILLEGAL!
                    "quote": "App deleted inventory.",
                }
            ],
        }
        env = {"required_clients_breakeven": 100.0, "monthly_churn_replacements": 5.0}
        fails, _ = run_v9_bullshit_filters(report, manifest, env)
        self.assertTrue(any("B5 (WTP Conflation)" in f for f in fails))

    def test_b6_biotech_clinical_physics(self):
        """Biotech models must reject preclinical translation traps and require shrunk effect size."""
        report = "Murine model demonstrated 80% tumor shrinkage in mice cohort."
        manifest = {
            "domain": "biotech",
            "verdict": "GO",
            "clinical_physics": {
                "endpoint_type": "biomarker_surrogate",  # Not in allowed
                "trial_phase": 0,
            },
        }
        fails, _ = run_v9_bullshit_filters(report, manifest, {})
        self.assertTrue(any("B6 (Endpoint Rigor)" in f for f in fails))
        self.assertTrue(any("B6 (Preclinical Translation Trap)" in f for f in fails))
        self.assertTrue(any("B6 (Clinical Power & Attrition)" in f for f in fails))

    def test_b7_legal_tax_normative_hierarchy(self):
        """Legal and tax models must declare authority tier and prohibit unmapped jurisdiction conflation."""
        report = "Using Section 1256 combined with Bulgarian ЗДДФЛ."
        manifest = {
            "domain": "tax",
            "verdict": "GO",
            "normative_physics": {
                "jurisdiction": "BG",
                "primary_statute": "ЗДДФЛ",
                "authority_tier": "administrative_guidance",
            },
        }
        fails, _ = run_v9_bullshit_filters(report, manifest, {})
        self.assertTrue(any("B7 (Sub-Statutory Guidance Trap)" in f for f in fails))
        self.assertTrue(any("B7 (Jurisdiction Conflation)" in f for f in fails))
        self.assertTrue(any("B7 (Tax Friction Math)" in f for f in fails))

    def test_b8_deeptech_thermodynamic_and_bom_physics(self):
        """DeepTech models must enforce thermodynamic headroom <= 0.95 and mandatory BOM economics."""
        report = "Novel thermal cycle."
        manifest = {
            "domain": "deeptech",
            "verdict": "GO",
            "physical_limits": {"limit_name": "carnot_efficiency"},
        }
        env = {
            "thermodynamic_headroom_ratio": 0.98,  # > 0.95 violation!
            "bom_unit_cost_usd": 250.0,
            "first_pass_yield_pct": 75.0,
        }
        fails, _ = run_v9_bullshit_filters(report, manifest, env)
        self.assertTrue(any("B8 (Thermodynamic Violation)" in f for f in fails))

    def test_b9_temporal_recency_and_sota_grounding(self):
        """Claims of 'best model' or SOTA must cite measured Tier 2 benchmarks and cannot cite deprecated dinosaurs."""
        # 1. Uncalibrated SOTA claim without Tier 2 measured benchmark -> FAILS
        bad_sota_report = "Това е най-добрият AI модел за анализ."
        bad_manifest = {"domain": "ai", "verdict": "GO", "evidence": []}
        fails, _ = run_v9_bullshit_filters(bad_sota_report, bad_manifest, {})
        self.assertTrue(any("B9 (Uncalibrated SOTA Claim)" in f for f in fails))

        # 2. Deprecated model (BloombergGPT) cited without obsolescence disclaimer -> FAILS
        dinosaur_report = "Използваме BloombergGPT като водещ финансов модел."
        fails_dino, _ = run_v9_bullshit_filters(dinosaur_report, bad_manifest, {})
        self.assertTrue(any("B9 (Deprecated Dinosaur SOTA Trap)" in f for f in fails_dino))

        # 3. Valid report with Artificial Analysis benchmark cite and obsolescence disclaimer -> PASSES
        good_report = (
            "Най-добрият AI модел за финанси е Gemini 4 Carbon с резултат 63 [E001]. "
            "BloombergGPT е остарял динозавър от 2023 г."
        )
        good_manifest = {
            "domain": "ai",
            "verdict": "GO",
            "evidence": [
                {
                    "id": "E001",
                    "source": "S001",
                    "quote": "Rank 1: Gemini 4 Carbon (high) - Overall Score: 63 on Artificial Analysis Index",
                }
            ],
        }
        fails_good, _ = run_v9_bullshit_filters(good_report, good_manifest, {})
        self.assertFalse(any("B9" in f for f in fails_good))


if __name__ == "__main__":
    unittest.main()
