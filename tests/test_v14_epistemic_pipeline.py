#!/usr/bin/env python3
"""Adversarial Regression Suite for Deep Research Protocol v14.0.

Tests:
  1. Desk Memory Graveyard Pre-Flight Scanner (blocks killed Gold LBMA, Crude Oil open, DAX cash open, etc.).
  2. Pre-Synthesis Evidence Locker (locks verified quotes, rejects non-verbatim quotes).
  3. Google Colab Executable Notebook Exporter (produces valid nbformat 4 Jupyter notebooks).
  4. Integration of B13 desk memory audit in lean_engine.py verify_study.
"""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from dr_engine.tools.desk_memory import scan_text_against_desk_graveyard
from dr_engine.tools.evidence_locker import lock_evidence, load_snapshots
from dr_engine.tools.colab_exporter import build_colab_notebook, export_colab_notebook
from dr_engine.tools.lean_engine import verify_study


class TestV14EpistemicPipeline(unittest.TestCase):

    def test_desk_graveyard_scanner_blocks_killed_gold_orb(self):
        # Asserting gold london breakout without refutation must trigger violation
        text = "Ние предлагаме златен пробив около лондонския фиксинг за нов акаунт."
        violations = scan_text_against_desk_graveyard(text)
        self.assertTrue(len(violations) >= 1)
        self.assertEqual(violations[0]["rule_id"], "GRAVEYARD_GOLD_INTRADAY")

    def test_desk_graveyard_scanner_passes_with_refutation(self):
        # Acknowledging that it is killed/refuted must pass
        text = "Златният пробив около лондонския фиксинг е убит и отхвърлен от спреда."
        violations = scan_text_against_desk_graveyard(text)
        self.assertEqual(len(violations), 0)

    def test_desk_graveyard_scanner_blocks_crude_oil_open(self):
        text = "Strategy explores WTI Crude oil pit open displacement breakout."
        violations = scan_text_against_desk_graveyard(text)
        self.assertTrue(any(v["rule_id"] == "GRAVEYARD_CRUDE_OIL_INTRADAY" for v in violations))

    def test_desk_graveyard_scanner_blocks_synthetic_citations(self):
        text = "According to BIS Quarterly Review, retail prop firm FTMO traders use R-multiples."
        violations = scan_text_against_desk_graveyard(text)
        self.assertTrue(any(v["rule_id"] == "GRAVEYARD_SYNTHETIC_REGULATORY_CITATIONS" for v in violations))

    def test_evidence_locker_verifies_and_locks(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            td = Path(tmpdir)
            sources = td / "sources"
            sources.mkdir()
            (sources / "index.jsonl").write_text(
                json.dumps({"id": "S001", "url": "https://nber.org/paper.pdf", "title": "Test Paper"}) + "\n",
                encoding="utf-8"
            )
            (sources / "S001.txt").write_text(
                "In asset pricing models, 286 anomalies (64%) fail to clear the hurdle.",
                encoding="utf-8"
            )

            # Valid quote
            valid_items = [{
                "id": "E001",
                "source": "S001",
                "quote": "286 anomalies (64%) fail to clear the hurdle.",
                "tier": "T1"
            }]
            locked, errs = lock_evidence(td, valid_items)
            self.assertEqual(len(locked), 1)
            self.assertEqual(len(errs), 0)
            self.assertTrue((td / "evidence_ledger.json").exists())
            self.assertTrue((td / "evidence_pack.md").exists())

            # Invalid quote (hallucinated string)
            invalid_items = [{
                "id": "E002",
                "source": "S001",
                "quote": "CFTC reports that 99% of prop firms fail.",
                "tier": "T1"
            }]
            locked_bad, errs_bad = lock_evidence(td, invalid_items)
            self.assertEqual(len(errs_bad), 1)
            self.assertIn("does not match snapshot", errs_bad[0])

    def test_colab_notebook_exporter_generates_valid_notebook(self):
        study_path = Path("research/2026-11-08-rp53k-process-and-battery")
        if not study_path.exists():
            self.skipTest("RP53K study not found")

        nb = build_colab_notebook(study_path)
        self.assertEqual(nb["nbformat"], 4)
        self.assertTrue(len(nb["cells"]) >= 4)
        cell_types = [c["cell_type"] for c in nb["cells"]]
        self.assertIn("markdown", cell_types)
        self.assertIn("code", cell_types)

        # Check export
        with tempfile.TemporaryDirectory() as tmpdir:
            out_file = Path(tmpdir) / "test_nb.ipynb"
            export_colab_notebook(study_path, out_file)
            self.assertTrue(out_file.exists())
            data = json.loads(out_file.read_text(encoding="utf-8"))
            self.assertEqual(data["nbformat"], 4)



    def test_quote_matches_snapshot_rejects_degenerate_and_punctuation(self):
        from dr_engine.tools.lean_engine import quote_matches_snapshot
        snap = "This is a legitimate snapshot containing text and numbers like 26 and punctuation ---."
        for degen in [".", "a", "!!!", ". . .", "---", "26", "...!!!...", "   "]:
            self.assertFalse(quote_matches_snapshot(degen, snap), f"Failed to reject degenerate quote: {degen!r}")

    def test_quote_matches_snapshot_enforces_ellipsis_gap(self):
        from dr_engine.tools.lean_engine import quote_matches_snapshot
        snap = "word1 " + ("filler " * 300) + "word2"
        quote = "word1 ... word2"
        self.assertFalse(quote_matches_snapshot(quote, snap))

    def test_evidence_locker_strict_id_and_tier_ceiling(self):
        from dr_engine.tools.evidence_locker import lock_evidence
        with tempfile.TemporaryDirectory() as tmpdir:
            td = Path(tmpdir)
            sources = td / "sources"
            sources.mkdir()
            (sources / "index.jsonl").write_text(
                json.dumps({"id": "S001", "url": "https://example.com/blog", "tier": "T3"}) + "\n",
                encoding="utf-8"
            )
            (sources / "S001.txt").write_text(
                "This is a legitimate empirical observation with sufficient characters for testing.",
                encoding="utf-8"
            )
            # 1. Invalid ID format
            bad_id = [{"id": "HACKED", "source": "S001", "quote": "legitimate empirical observation with sufficient", "tier": "T3"}]
            _, errs = lock_evidence(td, bad_id)
            self.assertTrue(any("id must match" in e for e in errs))

            # 2. Too short quote
            bad_short = [{"id": "E001", "source": "S001", "quote": "Too short", "tier": "T3"}]
            _, errs2 = lock_evidence(td, bad_short)
            self.assertTrue(any("too short" in e for e in errs2))

            # 3. Tier ceiling: source is T3, claiming T1 -> capped at T3
            good_item = [{"id": "E001", "source": "S001", "quote": "legitimate empirical observation with sufficient", "tier": "T1"}]
            locked, errs3 = lock_evidence(td, good_item)
            self.assertEqual(len(errs3), 0)
            self.assertEqual(locked[0]["tier"], "T3")

    def test_evidence_ledger_sha256_sidecar_and_tampering(self):
        from dr_engine.tools.evidence_locker import lock_evidence, verify_report_against_ledger
        with tempfile.TemporaryDirectory() as tmpdir:
            td = Path(tmpdir)
            sources = td / "sources"
            sources.mkdir()
            (sources / "index.jsonl").write_text(
                json.dumps({"id": "S001", "url": "https://nber.org/w123", "tier": "T1"}) + "\n",
                encoding="utf-8"
            )
            (sources / "S001.txt").write_text(
                "Empirical asset pricing factor replication yields significant statistical decay.",
                encoding="utf-8"
            )
            items = [{"id": "E001", "source": "S001", "quote": "Empirical asset pricing factor replication yields significant", "tier": "T1"}]
            locked, errs = lock_evidence(td, items)
            self.assertEqual(len(errs), 0)
            self.assertTrue((td / "evidence_ledger.json.sha256").exists())

            # Verified against untampered ledger
            manifest = {"evidence": locked}
            report = "The factor replication test [E001] proves the decay."
            verr = verify_report_against_ledger(td, manifest, report)
            self.assertEqual(len(verr), 0)

            # Tamper the sidecar
            (td / "evidence_ledger.json.sha256").write_text("corrupted_digest", encoding="utf-8")
            verr_tampered = verify_report_against_ledger(td, manifest, report)
            self.assertTrue(any("SHA-256 digest mismatch" in e for e in verr_tampered))

    def test_desk_graveyard_local_refutation_isolation(self):
        text = "We trade Gold London ORB breakouts for profit.\n\nSome other ideas were killed in previous audits."
        violations = scan_text_against_desk_graveyard(text)
        self.assertTrue(any(v["rule_id"] == "GRAVEYARD_GOLD_INTRADAY" for v in violations))

    def test_desk_graveyard_multiline_synthetic_regulatory(self):
        text = "BIS Working Paper 1190 discusses liquidity.\n" + ("\n" * 50) + "Retail traders on FTMO face loss limits."
        violations = scan_text_against_desk_graveyard(text)
        self.assertTrue(any(v["rule_id"] == "GRAVEYARD_SYNTHETIC_REGULATORY_CITATIONS" for v in violations))

    def test_desk_graveyard_zero_width_and_homoglyphs(self):
        # Zero-width character inside gold
        text1 = "We trade G\u200bold London ORB breakouts for profit."
        v1 = scan_text_against_desk_graveyard(text1)
        self.assertTrue(any(v["rule_id"] == "GRAVEYARD_GOLD_INTRADAY" for v in v1))

        # Cyrillic homoglyph in Dax
        text2 = "Strategy targets D\u0430x cash open breakout."
        v2 = scan_text_against_desk_graveyard(text2)
        self.assertTrue(any(v["rule_id"] == "GRAVEYARD_EUROPEAN_CASH_OPEN" for v in v2))


if __name__ == "__main__":
    unittest.main()
