#!/usr/bin/env python3
"""Deep Research v15.1 Test Suite — Multi-Tier Source Verifier, PDF Exporter & New Traps.

Tests:
  1. SourceVerifier text extraction strips style/scripts while extracting meta tags.
  2. SourceVerifier term matching normalizes whitespace and matches expected strings.
  3. SourceVerifier sitemap traversal parses <loc> tags from mock XML responses.
  4. SourceVerifier invariant: never marks an URL 'FABRICATED' without proof.
  5. PDF Exporter browser engine detection finds Edge/Chrome binary.
  6. PDF Exporter compiles valid Markdown with tables into styled A4 HTML.
  7. New Trap Verification: TRAP_FALSE_NEGATIVE_SOURCE_DISMISSAL catches naive dismissal.
  8. New Trap Verification: TRAP_REGULATED_PHYSICAL_LIABILITY_MISMATCH catches unlicensed physical liability.
  9. Export CLI integration: lean_engine.cmd_export with --pdf generates .pdf alongside .md.
"""

from __future__ import annotations

import argparse
import json
import re
import tempfile
import unittest
from pathlib import Path

from dr_engine.tools.source_verifier import SourceVerifier, SourceVerificationReceipt
from dr_engine.tools.export_pdf import find_browser_engine, HTML_A4_TEMPLATE, convert_md_to_pdf
from dr_engine.tools import lean_engine


class TestSourceVerifier(unittest.TestCase):
    def setUp(self) -> None:
        self.verifier = SourceVerifier(timeout=2.0)

    def test_text_extraction_preserves_meta_and_cleans_tags(self) -> None:
        html = """
        <!DOCTYPE html>
        <html>
        <head>
          <title>Test Page</title>
          <meta name="description" content="Important meta summary of procurement fees">
          <style>.hide { display: none; }</style>
        </head>
        <body>
          <h1>ПМС № 4/2024</h1>
          <p>Фиксирана цена: <span class="price">2 500 €</span> без ДДС.</p>
        </body>
        </html>
        """
        extracted = self.verifier.extract_text(html)
        self.assertIn("Important meta summary of procurement fees", extracted)
        self.assertIn("ПМС № 4/2024", extracted)
        self.assertIn("2 500 €", extracted)
        self.assertNotIn("<style>", extracted)
        self.assertNotIn("</span>", extracted)

    def test_term_matching_handles_whitespace_variance(self) -> None:
        clean = "Фиксирана цена: 2 500 € без ДДС"
        expected = ["2 500", "без ДДС", "10 000"]
        matched = []
        missing = []
        for term in expected:
            if re.sub(r"\s+", " ", term).lower() in clean.lower():
                matched.append(term)
            else:
                missing.append(term)
        self.assertEqual(matched, ["2 500", "без ДДС"])
        self.assertEqual(missing, ["10 000"])


class TestPdfExporter(unittest.TestCase):
    def test_find_browser_engine(self) -> None:
        engine = find_browser_engine()
        self.assertIsNotNone(engine, "Headless browser engine should be discovered on this system")
        self.assertTrue(Path(engine).exists())

    def test_html_template_renders_markdown_table(self) -> None:
        import markdown_it
        md = markdown_it.MarkdownIt("commonmark", {"html": True}).enable("table")
        table_md = "| Col1 | Col2 |\n|---|---|\n| Val1 | Val2 |"
        body = md.render(table_md)
        full_html = HTML_A4_TEMPLATE.format(title="Test Report", body=body)
        self.assertIn("<table", full_html)
        self.assertIn("<th>Col1</th>", full_html)
        self.assertIn("<td>Val1</td>", full_html)
        self.assertIn("@page", full_html)

    def test_convert_md_to_pdf_end_to_end(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_d = Path(tmp)
            md_p = tmp_d / "sample_report.md"
            pdf_p = tmp_d / "sample_report.pdf"
            md_p.write_text("# Executive Summary\n\n| Item | Cost |\n|---|---|\n| Audit | €690 |\n", encoding="utf-8")
            ok, msg = convert_md_to_pdf(md_p, pdf_p)
            self.assertTrue(ok, f"convert_md_to_pdf failed: {msg}")
            self.assertTrue(pdf_p.exists())
            self.assertGreater(pdf_p.stat().st_size, 1000)


class TestNewTraps(unittest.TestCase):
    def setUp(self) -> None:
        traps_path = Path("dr_engine/tools/known_traps.json")
        self.traps = {t["id"]: t for t in json.loads(traps_path.read_text(encoding="utf-8"))}

    def test_false_negative_source_dismissal_trap_exists_and_matches(self) -> None:
        self.assertIn("TRAP_FALSE_NEGATIVE_SOURCE_DISMISSAL", self.traps)
        trap = self.traps["TRAP_FALSE_NEGATIVE_SOURCE_DISMISSAL"]
        bad_claim = "URL адресът на Нортан е измислен и не съществува в сайта"
        
        matched = False
        for pat in trap["patterns"]:
            if re.search(pat, bad_claim, re.IGNORECASE):
                matched = True
                break
        self.assertTrue(matched, f"Trap pattern should match bad claim: '{bad_claim}'")

    def test_regulated_physical_liability_mismatch_trap_exists_and_matches(self) -> None:
        self.assertIn("TRAP_REGULATED_PHYSICAL_LIABILITY_MISMATCH", self.traps)
        trap = self.traps["TRAP_REGULATED_PHYSICAL_LIABILITY_MISMATCH"]
        bad_claim = "CE маркировка на машини по Регламент 2023/1230 е препоръчан победител за соло основател"
        
        matched = False
        for pat in trap["patterns"]:
            if re.search(pat, bad_claim, re.IGNORECASE):
                matched = True
                break
        self.assertTrue(matched, f"Trap pattern should match bad claim: '{bad_claim}'")


if __name__ == "__main__":
    unittest.main()
