#!/usr/bin/env python3
"""v10.0 Architectural Hardening — regression & adversarial test suite.

Covers the five upgrades from the 2026-11-06 audit:
  1. fail-closed epistemic gate (epistemic_guard + v9_bullshit_filters + verify_study)
  2. resilient polyglot transport & ranking (http_resilience, polyglot_text, context_ranker)
  3. trench miner honesty layer (trench_miner)
  4. benchmark provenance & reachable AI domain (benchmark_radar, auto_spec)
  5. executive decision instruments (decision_card)

All tests are offline: network calls are mocked, no API keys, no external deps.
"""

from __future__ import annotations

import argparse
import gzip
import io
import json
import math
import re
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from dr_engine.tools import (
    auto_spec, benchmark_radar, context_ranker, decision_card, epistemic_guard,
    http_resilience, lean_engine, polyglot_text, trench_miner, v9_bullshit_filters,
)
from dr_engine.tools.benchmark_radar import BenchmarkRadar
from dr_engine.tools.epistemic_guard import run_filters_fail_closed
from dr_engine.tools.polyglot_text import detect_scripts, number_density, tokenize
from dr_engine.tools.v9_bullshit_filters import run_v9_bullshit_filters


class _FakeResponse:
    """Minimal urllib response supporting the context-manager protocol."""

    def __init__(self, body: bytes, status: int = 200, headers: dict | None = None):
        self._body = body
        self.status = status
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self, n: int = -1) -> bytes:
        return self._body if n < 0 else self._body[:n]


def _http_error(url: str, code: int, body: bytes = b"", headers: dict | None = None):
    return urllib.error.HTTPError(
        url, code, "blocked", headers or {}, io.BytesIO(body)
    )


# ---------------------------------------------------------------------------
# 1. Polyglot text layer
# ---------------------------------------------------------------------------
class TestPolyglotText(unittest.TestCase):
    def test_cjk_bigrams_are_produced(self):
        zh = tokenize("生产环境实际测试滑点回测失效踩坑")
        self.assertGreaterEqual(len(zh), 8)
        self.assertTrue(any(len(t) == 2 for t in zh))
        self.assertTrue(polyglot_text.is_cjk_heavy("生产环境实际测试滑点"))
        self.assertEqual(detect_scripts("生产环境")["han"], 1.0)

    def test_accented_latin_and_cyrillic_are_not_destroyed(self):
        de = tokenize("Im Produktivbetrieb verursachte ein Fehler Slippage und Latenz.")
        self.assertIn("produktivbetrieb", de)
        fr = tokenize("Une défaillance en production avec écart d'exécution.")
        self.assertIn("defaillance", fr)
        es = tokenize("Pérdida por deslizamiento en producción.")
        self.assertIn("perdida", es)
        ru = tokenize("Сбой в алгоритме исполнения привел к убытку в 440 миллионов.")
        # A global NFD fold would turn Cyrillic й into и and corrupt keywords.
        self.assertIn("сбой", ru)
        self.assertIn("убытку", ru)

    def test_two_letter_acronyms_survive(self):
        mixed = tokenize("ＡＩ LLM 大模型 GPT-6 0DTE")
        for term in ("ai", "llm", "0dte"):
            self.assertIn(term, mixed)

    def test_number_density_and_shingles(self):
        self.assertGreater(number_density("Revenue 1234 USD in 2025"), 0.0)
        self.assertEqual(
            polyglot_text.shingles("alpha beta gamma delta", k=3),
            {("alpha", "beta", "gamma"), ("beta", "gamma", "delta")},
        )


# ---------------------------------------------------------------------------
# 2. Resilient HTTP transport
# ---------------------------------------------------------------------------
class TestHttpResilience(unittest.TestCase):
    def test_charset_detection(self):
        bom = http_resilience.decode_bytes(
            b"\xef\xbb\xbf" + "AI model".encode("utf-8"), "text/plain"
        )
        self.assertEqual(bom.text, "AI model")
        self.assertFalse(bom.lossy)
        self.assertIn("Сбой", http_resilience.decode_bytes(
            "Сбой в проде".encode("cp1251"), "text/html; charset=windows-1251").text)
        self.assertIn("本番", http_resilience.decode_bytes(
            "本番環境".encode("shift_jis"), "text/html; charset=Shift_JIS").text)
        self.assertIn("生产", http_resilience.decode_bytes(
            "生产环境".encode("gb18030"), "text/html; charset=gb2312").text)
        # Mislabelled single-byte header on a genuine UTF-8 body is corrected.
        self.assertEqual(
            http_resilience.decode_bytes(
                "Сбой в проде".encode("utf-8"), "text/html; charset=windows-1251"
            ).charset,
            "utf-8",
        )

    def test_gzip_and_bot_wall_detection(self):
        raw = gzip.compress(b"<html><body>" + b"x" * 200 + b"</body></html>")
        body, coding = http_resilience._maybe_decompress(raw, {"Content-Encoding": "gzip"})
        self.assertEqual(coding, "gzip")
        self.assertIn(b"xxx", body)
        self.assertTrue(http_resilience.detect_bot_wall(403, {}, ""))
        self.assertTrue(http_resilience.detect_bot_wall(200, {"Server": "cloudflare"}, ""))
        self.assertTrue(http_resilience.detect_bot_wall(200, {}, "Just a moment..."))
        self.assertFalse(http_resilience.detect_bot_wall(200, {}, "Engineering postmortem."))

    def test_unsafe_urls_are_rejected_without_network(self):
        self.assertTrue(http_resilience.is_safe_url("https://example.com/a"))
        self.assertTrue(http_resilience.is_safe_url("http://127.0.0.1:9/", allow_private=True))
        for bad in ("file:///C:/secret.txt", "javascript:alert(1)",
                    "data:text/html,x", "https://user:pass@example.com/"):
            self.assertFalse(http_resilience.is_safe_url(bad), bad)
        res = http_resilience.resilient_fetch("file:///etc/passwd")
        self.assertFalse(res.ok)
        self.assertIn("unsafe", res.error)

    @mock.patch("dr_engine.tools.http_resilience.urllib.request.urlopen")
    def test_successful_fetch_carries_provenance(self, urlopen):
        body = "CBOE microstructure report: effective spread 1.2 bps in 2026. " * 4
        urlopen.return_value = _FakeResponse(
            body.encode("utf-8"), 200, {"Content-Type": "text/html; charset=utf-8"}
        )
        res = http_resilience.resilient_fetch("https://cboe.com/report", retries=1)
        self.assertTrue(res.ok)
        self.assertEqual(res.via, "direct")
        self.assertEqual(res.charset, "utf-8")
        self.assertEqual(len(res.sha256), 64)
        self.assertFalse(res.bot_wall)
        self.assertEqual(res.attempts, 1)

    @mock.patch("dr_engine.tools.http_resilience.urllib.request.urlopen")
    @mock.patch("dr_engine.tools.http_resilience.time.sleep")
    def test_transient_retry_and_hard_bot_wall(self, _sleep, urlopen):
        urlopen.side_effect = [
            _http_error("https://x.test", 429, b"slow down", {"Retry-After": "0"}),
            _FakeResponse(b"Recovered page content with enough characters to pass. " * 3,
                          200, {"Content-Type": "text/plain"}),
        ]
        res = http_resilience.resilient_fetch("https://x.test", retries=2)
        self.assertTrue(res.ok)
        self.assertEqual(res.attempts, 2)

        urlopen.side_effect = [
            _http_error("https://x.test", 403, b"Access Denied")
        ]
        blocked = http_resilience.resilient_fetch("https://x.test", retries=2)
        self.assertFalse(blocked.ok)
        self.assertTrue(blocked.bot_wall)
        self.assertIn("403", blocked.error)
        # Structured failure, never an exception or a silent empty success.
        self.assertEqual(blocked.attempts, 1)

    @mock.patch("dr_engine.tools.http_resilience.urllib.request.urlopen")
    def test_json_parse_failure_is_structured(self, urlopen):
        urlopen.return_value = _FakeResponse(
            b"<html>not json but long enough to be a body</html>" + b"x" * 100,
            200, {"Content-Type": "text/html"},
        )
        res, data = http_resilience.fetch_json("https://api.test/x", retries=1)
        self.assertFalse(res.ok)
        self.assertIsNone(data)
        self.assertIn("JSON parse", res.error)


# ---------------------------------------------------------------------------
# 3. Fail-closed epistemic gate
# ---------------------------------------------------------------------------
class TestEpistemicGuard(unittest.TestCase):
    def test_verdict_normalisation_and_numeric_coercion(self):
        self.assertEqual(epistemic_guard.normalize_verdict("conditional go"), "CONDITIONAL_GO")
        self.assertEqual(epistemic_guard.normalize_verdict("NO-GO"), "NO_GO")
        self.assertIn("CONDITIONAL_GO", epistemic_guard.POSITIVE_VERDICTS)
        for bad in (float("nan"), float("inf"), True, "8.4"):
            self.assertIsNone(epistemic_guard.safe_number(bad))
        self.assertIsNone(epistemic_guard.safe_int("2026-Q3"))
        self.assertEqual(epistemic_guard.safe_int("2026"), 2026)

    def test_scoped_mitigation_rejects_distant_disarm_word(self):
        trigger = re.compile(r"two-way real-time sync", re.I)
        distant = ("We will deploy a two-way real-time sync across channels. "
                   + "Unrelated filler sentence. " * 30 + " avoid")
        self.assertTrue(epistemic_guard.unmitigated_spans(
            distant, trigger, terms=("avoid", "rejected")))
        near = "We avoid a two-way real-time sync; instead we use read-only diffs."
        self.assertFalse(epistemic_guard.unmitigated_spans(
            near, trigger, terms=("avoid", "rejected")))

    def test_preflight_validation_is_a_hard_failure(self):
        self.assertTrue(epistemic_guard.validate_inputs({}, {"x": float("nan")}))
        self.assertTrue(epistemic_guard.validate_inputs(
            {"counterparty_physics": {"sample_end_year": "2026-Q3"}}, {}))
        self.assertFalse(epistemic_guard.validate_inputs(
            {"counterparty_physics": {"sample_end_year": 2026}}, {"x": 1.0}))

    @mock.patch("dr_engine.tools.v9_bullshit_filters.run_v9_bullshit_filters",
                side_effect=RuntimeError("simulated filter crash"))
    def test_filter_exception_is_fail_closed_B0(self, _crash):
        fails, _ = run_filters_fail_closed("# Report", {"domain": "quant"}, {})
        self.assertTrue(fails)
        self.assertTrue(any("B0 (Filter Integrity / FAIL-CLOSED)" in f for f in fails))

    def test_b2_distant_avoid_no_longer_disarms(self):
        report = ("We will deploy a two-way real-time sync across channels. "
                  + "Unrelated discussion of market microstructure. " * 25 + " avoid")
        manifest = {"domain": "saas", "verdict": "GO", "architecture_mode": "read_only_diff"}
        fails, _ = run_v9_bullshit_filters(report, manifest, {})
        self.assertTrue(any("B2 (Operational Physics)" in f for f in fails))

    def test_b3_conditional_go_friction_gate(self):
        manifest = {
            "domain": "quant", "verdict": "CONDITIONAL_GO",
            "counterparty_physics": {
                "forced_actor": "dealers", "sample_end_year": 2026,
                "gross_edge_bp": 10.0, "friction_cost_bp": 2.0,
            },
        }
        fails, _ = run_v9_bullshit_filters(
            "Quant analysis with modern microstructure.", manifest,
            {"friction_share_of_1r": 0.05, "net_alpha_bp": 8.0},
        )
        self.assertTrue(any("B3 (Jacobian Friction Gate)" in f for f in fails))

    def test_b7_treaty_keyword_no_longer_disarms(self):
        report = "Using Section 1256 combined with Bulgarian ЗДДФЛ. " + \
                 "We reviewed a treaty somewhere in the appendix. " * 20
        manifest = {
            "domain": "tax", "verdict": "GO",
            "normative_physics": {
                "jurisdiction": "BG", "primary_statute": "ЗДДФЛ",
                "authority_tier": "binding_statute",
            },
        }
        fails, _ = run_v9_bullshit_filters(report, manifest, {})
        self.assertTrue(any("B7 (Jurisdiction Conflation)" in f for f in fails))

    def test_b8_nan_is_rejected(self):
        manifest = {
            "domain": "deeptech", "verdict": "GO",
            "physical_limits": {"limit_name": "carnot_efficiency"},
        }
        env = {
            "thermodynamic_headroom_ratio": float("nan"),
            "bom_unit_cost_usd": 150.0, "first_pass_yield_pct": 85.0,
        }
        fails, _ = run_v9_bullshit_filters("Novel thermal cycle.", manifest, env)
        self.assertTrue(any("B8 (Thermodynamic Violation)" in f for f in fails))

    def test_b9_is_claim_triggered_not_domain_gated(self):
        # v9.0 only ran B9 for ai/tech/software/finance -- domains auto_spec
        # could never emit. A SOTA claim in a "quant" study must still be gated.
        manifest = {"domain": "quant", "verdict": "GO", "evidence": []}
        fails, _ = run_v9_bullshit_filters(
            "This is the best model for our quant stack.", manifest, {})
        self.assertTrue(any("B9 (Uncalibrated SOTA Claim)" in f for f in fails))

    def test_b9_requires_snapshot_verified_evidence(self):
        manifest = {
            "domain": "ai", "verdict": "GO",
            "evidence": [{
                "id": "E001", "source": "S001",
                "quote": "Rank 1: Model X - Overall Score: 99 on Artificial Analysis",
            }],
        }
        report = "The best AI model is Model X [E001]."
        clean, _ = run_v9_bullshit_filters(report, manifest, {})
        self.assertFalse(any("B9" in f for f in clean))
        strict, _ = run_v9_bullshit_filters(
            report, manifest, {}, verified_evidence_ids={"E999"})
        self.assertTrue(any("B9 (Uncalibrated SOTA Claim)" in f for f in strict))

    def test_b1_remote_sample_size_does_not_calibrate(self):
        report = ("We estimate EV using Base 50% / Bear 35% / Stress 15%. "
                  + "Unrelated methodology appendix. " * 30 + "n=45")
        fails, _ = run_v9_bullshit_filters(report, {"domain": "quant", "verdict": "GO"}, {})
        self.assertTrue(any("B1 (No Fake EV)" in f for f in fails))


# ---------------------------------------------------------------------------
# 4. Context ranker & lean_engine integration
# ---------------------------------------------------------------------------
class TestContextRankerAndVerify(unittest.TestCase):
    @staticmethod
    def _sources():
        long_para = ("Introductory commentary on microstructure. " * 60
                     + "CRITICAL TABLE ROW: friction 3.0 bps net alpha 5.4 bps in 2026.")
        zh = ("生产环境实际测试滑点回测失效踩坑 实测滑点 3.2 bp 手续费 1.1 bp "
              "合计 4.3 bp 净 alpha 为负 ") * 4
        return {"S001": long_para, "S002": zh}

    def test_windows_polyglot_dedup_and_budget(self):
        sources = self._sources()
        queries = {"SQ1": "execution friction net alpha bps",
                   "SQ2": "生产环境 滑点 实测", "K1": "execution friction"}
        passages = context_ranker.build_passages(sources)
        self.assertGreaterEqual(len(passages), 3)
        self.assertTrue(any("CRITICAL TABLE ROW" in p.text for p in passages))
        ranked = context_ranker.rank_passages(sources, queries, top_k_per_query=3)
        self.assertTrue(any(r["sid"] == "S002" for r in ranked), "CJK source invisible to BM25")
        locators = [r["locator"] for r in ranked]
        self.assertEqual(len(locators), len(set(locators)), "duplicate span across queries")
        budgeted = context_ranker.rank_passages(sources, queries, max_chars=500)
        self.assertLessEqual(sum(len(r["quote_span"]) for r in budgeted), 1400)

    def test_ast_sandbox_has_a_deterministic_resource_budget(self):
        self.assertEqual(
            lean_engine.execute_model_block("a = 2 ** 10\nb = a / 4"),
            {"a": 1024.0, "b": 256.0},
        )
        with self.assertRaises(ValueError):
            lean_engine.execute_model_block("x = 2 ** 100000000")
        with self.assertRaises(ValueError):
            lean_engine.execute_model_block('y = "a" * 99999999')

    def test_quote_matcher_bounded_ellipsis_and_coordinates(self):
        snap = ("Federal Reserve H.15: The daily overnight bank funding rate (OBFR) averaged "
                "5.31 percent across the window, with standard deviation 0.04 percent.")
        quote = "overnight bank funding rate (OBFR) averaged 5.31 percent ... standard deviation 0.04 percent"
        self.assertTrue(lean_engine.quote_matches_snapshot(quote, snap))
        spliced = "overnight bank funding rate ... " + ("filler " * 500) + "0.04 percent"
        self.assertFalse(lean_engine.quote_matches_snapshot(spliced, snap))

    def test_ingest_records_provenance_and_unverified_seed_flag(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp) / "study"
            d.mkdir()
            spec = {
                "inline_sources": {
                    "https://artificialanalysis.ai/indexes/finance-and-accounting":
                        "Benchmark seed: Rank 1: Model X - Overall Score: 63. " * 4,
                    "https://cboe.com/report":
                        "CBOE report: effective spread 1.2 bps across 500 sessions. " * 4,
                },
                "unverified_inline_sources": [
                    "https://artificialanalysis.ai/indexes/finance-and-accounting"
                ],
                "sub_questions": {"SQ1": "spread friction benchmark"},
                "kill_hypotheses": {"K1": "spread exceeds gross edge"},
            }
            (d / "study_spec.json").write_text(json.dumps(spec), encoding="utf-8")
            rc = lean_engine.cmd_ingest(argparse.Namespace(dir=str(d), spec=str(d / "study_spec.json")))
            self.assertEqual(rc, 0)
            rows = [json.loads(l) for l in (d / "sources" / "index.jsonl").read_text(
                encoding="utf-8").splitlines() if l.strip()]
            self.assertEqual(len(rows), 2)
            self.assertTrue(all(r["via"] == "inline_seed" for r in rows))
            self.assertTrue(any(r["unverified_bundled"] for r in rows))
            self.assertTrue((d / "context_pack.md").exists())

    @mock.patch("dr_engine.tools.v9_bullshit_filters.run_v9_bullshit_filters",
                side_effect=TypeError("simulated malformed manifest"))
    def test_verify_study_is_fail_closed_on_filter_crash(self, _crash):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp) / "study"
            src = d / "sources"
            src.mkdir(parents=True)
            text = ("CBOE microstructure report: effective spread 1.2 bps, "
                    "slippage 0.9 bps, total friction 3.0 bps in 2026. " * 3)
            for i in (1, 2, 3):
                (src / f"S{i:03d}.txt").write_text(text, encoding="utf-8")
            rows = [{
                "id": f"S{i:03d}", "url": f"https://cboe.com/{i}",
                "sha256": lean_engine.sha256_text(text), "chars": len(text),
            } for i in (1, 2, 3)]
            (src / "index.jsonl").write_text(
                "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
            manifest = {
                "domain": "quant", "verdict": "GO",
                "counterparty_physics": {"forced_actor": "dealers", "sample_end_year": 2026},
                "evidence": [
                    {"id": f"E{i:03d}", "source": f"S{i:03d}", "tier": "T1",
                     "quote": "effective spread 1.2 bps"} for i in (1, 2, 3)
                ],
                "kills": [
                    {"id": "K1", "verdict": "refuted", "eids": ["E001"]},
                    {"id": "K2", "verdict": "refuted", "eids": ["E002"]},
                    {"id": "K3", "verdict": "unresolved", "eids": []},
                ],
            }
            report = (
                "# Study\n\n"
                "```json:manifest\n" + json.dumps(manifest) + "\n```\n\n"
                "```python:model C001\ngross_bp = 8.4\nfriction_share_of_1r = 0.024\n"
                "net_alpha_bp = 5.4\n```\n\n"
                "Effective spread is 1.2 bps [E001].\n"
            )
            (d / "report.md").write_text(report, encoding="utf-8")
            rep = lean_engine.verify_study(d)
            self.assertFalse(rep.passed, "filter crash must NOT certify the study")
            self.assertTrue(any("B0 (Filter Integrity" in f for f in rep.failures))


# ---------------------------------------------------------------------------
# 5. Trench miner honesty layer
# ---------------------------------------------------------------------------
class TestTrenchMiner(unittest.TestCase):
    def test_english_prompt_expands_concepts(self):
        poly = trench_miner.build_polyglot_queries("best LLM for finance slippage bugs")
        self.assertTrue(any("финансы" in q or "алготрейдинг" in q for q in poly["ru"]))
        self.assertTrue(any("金融" in q or "量化" in q for q in poly["zh"]))
        bg = trench_miner.build_polyglot_queries("Кой е най-добрият AI модел за финанси")
        self.assertTrue(any("大模型" in q or "金融" in q for q in bg["zh"]))

    def test_unknown_dates_are_not_fabricated(self):
        self.assertEqual(trench_miner._safe_date(None), ("unknown", False))
        self.assertEqual(trench_miner._safe_date("not-a-date"), ("unknown", False))
        self.assertEqual(
            trench_miner._safe_date("Wed, 05 Nov 2026 10:00:00 GMT"),
            ("2026-11-05", True),
        )

    def test_snapshot_is_hash_anchored_and_comparable_scores(self):
        item = trench_miner.TrenchEvidenceItem(
            "Habr", "RU", "a", "Knight Capital", "https://habr.com/1",
            "2026-11-01", 45, "Сбой в алгоритме исполнения привел к убытку в 440 миллионов.",
            alpha_flag=True, lang="ru",
        )
        snap = item.render_snapshot_block()
        self.assertIn("sha256=", snap)
        self.assertIn(item.content_sha256[:16], snap)
        self.assertIn("[HIGH-SIGNAL TRENCH ALPHA]", snap)
        known = trench_miner.TrenchEvidenceItem(
            "Habr", "RU", "a", "t", "https://habr/1", "2026-11-01", 10, "y" * 60)
        unknown = trench_miner.TrenchEvidenceItem(
            "Habr", "RU", "a", "t", "https://habr/2", "unknown", 10, "y" * 60,
            date_known=False)
        self.assertGreater(known.signal_score, unknown.signal_score)
        self.assertTrue(all(0.0 <= x.signal_score <= 100.0 for x in (item, known, unknown)))

    def test_github_query_is_precision_trimmed(self):
        q = trench_miner.github_query(
            "Gemini GPT-6 best top leading benchmark finance quantitative trading accounting",
            "en",
        )
        self.assertIn("is:issue", q)
        self.assertLessEqual(len(q.split()), 6)
        self.assertNotIn("quantitative", q)
        self.assertIn("Gemini", q)

    def test_collector_ledger_records_failures(self):
        led = trench_miner.CollectorLedger()
        led.record(trench_miner.CollectorOutcome(
            "github_zh", "https://api.github.com/x", False, 0, 403,
            "direct", "blocked", True, 1.0))
        led.record(trench_miner.CollectorOutcome(
            "habr_ru", "https://habr.com/rss", True, 2, 200,
            "direct", "", False, 2.0))
        s = led.summary()
        self.assertEqual(s["collectors"], 2)
        self.assertEqual(s["failed"], 1)
        self.assertEqual(s["bot_walled"], 1)
        self.assertEqual(s["items"], 2)
        self.assertEqual(s["coverage_pct"], 50.0)


# ---------------------------------------------------------------------------
# 6. Benchmark provenance & auto_spec domain reachability
# ---------------------------------------------------------------------------
class TestBenchmarkAndAutoSpec(unittest.TestCase):
    def test_bundled_seed_is_explicitly_unverified(self):
        prov = BenchmarkRadar.provenance("finance")
        self.assertFalse(prov["verified"])
        self.assertFalse(prov["citation_allowed"])
        text = BenchmarkRadar.render_snapshot("finance")
        self.assertIn("NOT VERIFIED", text)
        self.assertIn("BUNDLED OFFLINE SEED", text)
        self.assertIn("Rank 1: Gemini 4 Carbon (high) - Overall Score: 63", text)

    def test_unknown_category_and_metric_fail_loudly(self):
        with self.assertRaises(ValueError):
            BenchmarkRadar.get_benchmark("biotech")
        with self.assertRaises(ValueError):
            BenchmarkRadar.get_leader("coding", "non_hallucination")
        self.assertEqual(
            BenchmarkRadar.get_leader("finance", "reasoning", top_n=5)["model"],
            "Claude Opus 5.5 (max)",
        )

    def test_live_text_renders_verified_snapshot(self):
        live = BenchmarkRadar.render_snapshot("finance", live_text="Rank 1: Measured 77")
        self.assertIn("LIVE FETCH", live)
        self.assertIn("sha256:", live)
        self.assertIn("Measured 77", live)
        fresh = BenchmarkRadar.staleness("finance")
        self.assertIn(fresh["status"], ("FRESH", "STALE"))
        self.assertIsInstance(fresh["age_days"], int)
        self.assertEqual(fresh["max_age_days"], 45)
        # Freshness is a real computation, not a constant claim.
        old = BenchmarkRadar.staleness("finance", today=__import__("datetime").date(2030, 1, 1))
        self.assertEqual(old["status"], "STALE")

    def test_ai_domain_is_reachable_and_unmatched_is_general(self):
        self.assertEqual(
            auto_spec.classify_prompt_domain(
                "Best LLM on the Artificial Analysis leaderboard for SOTA coding"), "ai")
        self.assertEqual(
            auto_spec.classify_prompt_domain("A question with no domain vocabulary"), "general")
        self.assertEqual(
            auto_spec.classify_prompt_domain("US100 M15 gamma imbalance alpha"), "quant")
        skeleton = auto_spec.build_adversarial_spec_skeleton("Which LLM is SOTA")
        self.assertEqual(len(skeleton["kill_hypotheses"]), 3)

    def test_offline_spec_has_provenance_and_no_fabricated_years(self):
        spec = auto_spec.generate_autonomous_study_spec(
            "Evaluate US100 M15 0DTE gamma imbalance momentum after spread friction",
            offline_only=True,
        )
        self.assertIn("collector_provenance", spec)
        self.assertIn("warnings", spec)
        self.assertIn("unverified_inline_sources", spec)
        self.assertTrue(spec["warnings"], "empty discovery must raise a warning")
        self.assertEqual(auto_spec._year_of("unknown"), 0)


# ---------------------------------------------------------------------------
# 7. Decision instruments
# ---------------------------------------------------------------------------
class TestDecisionCard(unittest.TestCase):
    MODEL = """
gross_bp = 8.4
spread_bp = 1.2
slippage_rt_bp = 1.8
stop_1r_bp = 100.0
total_friction_bp = spread_bp + slippage_rt_bp
friction_share_of_1r = total_friction_bp / stop_1r_bp
net_alpha_bp = net_edge_bp(gross_bp, spread_bp, slippage_rt_bp)
""".strip()

    def test_exact_bisection_and_linear_fallback(self):
        inputs, metrics, _ = decision_card.compile_models_for_decision_card(
            [("C001", self.MODEL)])
        net = next(m for m in metrics if m.name == "net_alpha_bp")
        self.assertAlmostEqual(net.breakeven_bounds["gross_bp"], 3.0, places=3)
        self.assertTrue(net.breakeven_exact.get("gross_bp"))
        nonlinear = ("gross_bp = 20.0\nspread_bp = 2.0\n"
                     "cost_bp = spread_bp * spread_bp\nnet_bp = gross_bp - cost_bp - 4.0")
        _, nmetrics, _ = decision_card.compile_models_for_decision_card(
            [("C002", nonlinear)])
        nm = next(m for m in nmetrics if m.name == "net_bp")
        self.assertAlmostEqual(nm.breakeven_bounds["spread_bp"], 4.0, places=2)
        self.assertTrue(nm.breakeven_exact.get("spread_bp"))

    def test_monte_carlo_is_reproducible_and_ordered(self):
        inputs, metrics, code = decision_card.compile_models_for_decision_card(
            [("C001", self.MODEL)])
        a = decision_card.compute_monte_carlo(code, inputs, metrics, n_samples=300, seed=7)
        b = decision_card.compute_monte_carlo(code, inputs, metrics, n_samples=300, seed=7)
        self.assertEqual(a, b)
        self.assertEqual(a["seed"], 7)
        for name, d in a["metrics"].items():
            self.assertLessEqual(d["p5"], d["p50"])
            self.assertLessEqual(d["p50"], d["p95"])
            self.assertTrue(0.0 <= d["p_below_zero"] <= 1.0)
            self.assertEqual(len(d["histogram"]), 18)
        self.assertIn("<svg", decision_card.render_histogram_svg(
            a["metrics"]["net_alpha_bp"]["histogram"]))
        scenarios = decision_card.compute_stress_scenarios(code, inputs, metrics)
        self.assertEqual(len(scenarios), 4)

    def test_rendered_card_has_mc_panel_and_sanitised_links(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp) / "study"
            src = d / "sources"
            src.mkdir(parents=True)
            body = ("CBOE empirical microstructure report: effective spread 1.2 bps, "
                    "slippage 1.8 bps, total friction 3.0 bps, net alpha 5.4 bps in 2026. " * 3)
            (src / "S001.txt").write_text(body, encoding="utf-8")
            (src / "index.jsonl").write_text(json.dumps({
                "id": "S001", "url": "javascript:alert(1)",
                "sha256": lean_engine.sha256_text(body), "chars": len(body),
            }) + "\n", encoding="utf-8")
            manifest = {
                "domain": "quant", "verdict": "GO",
                "evidence": [{"id": "E001", "source": "S001", "tier": "T1",
                              "quote": "effective spread 1.2 bps"}],
                "kills": [],
            }
            report = ("# Executable Decision Study\n\n"
                      "```json:manifest\n" + json.dumps(manifest) + "\n```\n\n"
                      "```python:model C001\n" + self.MODEL + "\n```\n\n"
                      "Effective spread is 1.2 bps [E001].\n")
            (d / "report.md").write_text(report, encoding="utf-8")
            fake_rep = SimpleNamespace(
                passed=True, max_confidence="High", epistemic_index=93.8,
                information_density_index=101.1, n_eff_clusters=3.0,
                bound_units=1, total_claim_units=1, n_evidence=1,
            )
            html_out = decision_card.render_decision_card_html(d, verification=fake_rep)
            self.assertIn("Monte Carlo Distribution", html_out)
            self.assertIn("Deterministic Joint Stress Presets", html_out)
            self.assertIn("<svg", html_out)
            self.assertNotIn("href='javascript:", html_out)
            self.assertIn("GATE: PASS", html_out)

    def test_full_pipeline_builds_a_card_for_a_verified_study(self):
        """auto_spec-style spec -> ingest -> verified report -> Decision Card."""
        code_block = """
import math

class FrictionEngine:
    def __init__(self, stop_bp, spread_bp, slip_bp):
        self.stop_bp = stop_bp
        self.spread_bp = spread_bp
        self.slip_bp = slip_bp

    def friction_ratio(self):
        total_rt = self.spread_bp + 2.0 * self.slip_bp
        return total_rt / self.stop_bp if self.stop_bp > 0 else 1.0

    def evaluate_bar(self, net_gex_bn, moc_imbalance_mm, vol_bps):
        ratio = self.friction_ratio()
        if ratio > 0.030:
            return {"signal": 0, "reason": "FRICTION_KILL_GATE"}
        if net_gex_bn <= -2.5 and abs(moc_imbalance_mm) >= 500.0:
            direction = 1 if moc_imbalance_mm > 0 else -1
            expected_gross = 0.42 * vol_bps
            net_ev = expected_gross - (self.spread_bp + 2.0 * self.slip_bp)
            if net_ev > 2.5:
                return {"signal": direction, "net_ev_bp": round(net_ev, 2),
                        "stop_bp": self.stop_bp}
        return {"signal": 0, "reason": "NO_FORCED_FLOW"}

    def position_contracts(self, equity_usd, risk_pct, point_val, stop_pts):
        if stop_pts <= 0 or point_val <= 0:
            return 0
        dollar_risk = equity_usd * risk_pct
        return max(0, int(math.floor(dollar_risk / (stop_pts * point_val))))

    def is_regular_trading_hours(self, hour, minute):
        minute_of_day = hour * 60 + minute
        return 570 <= minute_of_day <= 960

    def compute_daily_pnl_bps(self, gross_move_pts, point_val, stop_pts):
        ratio = self.friction_ratio()
        if ratio > 0.030:
            return 0.0
        gross_bps = (gross_move_pts / stop_pts) * self.stop_bp
        net_bps = gross_bps - (self.spread_bp + 2.0 * self.slip_bp)
        return round(net_bps, 2)
""".strip()
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp) / "study"
            src = d / "sources"
            src.mkdir(parents=True)
            body = ("CBOE microstructure report 2026: effective spread 1.2 bps, "
                    "slippage 0.9 bps per side, total friction 3.0 bps, "
                    "net alpha 5.4 bps across 500 sessions. " * 4)
            for i in (1, 2, 3):
                (src / f"S{i:03d}.txt").write_text(body, encoding="utf-8")
            rows = [{
                "id": f"S{i:03d}", "url": f"https://cboe.com/report/{i}",
                "sha256": lean_engine.sha256_text(body), "chars": len(body),
                "via": "inline_seed", "unverified_bundled": False,
            } for i in (1, 2, 3)]
            (src / "index.jsonl").write_text(
                "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
            manifest = {
                "domain": "quant", "verdict": "CONDITIONAL_GO",
                "counterparty_physics": {
                    "forced_actor": "Short-gamma dealers delta-hedging into MOC imbalance",
                    "sample_end_year": 2026,
                    "gross_edge_bp": 8.4, "friction_cost_bp": 3.0,
                },
                "evidence": [
                    {"id": f"E{i:03d}", "source": f"S{i:03d}", "tier": "T1",
                     "quote": "effective spread 1.2 bps"} for i in (1, 2, 3)
                ],
                "kills": [
                    {"id": "K1", "verdict": "unresolved", "eids": []},
                    {"id": "K2", "verdict": "unresolved", "eids": []},
                    {"id": "K3", "verdict": "unresolved", "eids": []},
                ],
            }
            model = (
                "gross_bp = 8.4\nspread_bp = 1.2\nslippage_rt_bp = 1.8\n"
                "stop_1r_bp = 100.0\n"
                "total_friction_bp = spread_bp + slippage_rt_bp\n"
                "friction_share_of_1r = total_friction_bp / stop_1r_bp\n"
                "net_alpha_bp = net_edge_bp(gross_bp, spread_bp, slippage_rt_bp)\n"
            )
            report = (
                "# Intraday Execution Friction Study\n\n"
                "Effective spread is 1.2 bps [E001]. Net alpha is 5.4 bps [E001, C001].\n\n"
                "```json:manifest\n" + json.dumps(manifest) + "\n```\n\n"
                "```python:model C001\n" + model + "```\n\n"
                "```python\n" + code_block + "\n```\n"
            )
            (d / "report.md").write_text(report, encoding="utf-8")
            from dr_engine.tools.evidence_locker import lock_evidence
            lock_evidence(d, manifest["evidence"])

            rep = lean_engine.verify_study(d)
            self.assertTrue(rep.passed, f"verification unexpectedly failed: {rep.failures}")
            rc = decision_card.cmd_build(argparse.Namespace(
                dir=str(d), out=None, allow_failed=False))
            self.assertEqual(rc, 0)
            card = (d / "decision_card.html").read_text(encoding="utf-8")
            self.assertIn("GATE: PASS", card)
            self.assertIn("Monte Carlo Distribution", card)
            self.assertIn("<svg", card)

    def test_build_refuses_a_failed_study(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp) / "broken"
            d.mkdir()
            args = argparse.Namespace(dir=str(d), out=None, allow_failed=False)
            rc = decision_card.cmd_build(args)
            self.assertEqual(rc, 2)

    def test_safe_href_rejects_non_http_schemes(self):
        self.assertEqual(decision_card.safe_href("https://x.test/a"), "https://x.test/a")
        for bad in ("javascript:alert(1)", "data:text/html,x", "file:///etc/passwd", ""):
            self.assertEqual(decision_card.safe_href(bad), "#")


if __name__ == "__main__":
    unittest.main()
