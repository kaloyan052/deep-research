#!/usr/bin/env python3
"""Deep Research Engine v14.1 — Notebook Execution Regression Tests."""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from dr_engine.tools.notebook_verifier import verify_notebook


class TestNotebookExecution(unittest.TestCase):
    def test_reference_notebook_runs_headless(self):
        p = Path("reports/RP53K_RESEARCH_NOTEBOOK.ipynb")
        if not p.exists():
            p = Path("research/2026-11-08-rp53k-process-and-battery/research_notebook.ipynb")
        if not p.exists():
            self.skipTest("reference notebook absent")
        try:
            r = verify_notebook(p, timeout=300)
        except ImportError:
            self.skipTest("nbformat/nbclient not installed")
        self.assertTrue(r.get("passed"), r.get("cell_errors") or r.get("error"))
        self.assertGreaterEqual(r.get("nbformat_minor", 0), 5)


if __name__ == "__main__":
    unittest.main()
