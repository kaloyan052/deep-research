#!/usr/bin/env python3
"""Deep Research Engine v12.0 — adversarial regression suite.

Mission: prove that the engine no longer stops at the first high-SEO answer
("Premature Search Termination") and that it surfaces the hidden multilingual
practitioner disclosure ("Golden Nugget") into the context pack and the report.

Coverage required by the mandate:
  1. O_dethrone detects when a record / leader is actually beaten (the 510 kg
     -> 511 kg upset), and refuses certification when it is not checked.
  2. Insider-witness markers in all 8 trench languages trigger the exact 3.0x
     BM25 prior boost (and a reserved slot for zero-overlap comments).
  3. The Epistemic Alpha Delta (R18) gate enforces a REAL contrast between the
     superficial consensus and the trench ground-truth.
Plus: zero-lag recency windows, B0 fail-closed behaviour for the new gates,
malformed-input totality, and preservation of pre-v12 studies.

All tests are offline, deterministic and stdlib-only.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from dr_engine.tools import (
    auto_spec,
    context_ranker,
    ead_gate,
    http_resilience,
    lean_engine,
    trench_miner,
)
from dr_engine.tools.dethrone import (
    MIN_DETHRONING_VECTORS,
    RECENCY_WINDOWS_DAYS,
    adjudicate_dethroning,
    build_dethroning_vectors,
    detect_superlative_claims,
    detect_supersession,
    extract_leader_value,
    run_b11_dethroning_filter,
)
from dr_engine.tools.insider_anomaly import (
    INSIDER_MARKERS,
    INSIDER_PRIOR_BOOST,
    SUPPORTED_LANGUAGES,
    insider_prior,
    scan_insider_markers,
)

TODAY = dt.date.today()

EIGHT_LANGUAGE_SAMPLES = {
    "en": "I was there when the lift was judged; the real number was 511 kg, not 510 kg.",
    "ru": "На самом деле вчера на помосте слили в закрытый чат настоящий результат.",
    "zh": "内部消息：实际跑分实测翻车，世界纪录被打破，现场看到 511 公斤。",
    "es": "En vivo vimos que superó a Björnsson: nuevo récord de 511 kg.",
    "de": "Tatsächlich geschlagen: neuer Rekord, im Produktivbetrieb gescheitert.",
    "ko": "실제로는 어제 대회에서 신기록 달성, 실서버 장애도 있었다.",
    "ja": "実際の測定値では新記録達成、本番で発覚した不具合。",
    "fr": "Sur place nous avons vu un nouveau record: en réalité c'était 511 kg.",
}


def _good_ead() -> str:
    return (
        "## Epistemic Alpha Delta\n\n"
        "### Superficial Consensus\n\n"
        "Generic search still reports Hafthor Bjornsson's 510 kg deadlift as the "
        "standing world record, and most model responses repeat that stale "
        "authoritative page without checking the last 30 days. [E001]\n\n"
        "### Trench Ground-Truth (The Alpha)\n\n"
        "En vivo vimos que superó a Björnsson: nuevo récord de 511 kg in "
        "Birmingham. A Spanish eyewitness comment and the federation results "
        "snapshot both confirm the new measured value. [E003]\n\n"
        "### Delta Impact\n\n"
        "Settling a sponsorship at the stale number would have caused a "
        "250000 USD financial mispricing plus a strategic contract and "
        "reputational loss once 511 kg was ratified. [E003, C001]\n"
    )


def _dethroning_record() -> dict:
    return {
        "leader": "Hafthor Bjornsson",
        "metric": "deadlift world record",
        "status": "intact",
        "vectors_run": 16,
        "window_days": 30,
        "checked_at": TODAY.isoformat(),
        "recency_verified": True,
        "evidence_ids": ["E003"],
    }


def _make_v12_study(root: Path, *, with_ead: bool = True,
                    with_dethroning: bool = True) -> Path:
    """Create a minimal but structurally valid v12 study directory."""
    d = root / "study"
    src = d / "sources"
    src.mkdir(parents=True)
    bodies = {
        "S001": (
            "Federation archive page: the listed deadlift world record is 510 kg, "
            "set in 2020, and the entry list still shows 510 kg as current. "
            "Operator notes on the archive page confirm the publication date."
        ),
        "S002": (
            "Exchange microstructure benchmark: effective spread 1.2 bps and "
            "round-turn friction 3.0 bps across 500 sessions in 2026. "
            "Session counts and instrument classes are tabulated by the venue."
        ),
        "S003": (
            "Birmingham event results snapshot: an eyewitness reported a "
            "511 kg deadlift, and the federation ratified the 511 kg mark. "
            "En vivo vimos que superó a Björnsson: nuevo récord de 511 kg."
        ),
    }
    hosts = {"S001": "federation.test", "S002": "venue.test", "S003": "event.test"}
    for sid, body in bodies.items():
        (src / f"{sid}.txt").write_text(body, encoding="utf-8")
    rows = [{
        "id": sid, "url": f"https://{hosts[sid]}/page",
        "sha256": lean_engine.sha256_text(body), "chars": len(body),
    } for sid, body in bodies.items()]
    (src / "index.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    (d / "study_spec.json").write_text(
        json.dumps({"protocol_version": "12.0", "dethroning": {"vectors": []}}),
        encoding="utf-8")

    manifest = {
        "protocol_version": "12.0",
        "domain": "general",
        "verdict": "GO",
        "evidence": [
            {"id": "E001", "source": "S001", "tier": "T1",
             "quote": "the listed deadlift world record is 510 kg"},
            {"id": "E002", "source": "S002", "tier": "T1",
             "quote": "effective spread 1.2 bps and round-turn friction 3.0 bps"},
            {"id": "E003", "source": "S003", "tier": "T1",
             "quote": "En vivo vimos que superó a Björnsson: nuevo récord de 511 kg."},
        ],
        "kills": [
            {"id": "K1", "verdict": "refuted", "eids": ["E001"]},
            {"id": "K2", "verdict": "confirmed", "eids": ["E003"]},
            {"id": "K3", "verdict": "unresolved", "eids": []},
        ],
    }
    if with_dethroning:
        manifest["dethroning"] = [_dethroning_record()]
    report = (
        "# Zero-Lag Record Verification\n\n"
        "The archive lists a 510 kg deadlift world record [E001], while the "
        "ratified event value is 511 kg [E003]. Friction is 3.0 bps [E002].\n\n"
        + (_good_ead() if with_ead else "")
        + "\n```json:manifest\n" + json.dumps(manifest) + "\n```\n\n"
        + "```python:model C001\nloss_usd = 250000\nfriction_bp = 3.0\n```\n"
    )
    (d / "report.md").write_text(report, encoding="utf-8")
    return d


# ===========================================================================
# FRONTIER 1 — Active Dethroning Protocol
# ===========================================================================
class TestDethroningProtocol(unittest.TestCase):
    def test_operator_detects_a_beaten_world_record(self):
        """The 510 kg high-SEO answer must be dethroned by a fresh 511 kg upset."""
        upset = {
            "text": ("Raúl Flores beat Hafthor Bjornsson with a new record of "
                     "511 kg in Birmingham."),
            "date": (TODAY - dt.timedelta(days=2)).isoformat(),
            "evidence_id": "E003",
        }
        verdict = adjudicate_dethroning(
            "Hafthor Bjornsson", "deadlift world record", [upset],
            leader_value=510.0, as_of=TODAY, vectors_run=16,
        )
        self.assertEqual(verdict.status, "dethroned")
        self.assertEqual(verdict.challenger_value, 511.0)
        self.assertFalse(verdict.certifiable)
        self.assertTrue(verdict.supersession_phrases)

    def test_stale_upset_cannot_dethrone_and_cannot_certify(self):
        old = {"text": "A new record of 511 kg beat the old 510 kg mark.",
               "date": "2020-05-01", "evidence_id": "E009"}
        v = adjudicate_dethroning(
            "L", "M", [old], leader_value=510.0, as_of=TODAY, vectors_run=16)
        self.assertEqual(v.status, "unverified")
        self.assertFalse(v.certifiable)
        self.assertEqual(v.fresh_checks, 0)

    def test_intact_requires_both_fresh_evidence_and_full_vector_coverage(self):
        fresh = {"text": "The federation published the ratified entry list; "
                         "no new record was ratified this cycle.",
                 "date": (TODAY - dt.timedelta(days=1)).isoformat(),
                 "evidence_id": "E002"}
        ok = adjudicate_dethroning("L", "M", [fresh], leader_value=510.0,
                                   as_of=TODAY, vectors_run=16)
        self.assertEqual(ok.status, "intact")
        self.assertTrue(ok.certifiable)
        thin = adjudicate_dethroning("L", "M", [fresh], leader_value=510.0,
                                     as_of=TODAY, vectors_run=2)
        self.assertEqual(thin.status, "unverified")
        self.assertFalse(thin.certifiable)
        self.assertEqual(adjudicate_dethroning("L", "M", []).status,
                         "insufficient_evidence")

    def test_negation_does_not_false_dethrone(self):
        sig = detect_supersession("No new record was ratified by the federation.")
        self.assertFalse(sig["has_upset_language"], sig)
        self.assertTrue(detect_supersession(
            "The 511 kg lift was set by Raúl Flores, surpassing 510 kg.")["challenger"])

    def test_vectors_are_multilingual_adversarial_and_zero_lag(self):
        vecs = build_dethroning_vectors(
            "Hafthor Bjornsson", "deadlift world record", as_of=TODAY)
        self.assertGreaterEqual(len(vecs), 16)
        self.assertEqual({v.window_days for v in vecs}, set(RECENCY_WINDOWS_DAYS))
        langs = {v.lang for v in vecs}
        self.assertEqual(langs, set(SUPPORTED_LANGUAGES))
        en = [v for v in vecs if v.lang == "en" and v.window_days == 30][0]
        for fragment in ("surpassed by", "beat Hafthor Bjornsson", "new record",
                         "defeated by", "outperformed Hafthor Bjornsson"):
            self.assertIn(fragment, en.query)
        for v in vecs:
            self.assertEqual(v.until, TODAY.isoformat())
            self.assertEqual((TODAY - dt.date.fromisoformat(v.since)).days,
                             v.window_days)
            self.assertIn(v.since, v.query)
        # A different as_of must produce different dates (no hardcoded year).
        shifted = build_dethroning_vectors("L", "M", as_of=TODAY - dt.timedelta(days=400))
        self.assertNotEqual(shifted[0].until, vecs[0].until)

    def test_superlative_detection_is_phrase_based(self):
        self.assertTrue(detect_superlative_claims(
            "Who holds the deadlift world record and is the leading model?"))
        self.assertFalse(detect_superlative_claims(
            "A best practice is to log the effective spread."))
        self.assertEqual(extract_leader_value(
            "The record was 510 kg in 2025 and 511 kg today.")["value"], 511.0)

    def test_b11_rejects_premature_search_termination(self):
        fails, _, diag = run_b11_dethroning_filter(
            "The deadlift world record is 510 kg.", {}, as_of=TODAY)
        self.assertTrue(any("B11 (Premature Search Termination)" in f for f in fails))
        self.assertFalse(diag["certifiable"])

    def test_b11_rejects_thin_stale_or_unverified_checks(self):
        prose = "The deadlift world record is 510 kg."
        base = _dethroning_record()
        cases = [
            dict(base, vectors_run=2),
            dict(base, window_days=365),
            dict(base, checked_at="2020-01-01"),
            dict(base, recency_verified=False),
            dict(base, evidence_ids=[]),
            dict(base, evidence_ids=["E999"]),
            dict(base, status="unverified"),
        ]
        for rec in cases:
            with self.subTest(rec=rec):
                fails, _, _ = run_b11_dethroning_filter(
                    prose, {"dethroning": [rec]},
                    verified_evidence_ids={"E003"}, as_of=TODAY)
                self.assertTrue(fails, f"thin check was certified: {rec}")

    def test_b11_demands_the_new_leader_when_dethroned(self):
        rec = dict(_dethroning_record(), status="dethroned",
                   superseded_by="Raúl Flores")
        fails, warns, _ = run_b11_dethroning_filter(
            "The deadlift world record is 510 kg.", {"dethroning": [rec]},
            as_of=TODAY)
        self.assertTrue(fails, "the stale leader was still presented as current")
        ok, warns2, _ = run_b11_dethroning_filter(
            "The deadlift world record is 510 kg, but Raúl Flores now holds it.",
            {"dethroning": [rec]}, as_of=TODAY)
        self.assertFalse(ok)
        self.assertTrue(any("W_B11_UPSET" in w for w in warns2))

    def test_valid_b11_record_certifies(self):
        fails, _, diag = run_b11_dethroning_filter(
            "The deadlift world record is 510 kg.",
            {"dethroning": [_dethroning_record()]},
            verified_evidence_ids={"E003"}, as_of=TODAY)
        self.assertFalse(fails, fails)
        self.assertTrue(diag["certifiable"])
        self.assertEqual(MIN_DETHRONING_VECTORS, 8)

    def test_auto_spec_spawns_dethroning_for_superlative_prompts(self):
        spec = auto_spec.generate_autonomous_study_spec(
            "Who holds the deadlift world record of 510 kg and is still #1?",
            offline_only=True)
        self.assertIn(spec["protocol_version"], ("12.0", "13.0"))
        self.assertTrue(spec["dethroning"]["protocol_active"])
        self.assertGreaterEqual(spec["dethroning"]["vector_count"], 16)
        self.assertEqual(spec["dethroning"]["leader_value"], 510.0)
        self.assertEqual(spec["dethroning"]["leader"], "the current leader")
        named = auto_spec.generate_autonomous_study_spec(
            "Hafþór Björnsson holds the deadlift world record of 510 kg",
            offline_only=True)
        self.assertEqual(named["dethroning"]["leader"], "Hafþór Björnsson")
        self.assertTrue(any("beat Hafþór Björnsson" in v["query"]
                            for v in named["dethroning"]["vectors"]))
        self.assertIn("dethrone_30d_en", spec["adversarial_search_vectors"])
        self.assertTrue(any("SUPERLATIVE CLAIM DETECTED" in w
                            for w in spec["warnings"]))
        neutral = auto_spec.generate_autonomous_study_spec(
            "Estimate execution friction in basis points.", offline_only=True)
        self.assertFalse(neutral["dethroning"]["protocol_active"])
        self.assertEqual(neutral["dethroning"]["vector_count"], 0)


# ===========================================================================
# FRONTIER 2 — Golden Nugget / Insider Anomaly 3.0x BM25 prior
# ===========================================================================
class TestGoldenNuggetPrior(unittest.TestCase):
    def test_all_eight_languages_trigger_exactly_3x(self):
        self.assertEqual(len(SUPPORTED_LANGUAGES), 8)
        for lang, sample in EIGHT_LANGUAGE_SAMPLES.items():
            with self.subTest(lang=lang):
                rec = scan_insider_markers(sample)
                self.assertTrue(rec["is_insider"], lang)
                self.assertEqual(rec["prior"], INSIDER_PRIOR_BOOST)
                self.assertEqual(insider_prior(sample), 3.0)
                self.assertIn(lang, rec["languages"])
                self.assertGreater(rec["entropy"], 0.0)
        for lang in SUPPORTED_LANGUAGES:
            self.assertTrue(INSIDER_MARKERS[lang])

    def test_marker_inventory_contains_every_mandated_phrase(self):
        mandated = {
            "en": ("i was there", "in production we saw", "the real number was",
                   "actually pulled", "quietly deprecated", "leaked benchmark"),
            "ru": ("на самом деле", "вчера на помосте", "слили в закрытый чат",
                   "в проде отвалилось"),
            "zh": ("实测翻车", "内部消息", "实际跑分", "被打破"),
            "es": ("en realidad fue", "superó a", "en vivo vimos", "nuevo récord"),
            "de": ("tatsächlich geschlagen", "im Produktivbetrieb gescheitert",
                   "neuer Rekord"),
            "ko": ("실제로는", "신기록 달성", "어제 대회에서", "실서버 장애"),
            "ja": ("実際の測定値", "新記録達成", "本番で発覚"),
        }
        for lang, phrases in mandated.items():
            folded = {p.lower() for p in INSIDER_MARKERS[lang]}
            for phrase in phrases:
                self.assertIn(phrase.lower(), folded, f"{lang}: {phrase}")

    def test_generic_press_release_is_never_boosted(self):
        generic = ("The vendor announced a new benchmark result and published "
                   "a detailed comparison table for the platform.")
        self.assertFalse(scan_insider_markers(generic)["is_insider"])
        self.assertEqual(insider_prior(generic), 1.0)
        self.assertEqual(insider_prior(None), 1.0)

    def test_normalisation_handles_case_diacritics_and_whitespace(self):
        self.assertTrue(scan_insider_markers("NUEVO   RECORD en vivo vimos")["is_insider"])
        self.assertTrue(scan_insider_markers("I   was\tthere")["is_insider"])
        self.assertTrue(scan_insider_markers(b"I was there")["is_insider"])
        # NFKC folding maps full-width Latin to ASCII, so a full-width Spanish
        # record disclosure is still detected.
        self.assertTrue(scan_insider_markers("ＮＵＥＶＯ ＲＥＣＯＲＤ")["is_insider"])
        self.assertIn("es", scan_insider_markers("ＮＵＥＶＯ ＲＥＣＯＲＤ")["languages"])

    def test_context_ranker_applies_exact_3x_to_bm25_score(self):
        sources = {
            "S010": ("I was there when the lift was judged; the real number was "
                     "511 kg, not 510 kg, at the Birmingham deadlift world record event."),
            "S011": ("The federation published the official entry list and "
                     "confirmed the 510 kg deadlift world record for 2026."),
        }
        ranked = context_ranker.rank_passages(
            sources, {"SQ1": "deadlift world record 510 kg federation"},
            top_k_per_query=2)
        boosted = [r for r in ranked if r["insider_prior"] == 3.0]
        plain = [r for r in ranked if r["insider_prior"] == 1.0]
        self.assertTrue(boosted, f"nugget never surfaced: {ranked}")
        self.assertTrue(plain)
        self.assertAlmostEqual(boosted[0]["score"],
                               3.0 * boosted[0]["bm25_base_score"], delta=0.02)
        self.assertAlmostEqual(plain[0]["score"],
                               plain[0]["bm25_base_score"], delta=0.02)
        self.assertIn("en", boosted[0]["insider_languages"])
        self.assertTrue(boosted[0]["insider_markers"])

    def test_reserved_slot_surfaces_zero_overlap_multilingual_comment(self):
        zh = "内部消息：实际跑分实测翻车，世界纪录被打破，现场看到 511 公斤。" * 3
        mixed = {
            "S020": zh,
            "S021": ("The federation published the official entry list and "
                     "confirmed the 510 kg deadlift world record for 2026. "
                     "The entry list is attached for reference. " * 2),
        }
        ranked = context_ranker.rank_passages(
            mixed, {"SQ9": "deadlift world record 510 kg federation"},
            top_k_per_query=1)
        nugget = [r for r in ranked if r["insider_prior"] == 3.0]
        self.assertTrue(nugget, ranked)
        self.assertTrue(nugget[0]["reserved_slot"])
        self.assertIn("内部消息", nugget[0]["insider_markers"])

    def test_prior_survives_into_trench_snapshot(self):
        item = trench_miner.TrenchEvidenceItem(
            "NicheForum", "ES", "eyewitness", "Birmingham",
            "https://forum.test/es/1", TODAY.isoformat(), 1,
            EIGHT_LANGUAGE_SAMPLES["es"], lang="es")
        block = item.render_snapshot_block()
        self.assertTrue(item.is_golden_nugget)
        self.assertEqual(item.insider_prior, 3.0)
        self.assertIn("bm25_prior=x3.0", block)
        self.assertIn("[GOLDEN NUGGET / INSIDER ANOMALY]", block)
        self.assertIn("[INSIDER ANOMALY", block)
        self.assertIn("ES", item.insider_languages[0].upper())

    def test_boost_can_be_disabled_without_touching_other_ranking(self):
        sources = {"S1": "I was there; the real number was 511 kg, not 510 kg. " * 3}
        default = context_ranker.rank_passages(sources, {"Q": "511 kg"}, top_k_per_query=1)
        off = context_ranker.rank_passages(
            sources, {"Q": "511 kg"}, top_k_per_query=1, insider_prior_boost=1.0)
        self.assertEqual(default[0]["insider_prior"], 3.0)
        self.assertEqual(off[0]["score"], round(off[0]["bm25_base_score"], 2))


# ===========================================================================
# FRONTIER 3 — Epistemic Alpha Delta (R18)
# ===========================================================================
class TestEpistemicAlphaDelta(unittest.TestCase):
    def test_real_contrast_passes(self):
        fails, diag = ead_gate.validate_ead_section(
            _good_ead(), {}, verified_evidence_ids={"E001", "E003"})
        self.assertFalse(fails, fails)
        self.assertTrue(diag["passed"])
        self.assertLess(diag["contrast_jaccard"], ead_gate.MAX_CONTRAST_JACCARD)
        self.assertIn("E003", diag["verified_trench_evidence"])
        self.assertTrue(diag["loss_vectors"])

    def test_missing_section_is_a_hard_failure(self):
        fails, diag = ead_gate.validate_ead_section(
            "# Report\n\nOnly consensus-level prose here.\n", {}, set())
        self.assertTrue(any("R18 (Epistemic Alpha Delta Missing)" in f for f in fails))
        self.assertFalse(diag["present"])

    def test_all_three_subsections_are_required(self):
        broken = _good_ead().replace("### Delta Impact", "### Appendix")
        fails, diag = ead_gate.validate_ead_section(broken, {}, {"E001", "E003"})
        self.assertIn("delta_impact", diag["missing"])
        self.assertTrue(any("R18 (EAD Subsection Missing)" in f for f in fails))

    def test_placeholders_are_rejected(self):
        fails, _ = ead_gate.validate_ead_section(
            ead_gate.render_ead_template(), {}, set())
        self.assertTrue(any("R18 (EAD Placeholder)" in f for f in fails))

    def test_copy_pasting_consensus_into_the_alpha_section_fails(self):
        consensus = _good_ead().split("### Superficial Consensus\n\n", 1)[1].split(
            "### Trench Ground-Truth", 1)[0].strip()
        copied = _good_ead().replace(
            "En vivo vimos que superó a Björnsson: nuevo récord de 511 kg in "
            "Birmingham. A Spanish eyewitness comment and the federation results "
            "snapshot both confirm the new measured value. [E003]",
            consensus.replace("[E001]", "[E003]"),
        )
        fails, diag = ead_gate.validate_ead_section(
            copied, {}, verified_evidence_ids={"E001", "E003"})
        self.assertTrue(any("R18 (Contrast Collapse)" in f for f in fails), fails)
        self.assertGreaterEqual(diag["contrast_jaccard"],
                                ead_gate.MAX_CONTRAST_JACCARD)

    def test_trench_ground_truth_must_cite_a_novel_verified_snapshot(self):
        no_novel = _good_ead().replace(
            "En vivo vimos que superó a Björnsson: nuevo récord de 511 kg in "
            "Birmingham. A Spanish eyewitness comment and the federation results "
            "snapshot both confirm the new measured value. [E003]",
            "The 510 kg figure was repeated by the same archive page. [E001]",
        )
        fails, _ = ead_gate.validate_ead_section(
            no_novel, {}, verified_evidence_ids={"E001"})
        self.assertTrue(any("R18 (No Epistemic Delta)" in f for f in fails), fails)
        unverified, _ = ead_gate.validate_ead_section(
            _good_ead(), {}, verified_evidence_ids={"E001"})
        self.assertTrue(any("R18 (Unverified Trench Evidence)" in f for f in unverified))
        uncited = _good_ead().replace(
            "snapshot both confirm the new measured value. [E003]",
            "snapshot both confirm the new measured value without a citation.",
        )
        fails2, _ = ead_gate.validate_ead_section(
            uncited, {}, verified_evidence_ids={"E001", "E003"})
        self.assertTrue(any("R18 (Trench Alpha Uncited)" in f for f in fails2),
                        fails2)

    def test_delta_impact_must_name_a_consequence_and_a_number(self):
        vague = _good_ead().replace(
            "Settling a sponsorship at the stale number would have caused a "
            "250000 USD financial mispricing plus a strategic contract and "
            "reputational loss once 511 kg was ratified. [E003, C001]",
            "It matters for the reader to know that things changed.",
        )
        fails, _ = ead_gate.validate_ead_section(vague, {}, {"E001", "E003"})
        self.assertTrue(any("R18 (Delta Impact Not Consequential)" in f for f in fails))
        self.assertTrue(any("R18 (Delta Impact Unquantified)" in f for f in fails))

    def test_v12_gates_are_fail_closed_on_exception(self):
        with mock.patch("dr_engine.tools.ead_gate.validate_ead_section",
                        side_effect=RuntimeError("simulated malformed EAD")):
            fails, _, diag = ead_gate.run_v12_gates_fail_closed(
                _good_ead(), {}, set(), protocol_active=True, as_of=TODAY)
        self.assertTrue(any("B0 (v12 Gate Integrity / FAIL-CLOSED)" in f for f in fails))
        self.assertFalse(diag["passed"])

    def test_legacy_studies_are_warned_not_retroactively_failed(self):
        fails, warns, diag = ead_gate.run_v12_gates_fail_closed(
            "No EAD section.", {"domain": "quant"}, set(), protocol_active=False)
        self.assertFalse(fails)
        self.assertTrue(any("W_EAD_LEGACY_STUDY" in w for w in warns))
        self.assertEqual(diag["protocol_version"], "legacy")
        self.assertFalse(ead_gate.is_v12_protocol(None, {"domain": "quant"}))
        self.assertTrue(ead_gate.is_v12_protocol(None, {}, force=True))
        self.assertTrue(ead_gate.is_v12_protocol(
            None, {"protocol_version": "12.0"}))
        self.assertTrue(ead_gate.is_v12_protocol(
            None, {"dethroning": [_dethroning_record()]}))

    def test_verify_study_enforces_ead_on_v12_studies(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = _make_v12_study(Path(tmp), with_ead=False)
            rep = lean_engine.verify_study(d)
            self.assertTrue(rep.v12_protocol_active)
            self.assertTrue(any("R18 (Epistemic Alpha Delta Missing)" in f
                                for f in rep.failures), rep.failures)
            self.assertFalse(rep.ead_diagnostics.get("passed"))
            self.assertFalse(rep.passed)

    def test_verify_study_accepts_a_real_ead_and_dethroning_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = _make_v12_study(Path(tmp), with_ead=True, with_dethroning=True)
            rep = lean_engine.verify_study(d)
            self.assertTrue(rep.v12_protocol_active)
            self.assertTrue(rep.ead_diagnostics.get("passed"),
                            rep.failures)
            self.assertFalse(any("R18" in f or "B11" in f or
                                 "B0 (v12" in f for f in rep.failures),
                             rep.failures)
            self.assertTrue(any("W_EAD_PASS" in w for w in rep.warnings))
            self.assertEqual(rep.dethroning_diagnostics.get("claims_detected", 0) > 0,
                             True)

    def test_verify_study_rejects_v12_study_without_b11_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = _make_v12_study(Path(tmp), with_ead=True, with_dethroning=False)
            rep = lean_engine.verify_study(d)
            self.assertTrue(any("B11 (Premature Search Termination)" in f
                                for f in rep.failures), rep.failures)

    def test_strict_v12_forces_gates_on_a_legacy_study(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = _make_v12_study(Path(tmp), with_ead=False)
            (d / "study_spec.json").write_text(
                json.dumps({"domain": "general"}), encoding="utf-8")
            manifest_txt = (d / "report.md").read_text(encoding="utf-8")
            (d / "report.md").write_text(
                manifest_txt.replace('"protocol_version": "12.0"',
                                     '"protocol_version": "11.0"'),
                encoding="utf-8")
            rep = lean_engine.verify_study(d, force_v12=True)
            self.assertTrue(rep.v12_protocol_active)
            self.assertTrue(any("R18" in f for f in rep.failures))


# ===========================================================================
# FRONTIER 4 — Zero-fluff pipeline & malformed-input totality
# ===========================================================================
class TestZeroLagPipeline(unittest.TestCase):
    def test_ingest_compiles_dethrone_vectors_and_ead_checklist(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp) / "study"
            d.mkdir()
            spec = auto_spec.generate_autonomous_study_spec(
                "Who holds the deadlift world record of 510 kg?",
                offline_only=True)
            spec["inline_sources"] = {
                "https://forum.test/es/1": (
                    "En vivo vimos que superó a Björnsson: nuevo récord de 511 kg "
                    "in Birmingham, according to an eyewitness at the event. "
                    "The federation results page lists 511 kg as ratified. " * 2
                ),
            }
            (d / "study_spec.json").write_text(
                json.dumps(spec, ensure_ascii=False), encoding="utf-8")
            rc = lean_engine.cmd_ingest(
                argparse.Namespace(dir=str(d), spec=None))
            self.assertEqual(rc, 0)
            pack = (d / "context_pack.md").read_text(encoding="utf-8")
            self.assertIn("Mandatory Report Section (Rule R18)", pack)
            self.assertIn("Epistemic Alpha Delta", pack)
            self.assertIn("O_dethrone", pack)
            self.assertIn("GOLDEN NUGGET prior=x3.0", pack)
            self.assertIn("DTH-EN-D30", pack)

    def test_malformed_urls_never_raise(self):
        for bad in (None, 0, b"https://x.test", "", "ftp://x", "https://",
                    "javascript:alert(1)", object()):
            with self.subTest(bad=repr(bad)):
                self.assertFalse(http_resilience.is_safe_url(bad))
                r = http_resilience.resilient_fetch(bad, retries=1, timeout=None)
                self.assertFalse(r.ok)
                self.assertIsInstance(r.url, str)
                _, j = http_resilience.fetch_json(bad, retries=1)
                _, x = http_resilience.fetch_xml(bad, retries=1)
                self.assertIsNone(j)
                self.assertIsNone(x)
                f = http_resilience.fetch_with_fallbacks(bad, allow_fallbacks=True)
                self.assertFalse(f.ok)

    def test_malformed_trench_inputs_never_raise(self):
        self.assertIn("en", trench_miner.build_polyglot_queries(None))
        self.assertIn("is:issue", trench_miner.github_query(None, "en"))
        ledger = trench_miner.CollectorLedger()
        self.assertEqual(trench_miner.mine_rss_feed(
            "https://feed.test/{query}/{bad}", "record", ledger=ledger), [])
        self.assertTrue(any("malformed feed template" in r.error
                            for r in ledger.outcomes))
        self.assertEqual(trench_miner.mine_dethroning_vectors(
            [None, {}, 42, {"query": "x"}], timeout=0.1, max_items=0,
            max_vectors=0), [])
        self.assertEqual(insider_prior(None), 1.0)

    def test_ead_template_renders_all_three_contrast_parts(self):
        tpl = ead_gate.render_ead_template()
        for heading in ("Epistemic Alpha Delta", "Superficial Consensus",
                        "Trench Ground-Truth", "Delta Impact"):
            self.assertIn(heading, tpl)
        parsed = ead_gate.parse_ead_section(_good_ead())
        self.assertTrue(parsed["present"])
        self.assertEqual(set(parsed["sections"]),
                         {"superficial_consensus", "trench_ground_truth",
                          "delta_impact"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
