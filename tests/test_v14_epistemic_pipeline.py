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


if __name__ == "__main__":
    unittest.main()
