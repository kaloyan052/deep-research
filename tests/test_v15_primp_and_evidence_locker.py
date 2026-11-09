#!/usr/bin/env python3
"""Deep Research v15.0 Test Suite — Tier-0 Primp Transport & Grounded Quote Extraction.

Tests:
  1. Primp TLS browser impersonation client construction and version fallback (chrome_131 -> chrome_146).
  2. Direct localhost loopback fetch via primp (status, headers, text, sha256, via='direct:primp').
  3. Primp max_bytes truncation and gzip decompression handling.
  4. Primp bot wall detection (HTTP 403 and Cloudflare interstitial challenge).
  5. Graceful fallback from primp to urllib.request and reader/mirrors when primp encounters network failure.
  6. DR_DISABLE_PRIMP environment variable toggle.
  7. High-precision sentence segmentation (split_grounded_sentences) protecting decimals, legal citations, and abbreviations.
  8. Grounded character-span candidate extraction (extract_candidate_quotes) with exact source text alignment.
  9. LangExtract CharInterval integration and tier laundering prevention.
 10. End-to-end evidence locking from extracted candidate spans with 0 verification errors.
"""

from __future__ import annotations

import gzip
import http.server
import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

try:
    import primp
except ImportError:
    primp = None

try:
    import langextract as lx
except ImportError:
    lx = None

from dr_engine.tools.http_resilience import (
    FetchResult,
    _fetch_with_primp,
    _get_primp_client,
    fetch_with_primp,
    is_primp_available,
    resilient_fetch,
)
from dr_engine.tools.evidence_locker import (
    CharInterval,
    extract_candidate_quotes,
    load_snapshots,
    lock_evidence,
    split_grounded_sentences,
)


class TestPrimpTransport(unittest.TestCase):
    """Test Tier-0 native TLS impersonation via primp."""

    def test_primp_availability(self):
        if primp is None:
            self.skipTest("primp is not installed")
        self.assertTrue(is_primp_available())

    def test_primp_client_builder_and_fallback(self):
        if primp is None:
            self.skipTest("primp is not installed")
        # Direct modern profile
        client1 = _get_primp_client("chrome_146")
        self.assertIsNotNone(client1)

        # Fallback profile when an unmapped version like chrome_131 is requested
        client2 = _get_primp_client("chrome_131")
        self.assertIsNotNone(client2)

        # Default client
        client3 = _get_primp_client(None)
        self.assertIsNotNone(client3)

    def test_primp_fetch_live_loopback(self):
        if primp is None:
            self.skipTest("primp is not installed")

        response_body = b"<!DOCTYPE html><html><body>Modern Tier-0 TLS Impersonation Test Body with ample chars.</body></html>"
        
        class LoopbackHandler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("X-Custom-Server", "PrimpLoopback/1.0")
                self.end_headers()
                self.wfile.write(response_body)

            def log_message(self, *args):
                pass

        server = http.server.HTTPServer(("127.0.0.1", 0), LoopbackHandler)
        port = server.server_port
        t = threading.Thread(target=server.handle_request, daemon=True)
        t.start()

        url = f"http://127.0.0.1:{port}/test-page"
        try:
            res = fetch_with_primp(url, timeout=5.0, allow_private=True)
            self.assertTrue(res.ok)
            self.assertEqual(res.status, 200)
            self.assertEqual(res.via, "direct:primp")
            self.assertEqual(res.evidence_class, "primary_fetched")
            self.assertIn("Modern Tier-0 TLS Impersonation Test Body", res.text)
            self.assertEqual(len(res.sha256), 64)
            self.assertFalse(res.bot_wall)
        finally:
            server.server_close()

    def test_primp_custom_headers_propagation(self):
        if primp is None:
            self.skipTest("primp is not installed")

        received_headers: dict[str, str] = {}

        class HeaderHandler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                for k in ("x-test-token", "accept"):
                    received_headers[k] = self.headers.get(k, "")
                self.send_response(200)
                self.send_header("Content-Type", "text/plain")
                self.end_headers()
                self.wfile.write(b"Headers received with sufficient character length to pass min_chars.")

            def log_message(self, *args):
                pass

        server = http.server.HTTPServer(("127.0.0.1", 0), HeaderHandler)
        port = server.server_port
        t = threading.Thread(target=server.handle_request, daemon=True)
        t.start()

        url = f"http://127.0.0.1:{port}/headers"
        try:
            custom_headers = {"X-Test-Token": "SecretAuth987"}
            res = fetch_with_primp(url, timeout=5.0, headers=custom_headers, allow_private=True)
            self.assertTrue(res.ok)
            self.assertEqual(received_headers.get("x-test-token"), "SecretAuth987")
        finally:
            server.server_close()

    def test_primp_max_bytes_truncation(self):
        if primp is None:
            self.skipTest("primp is not installed")

        class LongHandler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-Type", "text/plain")
                self.end_headers()
                self.wfile.write(b"X" * 5000)

            def log_message(self, *args):
                pass

        server = http.server.HTTPServer(("127.0.0.1", 0), LongHandler)
        port = server.server_port
        t = threading.Thread(target=server.handle_request, daemon=True)
        t.start()

        url = f"http://127.0.0.1:{port}/long"
        try:
            res = fetch_with_primp(url, timeout=5.0, max_bytes=2000, allow_private=True)
            self.assertTrue(res.ok)
            self.assertTrue(res.truncated)
            self.assertEqual(len(res.text), 2000)
        finally:
            server.server_close()

    def test_primp_gzip_decompression(self):
        if primp is None:
            self.skipTest("primp is not installed")

        payload = b"Compressed payload via primp that contains valid text characters." * 3

        class GzipHandler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                compressed = gzip.compress(payload)
                self.send_response(200)
                self.send_header("Content-Type", "text/plain")
                self.send_header("Content-Encoding", "gzip")
                self.end_headers()
                self.wfile.write(compressed)

            def log_message(self, *args):
                pass

        server = http.server.HTTPServer(("127.0.0.1", 0), GzipHandler)
        port = server.server_port
        t = threading.Thread(target=server.handle_request, daemon=True)
        t.start()

        url = f"http://127.0.0.1:{port}/gzip"
        try:
            res = fetch_with_primp(url, timeout=5.0, allow_private=True)
            self.assertTrue(res.ok)
            self.assertIn("Compressed payload via primp", res.text)
        finally:
            server.server_close()

    def test_primp_bot_wall_detection(self):
        if primp is None:
            self.skipTest("primp is not installed")

        class WallHandler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(403)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(b"<html><body>Attention Required! Cloudflare DDOS Protection.</body></html>")

            def log_message(self, *args):
                pass

        server = http.server.HTTPServer(("127.0.0.1", 0), WallHandler)
        port = server.server_port
        t = threading.Thread(target=server.handle_request, daemon=True)
        t.start()

        url = f"http://127.0.0.1:{port}/botwall"
        try:
            res = fetch_with_primp(url, timeout=5.0, allow_private=True)
            self.assertFalse(res.ok)
            self.assertTrue(res.bot_wall)
            self.assertEqual(res.status, 403)
        finally:
            server.server_close()

    def test_primp_unsafe_url_blocking(self):
        # File scheme must be rejected immediately without network attempt
        file_res = fetch_with_primp("file:///etc/passwd", allow_private=False)
        self.assertFalse(file_res.ok)
        self.assertEqual(file_res.attempts, 0)
        self.assertEqual(file_res.evidence_class, "none")
        self.assertIn("unsafe or unsupported URL scheme/host", file_res.error)

        # Loopback URL without allow_private=True must be blocked
        loopback_res = fetch_with_primp("http://127.0.0.1:8080/internal", allow_private=False)
        self.assertFalse(loopback_res.ok)
        self.assertEqual(loopback_res.attempts, 0)
        self.assertIn("unsafe or unsupported URL scheme/host", loopback_res.error)

    def test_resilient_fetch_falls_back_when_primp_fails(self):
        # When primp returns a failure, resilient_fetch must fall back to urllib.request
        class FallbackHandler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-Type", "text/plain")
                self.end_headers()
                self.wfile.write(b"Recovered via standard urllib fallback path with sufficient length.")

            def log_message(self, *args):
                pass

        server = http.server.HTTPServer(("127.0.0.1", 0), FallbackHandler)
        port = server.server_port
        t = threading.Thread(target=server.handle_request, daemon=True)
        t.start()

        url = f"http://127.0.0.1:{port}/fallback"
        try:
            with mock.patch("dr_engine.tools.http_resilience._fetch_with_primp") as mock_primp:
                mock_primp.return_value = FetchResult(
                    ok=False, url=url, text="", status=500,
                    via="direct:primp", charset="", sha256="", attempts=1, error="network timeout",
                    bot_wall=False, elapsed_ms=10.0, truncated=False, lossy=False, evidence_class="none",
                )
                res = resilient_fetch(url, timeout=5.0, allow_private=True, retries=1)
                self.assertTrue(res.ok)
                self.assertEqual(res.via, "direct")
                self.assertIn("Recovered via standard urllib", res.text)
                self.assertTrue(any("falling back to urllib.request" in w for w in res.warnings))
        finally:
            server.server_close()

    def test_disable_primp_via_env(self):
        os.environ["DR_DISABLE_PRIMP"] = "1"
        try:
            self.assertFalse(is_primp_available())
            self.assertIsNone(_get_primp_client())
        finally:
            del os.environ["DR_DISABLE_PRIMP"]


class TestGroundedSentenceExtraction(unittest.TestCase):
    """Test exact sentence splitting and character-span grounding with LangExtract."""

    def test_split_grounded_sentences_protects_decimals_and_abbreviations(self):
        text = (
            "Pursuant to Art. 97a of the VAT Act, registration is mandatory. "
            "Dr. Smith said the fund lost 5.5% vs. 4.2% in U.S. markets! "
            "Finally, a third sentence."
        )
        spans = split_grounded_sentences(text)
        self.assertEqual(len(spans), 3)

        s1, e1, q1 = spans[0]
        self.assertEqual(q1, "Pursuant to Art. 97a of the VAT Act, registration is mandatory.")
        self.assertEqual(text[s1:e1], q1)

        s2, e2, q2 = spans[1]
        self.assertEqual(q2, "Dr. Smith said the fund lost 5.5% vs. 4.2% in U.S. markets!")
        self.assertEqual(text[s2:e2], q2)

        s3, e3, q3 = spans[2]
        self.assertEqual(q3, "Finally, a third sentence.")
        self.assertEqual(text[s3:e3], q3)

    def test_split_grounded_sentences_cyrillic_statutory(self):
        text = (
            "Съгласно чл. 26, ал. 7 от ЗДДФЛ доходите се облагат с 10%. "
            "За 2026 г. срокът е фиксиран."
        )
        spans = split_grounded_sentences(text)
        self.assertEqual(len(spans), 2)
        for s, e, q in spans:
            self.assertEqual(text[s:e], q)

    def test_split_grounded_sentences_cyrillic_terminal_abbrev(self):
        text = "Срокът изтече през 2026 г. Новият период започва утре."
        spans = split_grounded_sentences(text)
        self.assertEqual(len(spans), 2)
        self.assertEqual(spans[0][2], "Срокът изтече през 2026 г.")
        self.assertEqual(spans[1][2], "Новият период започва утре.")
        for s, e, q in spans:
            self.assertEqual(text[s:e], q)

    def test_split_grounded_sentences_etc_terminal(self):
        text = "We bought apples, oranges, etc. Then we went home."
        spans = split_grounded_sentences(text)
        self.assertEqual(len(spans), 2)
        self.assertEqual(spans[0][2], "We bought apples, oranges, etc.")
        self.assertEqual(spans[1][2], "Then we went home.")
        for s, e, q in spans:
            self.assertEqual(text[s:e], q)

    def test_split_grounded_sentences_author_initials(self):
        text = "Author J. K. Rowling wrote Harry Potter. Next sentence."
        spans = split_grounded_sentences(text)
        self.assertEqual(len(spans), 2)
        self.assertEqual(spans[0][2], "Author J. K. Rowling wrote Harry Potter.")
        self.assertEqual(spans[1][2], "Next sentence.")
        for s, e, q in spans:
            self.assertEqual(text[s:e], q)

    def test_split_grounded_sentences_academic_citations(self):
        text = "According to A. Vaswani et al. (2017), the transformer architecture scales well. We verify this."
        spans = split_grounded_sentences(text)
        self.assertEqual(len(spans), 2)
        self.assertEqual(spans[0][2], "According to A. Vaswani et al. (2017), the transformer architecture scales well.")
        self.assertEqual(spans[1][2], "We verify this.")
        for s, e, q in spans:
            self.assertEqual(text[s:e], q)

    def test_split_grounded_sentences_section_and_list_numbering(self):
        # Section header
        sec_text = "In Section 1. Introduction, the authors explain the problem. The methodology follows."
        sec_spans = split_grounded_sentences(sec_text)
        self.assertEqual(len(sec_spans), 2)
        self.assertEqual(sec_spans[0][2], "In Section 1. Introduction, the authors explain the problem.")
        self.assertEqual(sec_spans[1][2], "The methodology follows.")

        # Numbered list items
        list_text = "1. The model achieves 95% accuracy on the test set. 2. Next point."
        list_spans = split_grounded_sentences(list_text)
        self.assertEqual(len(list_spans), 2)
        self.assertEqual(list_spans[0][2], "1. The model achieves 95% accuracy on the test set.")
        self.assertEqual(list_spans[1][2], "2. Next point.")
        for s, e, q in list_spans:
            self.assertEqual(list_text[s:e], q)

    def test_split_grounded_sentences_asian_cjk_punctuation(self):
        text = "これは最初の文です。これは二番目の文です。"
        spans = split_grounded_sentences(text)
        self.assertEqual(len(spans), 2)
        self.assertEqual(spans[0][2], "これは最初の文です。")
        self.assertEqual(spans[1][2], "これは二番目の文です。")
        for s, e, q in spans:
            self.assertEqual(text[s:e], q)

    def test_split_grounded_sentences_corporate_and_us_abbrev(self):
        text1 = "The contract was signed by Acme Corp. Next, we reviewed the budget."
        spans1 = split_grounded_sentences(text1)
        self.assertEqual(len(spans1), 2)
        self.assertEqual(spans1[0][2], "The contract was signed by Acme Corp.")
        self.assertEqual(spans1[1][2], "Next, we reviewed the budget.")

        text2 = "The U.S. Federal Reserve raised rates. Next sentence."
        spans2 = split_grounded_sentences(text2)
        self.assertEqual(len(spans2), 2)
        self.assertEqual(spans2[0][2], "The U.S. Federal Reserve raised rates.")
        self.assertEqual(spans2[1][2], "Next sentence.")

    def test_char_interval_dataclass_fallback(self):
        ci = CharInterval(start_pos=10, end_pos=42)
        self.assertEqual(ci.start_pos, 10)
        self.assertEqual(ci.end_pos, 42)

    def test_extract_candidate_quotes_exact_grounding(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            td = Path(tmpdir)
            sources = td / "sources"
            sources.mkdir()
            (sources / "index.jsonl").write_text(
                json.dumps({"id": "S001", "url": "https://nber.org/paper.pdf", "tier": "T1"}) + "\n",
                encoding="utf-8",
            )
            snap_text = (
                "Empirical factor decay reaches 42% out-of-sample across 286 tested anomalies. "
                "Second finding documents that transaction friction reduces Sharpe by 0.65."
            )
            (sources / "S001.txt").write_text(snap_text, encoding="utf-8")

            candidates = extract_candidate_quotes(td, keywords=["decay", "friction"])
            self.assertEqual(len(candidates), 2)

            for cand in candidates:
                self.assertEqual(cand["source"], "S001")
                self.assertEqual(cand["tier"], "T1")
                s = cand["char_start"]
                e = cand["char_end"]
                self.assertEqual(snap_text[s:e], cand["quote"])
                self.assertEqual(cand["char_len"], len(cand["quote"]))
                if lx is not None:
                    self.assertIn("char_interval", cand)
                    self.assertEqual(cand["char_interval"].start_pos, s)
                    self.assertEqual(cand["char_interval"].end_pos, e)

    def test_extract_candidate_quotes_safe_tier_no_tier_laundering(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            td = Path(tmpdir)
            sources = td / "sources"
            sources.mkdir()
            (sources / "index.jsonl").write_text(
                json.dumps({"id": "S001", "url": "https://notedu.evil.example/paper.pdf"}) + "\n"
                + json.dumps({"id": "S002", "url": "https://economics.harvard.edu/paper.pdf"}) + "\n",
                encoding="utf-8",
            )
            (sources / "S001.txt").write_text(
                "First observation from evil domain with enough length to qualify as a candidate quote.",
                encoding="utf-8",
            )
            (sources / "S002.txt").write_text(
                "Second observation from genuine edu domain with enough length to qualify as a candidate quote.",
                encoding="utf-8",
            )

            candidates = extract_candidate_quotes(td)
            tier_by_src = {c["source"]: c["tier"] for c in candidates}
            # Evil domain containing 'edu' substring must NOT be laundered to T1
            self.assertEqual(tier_by_src.get("S001"), "T3")
            # Genuine .edu domain receives T1
            self.assertEqual(tier_by_src.get("S002"), "T1")

    def test_extract_candidate_quotes_malformed_keywords(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            td = Path(tmpdir)
            sources = td / "sources"
            sources.mkdir()
            (sources / "index.jsonl").write_text(
                json.dumps({"id": "S001", "url": "https://example.com/blog", "tier": "T3"}) + "\n",
                encoding="utf-8",
            )
            (sources / "S001.txt").write_text(
                "Valid empirical sentence with more than twenty characters for quote verification.",
                encoding="utf-8",
            )
            # Passing None, ints, or empty strings in keywords must not crash
            candidates = extract_candidate_quotes(td, keywords=[None, 12345, "   ", "empirical"])
            self.assertEqual(len(candidates), 1)

    def test_extracted_candidates_lock_cleanly(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            td = Path(tmpdir)
            sources = td / "sources"
            sources.mkdir()
            (sources / "index.jsonl").write_text(
                json.dumps({"id": "S001", "url": "https://nber.org/w100", "tier": "T1"}) + "\n",
                encoding="utf-8",
            )
            doc_text = (
                "Statistically significant anomalies diminish rapidly after peer review publication. "
                "Trading friction accounts for the majority of the post-publication performance drop."
            )
            (sources / "S001.txt").write_text(doc_text, encoding="utf-8")

            candidates = extract_candidate_quotes(td)
            self.assertTrue(len(candidates) >= 2)

            # Assign valid [E001, E002, ...] IDs
            items_to_lock = []
            for i, cand in enumerate(candidates, 1):
                cand["id"] = f"E{i:03d}"
                items_to_lock.append(cand)

            locked, errors = lock_evidence(td, items_to_lock)
            self.assertEqual(len(errors), 0)
            self.assertEqual(len(locked), len(items_to_lock))
            self.assertTrue((td / "evidence_ledger.json").exists())
            self.assertTrue((td / "evidence_ledger.json.sha256").exists())
            self.assertTrue((td / "evidence_pack.md").exists())

    def test_split_grounded_sentences_edge_cases(self):
        # Empty and non-string inputs
        self.assertEqual(split_grounded_sentences(""), [])
        self.assertEqual(split_grounded_sentences("   \n\t   "), [])
        self.assertEqual(split_grounded_sentences(None), [])
        self.assertEqual(split_grounded_sentences(12345), [])

        # Text without terminal punctuation
        spans = split_grounded_sentences("This is an unpunctuated text fragment")
        self.assertEqual(len(spans), 1)
        self.assertEqual(spans[0][2], "This is an unpunctuated text fragment")

        # Multi-dot ellipsis and question/exclamation marks
        text = "Is Sharpe ratio >= 1.5 achievable? Yes! However, slippage degrades returns..."
        spans = split_grounded_sentences(text)
        self.assertEqual(len(spans), 3)
        for s, e, q in spans:
            self.assertEqual(text[s:e], q)

    def test_extract_candidate_quotes_empty_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            td = Path(tmpdir)
            self.assertEqual(extract_candidate_quotes(td), [])

    def test_primp_client_builder_invalid_profiles(self):
        if primp is None:
            self.skipTest("primp is not installed")
        # Passing completely invalid profile name should recover to valid fallback
        client = _get_primp_client("non_existent_profile_999")
        self.assertIsNotNone(client)


if __name__ == "__main__":
    unittest.main()
