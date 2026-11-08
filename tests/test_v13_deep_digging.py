#!/usr/bin/env python3
"""Deep Research Engine v13.0 — adversarial regression suite.

Proves mechanically that every failure mode exposed in the RP52A-H postmortem
is now impossible to certify or deliver:
  1. Frontier 1 (`deep_digger.py`): HTML tables stay `|`-delimited, JSON-LD /
     Next.js FAQ schemas are recovered, and multi-hop spidering follows `/terms`,
     `/faq`, `help.*` and `.pdf` subpages while skipping locale mirrors & login noise.
  2. Frontier 2 (Rule R19 — Anti-Truncation): 15-30 line stubs can no longer
     game R17 (`IDI = 1000 / word_count * ...`) by shrinking prose length.
  3. Frontier 3 (Rule R20 — Mandatory `Claim -> URL -> Verbatim Quote` Ledger):
     missing ledgers, missing URLs, mismatched domains, and non-verbatim quotes
     hard-FAIL verification.
  4. Frontier 4 (Rule B12 & Known Traps): `MAXIMUM CONVICTION GO`, uncalculated
     `11.8x` multipliers, unbacked `~100-150 occurrences/year` frequency guesses,
     and the dead `funding dip rebound` setup all hard-FAIL.
  5. Frontier 5 (Rule R21 — Deliverable Attestation & `reports/` Anti-Bypass):
     `lean_engine.py export` refuses unverified studies, stamps `DR-ATTESTATION`
     on verified exports, and `audit-deliverables` catches raw `reports/*.md`
     bypass files and post-export tampering.
  6. Rule B0 Fail-Closed: any exception inside v13 gates yields `B0 (v13 Gate Integrity)`.

Pure Python stdlib, 100% offline & deterministic.
"""

from __future__ import annotations

import argparse
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from dr_engine.tools import (
    auto_spec,
    deep_digger,
    depth_and_ledger_gate,
    lean_engine,
    v9_bullshit_filters,
)


def _build_compliant_v13_study(root: Path, *, compact_words: int | None = None) -> Path:
    """Create a realistic, fully compliant v13.0 study directory."""
    d = root / "2026-11-07-v13-prop-audit"
    src = d / "sources"
    src.mkdir(parents=True)

    snapshots = {
        "S001": (
            "https://www.fintokei.com/protrader/",
            "ProTrader Evaluation Schedule\n"
            "Account | Fee | Daily Loss | Max Loss | Phase 1 | Phase 2\n"
            "USD 100,000 | $549 | 5% Equity | 10% Fixed Initial Balance | 8% | 6%\n"
            "Automated trading strategies (EAs) are permitted provided total open risk stays at or below 3%.",
        ),
        "S002": (
            "https://help.fintokei.com/en/articles/drawdown-rules",
            "FAQ Q: Is the 10% maximum drawdown trailing or fixed?\n"
            "FAQ A: On ProTrader accounts, the 10% Overall Loss limit is fixed at 90% of the initial starting balance ($90,000 on a $100,000 account) and does not trail peak profits.",
        ),
        "S003": (
            "https://help.fintokei.com/en/articles/copy-trading-policy",
            "FAQ Q: Can I copy trades from another prop firm account?\n"
            "FAQ A: Copy trading your own trades from your own external MT4/MT5 account (including another prop firm) is allowed up to 400,000 EUR combined Fintokei allocation, provided the strategy is solely yours.",
        ),
        "S004": (
            "https://the5ers.com/high-stakes/",
            "The5ers High Stakes 100K fee is $495 with 5% daily pause and 10% static max loss. "
            "Using an EA or trading bot requires prior written support review and a live video verification interview.",
        ),
        "S005": (
            "https://ftmo.com/en/pricing/",
            "FTMO 1-Step 100K evaluation fee is 399 EUR with 3% daily loss limit and 10% EOD trailing max loss.",
        ),
    }

    idx_rows = []
    for sid, (url, body) in snapshots.items():
        (src / f"{sid}.txt").write_text(body, encoding="utf-8")
        idx_rows.append({
            "id": sid,
            "url": url,
            "sha256": lean_engine.sha256_text(body),
            "chars": len(body),
            "via": "direct",
            "evidence_class": "primary_fetched",
            "secondary_transcription": False,
        })
    (src / "index.jsonl").write_text(
        "\n".join(json.dumps(r) for r in idx_rows) + "\n", encoding="utf-8"
    )

    quotas = {
        "min_words": compact_words if compact_words is not None else 1000,
        "min_sources": 5,
        "min_evidence": 8,
        "min_tables": 2,
        "min_sections": 5,
        "min_model_vars": 4,
        "min_ledger_rows": 8,
    }
    if compact_words is not None and compact_words < 350:
        quotas["allow_compact_fixture"] = True

    (d / "study_spec.json").write_text(
        json.dumps({"protocol_version": "13.0", "depth_quotas": quotas}, indent=2),
        encoding="utf-8",
    )

    manifest = {
        "protocol_version": "13.0",
        "domain": "general",
        "verdict": "CONDITIONAL_GO",
        "evidence": [
            {"id": "E001", "source": "S001", "tier": "T1", "quote": "USD 100,000 | $549 | 5% Equity | 10% Fixed Initial Balance | 8% | 6%"},
            {"id": "E002", "source": "S001", "tier": "T1", "quote": "Automated trading strategies (EAs) are permitted provided total open risk stays at or below 3%."},
            {"id": "E003", "source": "S002", "tier": "T1", "quote": "the 10% Overall Loss limit is fixed at 90% of the initial starting balance ($90,000 on a $100,000 account) and does not trail peak profits."},
            {"id": "E004", "source": "S003", "tier": "T1", "quote": "Copy trading your own trades from your own external MT4/MT5 account (including another prop firm) is allowed up to 400,000 EUR combined Fintokei allocation"},
            {"id": "E005", "source": "S004", "tier": "T1", "quote": "The5ers High Stakes 100K fee is $495 with 5% daily pause and 10% static max loss."},
            {"id": "E006", "source": "S004", "tier": "T1", "quote": "Using an EA or trading bot requires prior written support review and a live video verification interview."},
            {"id": "E007", "source": "S005", "tier": "T1", "quote": "FTMO 1-Step 100K evaluation fee is 399 EUR with 3% daily loss limit and 10% EOD trailing max loss."},
            {"id": "E008", "source": "S003", "tier": "T1", "quote": "provided the strategy is solely yours"},
        ],
        "kills": [
            {"id": "K1", "verdict": "refuted", "eids": ["E003"]},
            {"id": "K2", "verdict": "refuted", "eids": ["E004", "E008"]},
            {"id": "K3", "verdict": "confirmed", "eids": ["E006"]},
        ],
    }

    # Build dense, non-boilerplate analytical paragraphs so R19 (>=1000w) and R17 (IDI>=100) both pass.
    analytical_sections = (
        "## 1. Executive Synthesis & Structural Verdict\n\n"
        "Primary verification of official contractual schedules confirms Fintokei ProTrader 100,000 USD charges $549 "
        "with Phase 1 target 8% and Phase 2 target 6% [E001]. Daily drawdown is 5% equity-based while overall drawdown "
        "is 10% fixed at $90,000 on a $100,000 account [E001, E003]. Expert Advisors remain allowed when open risk "
        "stays at or below 3% [E002]. By contrast, FTMO 1-Step 100K costs 399 EUR with 3% daily loss and 10% EOD "
        "trailing loss [E007], whereas The5ers High Stakes 100K charges $495 [E005] and imposes a mandatory written "
        "review plus video interview gate for bots [E006]. Computed net annual payout ratio is 6.8x [C001].\n\n"
        "## 2. Claim-Link-Quote Evidence Ledger\n\n"
        "| Твърдение (Claim) | Източник / Линк (URL) | Дословен цитат (Verbatim Quote) | ID |\n"
        "| :-- | :-- | :-- | :-- |\n"
        "| Fintokei 100K струва $549 с цели 8% и 6% | https://www.fintokei.com/protrader/ | \"USD 100,000 \\| $549 \\| 5% Equity \\| 10% Fixed Initial Balance \\| 8% \\| 6%\" | [E001] |\n"
        "| Ботовете са позволени при <= 3% отворен риск | https://www.fintokei.com/protrader/ | \"Automated trading strategies (EAs) are permitted provided total open risk stays at or below 3%.\" | [E002] |\n"
        "| Максималната загуба от 10% е фиксирана на $90,000 | https://help.fintokei.com/en/articles/drawdown-rules | \"the 10% Overall Loss limit is fixed at 90% of the initial starting balance ($90,000 on a $100,000 account) and does not trail peak profits.\" | [E003] |\n"
        "| Копиране на собствени сделки от друга фирма е позволено до 400,000 EUR | https://help.fintokei.com/en/articles/copy-trading-policy | \"Copy trading your own trades from your own external MT4/MT5 account (including another prop firm) is allowed up to 400,000 EUR combined Fintokei allocation\" | [E004] |\n"
        "| Стратегията при self-copy трябва да е изцяло собствена | https://help.fintokei.com/en/articles/copy-trading-policy | \"provided the strategy is solely yours\" | [E008] |\n"
        "| The5ers High Stakes 100K струва $495 със статичен 10% лимит | https://the5ers.com/high-stakes/ | \"The5ers High Stakes 100K fee is $495 with 5% daily pause and 10% static max loss.\" | [E005] |\n"
        "| The5ers изисква писмено одобрение и видео интервю за EA | https://the5ers.com/high-stakes/ | \"Using an EA or trading bot requires prior written support review and a live video verification interview.\" | [E006] |\n"
        "| FTMO 1-Step 100K струва 399 EUR с 3% дневен лимит | https://ftmo.com/en/pricing/ | \"FTMO 1-Step 100K evaluation fee is 399 EUR with 3% daily loss limit and 10% EOD trailing max loss.\" | [E007] |\n\n"
        "## 3. Comparative Prop Firm Matrix & Rejection Criteria\n\n"
        "| Firm [I] | Fee | Daily Limit | Max Loss | Net Ratio | Citation |\n"
        "| :-- | :-- | :-- | :-- | :-- | :-- |\n"
        "| Fintokei ProTrader | $549 | 5% | 10% | 6.8x | [E001, E003, C001] |\n"
        "| The5ers High Stakes | $495 | 5% | 10% | 6.1x | [E005, E006, C001] |\n"
        "| FTMO 1-Step | 399 EUR | 3% | 10% | 7.6x | [E007, C001] |\n\n"
        "## 4. Epistemic Alpha Delta\n\n"
        "### Superficial Consensus\n\n"
        "Surface summaries claim Fintokei charges 549 EUR with EOD balance daily loss and The5ers accepts bots "
        "with a simple notification email while FTMO 1-Step costs 540 EUR [E007].\n\n"
        "### Trench Ground-Truth (The Alpha)\n\n"
        "Help-center clause verification proves Fintokei charges $549 USD with equity-based 5% daily loss and "
        "a fixed $90,000 floor [E001, E003], permits self-copying across firms up to 400,000 EUR [E004], while "
        "The5ers mandates a live video verification interview for EAs [E006].\n\n"
        "### Delta Impact\n\n"
        "Deploying an unapproved EA on The5ers or mispricing equity vs balance daily loss risks immediate account "
        "termination and forfeiture of $549 in evaluation fees plus $3,733 in annual net cashflow [E001, C001].\n\n"
        "## 5. Quantitative Capital & Breakeven Model\n\n"
        "Under $100,000 notional allocation [E001] with $549 fee [E001], annual net payout after split is $3,733.2 "
        "producing a verified 6.8x cash-to-fee ratio [C001], compared against $495 on The5ers yielding 6.1x [E005, C001] "
        "and 399 EUR on FTMO yielding 7.6x [E007, C001]. Combined allocation remains bounded below 400,000 EUR [E004] "
        "and open risk stays below 3% [E002].\n"
    )

    # Add grounded clause-by-clause audit commentary so prose >= 1000 words while maintaining high IDI & entity density.
    extra_grounded = (
        "\n### Clause-Level Operational Verification\n\n"
        + "\n".join(
            f"- Operational check {idx}: contractual audit confirms the $90,000 static floor on a $100,000 "
            f"ProTrader balance never trails above initial deposit [E003], while daily equity monitoring "
            f"enforces 5% intraday protection [E001] and caps concurrent exposure at 3% [E002]. External "
            f"MT5 self-copying under 400,000 EUR [E004] requires exclusive strategy ownership [E008], "
            f"whereas $495 High Stakes [E005] gates automated bots behind video review [E006] and 399 EUR "
            f"FTMO 1-Step [E007] enforces 3% daily risk with 6.8x net cash-to-fee [C001]."
            for idx in range(1, 10)
        )
        + "\n"
    )

    helper_code = (
        "\n```python\n"
        "def check_static_floor(equity: float, initial_balance: float) -> bool:\n"
        "    return equity >= 0.90 * initial_balance\n\n"
        "def check_daily_equity_limit(equity: float, midnight_equity: float) -> bool:\n"
        "    return equity >= 0.95 * midnight_equity\n\n"
        "def check_open_risk_cap(open_risk_usd: float, initial_balance: float) -> bool:\n"
        "    return open_risk_usd <= 0.03 * initial_balance\n"
        "```\n"
    )

    model_block = (
        "\n```python:model C001\n"
        "fintokei_fee_usd = 549.0\n"
        "the5ers_fee_usd = 495.0\n"
        "ftmo_fee_eur = 399.0\n"
        "expected_annual_payout_usd = 3733.2\n"
        "fintokei_cash_to_fee = round(expected_annual_payout_usd / fintokei_fee_usd, 1)\n"
        "the5ers_cash_to_fee = round(3019.5 / the5ers_fee_usd, 1)\n"
        "ftmo_cash_to_fee = round(3032.4 / ftmo_fee_eur, 1)\n"
        "```\n"
    )

    report_md = (
        "# Fintokei ProTrader 100K & Prop Firm Rule Verification\n\n"
        + analytical_sections
        + extra_grounded
        + helper_code
        + model_block
        + "\n```json:manifest\n" + json.dumps(manifest, indent=2) + "\n```\n"
    )
    (d / "report.md").write_text(report_md, encoding="utf-8")
    from dr_engine.tools.evidence_locker import lock_evidence
    lock_evidence(d, manifest["evidence"])
    return d


class TestDeepDigger(unittest.TestCase):
    def test_html_tables_and_jsonld_faq_preserved(self):
        html_doc = """
        <html><head><script type="application/ld+json">
        {"@type":"FAQPage","mainEntity":[{"@type":"Question","name":"Max loss mode?","acceptedAnswer":{"@type":"Answer","text":"Fixed at 90% of initial balance."}}]}
        </script></head><body>
        <table><tr><th>Tier</th><th>Fee</th></tr><tr><td>100K</td><td>$549</td></tr></table>
        </body></html>
        """
        snap = deep_digger.html_to_structured_snapshot(html_doc)
        self.assertIn("Tier | Fee", snap)
        self.assertIn("100K | $549", snap)
        self.assertIn("Fixed at 90% of initial balance.", snap)

    def test_multi_hop_spider_expands_subpages_offline_mocked(self):
        seed_html = """
        <html><body>
        <h1>Prop Landing</h1>
        <a href="/terms-and-conditions">Terms and Conditions</a>
        <a href="https://help.propfirm.test/articles/copy-trading">Copy Trading FAQ</a>
        <a href="/jp/home">Japanese Locale</a>
        <a href="/login">Login</a>
        </body></html>
        """
        terms_html = "<html><body><h2>General Terms</h2><p>Overall drawdown is 10% static floor.</p></body></html>"
        faq_html = "<html><body><h2>Copy Trading</h2><p>Self-copying between your own accounts is permitted.</p></body></html>"

        def fake_fetch(url: str, **kwargs):
            mapping = {
                "https://propfirm.test": seed_html,
                "https://propfirm.test/terms-and-conditions": terms_html,
                "https://help.propfirm.test/articles/copy-trading": faq_html,
            }
            body = mapping.get(url.rstrip("/"), "")
            return deep_digger.DugDocument(
                url=url,
                text=deep_digger.html_to_structured_snapshot(body),
                raw_html=body,
                ok=bool(body),
                via="direct",
                evidence_class="primary_fetched",
                status=200 if body else 404,
                sha256=lean_engine.sha256_text(deep_digger.html_to_structured_snapshot(body)) if body else "",
                hop_depth=kwargs.get("hop_depth", 0),
                parent_url=kwargs.get("parent_url", ""),
                reason=kwargs.get("reason", "seed"),
            )

        with mock.patch("dr_engine.tools.deep_digger.fetch_document_snapshot", side_effect=fake_fetch):
            dug = deep_digger.deep_dig_urls(
                ["https://propfirm.test/"],
                focus_query="drawdown copy trading",
                max_depth=2,
                max_subpages=6,
                allow_private=True,
            )
        urls = [d.url for d in dug if d.ok]
        self.assertEqual(len(urls), 3)
        self.assertIn("https://propfirm.test/terms-and-conditions", urls)
        self.assertIn("https://help.propfirm.test/articles/copy-trading", urls)


class TestV13AntiLazinessAndLedgerGates(unittest.TestCase):
    def test_compliant_v13_study_passes_all_gates(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = _build_compliant_v13_study(Path(tmp))
            rep = lean_engine.verify_study(d)
            self.assertTrue(rep.v13_protocol_active)
            self.assertTrue(rep.v12_protocol_active)
            self.assertTrue(rep.passed, f"Unexpected failures: {rep.failures}")
            self.assertTrue((d / "verification_receipt.json").exists())

    def test_r19_rejects_short_20_line_stub_closing_r17_goodhart_loop(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = _build_compliant_v13_study(Path(tmp))
            # Truncate prose to a 25-line stub while keeping manifest/models intact
            full_txt = (d / "report.md").read_text(encoding="utf-8")
            code_idx = full_txt.index("```python\n")
            stub_txt = "# Truncated Stub\n\nFee is $549 [E001] and 399 EUR [E007].\n\n" + full_txt[code_idx:]
            (d / "report.md").write_text(stub_txt, encoding="utf-8")

            rep = lean_engine.verify_study(d)
            self.assertFalse(rep.passed)
            self.assertTrue(any("R19 (Shallow Prose / Truncation)" in f for f in rep.failures), rep.failures)
            self.assertTrue(any("R20 (Claim-Link-Quote Ledger Missing)" in f for f in rep.failures), rep.failures)

    def test_r20_rejects_mismatched_domain_and_non_verbatim_quote_in_ledger(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = _build_compliant_v13_study(Path(tmp))
            txt = (d / "report.md").read_text(encoding="utf-8")
            # Corrupt one URL domain and paraphrase one quote in the Claim-Link-Quote table
            corrupted = txt.replace(
                "https://the5ers.com/high-stakes/ | \"The5ers High Stakes 100K fee is $495 with 5% daily pause and 10% static max loss.\"",
                "https://wrong-domain.example/foo | \"The5ers charges roughly 495 dollars for 100K.\"",
            )
            (d / "report.md").write_text(corrupted, encoding="utf-8")
            rep = lean_engine.verify_study(d)
            self.assertFalse(rep.passed)
            self.assertTrue(any("R20 (URL/Snapshot Mismatch" in f for f in rep.failures), rep.failures)

    def test_b12_catches_rp52h_and_rp52e_hallucinations(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = _build_compliant_v13_study(Path(tmp))
            txt = (d / "report.md").read_text(encoding="utf-8")
            injected = txt.replace(
                "## 1. Executive Synthesis & Structural Verdict",
                "## 1. Executive Synthesis & Structural Verdict\n\n"
                "Status: MAXIMUM CONVICTION GO. Uncalculated ratio is 11.8x. "
                "Event rate is ~100-150 occurrences/year.",
            )
            (d / "report.md").write_text(injected, encoding="utf-8")
            rep = lean_engine.verify_study(d)
            self.assertFalse(rep.passed)
            self.assertTrue(any("B12 (Hyperbolic Verdict Trap)" in f for f in rep.failures), rep.failures)
            self.assertTrue(any("B12 (Uncalculated Multiplier Hallucination)" in f for f in rep.failures), rep.failures)
            self.assertTrue(any("B12 (Unbacked Frequency Guess)" in f for f in rep.failures), rep.failures)

    def test_b3_catches_dead_btc_funding_dip_rebound_anomaly(self):
        fails, _ = v9_bullshit_filters.run_v9_bullshit_filters(
            "We deploy the BTC funding dip rebound at 08:00 UTC for easy alpha.",
            {"domain": "quant", "verdict": "GO", "counterparty_physics": {"forced_actor": "retail", "sample_end_year": 2026}},
            {"friction_share_of_1r": 0.01, "net_alpha_bp": 5.0},
        )
        self.assertTrue(any("funding dip rebound" in f.lower() for f in fails), fails)


class TestR21DeliverableExportAndBypassGuard(unittest.TestCase):
    def test_export_gates_reports_and_detects_bypass_or_tampering(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            res_root = root / "research"
            rep_dir = root / "reports"
            res_root.mkdir()
            rep_dir.mkdir()

            study = _build_compliant_v13_study(res_root)
            out_md = rep_dir / "VERIFIED_REPORT.md"

            # 1. Valid study exports cleanly and passes deliverables audit
            rc = lean_engine.cmd_export(argparse.Namespace(
                dir=str(study), out=str(out_md), strict_v12=False, strict_v13=True,
            ))
            self.assertEqual(rc, 0)
            self.assertTrue(out_md.exists())

            audit_ok = depth_and_ledger_gate.audit_deliverables_directory(
                rep_dir, res_root, check_all=True
            )
            self.assertTrue(audit_ok["passed"], audit_ok)
            self.assertEqual(audit_ok["verified"], ["VERIFIED_REPORT.md"])

            # 2. Dropping an unverified stub directly into reports/ MUST FAIL R21
            bypass_stub = rep_dir / "RP52_BYPASS_STUB.md"
            bypass_stub.write_text("# Unverified 15-line stub\nStatus: GO\n", encoding="utf-8")
            audit_fail = depth_and_ledger_gate.audit_deliverables_directory(
                rep_dir, res_root, check_all=True
            )
            self.assertFalse(audit_fail["passed"])
            self.assertTrue(any("RP52_BYPASS_STUB.md" == v["file"] for v in audit_fail["violations"]))
            bypass_stub.unlink()

            # 3. Editing numbers in VERIFIED_REPORT.md after export MUST FAIL tamper check
            tampered = out_md.read_text(encoding="utf-8").replace("$549", "€999")
            out_md.write_text(tampered, encoding="utf-8")
            audit_tamper = depth_and_ledger_gate.audit_deliverables_directory(
                rep_dir, res_root, check_all=True
            )
            self.assertFalse(audit_tamper["passed"])
            self.assertTrue(any("Tampering" in v["reason"] for v in audit_tamper["violations"]))

    def test_export_refuses_failing_study(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bad_study = root / "bad_study"
            bad_study.mkdir()
            out_md = root / "reports" / "SHOULD_NOT_EXIST.md"
            rc = lean_engine.cmd_export(argparse.Namespace(
                dir=str(bad_study), out=str(out_md), strict_v12=False, strict_v13=True,
            ))
            self.assertEqual(rc, 1)
            self.assertFalse(out_md.exists())

    def test_v13_gate_is_fail_closed_under_b0(self):
        with mock.patch(
            "dr_engine.tools.depth_and_ledger_gate.validate_depth_quotas",
            side_effect=RuntimeError("synthetic boom"),
        ):
            fails, _, _ = depth_and_ledger_gate.run_v13_gates_fail_closed(
                "# Report",
                study_dir=None,
                manifest={"protocol_version": "13.0"},
                sources_index={},
                source_texts={},
                verified_evidence_ids=set(),
                model_env={},
                protocol_active=True,
            )
        self.assertTrue(any("B0 (v13 Gate Integrity / FAIL-CLOSED)" in f for f in fails), fails)

    def test_markdown_numbered_headings_do_not_false_trigger_b11_while_real_hash1_does(self):
        from dr_engine.tools.dethrone import detect_superlative_claims
        self.assertEqual(detect_superlative_claims("## 1. Executive Synthesis\n### 1. Subheading"), [])
        hits = detect_superlative_claims("Vendor claims Model Z is #1 on coding.")
        self.assertEqual([h.kind for h in hits], ["number_one"])

    def test_b12_frequency_citation_laundering_blocked(self):
        manifest = {
            "evidence": [
                {"id": "E001", "source": "S001", "tier": "T1", "quote": "Evaluation fee is $549 USD."},
            ]
        }
        fails, _ = depth_and_ledger_gate.run_b12_anti_hallucination_filter(
            "Strategy triggers ~120-160 occurrences/year [E001].",
            manifest=manifest,
            model_env={"fee_usd": 549.0},
            verified_evidence_ids={"E001"},
        )
        self.assertTrue(any("B12 (Unbacked Frequency Guess)" in f for f in fails), fails)

    def test_r3_url_numeric_path_exemption(self):
        nums = lean_engine.extract_numbers(
            "Official rule at https://help.fintokei.com/en/articles/9841273-copy-trading charges $549.",
            strip_exempt=True,
        )
        self.assertIn(549.0, nums)
        self.assertNotIn(9841273.0, nums)

    def test_auto_spec_v13_emits_deep_digging_quotas_and_claim_ledger_scaffold(self):
        spec = auto_spec.generate_autonomous_study_spec(
            "Compare Fintokei ProTrader 100K vs FTMO 1-Step 100K drawdown and copy trading rules",
            offline_only=True,
        )
        self.assertEqual(spec["protocol_version"], "13.0")
        self.assertTrue(spec["claim_ledger_required"])
        self.assertIn("deep_digging", spec)
        self.assertGreaterEqual(spec["depth_quotas"]["min_words"], 1000)
        self.assertIn("Дословен цитат", spec["claim_ledger_scaffold"])

    def test_cloudflare_cdn_http200_with_real_article_not_falsely_blocked(self):
        from dr_engine.tools import http_resilience
        intercom_html = (
            "<html><head>"
            "<script src='https://static.cloudflareinsights.com/beacon.min.js'></script>"
            "<noscript>Enable JavaScript to run this app.</noscript>"
            "</head><body><article>"
            + ("Copy trading your own external MT5 account is permitted up to 400,000 EUR. " * 60)
            + "</article></body></html>"
        )
        self.assertFalse(http_resilience.detect_bot_wall(200, {"Server": "cloudflare"}, intercom_html))
        self.assertTrue(http_resilience.detect_bot_wall(200, {"Server": "cloudflare", "Cf-Mitigated": "challenge"}, intercom_html))
        self.assertTrue(http_resilience.detect_bot_wall(200, {"Server": "cloudflare"}, "<title>Just a moment...</title>"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
