"""Offline tests for dr_engine/tools (report gate + citation verifier)."""

import sys
import tempfile
import textwrap
import unittest
import unittest.mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "dr_engine" / "tools"))
sys.path.insert(0, str(ROOT / "dr_engine" / "science"))
sys.path.insert(0, str(ROOT / "dr_engine" / "quant"))
sys.path.insert(0, str(ROOT / "dr_engine" / "evals"))

import check_report  # noqa: E402
import verify_citations  # noqa: E402
import extract_doc  # noqa: E402
import parse_pdf  # noqa: E402
import alpha_miner  # noqa: E402
import eval_runner  # noqa: E402

GOOD = """\
# Prop firm caps

**As of:** 2026-10-28

## Bottom line

FTMO caps allocation at $400,000 per trader [FTMO FAQ](https://ftmo.com/en/faq/a/). Confidence: High.

## Key findings

| # | Finding | Confidence | Evidence |
| :-- | :-- | :-- | :-- |
| 1 | BrightFunded caps funded capital at $400,000 | High | [BF](https://help.brightfunded.com/x) |
| 2 | Fintokei retired scaling in 2026 | Medium | [2] |

## Analysis

The5ers charges a 3.5% withdrawal fee.

- *Source:* [The5ers FAQ](https://the5ers.com/faqs/w/)

## Confidence

Mixed.

## Limitations

None material.

## Sources

| Ref | Source |
| :-- | :-- |
| [2] | [Fintokei](https://support.fintokei.com/en/articles/1) |
| [3] | [FunderPro](https://funderpro.com/terms/) |
"""


def _write(text: str) -> Path:
  f = tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8")
  f.write(textwrap.dedent(text))
  f.close()
  return Path(f.name)


class CheckReportTest(unittest.TestCase):

  def test_well_cited_report_passes(self):
    res = check_report.check(_write(GOOD))
    self.assertEqual(res.failures, [], res.uncited)
    self.assertEqual(res.coverage, 1.0)
    self.assertGreaterEqual(res.unique_domains, 3)

  def test_uncited_numbers_fail_coverage(self):
    text = GOOD.replace("## Analysis", "## Analysis\n\nFXIFY charges $6 per lot.\n\n"
                        "GetLeveraged was founded in 2025.\n\nThe edge is 0.056R per trade.")
    res = check_report.check(_write(text))
    self.assertLess(res.coverage, 0.8)
    self.assertTrue(any("coverage" in f for f in res.failures))
    self.assertTrue(any("FXIFY" in u["text"] for u in res.uncited))

  def test_source_tag_without_url_fails(self):
    text = GOOD.replace("The5ers charges", "[Source: The5ers FAQ] The5ers charges")
    res = check_report.check(_write(text))
    self.assertTrue(res.unlinkable_citations)
    self.assertTrue(any("without a URL" in f for f in res.failures))

  def test_numeric_ref_must_resolve_to_url(self):
    text = GOOD.replace("| [2] | [Fintokei](https://support.fintokei.com/en/articles/1) |",
                        "| [2] | Fintokei help centre |")
    res = check_report.check(_write(text))
    self.assertTrue(any("Fintokei retired" in u["text"] for u in res.uncited))

  def test_overclaim_and_missing_sections(self):
    text = "# T\n\n## Analysis\n\nThis edge is guaranteed to win 100% of the time.\n"
    res = check_report.check(_write(text))
    self.assertTrue(res.overclaims)
    self.assertIn("sources", res.missing_sections)
    self.assertIn("bottom_line", res.missing_sections)
    self.assertTrue(res.failures)

  def test_negated_overclaims_not_flagged(self):
    text = "# T\n\n## Analysis\n\nТова твърдение не е доказано и печалбата не е гарантирана. It is not proven.\n"
    res = check_report.check(_write(text))
    self.assertEqual(len(res.overclaims), 0)

  def test_code_and_mermaid_blocks_ignored(self):
    text = GOOD + "\n```mermaid\nflowchart TD\n  A[\"$6/lot 2025\"] --> B\n```\n"
    res = check_report.check(_write(text))
    self.assertEqual(res.failures, [])

  def test_bulgarian_headings_recognised(self):
    text = ("# Т\n\nДата: 2026-10-28\n\n## Резюме\n\nТекст.\n\n## Увереност\n\nСредна.\n\n"
            "## Ограничения\n\nНяма.\n\n## Източници\n\n- https://nra.bg/a\n")
    res = check_report.check(_write(text))
    self.assertEqual(res.missing_sections, [])

  def test_uncalibrated_probabilities_fails(self):
    # Interval without sample size
    t1 = GOOD.replace("FTMO caps allocation at $400,000 per trader",
                      "FTMO caps allocation with probability in range [0.02, 0.05, 0.12]")
    res1 = check_report.check(_write(t1))
    self.assertTrue(res1.uncalibrated_probabilities)
    self.assertTrue(any("uncalibrated" in f for f in res1.failures))

    # Prior π = 0.55 without sample size or calculation
    t2 = GOOD.replace("FTMO caps allocation at $400,000 per trader",
                      "We assign prior probability π = 0.55 to scaling success")
    res2 = check_report.check(_write(t2))
    self.assertTrue(res2.uncalibrated_probabilities)

  def test_calibrated_probabilities_with_sample_size_or_calculation_passes(self):
    # Empirical sample size n=100
    t1 = GOOD.replace("FTMO caps allocation at $400,000 per trader",
                      "FTMO caps allocation with probability in range [0.02, 0.05, 0.12] based on sample size n=100")
    res1 = check_report.check(_write(t1))
    self.assertEqual(res1.uncalibrated_probabilities, [])

    # Formal Calculation: label
    t2 = GOOD.replace("FTMO caps allocation at $400,000 per trader",
                      "Calculation: Model yields probability in range [0.02, 0.05, 0.12]")
    res2 = check_report.check(_write(t2))
    self.assertEqual(res2.uncalibrated_probabilities, [])

  def test_source_tier_inflation_in_sources_fails(self):
    t = GOOD + "\n| [4] | https://www.reddit.com/r/prop/comments/1 | T1 |\n"
    res = check_report.check(_write(t))
    self.assertTrue(res.source_tier_inflations)
    self.assertTrue(any("Source tier inflation" in f for f in res.failures))

  def test_known_killed_edge_fails_without_acknowledgment(self):
    t = GOOD.replace("FTMO caps allocation at $400,000 per trader",
                     "WM/R London 4 PM Fix FX Reversal е единственият оцелял шампион с предимство")
    res = check_report.check(_write(t))
    self.assertTrue(res.known_trap_violations)
    self.assertTrue(any("asserts known killed edge" in f for f in res.failures))

  def test_known_killed_edge_with_refutation_passes(self):
    t = GOOD.replace("FTMO caps allocation at $400,000 per trader",
                     "WM/R London 4 PM Fix FX Reversal беше опроверган в лабораторни тестове P31 (t = -5.2)")
    res = check_report.check(_write(t))
    self.assertEqual(res.known_trap_violations, [])

  def test_uncalibrated_probabilities_extended_forms(self):
    variants = [
        "Prior probability of 0.55 is recommended for model weighting",
        "We set prior = 0.55 in the decision framework",
        "The model uses prior: 0.55 before observing market regimes",
        "Субективна вероятност от 55% за успех на стратегията",
        "Вероятността се оценява в диапазона от 45% до 65% според опита",
        "We assume success probability in interval [0.02 - 0.12]",
        "Success rate is estimated in [2%, 5%, 12%]",
        "Probability bounded by [2% - 12%] without measurements",
    ]
    for v in variants:
      t = GOOD.replace("FTMO caps allocation at $400,000 per trader", v)
      res = check_report.check(_write(t))
      self.assertTrue(res.uncalibrated_probabilities, f"Failed to catch: {v}")
      self.assertTrue(any("uncalibrated" in f for f in res.failures), f"Missing failure for: {v}")

  def test_p_values_not_flagged_as_priors(self):
    p_statements = [
        "The difference in alpha returns was statistically significant (p = 0.04) [E001]",
        "A significance level of p < 0.05 was obtained across all out-of-sample runs [E001]",
        "The p-value = 0.01 indicates strong rejection of the null hypothesis [E001]",
    ]
    for s in p_statements:
      t = GOOD.replace("FTMO caps allocation at $400,000 per trader [E001].", s)
      res = check_report.check(_write(t))
      self.assertEqual(res.uncalibrated_probabilities, [], f"Falsely flagged p-value: {s}")

  def test_subdomain_and_github_io_source_tier_inflation(self):
    t_reddit_sub = GOOD + "\n| [4] | https://old.reddit.com/r/prop/comments/1 | T1 |\n"
    res1 = check_report.check(_write(t_reddit_sub))
    self.assertTrue(res1.source_tier_inflations)

    t_yt_sub = GOOD + "\n| [4] | https://m.youtube.com/watch?v=123 | Tier 2 |\n"
    res2 = check_report.check(_write(t_yt_sub))
    self.assertTrue(res2.source_tier_inflations)

    t_gh_io = GOOD + "\n| [4] | https://trader123.github.io/alpha-notes | T1 |\n"
    res3 = check_report.check(_write(t_gh_io))
    self.assertTrue(res3.source_tier_inflations)

    t_forum = GOOD + "\n| [4] | https://forum.propfirm.com/thread/1 | T2 |\n"
    res4 = check_report.check(_write(t_forum))
    self.assertTrue(res4.source_tier_inflations)

  def test_legal_conflation_trap_in_report(self):
    # Declaring kill hypothesis refuted based on Baštová fails
    t_bastova = GOOD.replace("FTMO caps allocation at $400,000 per trader",
                             "K1 refuted: analogous to CJEU Baštová, prizes are outside VAT")
    res1 = check_report.check(_write(t_bastova))
    self.assertTrue(any("Natural Person KYC != EU Consumer Status" in item["trap"]["name"]
                        for item in res1.known_trap_violations))

    # Declaring non-consumer refuted based on Natural Person KYC fails
    t_kyc = GOOD.replace("FTMO caps allocation at $400,000 per trader",
                         "K2 refuted: Natural Person KYC retains consumer protections under Directive 93/13/EEC")
    res2 = check_report.check(_write(t_kyc))
    self.assertTrue(any("Natural Person KYC != EU Consumer Status" in item["trap"]["name"]
                        for item in res2.known_trap_violations))


class MatchScoreTest(unittest.TestCase):
  PAGE = ("<html><body><p>At any given time, the total capital allocation across all "
          "accounts and products is limited to $400,000 per trader or strategy.</p>"
          "<script>var x = 1;</script></body></html>")

  def setUp(self):
    self.text = verify_citations.html_to_text(self.PAGE)

  def test_exact_quote_verified(self):
    q = "the total capital allocation across all accounts and products is limited to $400,000"
    self.assertEqual(verify_citations.match_score(q, self.text), 1.0)

  def test_typographic_quotes_and_whitespace_normalised(self):
    page = "It’s   limited to\n$400,000 — per trader."
    self.assertEqual(verify_citations.match_score("it's limited to $400,000 - per trader", page), 1.0)

  def test_ellipsis_fragments_verified(self):
    q = "At any given time, the total capital allocation... limited to $400,000 per trader"
    self.assertEqual(verify_citations.match_score(q, self.text), 1.0)

  def test_ellipsis_gap_bound(self):
    short_gap = "Start " + "word " * 20 + "End"  # ~106 chars
    self.assertEqual(verify_citations.match_score("Start ... End", short_gap), 1.0)
    long_gap = "Start " + "word " * 60 + "End"  # ~306 chars > 250
    score = verify_citations.match_score("Start ... End", long_gap)
    self.assertLess(score, 1.0)

  def test_ellipsis_negation_detection(self):
    # English: "not" in doc gap
    doc = "Trading bots are not allowed on this account."
    self.assertLess(verify_citations.match_score("Trading bots are ... allowed on this account", doc), 1.0)
    # English: "prohibited" in doc gap
    doc2 = "Scalping is prohibited under these terms."
    self.assertLess(verify_citations.match_score("Scalping is ... under these terms", doc2), 1.0)
    # Bulgarian: "не" in doc gap
    bg_doc = "Търговията с новини не е разрешена."
    self.assertLess(verify_citations.match_score("Търговията с новини ... разрешена", bg_doc), 1.0)
    # Bulgarian: "забранено" in doc gap
    bg_doc2 = "Използването на ботове е абсолютно забранено за фаза 1."
    self.assertLess(verify_citations.match_score("Използването на ботове е абсолютно ... за фаза 1", bg_doc2), 1.0)
    # Bulgarian inflections: "забранена" and "забранени"
    bg_doc3 = "Търговията с ботове е строго забранена тук."
    self.assertLess(verify_citations.match_score("Търговията с ботове е ... тук", bg_doc3), 1.0)
    # Chained ellipsis with negation in 3rd gap
    chained_doc = "Phase 1 is active, Phase 2 is standard, Phase 3 is not permitted."
    self.assertLess(verify_citations.match_score("Phase 1 ... Phase 2 ... Phase 3 ... permitted", chained_doc), 1.0)
    # Chained ellipsis without negation passes
    chained_pass = "Phase 1 is active, Phase 2 is standard, Phase 3 is fully permitted."
    self.assertEqual(verify_citations.match_score("Phase 1 ... Phase 2 ... Phase 3 ... permitted", chained_pass), 1.0)
    # Negation present in quote: match is accepted
    doc3 = "Trading bots are not permitted."
    self.assertEqual(verify_citations.match_score("Trading bots are not ... permitted", doc3), 1.0)
    # Bracketed ellipsis with spaces: [ ... ]
    bracketed_doc = "At any given time, the total capital allocation across all accounts is limited to $400,000 per trader."
    self.assertEqual(verify_citations.match_score("total capital [ ... ] limited to $400,000", bracketed_doc), 1.0)
    # Leading and trailing ellipsis around verbatim text
    self.assertEqual(verify_citations.match_score("... limited to $400,000 per trader ...", bracketed_doc), 1.0)

  def test_omission_without_ellipsis_is_not_verified(self):
    q = "the total capital allocation across all accounts is limited to $400,000 per trader"
    score = verify_citations.match_score(q, self.text)
    self.assertGreaterEqual(score, verify_citations.PARTIAL_THRESHOLD)
    self.assertLess(score, 1.0)

  def test_fabricated_quote_not_found(self):
    q = "the total capital allocation is unlimited for algorithmic traders and never capped"
    self.assertLess(verify_citations.match_score(q, self.text), verify_citations.PARTIAL_THRESHOLD)

  def test_script_text_stripped(self):
    self.assertNotIn("var x", self.text)


class CheckRecordTest(unittest.TestCase):

  def _cache(self, pages):
    cache = verify_citations.PageCache(timeout=1, jina=False)
    cache._cache.update(pages)  # pre-filled: no network
    return cache

  def test_statuses(self):
    page = "x " * 150 + "The fee is 3.5% per withdrawal."
    cache = self._cache({
        "https://a.test/ok": ("ok", page, "direct"),
        "https://a.test/dead": ("dead", "HTTP 404", "direct"),
        "https://a.test/wall": ("blocked", "empty page or bot wall", "direct"),
    })
    check = verify_citations.check_record
    self.assertEqual(check({"id": "1", "url": "https://a.test/ok",
                            "quote": "The fee is 3.5% per withdrawal"}, cache).status, "VERIFIED")
    self.assertEqual(check({"id": "2", "url": "https://a.test/ok",
                            "quote": "The fee is waived for funded traders"}, cache).status,
                     "NOT_FOUND")
    self.assertEqual(check({"id": "3", "url": "https://a.test/dead", "quote": "q"}, cache).status,
                     "DEAD")
    self.assertEqual(check({"id": "4", "url": "https://a.test/wall", "quote": "q"}, cache).status,
                     "BLOCKED")
    self.assertEqual(check({"id": "5", "url": "", "quote": "q"}, cache).status, "NOT_FOUND")

  def test_canonical_url_matching(self):
    self.assertEqual(verify_citations._canon("https://www.Example.org/a/#frag"),
                     verify_citations._canon("http://example.org/a"))


class PoliteHttpFallbackTest(unittest.TestCase):

  def test_api_surface(self):
    from _polite_http_fallback import http_client
    c = http_client.HttpClient("https://example.org/", qps=2.0, referer="r")
    self.assertEqual(c._url("api?q=1"), "https://example.org/api?q=1")
    self.assertEqual(c._url("https://other.org/x"), "https://other.org/x")
    self.assertIn(429, c.retryable_status_codes)
    err = http_client.HttpError("HTTP 404 for x:", 404, b"not here")
    self.assertEqual(err.status_code, 404)
    self.assertIn("not here", str(err))
    resp = http_client.HttpResponse(200, {}, b'{"a": 1}')
    self.assertEqual(resp.json(), {"a": 1})
    for name in ("DEFAULT_BACKOFF_BASE_SECS", "DEFAULT_BACKOFF_MAX_SECS", "DEFAULT_JITTER_SECS"):
      self.assertTrue(hasattr(http_client, name))



import contextlib  # noqa: E402
import io  # noqa: E402
import json  # noqa: E402

import evidence  # noqa: E402
import gate  # noqa: E402

SNAP = ("x " * 200 + "At any given time, the total capital allocation across all accounts "
        "is limited to $400,000 per trader. Commission is $3 per lot round turn.")
PLAN = """| SQ1 | caps | sizing | T1 | closed |
| K1 | scaling retired | contract | page | refuted | E002 |
| K2 | regulator warning | regulatory | site | unresolved | |
| K3 | fees kill edge | economics | inputs | unresolved | |
"""


def _study() -> Path:
  d = Path(tempfile.mkdtemp())
  (d / "sources").mkdir()
  (d / "sources" / "S001.txt").write_text(SNAP, encoding="utf-8")
  (d / "sources" / "index.jsonl").write_text(json.dumps(
      {"id": "S001", "url": "https://firm.test/faq", "fetched_at": "2026-10-28T10:00:00",
       "chars": len(SNAP), "sha256": evidence.sha256_text(SNAP)}) + "\n", encoding="utf-8")
  (d / "plan.md").write_text(PLAN, encoding="utf-8")
  with (d / "searches.jsonl").open("w", encoding="utf-8") as f:
    for i, purpose in enumerate(["SQ1"] * 6 + ["K1", "K2", "K3"] * 3):
      f.write(json.dumps({"id": f"Q{i:03d}", "purpose": purpose, "query": "q"}) + "\n")
  return d


def _add(d, **kw):
  args = ["add", "--dir", str(d), "--source", "S001", "--sq", "SQ1", "--tier", "T1",
          "--kind", "de_jure", "--stance", "supports", "--claim", "c"]
  for k, v in kw.items():
    args += [f"--{k}", v]
  with contextlib.redirect_stdout(io.StringIO()):
    return evidence.main(args)


class EvidencePipelineTest(unittest.TestCase):

  def test_add_refuses_unfetched_source_and_paraphrase(self):
    d = _study()
    self.assertEqual(_add(d, source="S099", quote="anything"), 1)
    self.assertEqual(_add(d, quote="allocation is capped at 400k dollars"), 1)
    self.assertEqual(_add(d, quote="total capital allocation across all accounts is limited "
                                   "to $400,000 per trader"), 0)
    self.assertEqual(len(evidence._jsonl(d / "evidence.jsonl")), 1)

  def test_add_refuses_tampered_snapshot(self):
    d = _study()
    (d / "sources" / "S001.txt").write_text(SNAP + " unlimited", encoding="utf-8")
    self.assertEqual(_add(d, quote="Commission is $3 per lot"), 1)

  def test_add_refuses_source_tier_inflation(self):
    d = _study()
    snap_reddit = "Reddit user post says FTMO denies payouts constantly." * 10
    (d / "sources" / "S002.txt").write_text(snap_reddit, encoding="utf-8")
    idx = evidence._jsonl(d / "sources" / "index.jsonl")
    idx.append({"id": "S002", "url": "https://www.reddit.com/r/propfirms/comments/123",
                "fetched_at": "2026-10-28T10:00:00", "chars": len(snap_reddit),
                "sha256": evidence.sha256_text(snap_reddit)})
    (d / "sources" / "index.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in idx), encoding="utf-8")

    # Marking community forum as T1 is refused
    rc_t1 = _add(d, source="S002", tier="T1", quote="FTMO denies payouts constantly")
    self.assertEqual(rc_t1, 1)

    # Marking community forum as T5 is accepted
    rc_t5 = _add(d, source="S002", tier="T5", quote="FTMO denies payouts constantly")
    self.assertEqual(rc_t5, 0)

  def test_add_refuses_personal_github_even_with_matching_publisher(self):
    d = _study()
    snap_code = "def alpha(): return 42" * 10
    (d / "sources" / "S003.txt").write_text(snap_code, encoding="utf-8")
    idx = evidence._jsonl(d / "sources" / "index.jsonl")
    idx.append({"id": "S003", "url": "https://raw.githubusercontent.com/VinayakChola/WorldQuant_Alphas/main/alpha.py",
                "fetched_at": "2026-10-28T10:00:00", "chars": len(snap_code),
                "sha256": evidence.sha256_text(snap_code)})
    (d / "sources" / "index.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in idx), encoding="utf-8")

    # Author matching publisher does NOT make a personal alpha repo T1
    rc = _add(d, source="S003", tier="T1", quote="def alpha(): return 42", publisher="VinayakChola")
    self.assertEqual(rc, 1)

  def test_add_refuses_community_subdomains(self):
    d = _study()
    snap_sub = "YouTube video comments claim strategy is dead." * 10
    (d / "sources" / "S004.txt").write_text(snap_sub, encoding="utf-8")
    idx = evidence._jsonl(d / "sources" / "index.jsonl")
    idx.append({"id": "S004", "url": "https://m.youtube.com/watch?v=123",
                "fetched_at": "2026-10-28T10:00:00", "chars": len(snap_sub),
                "sha256": evidence.sha256_text(snap_sub)})
    (d / "sources" / "index.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in idx), encoding="utf-8")

    rc = _add(d, source="S004", tier="T2", quote="YouTube video comments claim strategy is dead")
    self.assertEqual(rc, 1)

  def test_numbers_normalisation(self):
    self.assertEqual(gate.numbers("$400,000"), gate.numbers("400000"))
    self.assertIn(400000.0, gate.numbers("$400K"))
    self.assertIn(3.5, gate.numbers("3,5%"))
    self.assertNotIn(100.0, gate.numbers("US100 on MT5 [E001]"))
    self.assertEqual(gate.material(gate.numbers("2-Step, 3 firms")), set())

  def test_single_digit_units_preserved(self):
    nums = gate.numbers("fee is $6, 1% loss, 5 min window, 4% drawdown")
    mat = gate.material(nums)
    self.assertIn(6.0, mat)
    self.assertIn(1.0, mat)
    self.assertIn(5.0, mat)
    self.assertIn(4.0, mat)
    # Spelled-out and Bulgarian units
    spelled = gate.numbers("6 dollars fee, 1 percent loss, 4 percent drawdown, 5 minutes, 4 pt, 5 bps, 2 pips")
    mat_spelled = gate.material(spelled)
    for expected in (6.0, 1.0, 4.0, 5.0, 2.0):
      self.assertIn(expected, mat_spelled)
    bg = gate.numbers("5 минути, 1 процент, 4 процента, 5 лева, 6 долара")
    mat_bg = gate.material(bg)
    for expected in (5.0, 1.0, 4.0, 6.0):
      self.assertIn(expected, mat_bg)
    # Word numbers
    words = gate.numbers("five minutes, пет минути, two percent")
    mat_words = gate.material(words)
    self.assertIn(5.0, mat_words)
    self.assertIn(2.0, mat_words)
    # Bare unannotated digits are dropped
    bare = gate.numbers("1. step one, 2) step two, 2-Step model, 3 firms")
    self.assertEqual(gate.material(bare), set())

  def test_multiplier_leak(self):
    nums = gate.numbers("total allocation is 100 million dollars")
    self.assertIn(100000000.0, nums)
    self.assertNotIn(100.0, nums)
    nums_k = gate.numbers("funded with 50k")
    self.assertIn(50000.0, nums_k)
    self.assertNotIn(50.0, nums_k)
    nums_bg = gate.numbers("оборот от 10 млрд.")
    self.assertIn(10000000000.0, nums_bg)
    self.assertNotIn(10.0, nums_bg)

  def test_iso_date_binding(self):
    nums1 = gate.numbers("warning published 2026-04-07")
    nums2 = gate.numbers("warning published 2026-11-29")
    self.assertIn("2026-04-07", nums1)
    self.assertIn("2026-11-29", nums2)
    self.assertNotIn("2026-04-07", nums2)

  def test_cmd_fetch_jina_fallback(self):
    d = _study()
    args = unittest.mock.Mock(dir=str(d), urls=["https://botwall.test/page"],
                              refresh=False, timeout=10)
    mock_resp = unittest.mock.Mock(url="https://botwall.test/page", status_code=403,
                                   headers={"Content-Type": "text/html"})
    mock_resp.text = "403 Forbidden - Cloudflare Bot Management"
    with unittest.mock.patch("requests.get", return_value=mock_resp), \
         unittest.mock.patch("evidence.fetch_jina",
                             return_value=("ok", "x " * 200 + "Valid jina text content with enough chars")):
      rc = evidence.cmd_fetch(args)
      self.assertEqual(rc, 0)
      idx = evidence._jsonl(d / "sources" / "index.jsonl")
      self.assertTrue(any(r.get("via") == "jina" for r in idx))

    # Test HTTP 503 bot challenge fallback
    args503 = unittest.mock.Mock(dir=str(d), urls=["https://botwall503.test/page"],
                                 refresh=False, timeout=10)
    mock_503 = unittest.mock.Mock(url="https://botwall503.test/page", status_code=503,
                                  headers={"Content-Type": "text/html"})
    mock_503.text = "503 Service Temporarily Unavailable - Just a moment"
    with unittest.mock.patch("requests.get", return_value=mock_503), \
         unittest.mock.patch("evidence.fetch_jina",
                             return_value=("ok", "x " * 200 + "Content rescued via jina")):
      rc = evidence.cmd_fetch(args503)
      self.assertEqual(rc, 0)
      idx = evidence._jsonl(d / "sources" / "index.jsonl")
      self.assertTrue(any(r.get("url") == "https://botwall503.test/page" and r.get("via") == "jina" for r in idx))


class GateTest(unittest.TestCase):

  def _run(self, d, report):
    (d / "report.md").write_text(report, encoding="utf-8")
    g = gate.Gate(d)
    g.evidence_stage(min_searches=12, kill_share=0.3)
    g.report_stage(d / "report.md", min_coverage=0.9, min_urls=1)
    return [f.split()[0] for f in g.fail]

  def _setup(self):
    d = _study()
    _add(d, quote="limited to $400,000 per trader")
    _add(d, sq="K1", stance="contradicts", quote="Commission is $3 per lot round turn")
    return d

  GOOD = """# T

**As of:** 2026-10-28

## Bottom line

The cap is $400,000 per trader [E001]. Commission is $3 per lot [E002].

## Kill hypotheses

K1 refuted.

## Sources

| [E001] | [FAQ](https://firm.test/faq) |
| [E002] | [FAQ](https://firm.test/faq) |
"""

  def test_good_report_passes(self):
    d = self._setup()
    codes = self._run(d, self.GOOD)
    self.assertEqual([c for c in codes if c != "R1"], [])

  def test_unbound_number_fails_r3(self):
    d = self._setup()
    self.assertIn("R3", self._run(d, self.GOOD.replace("$400,000 per trader [E001]",
                                                        "$500,000 per trader [E001]")))

  def test_calculation_label_exempts_r3(self):
    d = self._setup()
    report = self.GOOD.replace("## Kill", "Calculation: 2 x $400,000 = $800,000 [E001].\n\n## Kill")
    self.assertNotIn("R3", self._run(d, report))

  def test_unaddressed_contradiction_fails_r4(self):
    d = self._setup()
    self.assertIn("R4", self._run(d, self.GOOD.replace(" Commission is $3 per lot [E002].", "")))

  def test_missing_eid_and_self_score(self):
    d = self._setup()
    codes = self._run(d, self.GOOD.replace("[E001].", "[E001]. Quality 10/10.").replace(
        "## Kill", "Fees are 7% higher elsewhere.\n\n## Kill"))
    self.assertIn("R2", codes)
    self.assertIn("R6", codes)

  def test_kill_budget_and_count(self):
    d = self._setup()
    (d / "searches.jsonl").write_text("".join(
        json.dumps({"purpose": "SQ1", "query": "q"}) + "\n" for _ in range(20)), encoding="utf-8")
    (d / "plan.md").write_text("| SQ1 | a | b | T1 | c |\n| K1 | x | y | z | unresolved | |\n",
                               encoding="utf-8")
    g = gate.Gate(d)
    g.evidence_stage(min_searches=12, kill_share=0.3)
    codes = [f.split()[0] for f in g.fail]
    self.assertIn("E3", codes)
    self.assertIn("E4", codes)

  def test_iso_date_mismatch_fails_r3(self):
    d = self._setup()
    report = self.GOOD.replace("The cap is $400,000 per trader [E001].",
                               "Warning published 2026-11-29 [E001].")
    codes = self._run(d, report)
    self.assertIn("R3", codes)

  def test_live_sample_dead_link_fails(self):
    d = self._setup()
    g = gate.Gate(d)
    g.evidence_stage(min_searches=12, kill_share=0.3)
    with unittest.mock.patch("gate.fetch_page", return_value={"ok": False, "error": "HTTP 404"}):
      g.live_sample(1)
    self.assertTrue(any(f.startswith("L1") for f in g.fail))
    self.assertFalse(any(w.startswith("L1") for w in g.warn))

  def test_e6_source_tier_inflation_fails(self):
    d = self._setup()
    # Add an evidence record with an inflated community tier
    snap_reddit = "Reddit user post says FTMO denies payouts constantly." * 10
    (d / "sources" / "S002.txt").write_text(snap_reddit, encoding="utf-8")
    idx = evidence._jsonl(d / "sources" / "index.jsonl")
    idx.append({"id": "S002", "url": "https://www.reddit.com/r/propfirms/comments/123",
                "fetched_at": "2026-10-28T10:00:00", "chars": len(snap_reddit),
                "sha256": evidence.sha256_text(snap_reddit)})
    (d / "sources" / "index.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in idx), encoding="utf-8")
    evid = evidence._jsonl(d / "evidence.jsonl")
    evid.append({"id": "E003", "source": "S002", "url": "https://www.reddit.com/r/propfirms/comments/123",
                 "sq": "SQ1", "tier": "T1", "kind": "de_facto", "stance": "supports",
                 "quote": "FTMO denies payouts constantly", "claim": "Reddit says denials happen",
                 "title": "", "publisher": "", "published": "", "accessed": "2026-10-28",
                 "snapshot_sha256": evidence.sha256_text(snap_reddit)})
    (d / "evidence.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in evid), encoding="utf-8")

    g = gate.Gate(d)
    g.evidence_stage(min_searches=12, kill_share=0.3)
    codes = [f.split()[0] for f in g.fail]
    self.assertIn("E6", codes)

  def test_r7_uncalibrated_prior_fails(self):
    d = self._setup()
    report = self.GOOD.replace("The cap is $400,000 per trader [E001].",
                               "Извод: Използва се предварителен ориентир π = 0.55 за успех [E001].")
    codes = self._run(d, report)
    self.assertIn("R7", codes)

  def test_r7_calibrated_or_calculation_passes(self):
    d = self._setup()
    # Calculation: label exempts R7
    rep_calc = self.GOOD.replace("The cap is $400,000 per trader [E001].",
                                 "Calculation: Формула с параметри от модела дава π = 0.55 [E001].")
    codes_calc = self._run(d, rep_calc)
    self.assertNotIn("R7", codes_calc)

    # Sample size n=100 exempts R7
    rep_sample = self.GOOD.replace("The cap is $400,000 per trader [E001].",
                                   "Оценка на база извадка n=100: вероятността за успех е в диапазона [0.02, 0.05, 0.12] [E001].")
    codes_sample = self._run(d, rep_sample)
    self.assertNotIn("R7", codes_sample)

  def test_r8_known_killed_edge_fails(self):
    d = self._setup()
    report = self.GOOD.replace("The cap is $400,000 per trader [E001].",
                               "WM/R London 4 PM Fix FX Reversal е единственият оцелял шампион [E001].")
    codes = self._run(d, report)
    self.assertIn("R8", codes)

  def test_r8_known_killed_edge_with_refutation_passes(self):
    d = self._setup()
    report = self.GOOD.replace("The cap is $400,000 per trader [E001].",
                               "WM/R London 4 PM Fix FX Reversal беше опроверган в лабораторни тестове P31 (t = -5.2) [E001].")
    codes = self._run(d, report)
    self.assertNotIn("R8", codes)

  def test_r8_legal_conflation_trap_fails(self):
    d = self._setup()
    report = self.GOOD.replace(
        "K1 refuted.",
        "K1 refuted: analogous to CJEU Baštová, prizes are outside VAT [E001]."
    )
    codes = self._run(d, report)
    self.assertIn("R8", codes)

  def test_r8_legal_conflation_with_proper_caveat_passes(self):
    d = self._setup()
    report = self.GOOD.replace(
        "K1 refuted.",
        "K1 unresolved: CJEU Baštová is untested in court and commercial contract overrides data reward [E001]."
    )
    codes = self._run(d, report)
    self.assertNotIn("R8", codes)

  def test_r8_seasonal_panel_conditional_approval_fails(self):
    d = self._setup()
    report = self.GOOD.replace(
        "The cap is $400,000 per trader [E001].",
        "Даваме условно одобрение на мулти-активен панел по сезонност за търговия [E001]."
    )
    codes = self._run(d, report)
    self.assertIn("R8", codes)

  def test_r8_annual_swap_vs_g9_floor_fails(self):
    d = self._setup()
    report = self.GOOD.replace(
        "The cap is $400,000 per trader [E001].",
        "Годишен суап от 8.5% p.a. надхвърля пода на G9 [E001]."
    )
    codes = self._run(d, report)
    self.assertIn("R8", codes)

  def test_r8_stock_cfd_double_counted_swap_fails(self):
    d = self._setup()
    report = self.GOOD.replace(
        "The cap is $400,000 per trader [E001].",
        "Книга от акции с 850 bp суап разход води до провал на акаунта [E001]."
    )
    codes = self._run(d, report)
    self.assertIn("R8", codes)

  def test_r8_fx_majors_s2_geometry_fails(self):
    d = self._setup()
    report = self.GOOD.replace(
        "The cap is $400,000 per trader [E001].",
        "Основни FX двойки като EURUSD покриват S2 при геометрията на Pillar 1 [E001]."
    )
    codes = self._run(d, report)
    self.assertIn("R8", codes)

  def test_r8_generic_ev_table_fails(self):
    d = self._setup()
    report = self.GOOD.replace(
        "The cap is $400,000 per trader [E001].",
        "Очакваната стойност е 38500 EUR брутно при тегла 50 / 35 / 15 и p* 2.6% [E001]."
    )
    codes = self._run(d, report)
    self.assertIn("R8", codes)


class ExtractDocTest(unittest.TestCase):

  def test_extract_doc_offline(self):
    with tempfile.TemporaryDirectory() as tmpdir:
      doc_path = Path(tmpdir) / "test_doc.txt"
      doc_path.write_text(
          "Fintokei applies a 3% open risk cap on all trades. "
          "The daily loss limit is 5% based on previous day balance.",
          encoding="utf-8"
      )
      html_path = Path(tmpdir) / "vis.html"
      json_path = Path(tmpdir) / "res.json"

      res = extract_doc.run_extraction(
          file_path=str(doc_path),
          category="prop_rules",
          offline=True,
          html_out=str(html_path),
          json_out=str(json_path),
      )
      self.assertGreaterEqual(len(res), 1)
      self.assertTrue(html_path.exists())
      self.assertTrue(json_path.exists())
      self.assertIn("3%", res[0]["text"])


class PdfParserTest(unittest.TestCase):

  def test_clean_scientific_text(self):
    raw = "The ﬁrst speciﬁcation of insti-\ntutional volume was reported—in ‘Table 1’."
    cleaned = parse_pdf.clean_scientific_text(raw)
    self.assertIn("first specification of institutional volume", cleaned)
    self.assertIn("'Table 1'", cleaned)
    self.assertNotIn("ﬁ", cleaned)
    self.assertNotIn("-\n", cleaned)

  def test_strip_headers_and_footers(self):
    pages = [
        "JOURNAL OF FINANCIAL ECONOMICS\nContent of page 1 with data.\nPage 1 of 3",
        "JOURNAL OF FINANCIAL ECONOMICS\nContent of page 2 with more data.\nPage 2 of 3",
        "JOURNAL OF FINANCIAL ECONOMICS\nContent of page 3 conclusion.\nPage 3 of 3",
    ]
    cleaned = parse_pdf.strip_headers_and_footers(pages)
    self.assertEqual(len(cleaned), 3)
    for p in cleaned:
      self.assertNotIn("JOURNAL OF FINANCIAL ECONOMICS", p)
      self.assertNotIn("Page 1 of 3", p)
      self.assertNotIn("Page 2 of 3", p)
      self.assertNotIn("Page 3 of 3", p)
    self.assertIn("Content of page 1 with data.", cleaned[0])


class AlphaMinerTest(unittest.TestCase):

  def test_generate_candidate_alphas(self):
    alphas = alpha_miner.generate_candidate_alphas(count=5, category="mean_reversion", seed=123)
    self.assertEqual(len(alphas), 5)
    for a in alphas:
      self.assertEqual(a.category, "mean_reversion")
      self.assertTrue(len(a.expression) > 0)
      self.assertIn("f1", a.parameters)

  def test_synthetic_evaluate_alpha(self):
    alpha = alpha_miner.AlphaFormula(
        expression="-ts_rank(close, 10)",
        category="mean_reversion",
        parameters={"f1": "close", "d1": 10},
    )
    metrics = alpha_miner.synthetic_evaluate_alpha(alpha, seed=42)
    self.assertIn("gross_sharpe", metrics)
    self.assertIn("net_sharpe", metrics)
    self.assertIn("turnover_pct", metrics)
    self.assertIn("mean_ic", metrics)
    self.assertGreater(metrics["gross_sharpe"], 0)

  def test_expression_similarity(self):
    e1 = "-ts_rank(close, 10)"
    e2 = "-ts_rank(close, 20)"
    e3 = "ts_corr(volume, vwap, 5)"
    sim_high = alpha_miner.compute_expression_similarity(e1, e2)
    sim_low = alpha_miner.compute_expression_similarity(e1, e3)
    self.assertGreater(sim_high, sim_low)
    self.assertEqual(alpha_miner.compute_expression_similarity(e1, e1), 1.0)

  def test_library_orthogonality(self):
    lib = [
        alpha_miner.AlphaFormula("-ts_rank(close, 10)", "mean_reversion", {}),
        alpha_miner.AlphaFormula("ts_corr(open, volume, 20)", "momentum", {}),
    ]
    cand_similar = alpha_miner.AlphaFormula("-ts_rank(close, 15)", "mean_reversion", {})
    cand_distinct = alpha_miner.AlphaFormula("decay_linear(vwap, 30)", "momentum", {})

    ok_sim, reason = alpha_miner.check_library_orthogonality(cand_similar, lib, max_similarity=0.70)
    self.assertFalse(ok_sim)
    self.assertIn("High similarity", reason)

    ok_dist, _ = alpha_miner.check_library_orthogonality(cand_distinct, lib, max_similarity=0.70)
    self.assertTrue(ok_dist)


class EvalRunnerTest(unittest.TestCase):

  def test_epistemic_eval_suite_passes(self):
    summary = eval_runner.run_benchmark_suite()
    self.assertEqual(summary["failed_cases"], 0)
    self.assertEqual(summary["accuracy_pct"], 100.0)
    self.assertGreaterEqual(summary["total_cases"], 32)


import argparse  # noqa: E402
import calc  # noqa: E402
import discover  # noqa: E402
import formula  # noqa: E402


class DeepResearchV3Test(unittest.TestCase):
  """Tests for Deep Research v3.0 upgrades: table Row-1 audit, encyclopedia E6,
  anti-duplication & depth floor E7, deterministic [C###] E8, Inference:/Извод: R3 closure,
  anti-bypass ceiling R9, mechanical confidence cap R10, formula.py, and discover.py."""

  def test_markdown_table_first_data_row_audited(self):
    # Previously, the first data row right below `| :-- | :-- |` was silently dropped!
    t = GOOD.replace(
        "| 1 | BrightFunded caps funded capital at $400,000 | High | [BF](https://help.brightfunded.com/x) |",
        "| 1 | Uncited firm charges $999 upfront fee in 2026 | High | none |",
    )
    res = check_report.check(_write(t))
    self.assertTrue(any("Uncited firm charges $999" in u["text"] for u in res.uncited))

  def test_tertiary_encyclopedia_tier_inflation_caught(self):
    t_wiki_t2 = GOOD + "\n| [4] | https://en.wikipedia.org/wiki/Sharpe_ratio | T2 |\n"
    res_t2 = check_report.check(_write(t_wiki_t2))
    self.assertTrue(res_t2.source_tier_inflations)

    t_inv_t3 = GOOD + "\n| [4] | https://www.investopedia.com/terms/s/sharperatio.asp | T3 |\n"
    res_t3 = check_report.check(_write(t_inv_t3))
    self.assertTrue(res_t3.source_tier_inflations)

    t_wiki_t4 = GOOD + "\n| [4] | https://en.wikipedia.org/wiki/Sharpe_ratio | T4 |\n"
    res_t4 = check_report.check(_write(t_wiki_t4))
    self.assertEqual(res_t4.source_tier_inflations, [])

  def test_add_refuses_wikipedia_as_t2_and_stance_flip(self):
    d = _study()
    snap_wiki = "Sequential probability ratio test was developed by Abraham Wald in 1945." * 8
    (d / "sources" / "S002.txt").write_text(snap_wiki, encoding="utf-8")
    idx = evidence._jsonl(d / "sources" / "index.jsonl")
    idx.append({
        "id": "S002",
        "url": "https://en.wikipedia.org/wiki/Sequential_probability_ratio_test",
        "fetched_at": "2026-10-28T10:00:00",
        "chars": len(snap_wiki),
        "sha256": evidence.sha256_text(snap_wiki),
    })
    (d / "sources" / "index.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in idx), encoding="utf-8"
    )
    # Wikipedia as T2 refused, as T4 accepted
    self.assertEqual(_add(d, source="S002", tier="T2", quote="developed by Abraham Wald in 1945"), 1)
    self.assertEqual(_add(d, source="S002", tier="T4", stance="supports", quote="developed by Abraham Wald in 1945"), 0)
    # Logging identical quote on S002 with opposite stance ('contradicts') refused
    self.assertEqual(_add(d, source="S002", tier="T4", sq="K1", stance="contradicts", quote="developed by Abraham Wald in 1945"), 1)

  def _run_gate(self, d: Path, report_text: str) -> list[str]:
    (d / "report.md").write_text(report_text, encoding="utf-8")
    g = gate.Gate(d)
    g.evidence_stage(min_searches=12, kill_share=0.30)
    g.report_stage(d / "report.md", min_coverage=0.90, min_urls=1)
    return [f.split()[0] for f in g.fail]

  def test_izvod_and_formulaless_calculation_fail_r3(self):
    d = _study()
    _add(d, quote="limited to $400,000 per trader")
    _add(d, sq="K1", stance="contradicts", quote="Commission is $3 per lot round turn")

    # 1. Bulgarian 'Извод:' cannot smuggle unbound numbers
    rep_izvod = GateTest.GOOD.replace(
        "The cap is $400,000 per trader [E001].",
        "Извод: Реалната очаквана доходност е 18.5% годишно [E001].",
    )
    self.assertIn("R3", self._run_gate(d, rep_izvod))

    # 2. English 'Inference:' cannot smuggle unbound numbers
    rep_inf = GateTest.GOOD.replace(
        "The cap is $400,000 per trader [E001].",
        "Inference: Effective slippage is 4.2 bps per trade [E001].",
    )
    self.assertIn("R3", self._run_gate(d, rep_inf))

    # 3. Formula-less 'Calculation:' without operator or [C###] fails R3
    rep_bad_calc = GateTest.GOOD.replace(
        "The cap is $400,000 per trader [E001].",
        "Calculation: Combined allocation across accounts reaches $800,000 [E001].",
    )
    self.assertIn("R3", self._run_gate(d, rep_bad_calc))

    # 4. Qualitative 'Inference:' with NO unbound numbers passes R3
    rep_qual_inf = GateTest.GOOD + "\nInference: The $400,000 cap restricts multi-strategy scaling [E001].\n"
    self.assertNotIn("R3", self._run_gate(d, rep_qual_inf))

  def test_verified_c_record_binds_numbers_and_tampering_fails_e8(self):
    d = _study()
    _add(d, quote="limited to $400,000 per trader")
    _add(d, sq="K1", stance="contradicts", quote="Commission is $3 per lot round turn")

    crec = calc.record_calculation(
        study_dir=d,
        label="Two max-allocated accounts after 20% haircut",
        expr="2 * cap * (1 - haircut)",
        variables={"cap": 400000, "haircut": 0.20},
        cited_eids=["E001"],
        unit="USD",
    )
    self.assertEqual(crec["id"], "C001")
    self.assertEqual(crec["result"], 640000.0)

    # Prose binds $640,000 and 20% via [E001, C001] with NO 'Calculation:' bypass label!
    rep_c = GateTest.GOOD.replace(
        "## Kill",
        "Net effective allocation across two accounts after 20% haircut is $640,000 [E001, C001].\n\n## Kill",
    )
    codes = self._run_gate(d, rep_c)
    self.assertNotIn("R3", codes)
    self.assertNotIn("E8", codes)

    # Tampering with stored result in calculations.jsonl triggers E8
    tampered = dict(crec)
    tampered["result"] = 999999.0
    (d / "calculations.jsonl").write_text(json.dumps(tampered) + "\n", encoding="utf-8")
    codes_tampered = self._run_gate(d, rep_c)
    self.assertIn("E8", codes_tampered)

  def test_e7_shallow_t4_depth_floor_fails(self):
    d = _study()
    _add(d, quote="limited to $400,000 per trader")  # 1 T1 item
    snap_t4 = "Alpha Beta Gamma Delta Epsilon Zeta Eta Theta." * 12
    (d / "sources" / "S002.txt").write_text(snap_t4, encoding="utf-8")
    idx = evidence._jsonl(d / "sources" / "index.jsonl")
    idx.append({
        "id": "S002",
        "url": "https://en.wikipedia.org/wiki/Proprietary_trading",
        "fetched_at": "2026-10-28T10:00:00",
        "chars": len(snap_t4),
        "sha256": evidence.sha256_text(snap_t4),
    })
    (d / "sources" / "index.jsonl").write_text("".join(json.dumps(r) + "\n" for r in idx), encoding="utf-8")
    # Add 3 T4 items -> 1/4 = 25% T1-T3 (< 50% required)
    _add(d, source="S002", tier="T4", sq="SQ1", quote="Alpha Beta Gamma")
    _add(d, source="S002", tier="T4", sq="K1", stance="contradicts", quote="Delta Epsilon Zeta")
    _add(d, source="S002", tier="T4", sq="K2", quote="Eta Theta")

    g = gate.Gate(d)
    g.evidence_stage(min_searches=12, kill_share=0.30)
    codes = [f.split()[0] for f in g.fail]
    self.assertIn("E7", codes)

  def test_r9_excessive_inline_calculation_bypasses_fail(self):
    d = _study()
    _add(d, quote="limited to $400,000 per trader")
    _add(d, sq="K1", stance="contradicts", quote="Commission is $3 per lot round turn")

    inline_flood = "\n\n".join([
        "Calculation: 1 * $400,000 + $100 = $400,100 [E001].",
        "Calculation: 2 * $400,000 = $800,000 [E001].",
        "Calculation: 3 * $400,000 = $1,200,000 [E001].",
        "Calculation: 4 * $400,000 = $1,600,000 [E001].",
    ])
    rep = GateTest.GOOD.replace("## Kill", inline_flood + "\n\n## Kill")
    codes = self._run_gate(d, rep)
    self.assertIn("R9", codes)

  def test_r10_mechanical_confidence_cap_enforced(self):
    d = _study()
    _add(d, quote="limited to $400,000 per trader")
    _add(d, sq="K1", stance="contradicts", quote="Commission is $3 per lot round turn")
    # Study has 1 domain and 2 unresolved kills -> formula.py caps confidence below High
    rep_overclaim = GateTest.GOOD.replace(
        "**As of:** 2026-10-28",
        "**As of:** 2026-10-28\n- **Overall Confidence:** High",
    )
    self.assertIn("R10", self._run_gate(d, rep_overclaim))

    rep_calibrated = GateTest.GOOD.replace(
        "**As of:** 2026-10-28",
        "**As of:** 2026-10-28\n- **Overall Confidence:** Low",
    )
    self.assertNotIn("R10", self._run_gate(d, rep_calibrated))

  def test_calc_safe_eval_and_decision_matrix(self):
    self.assertAlmostEqual(calc.safe_eval("ev_sunk_fee(0.40, 4000, 540, 20, 0.10, 0.20)"), 592.0)
    self.assertAlmostEqual(calc.safe_eval("kelly(0.55, 1.0)"), 0.10)
    self.assertAlmostEqual(calc.safe_eval("half_kelly(0.55, 1.0)"), 0.05)
    self.assertLess(calc.safe_eval("wilson_lower(40, 100)"), 0.40)
    self.assertGreater(calc.safe_eval("wilson_upper(40, 100)"), 0.40)
    self.assertAlmostEqual(calc.safe_eval("norm_cdf(0)"), 0.50)

    # Disallow unsafe constructs
    with self.assertRaises(ValueError):
      calc.safe_eval("__import__('os').system('echo x')")
    with self.assertRaises(ValueError):
      calc.safe_eval("2 ** 5000")

    d = _study()
    _add(d, quote="limited to $400,000 per trader")
    res = calc.build_decision_matrix(
        study_dir=d,
        title="FTMO 100k Challenge",
        cost=540.0,
        base_prob=0.42,
        base_payoff=4000.0,
        bear_prob=0.25,
        bear_payoff=2500.0,
        stress_prob=0.10,
        stress_payoff=1500.0,
        friction=25.0,
        tax_rate=0.10,
        haircut=0.20,
        cited_eids=["E001"],
    )
    self.assertEqual(len(calc.load_calculations(d)), 6)
    self.assertEqual(calc.verify_calculations(d, known_evidence_ids={"E001"}), [])
    self.assertIn("Flip Trigger: Min Win Prob", res["markdown"])
    self.assertIn("C006", res["markdown"])

  def test_formula_high_confidence_on_rigorous_multi_domain_study(self):
    d = Path(tempfile.mkdtemp())
    (d / "sources").mkdir()
    domains = ["https://statute.gov.test/law", "https://regulator.gov.test/reg",
               "https://journal.org.test/paper", "https://exchange.com.test/spec"]
    idx_rows = []
    for i, u in enumerate(domains, 1):
      sid = f"S{i:03d}"
      txt = ("x " * 120) + f"Clause {i} specifies limit 100 USD and fee 5%."
      (d / "sources" / f"{sid}.txt").write_text(txt, encoding="utf-8")
      idx_rows.append({
          "id": sid, "url": u, "fetched_at": "2026-10-28T10:00:00",
          "chars": len(txt), "sha256": evidence.sha256_text(txt),
      })
    (d / "sources" / "index.jsonl").write_text("".join(json.dumps(r) + "\n" for r in idx_rows), encoding="utf-8")
    (d / "plan.md").write_text(
        "| SQ1 | q1 | d1 | T1 | closed |\n"
        "| K1 | k1 | contract | t1 | refuted | E002 |\n"
        "| K2 | k2 | regulatory | t2 | refuted | E003 |\n"
        "| K3 | k3 | economics | t3 | confirmed | E004 |\n",
        encoding="utf-8",
    )
    with (d / "searches.jsonl").open("w", encoding="utf-8") as f:
      for i, p in enumerate(["SQ1"] * 6 + ["K1", "K2", "K3"] * 3):
        f.write(json.dumps({"id": f"Q{i:03d}", "purpose": p, "query": "q"}) + "\n")

    _add(d, source="S001", sq="SQ1", tier="T1", quote="Clause 1 specifies limit 100 USD and fee 5%.")
    _add(d, source="S002", sq="SQ1", tier="T2", quote="Clause 2 specifies limit 100 USD and fee 5%.")
    _add(d, source="S002", sq="K1", tier="T2", quote="Clause 2 specifies limit 100 USD")
    _add(d, source="S003", sq="K2", tier="T3", quote="Clause 3 specifies limit 100 USD")
    _add(d, source="S004", sq="K3", tier="T1", stance="contradicts", quote="fee 5%")

    calc.record_calculation(d, "Net after 5% fee", "100 * (1 - 0.05)", {}, ["E001"], "USD")
    (d / "report.md").write_text(
        "# Study\n\n**As of:** 2026-10-28\n- **Overall Confidence:** High\n\n"
        "## Bottom line\n\nLimit is 100 USD [E001, E002]. Net after 5% fee is 95 USD [E001, E005, C001].\n\n"
        "## Kill hypotheses\n\nK1 refuted [E003]. K2 refuted [E004]. K3 confirmed 5% fee [E005].\n\n"
        "## Sources\n\n"
        "| [E001] | https://statute.gov.test/law |\n"
        "| [E002] | https://regulator.gov.test/reg |\n"
        "| [E003] | https://regulator.gov.test/reg |\n"
        "| [E004] | https://journal.org.test/paper |\n"
        "| [E005] | https://exchange.com.test/spec |\n",
        encoding="utf-8",
    )
    sc = formula.compute_epistemic_score(d)
    self.assertEqual(sc["max_confidence"], "High", sc["limiting_factors"])
    self.assertGreaterEqual(sc["epistemic_index"], 75.0)
    self.assertFalse(sc["confidence_overclaimed"])
    md = formula.format_scorecard_markdown(sc)
    self.assertIn("Epistemic Index (EI):", md)

  def test_discover_deduplicates_across_registries_and_logs_search(self):
    d = _study()
    openalex_payload = {
        "results": [{
            "title": "Optimal Stopping Under Drawdown Constraints",
            "publication_year": 2024,
            "doi": "https://doi.org/10.1016/j.jfineco.2024.01.005",
            "type": "article",
            "cited_by_count": 42,
            "primary_location": {
                "landing_page_url": "https://doi.org/10.1016/j.jfineco.2024.01.005",
                "source": {"display_name": "Journal of Financial Economics", "type": "journal"},
            },
            "open_access": {"oa_url": "https://arxiv.org/abs/2401.12345v2"},
            "abstract_inverted_index": {"Optimal": [0], "stopping": [1], "drawdown": [2]},
        }]
    }
    crossref_payload = {
        "message": {
            "items": [{
                "title": ["Optimal Stopping Under Drawdown Constraints"],
                "DOI": "10.1016/j.jfineco.2024.01.005",
                "type": "journal-article",
                "container-title": ["Journal of Financial Economics"],
                "is-referenced-by-count": 45,
                "published-print": {"date-parts": [[2024, 3]]},
            }]
        }
    }
    arxiv_xml = """<?xml version="1.0" encoding="UTF-8"?>
    <feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
      <entry>
        <id>http://arxiv.org/abs/2502.99999v1</id>
        <published>2025-02-10T00:00:00Z</published>
        <title>Execution Slippage in Intraday Futures Breakouts</title>
        <summary>Measured queue slippage across CME MNQ contracts.</summary>
      </entry>
    </feed>"""

    def _fake_get(url, headers=None, timeout=12):
      m = unittest.mock.Mock()
      m.raise_for_status = lambda: None
      if "api.openalex.org" in url:
        m.json = lambda: openalex_payload
      elif "api.crossref.org" in url:
        m.json = lambda: crossref_payload
      else:
        m.text = arxiv_xml
      return m

    before_searches = len(evidence._jsonl(d / "searches.jsonl"))
    with unittest.mock.patch("discover.requests.get", side_effect=_fake_get):
      res = discover.discover_sources("drawdown stopping", sources=("openalex", "crossref", "arxiv"), limit=5)
      logged = discover.log_discovery_search(d, "SQ1", res)

    # OpenAlex + CrossRef duplicate DOI merged into 1 record + 1 arXiv record = 2 unique hits
    self.assertEqual(res["total_unique_hits"], 2)
    top = res["results"][0]
    self.assertEqual(top["suggested_tier"], "T3")
    self.assertEqual(top["citations"], 45)
    self.assertEqual(top["fetch_url"], "https://arxiv.org/html/2401.12345")
    arx_hit = res["results"][1]
    self.assertEqual(arx_hit["suggested_tier"], "T4")
    self.assertEqual(arx_hit["fetch_url"], "https://arxiv.org/html/2502.99999v1")

    after_searches = evidence._jsonl(d / "searches.jsonl")
    self.assertEqual(len(after_searches), before_searches + 1)
    self.assertEqual(after_searches[-1]["id"], logged["id"])
    self.assertTrue(after_searches[-1]["tool"].startswith("discover.py:"))


import re  # noqa: E402
import sqlite3  # noqa: E402

import audit  # noqa: E402
import claims  # noqa: E402
import corpus  # noqa: E402

NAV = "Home page for traders and investors. Pricing plans and account options. Contact us today for support. "
PAGES = {
    "S001": NAV + "The commission on index CFDs is six dollars per lot on the Raw feed. "
                  "Spreads on the All-In feed are wider during the session open. Swaps are charged nightly.",
    "S002": NAV + "The regulator issued no warning about this firm. The license number is listed "
                  "on the public register. Complaints are handled by the ombudsman.",
    "S003": NAV + "Cooking pasta requires boiling water and salt. Drain it after ten minutes. "
                  "Serve with grated cheese and olive oil.",
}


def _corpus_study(pages=PAGES) -> Path:
  d = Path(tempfile.mkdtemp())
  (d / "sources").mkdir()
  (d / "plan.md").write_text("| SQ1 | corpus test | x |\n", encoding="utf-8")  # a study folder
  with (d / "sources" / "index.jsonl").open("w", encoding="utf-8") as f:
    for sid, text in pages.items():
      (d / "sources" / f"{sid}.txt").write_text(text, encoding="utf-8")
      f.write(json.dumps({"id": sid, "url": f"https://site.test/{sid}",
                          "sha256": evidence.sha256_text(text)}) + "\n")
  return d


class CorpusTest(unittest.TestCase):

  def test_passages_are_exact_spans_of_snapshots(self):
    d = _corpus_study()
    info = corpus.build(d)
    self.assertEqual(info["docs"], 3)
    con = sqlite3.connect(d / "corpus.sqlite")
    rows = con.execute("SELECT sid, start, end, text FROM passages").fetchall()
    con.close()
    self.assertTrue(rows)
    for sid, s, e, text in rows:
      self.assertEqual(PAGES[sid][s:e], text)

  def test_boilerplate_never_returned_and_content_ranks_first(self):
    d = _corpus_study()
    corpus.build(d)
    con = sqlite3.connect(d / "corpus.sqlite")
    boiler = {r[0] for r in con.execute("SELECT pid FROM passages WHERE boiler > ?",
                                        (corpus.BOILER_MAX,))}
    con.close()
    self.assertTrue(boiler, "menu sentences repeated in 3 sources must be marked")
    for r in corpus.search(d, "pricing plans contact support traders", k=10):
      self.assertNotIn(r["pid"], boiler)
    top = corpus.search(d, "commission index CFDs Raw feed", k=3)
    self.assertEqual(top[0]["sid"], "S001")
    self.assertIn("six dollars per lot", top[0]["text"])

  def test_incremental_rebuild_on_changed_snapshot(self):
    d = _corpus_study()
    corpus.build(d)
    self.assertEqual(corpus.build(d)["added"] + corpus.build(d)["updated"], 0)
    pages = dict(PAGES, S002=PAGES["S002"] + " The warning was withdrawn in March.")
    d2 = _corpus_study(pages)
    (d2 / "corpus.sqlite").write_bytes((d / "corpus.sqlite").read_bytes())
    info = corpus.build(d2)
    self.assertEqual((info["added"], info["updated"]), (0, 1))
    self.assertEqual(corpus.search(d2, "warning withdrawn March", k=1)[0]["sid"], "S002")

  def test_query_log_records_result_set(self):
    d = _corpus_study()
    with contextlib.redirect_stdout(io.StringIO()):
      self.assertEqual(corpus.main(["query", "--dir", str(d), "regulator warning", "--log"]), 1)
      self.assertEqual(corpus.main(["query", "--dir", str(d), "regulator warning", "--log",
                                    "--purpose", "K2"]), 0)
    rec = evidence._jsonl(d / "searches.jsonl")[-1]
    self.assertEqual((rec["purpose"], rec["channel"]), ("K2", "corpus"))
    self.assertIn("S002", rec["opened"])
    self.assertTrue(all(re.match(r"^S\d{3}@\d+-\d+$", loc) for loc in rec["results"]))

  def test_syndicated_text_stays_searchable_and_is_reported(self):
    release = ("The regulator revoked the broker licence on 3 March after an inspection found "
               "client money held in the operating account. The firm has thirty days to appeal "
               "the decision before the revocation takes effect. ")
    pages = {f"S00{i}": release + f"Page {i} commentary about unrelated markets." for i in (1, 2, 3)}
    d = _corpus_study(pages)
    idx = [json.loads(line) for line in (d / "sources" / "index.jsonl").read_text().splitlines()]
    with (d / "sources" / "index.jsonl").open("w", encoding="utf-8") as f:
      for r, host in zip(idx, ("a.test", "news.b.test", "www.c.test")):
        f.write(json.dumps(dict(r, url=f"https://{host}/x")) + "\n")
    hits = corpus.search(d, "licence revoked client money operating account", k=5)
    self.assertEqual(len(hits), 3)  # per-site boilerplate rule: syndication is not a menu
    con = sqlite3.connect(d / "corpus.sqlite")
    pairs = {(p["a"], p["b"]) for p in corpus.shared_text(con)}
    con.close()
    self.assertEqual(pairs, {("S001", "S002"), ("S001", "S003"), ("S002", "S003")})

  def test_triage_blind_spots_and_surprise_queue(self):
    d = _corpus_study()
    (d / "plan.md").write_text("| SQ1 | commission on index CFDs on the Raw feed | x |\n"
                               "| K1 | currency hedging collateral haircut margin | y |\n",
                               encoding="utf-8")
    (d / "evidence.jsonl").write_text(json.dumps({"id": "E001", "source": "S001"}) + "\n",
                                      encoding="utf-8")
    t = corpus.triage(d)
    self.assertIn("K1", t["blind_spots"])
    self.assertNotIn("SQ1", t["blind_spots"])
    self.assertIn("S003", t["orphans"])
    self.assertNotIn("S001", t["orphans"])


def _claim(cid, value, eids, unit="", scope="", time="", method="", subject="Firm",
           attribute="commission per lot"):
  return {"id": cid, "subject": subject, "attribute": attribute, "value": value, "unit": unit,
          "scope": scope, "time": time, "method": method, "eids": eids}


class ClaimsTest(unittest.TestCase):

  EV = {"E001": {"tier": "T1", "kind": "de_jure", "published": "2026-01-01"},
        "E002": {"tier": "T1", "kind": "de_jure", "published": "2026-01-01"},
        "E003": {"tier": "T5", "kind": "de_facto", "published": "2026-06-01"}}

  def _add(self, d, value, eids):
    with contextlib.redirect_stdout(io.StringIO()):
      return claims.main(["add", "--dir", str(d), "--subject", "Firm", "--attribute",
                          "commission per lot", "--value", value, "--eids", eids])

  def test_add_binds_numbers_to_quotes(self):
    d = _study()
    _add(d, quote="Commission is $3 per lot round turn")
    self.assertEqual(self._add(d, "5", "E001"), 1)
    self.assertEqual(self._add(d, "3", "E009"), 1)
    self.assertEqual(self._add(d, "3", "E001"), 0)
    self.assertEqual(self._add(d, "commission-free", "E001"), 0)  # categorical: no binding
    self.assertEqual(len(evidence._jsonl(d / "claims.jsonl")), 2)

  def test_numeric_tolerance_and_scope_axis(self):
    same = claims.find_conflicts([_claim("CL001", "100", ["E001"], "USD"),
                                  _claim("CL002", "103", ["E002"], "USD")], self.EV)
    self.assertEqual(same, [])
    c = claims.find_conflicts([_claim("CL001", "6", ["E001"], "USD", scope="Raw"),
                               _claim("CL002", "commission-free", ["E002"], scope="All-In")], self.EV)
    self.assertEqual(len(c), 1)
    self.assertEqual(c[0]["axes"], ["scope"])  # unit differs, but only numbers have units

  def test_unexplained_time_authority_and_rule_vs_practice(self):
    c = claims.find_conflicts([_claim("CL001", "6", ["E001"], "USD"),
                               _claim("CL002", "9", ["E002"], "USD")], self.EV)
    self.assertEqual(c[0]["axes"], ["UNEXPLAINED"])
    c = claims.find_conflicts([_claim("CL001", "6", ["E001"], "USD"),
                               _claim("CL002", "9", ["E003"], "USD")], self.EV)
    self.assertEqual(set(c[0]["axes"]), {"time", "authority", "rule_vs_practice"})

  def test_different_attributes_never_conflict(self):
    self.assertEqual(claims.find_conflicts(
        [_claim("CL001", "6", ["E001"]), _claim("CL002", "9", ["E002"], attribute="swap")],
        self.EV), [])


class AuditTest(unittest.TestCase):

  def test_clopper_pearson_reference_values(self):
    self.assertAlmostEqual(audit.clopper_pearson_upper(0, 30), 0.0950, places=3)
    self.assertAlmostEqual(audit.clopper_pearson_upper(1, 30), 0.1486, places=3)
    self.assertAlmostEqual(audit.clopper_pearson_upper(0, 59), 0.0495, places=3)
    self.assertEqual(audit.clopper_pearson_upper(0, 0), 1.0)

  def test_hypergeometric_finite_population(self):
    self.assertEqual(audit.hypergeom_upper(0, 27, 27), 0.0)       # census: exact share
    self.assertAlmostEqual(audit.hypergeom_upper(2, 27, 27), 2 / 27)
    self.assertLess(audit.hypergeom_upper(0, 30, 60), audit.clopper_pearson_upper(0, 30))
    self.assertAlmostEqual(audit.hypergeom_upper(0, 30, 10**4),
                           audit.clopper_pearson_upper(0, 30), places=2)

  def _report(self, n):
    body = "\n\n".join(f"Fee {i} is $3 per lot [E00{1 + i % 2}]." for i in range(n))
    return f"# T\n\n## Bottom line\n\n{body}\n\n## Sources\n\n| [E001] | x |\n"

  def test_sample_is_deterministic_and_seeded_by_report(self):
    d = _study()
    (d / "report.md").write_text(self._report(12), encoding="utf-8")
    with contextlib.redirect_stdout(io.StringIO()):
      audit.main(["sample", "--dir", str(d), "--n", "5"])
      first = [it["text"] for it in audit.load(d)["items"]]
      audit.main(["sample", "--dir", str(d), "--n", "5"])
    self.assertEqual(first, [it["text"] for it in audit.load(d)["items"]])
    self.assertEqual(audit.load(d)["population"], 12)
    self.assertEqual(len(first), 5)

  def test_resample_carries_unchanged_verdicts_only(self):
    d = _study()
    report = self._report(4)
    (d / "report.md").write_text(report, encoding="utf-8")
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
      audit.main(["sample", "--dir", str(d)])
      for i, v in zip(("A01", "A02", "A03", "A04"), ("supported", "wrong_number", "supported", "supported")):
        audit.main(["record", "--dir", str(d), "--item", i, "--verdict", v])
      bad = audit.load(d)["items"][1]["text"]
      fixed = report.replace(bad, bad.replace("Fee 1 is", "Fee one is"))
      (d / "report.md").write_text(fixed, encoding="utf-8")
      audit.main(["sample", "--dir", str(d)])
    data = audit.load(d)
    self.assertEqual(sorted(data["verdicts"]), ["A01", "A03", "A04"])  # fixed sentence re-judged
    self.assertTrue(all(v["carried_from"] for v in data["verdicts"].values()))
    self.assertEqual(data["history"][0]["errors"], 1)
    self.assertEqual(audit.summary(data)["pending"], ["A02"])
    self.assertIn("A02", (d / "audit" / "brief.md").read_text(encoding="utf-8"))
    self.assertNotIn("## A01", (d / "audit" / "brief.md").read_text(encoding="utf-8"))
    self.assertTrue(list((d / "audit" / "history").glob("sample-*.json")))

  def test_stale_but_fixed_rule(self):
    data = {"report_sha256": "x", "items": [
        {"id": "A01", "line": 1, "text": "Fee is $3 [E001]."},
        {"id": "A02", "line": 2, "text": "Cap is $9 [E002]."}],
            "verdicts": {"A01": {"verdict": "supported"}, "A02": {"verdict": "wrong_number"}}}
    fixed = "# T\n\n## Body\n\nFee is $3 [E001].\n\nCap is $4 [E002].\n"
    self.assertEqual(audit.check_against_report(data, fixed), [])
    unfixed = "# T\n\n## Body\n\nFee is $3 [E001].\n\nCap is $9 [E002].\n"
    self.assertEqual(len(audit.check_against_report(data, unfixed)), 1)
    rewritten = "# T\n\n## Body\n\nFee is $5 [E001].\n\nCap is $4 [E002].\n"
    self.assertIn("A01", audit.check_against_report(data, rewritten)[0])
    s = audit.summary(dict(data, n=2, population=40))
    self.assertEqual((s["errors"], s["error_items"], s["pending"]), (1, ["A02"], []))


import calc  # noqa: E402
import units  # noqa: E402


class UnitsTest(unittest.TestCase):

  def test_round_turn_per_side_and_ambiguous_side(self):
    self.assertEqual(units.convert(3, "USD per side", "USD per lot RT"), 6.0)
    self.assertTrue(units.same_quantity(3, "USD per side", 6, "USD RT"))
    self.assertFalse(units.same_quantity(3, "USD per side", 3, "USD RT"))
    self.assertIsNone(units.same_quantity(6, "USD per lot", 6, "USD RT"))  # side unspecified
    self.assertEqual(units.convert(1.5, "bp per side", "bp per trade RT"), 3.0)

  def test_bp_percent_and_annual_daily(self):
    self.assertEqual(units.convert(1.25, "%", "bp"), 125.0)
    self.assertTrue(units.same_quantity(6, "% p.a.", 1.644, "bp/day"))
    self.assertIsNone(units.same_quantity(6, "% p.a.", 1.5, "bp per trade"))
    with self.assertRaises(ValueError):
      units.convert(6, "% p.a.", "bp per trade")
    self.assertIsNone(units.parse("commission-free"))
    self.assertIsNone(units.parse("pay as you go"))  # 'pa' inside words is not per annum

  def test_holding_cost_is_spread_plus_nights_times_daily(self):
    self.assertAlmostEqual(units.hold_cost_bp(3, 600, 1.5), 1.5 + 3 * 600 / 365)
    self.assertAlmostEqual(units.daily_bp(600), 600 / 365)

  def test_long_short_financing_nets_the_legs(self):
    self.assertEqual(units.ls_net_pct(8.5, 2.5), 6.0)
    self.assertAlmostEqual(units.ls_net_bp_day(8.5, 2.5), 1.644, places=3)
    hi, lo = units.ls_financing(5.5 + 3, 5.5 - 3), units.ls_financing(2 + 3, 2 - 3)
    self.assertAlmostEqual(hi["net_pct_pa_of_long_notional"], lo["net_pct_pa_of_long_notional"])
    f = units.ls_financing(8.5, 2.5, 1e6, 1e6)
    self.assertEqual((f["net_cost_per_year"], f["wrong_flat_cost_per_year"]), (60000.0, 170000.0))
    self.assertGreater(units.ls_net_pct(2.0, -0.5), units.ls_net_pct(2.0, 0.5))  # short pays too

  def test_bp_to_r_and_calc_integration(self):
    self.assertAlmostEqual(units.bp_to_r(0.7, 10), 0.07)
    self.assertAlmostEqual(units.r_to_bp(0.07, 10), 0.7)
    with self.assertRaises(ValueError):
      units.bp_to_r(1, 0)
    self.assertAlmostEqual(calc.safe_eval("hold_cost_bp(nights, annual, 1.5)",
                                          {"nights": 3, "annual": 600}), 1.5 + 3 * 600 / 365)
    self.assertAlmostEqual(calc.safe_eval("ls_net_bp_day(8.5, 2.5)"), 1.644, places=3)


class ClaimsV41Test(unittest.TestCase):

  EV = {"E001": {"tier": "T1", "kind": "de_jure", "url": "https://firm.test/faq"},
        "E002": {"tier": "T1", "kind": "de_jure", "url": "https://firm.test/terms"},
        "E003": {"tier": "T3", "kind": "empirical", "url": "https://journal.test/a",
                 "sample_period": "1990-2007", "sample_type": "in_sample"},
        "E004": {"tier": "T4", "kind": "empirical", "url": "https://firm.test/whitepaper",
                 "interest": "issuer", "sample_period": "2010-2019", "sample_type": "out_of_sample"},
        "E005": {"tier": "T3", "kind": "empirical", "url": "https://journal.test/b",
                 "interest": "academic"}}

  def test_units_normalised_before_comparing(self):
    same = claims.find_conflicts([_claim("CL001", "3", ["E001"], "USD per side"),
                                  _claim("CL002", "6", ["E002"], "USD RT")], self.EV)
    self.assertEqual(same, [])
    c = claims.find_conflicts([_claim("CL001", "2", ["E001"], "USD per side"),
                               _claim("CL002", "6", ["E002"], "USD RT")], self.EV)
    self.assertNotIn("unit", c[0]["axes"])
    self.assertIn("normalised: 4 USD per lot RT vs 6 USD per lot RT", c[0]["notes"])

  def test_annual_rate_vs_per_trade_cost_is_a_unit_conflict(self):
    c = claims.find_conflicts([_claim("CL001", "6", ["E001"], "% p.a."),
                               _claim("CL002", "1.5", ["E002"], "bp per trade")], self.EV)
    self.assertEqual(c[0]["axes"], ["unit"])
    self.assertIn("hold_cost_bp", c[0]["notes"][0])
    c = claims.find_conflicts([_claim("CL001", "6", ["E001"], "USD per lot"),
                               _claim("CL002", "6", ["E002"], "USD RT")], self.EV)
    self.assertIn("round-turn or per side", c[0]["notes"][0])

  def test_interest_axis_issuer_vs_peer_reviewed(self):
    c = claims.find_conflicts([_claim("CL001", "0.8", ["E004"], attribute="sharpe"),
                               _claim("CL002", "0.3", ["E005"], attribute="sharpe")], self.EV)
    self.assertIn("interest", c[0]["axes"])
    # the subject's own site counts as issuer even without --interest
    c = claims.find_conflicts([_claim("CL001", "0.8", ["E001"], attribute="sharpe"),
                               _claim("CL002", "0.3", ["E005"], attribute="sharpe")], self.EV)
    self.assertIn("interest", c[0]["axes"])

  def test_sample_axis_period_and_out_of_sample(self):
    c = claims.find_conflicts([_claim("CL001", "0.8", ["E003"], attribute="sharpe"),
                               _claim("CL002", "0.2", ["E004"], attribute="sharpe")], self.EV)
    self.assertIn("sample", c[0]["axes"])
    notes = " ".join(c[0]["notes"])
    self.assertIn("in_sample vs out_of_sample", notes)
    self.assertIn("non-overlapping", notes)

  def test_evidence_add_records_interest_and_sample(self):
    d = _study()
    self.assertEqual(_add(d, quote="Commission is $3 per lot round turn", interest="vendor",
                          **{"sample-period": "2010-2019", "sample-type": "out_of_sample"}), 0)
    r = evidence._jsonl(d / "evidence.jsonl")[-1]
    self.assertEqual((r["interest"], r["sample_period"], r["sample_type"]),
                     ("vendor", "2010-2019", "out_of_sample"))
    with self.assertRaises((SystemExit, argparse.ArgumentError)), \
         contextlib.redirect_stderr(io.StringIO()):
      _add(d, quote="limited to $400,000 per trader", interest="broker-pr")  # not a known interest


class AliasTest(unittest.TestCase):

  PAGES = {"S001": "The Cyprus Securities and Exchange Commission issued a warning about the firm. "
                   "Investors should check the register before depositing money.",
           "S002": "A separate notice covers market hours and holiday trading schedules for indices."}

  def test_acronym_finds_full_name(self):
    d = _corpus_study(self.PAGES)
    hit = corpus.search(d, "CySEC warning", k=1)[0]
    self.assertEqual((hit["sid"], hit["coverage"]), ("S001", 1.0))
    (d / "aliases.json").write_text(json.dumps({"disable": ["CySEC"]}), encoding="utf-8")
    self.assertLess(corpus.search(d, "CySEC warning", k=1)[0]["coverage"], 1.0)

  def test_longest_match_and_local_groups_merge(self):
    labels = [c["label"] for c in corpus.concepts(
        "Cyprus Securities and Exchange Commission and the SEC", corpus.load_aliases())]
    self.assertEqual(labels, ["CySEC", "SEC"])
    d = _corpus_study(self.PAGES)
    (d / "aliases.json").write_text(json.dumps(
        {"groups": [["CySEC", "Cyprus SEC"], ["FXIFY", "FXIFY Solutions Limited"]]}), encoding="utf-8")
    groups = corpus.load_aliases(d)
    cysec = next(g for g in groups if "CySEC" in g)
    self.assertIn("Cyprus SEC", cysec)
    self.assertEqual(sum(1 for g in groups if "CySEC" in g), 1)
    self.assertTrue(any(c["alias"] for c in corpus.concepts("FXIFY fees", groups)))

  def test_logged_query_records_expansion(self):
    d = _corpus_study(self.PAGES)
    with contextlib.redirect_stdout(io.StringIO()):
      corpus.main(["query", "--dir", str(d), "CySEC warning", "--log", "--purpose", "K1"])
    rec = evidence._jsonl(d / "searches.jsonl")[-1]
    self.assertIn("cyprus securities exchange commission", rec["expanded"]["CySEC"])


class E4StrictTest(unittest.TestCase):

  def _fails(self, d, strict):
    g = gate.Gate(d)
    g.evidence_stage(min_searches=12, kill_share=0.3, strict_kill_results=strict)
    return [f for f in g.fail if f.startswith("E4")], [w for w in g.warn if w.startswith("E4")]

  def test_unrecorded_kill_searches_fail_only_when_strict(self):
    d = _study()  # 9 kill searches, none recorded what it returned
    fails, warns = self._fails(d, strict=False)
    self.assertEqual(fails, [])
    self.assertTrue(warns)
    fails, _ = self._fails(d, strict=True)
    self.assertTrue(any("recorded result set" in f for f in fails))
    rows = evidence._jsonl(d / "searches.jsonl")
    with (d / "searches.jsonl").open("w", encoding="utf-8") as f:
      for r in rows:
        if r["purpose"].startswith("K"):
          r["opened"] = ["S001"]
        f.write(json.dumps(r) + "\n")
    self.assertEqual(self._fails(d, strict=True)[0], [])

  def test_tool_logged_empty_result_counts(self):
    self.assertTrue(gate.has_results({"purpose": "K1", "tool": "discover.py:openalex", "hits": 0,
                                      "opened": []}))
    self.assertFalse(gate.has_results({"purpose": "K1", "opened": [], "note": "Extra kill budget query"}))

  def test_strictness_from_marker_or_date(self):
    root = Path(tempfile.mkdtemp())
    for name, strict in (("2026-11-03-old", False), ("2026-11-04-new", True), ("undated", False)):
      (root / name).mkdir()
      self.assertEqual(gate.study_is_strict(root / name), strict, name)
    (root / "undated" / "study.json").write_text('{"protocol": "4.1"}', encoding="utf-8")
    self.assertTrue(gate.study_is_strict(root / "undated"))


class GateV4Test(unittest.TestCase):

  _run, _setup, GOOD = GateTest._run, GateTest._setup, GateTest.GOOD

  CONFLICTS = ("\n## Conflicts\n\n| Topic | A | B | Axis |\n| :-- | :-- | :-- | :-- |\n"
               "| Commission | Raw $3 per lot [E002] | All-In free [E001] | scope{extra} |\n\n## Sources")

  def _claims(self, d, scope_b="All-In"):
    (d / "claims.jsonl").write_text(
        json.dumps(_claim("CL001", "3", ["E002"], "USD", scope="Raw")) + "\n" +
        json.dumps(_claim("CL002", "commission-free", ["E001"], scope=scope_b)) + "\n",
        encoding="utf-8")

  def test_r11_conflict_must_be_in_conflicts_section(self):
    d = self._setup()
    self._claims(d)
    self.assertIn("R11", self._run(d, self.GOOD))
    self.assertNotIn("R11", self._run(d, self.GOOD.replace(
        "\n## Sources", self.CONFLICTS.format(extra=""))))

  def test_r11_unexplained_conflict_must_be_marked_unresolved(self):
    d = self._setup()
    self._claims(d, scope_b="Raw")
    self.assertIn("R11", self._run(d, self.GOOD.replace(
        "\n## Sources", self.CONFLICTS.format(extra=""))))
    self.assertNotIn("R11", self._run(d, self.GOOD.replace(
        "\n## Sources", self.CONFLICTS.format(extra=" - unresolved"))))

  def test_r12_audit_pending_supported_and_unfixed(self):
    d = self._setup()
    self.assertNotIn("R12", self._run(d, self.GOOD))  # no sample, not required
    g = gate.Gate(d)
    g.evidence_stage(min_searches=12, kill_share=0.3)
    g.report_stage(d / "report.md", min_coverage=0.9, min_urls=1, require_audit=True)
    self.assertIn("R12", [f.split()[0] for f in g.fail])
    with contextlib.redirect_stdout(io.StringIO()):
      audit.main(["sample", "--dir", str(d)])
    self.assertIn("R12", self._run(d, self.GOOD))  # pending
    with contextlib.redirect_stdout(io.StringIO()):
      audit.main(["record", "--dir", str(d), "--item", "A01", "--verdict", "supported"])
    self.assertNotIn("R12", self._run(d, self.GOOD))
    with contextlib.redirect_stdout(io.StringIO()):
      audit.main(["record", "--dir", str(d), "--item", "A01", "--verdict", "unsupported"])
    fails = [f for f in self._raw_fails(d) if f.startswith("R12")]
    self.assertTrue(any("still in the report unfixed" in f for f in fails))
    self.assertTrue(any("upper bound" in f for f in fails))

  def test_exempt_section_matching_is_exact(self):
    self.assertTrue(check_report.heading_exempt("## Проверка (Verification)", False))
    self.assertTrue(check_report.heading_exempt("## Източници", False))
    self.assertFalse(check_report.heading_exempt("## Проверка на убиващите хипотези (Kill)", True))
    self.assertTrue(check_report.heading_exempt("### Addendum", True))   # inherits from parent
    self.assertFalse(check_report.heading_exempt("### Addendum", False))

  def test_r13_finding_hidden_in_verification_fails(self):
    d = self._setup()
    hidden = self.GOOD + "\n## Verification\n\n### Addendum\n\n- Licence MB/22/0097 confirmed in the register.\n"
    self.assertIn("R13", self._run(d, hidden))
    process = self.GOOD + "\n## Verification\n\n- Kill search share: 12 of 20 searches.\n"
    self.assertNotIn("R13", self._run(d, process))
    status = self.GOOD + "\n## Verification\n\n- **Epistemic Index:** Verified against gates E1–E8.\n"
    self.assertNotIn("R13", self._run(d, status))  # pipeline status: a warning, not a finding
    g = gate.Gate(d)
    g.evidence_stage(min_searches=12, kill_share=0.3)
    g.report_stage(d / "report.md", min_coverage=0.9, min_urls=1)
    self.assertTrue(any(w.startswith("R13") for w in g.warn))

  def test_e4_warns_when_kill_searches_record_nothing(self):
    d = self._setup()
    g = gate.Gate(d)
    g.evidence_stage(min_searches=12, kill_share=0.3)
    self.assertTrue(any("unverifiable" in w for w in g.warn))

  def _raw_fails(self, d):
    g = gate.Gate(d)
    g.evidence_stage(min_searches=12, kill_share=0.3)
    g.report_stage(d / "report.md", min_coverage=0.9, min_urls=1)
    return g.fail


# ------------------------------------------------------------------ P2 (protocol 4.1)
import os  # noqa: E402

import next_step  # noqa: E402
import screening  # noqa: E402


def make_pdf(content: bytes) -> bytes:
  """Minimal one-page PDF (Helvetica) around a content stream."""
  objs = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
          b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
          b"/Resources << /Font << /F1 5 0 R >> >> >>",
          b"<< /Length %d >>\nstream\n" % len(content) + content + b"\nendstream",
          b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
  out, offsets = b"%PDF-1.4\n", []
  for i, o in enumerate(objs, 1):
    offsets.append(len(out))
    out += b"%d 0 obj\n" % i + o + b"\nendobj\n"
  xref = len(out)
  out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
  out += b"".join(b"%010d 00000 n \n" % off for off in offsets)
  return out + b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)


def _pdf_text(x, y, s):
  return b"BT /F1 10 Tf %d %d Td (%s) Tj ET\n" % (x, y, s)


def _grid():
  c = b"0.5 w\n"
  for x in (72, 222, 322, 422):
    c += b"%d 630 m %d 690 l S\n" % (x, x)
  for y in (630, 650, 670, 690):
    c += b"72 %d m 422 %d l S\n" % (y, y)
  return c


def table_pdf() -> bytes:
  c = _grid()
  c += _pdf_text(72, 750, b"Annual report of Example Holdings for the financial year ended 31 December 2025.")
  c += _pdf_text(72, 735, b"Revenue grew because of higher trading volumes across all regions and products.")
  c += _pdf_text(72, 700, b"Figures in thousands of USD")
  for y, row in ((676, (b"Item", b"2025", b"2024")), (656, (b"Revenue", b"1,234", b"1,100")),
                 (636, (b"Costs", b"\\(35\\)", b"\\(30\\)"))):
    for x, cell in zip((77, 227, 327), row):
      c += _pdf_text(x, y, cell)
  c += _pdf_text(72, 600, b"The board proposes no dividend for the year and keeps the capital buffer unchanged.")
  return make_pdf(c)


@unittest.skipUnless(parse_pdf.pdfplumber, "pdfplumber not installed")
class PdfTablesTest(unittest.TestCase):

  def test_render_table_repeats_headers_in_every_row(self):
    lines = parse_pdf.render_table([["Item", "2025", "2024"], ["Revenue", "1,234", "1,100"],
                                    ["Fees | other", "5", None]], "p2.t1", "in USD millions")
    self.assertEqual(lines[0], "[TABLE p2.t1]")
    self.assertIn("p2.t1 units: in USD millions", lines)
    self.assertIn("p2.t1 header: Item | 2025 | 2024", lines)
    self.assertIn("p2.t1 r1: Revenue | 2025: 1,234 | 2024: 1,100", lines)
    self.assertIn("p2.t1 r2: Fees / other | 2025: 5 | ", lines)  # a '|' inside a cell is not a column
    self.assertEqual(lines[-1], "[/TABLE]")

  def test_numeric_first_row_is_data_not_header(self):
    lines = parse_pdf.render_table([["1,234", "(35)"], ["5", "6"]], "p1.t2")
    self.assertFalse(any(" header: " in x for x in lines))
    self.assertIn("p1.t2 r1: 1,234 | (35)", lines)
    self.assertTrue(parse_pdf._is_header(["Item", "FY2025", "Q3 2024"]))

  def test_units_line_detection(self):
    self.assertEqual(parse_pdf.units_line("Consolidated statement\nFigures in thousands of USD"),
                     "Figures in thousands of USD")
    self.assertEqual(parse_pdf.units_line("Сума в хиляди лева"), "Сума в хиляди лева")
    self.assertEqual(parse_pdf.units_line("Consolidated statement"), "")

  def test_pdf_table_becomes_quotable_rows(self):
    text, info = parse_pdf.pdf_snapshot(table_pdf())
    self.assertEqual((info["parser"], info["tables"], info["pages"]), ("pdfplumber", 1, 1))
    self.assertTrue(text.startswith("=== Page 1 ==="))
    self.assertIn("p1.t1 units: Figures in thousands of USD", text)
    self.assertIn("p1.t1 header: Item | 2025 | 2024", text)
    self.assertIn("p1.t1 r1: Revenue | 2025: 1,234 | 2024: 1,100", text)
    self.assertIn("p1.t1 r2: Costs | 2025: (35) | 2024: (30)", text)
    prose = text.split("[TABLE")[0]
    self.assertIn("financial year ended 31 December 2025", prose)
    self.assertNotIn("1,234", prose)  # the table is cut out of the prose, not duplicated

  def test_imported_pdf_row_is_citable(self):
    d = _study()
    pdf = d / "annual.pdf"
    pdf.write_bytes(table_pdf())
    with contextlib.redirect_stdout(io.StringIO()):
      rec = parse_pdf.import_into_evidence(pdf, d, "https://firm.test/annual.pdf")
      again = parse_pdf.import_into_evidence(pdf, d, "https://firm.test/annual.pdf")
    self.assertEqual((rec["id"], rec["tables"], again["id"]), ("S002", 1, "S002"))
    self.assertEqual(_add(d, source="S002", quote="p1.t1 r1: Revenue | 2025: 1,234 | 2024: 1,100"), 0)
    self.assertNotEqual(_add(d, source="S002", quote="Revenue 1,234 in 2025"), 0)

  def test_scanned_pdf_is_refused(self):
    with self.assertRaises(ValueError) as cm:
      parse_pdf.pdf_snapshot(make_pdf(_grid()))
    self.assertIn("OCR", str(cm.exception))
    tmp = Path(tempfile.mkdtemp()) / "scan.pdf"
    tmp.write_bytes(make_pdf(_grid()))
    with contextlib.redirect_stdout(io.StringIO()) as out:
      self.assertEqual(parse_pdf.main([str(tmp)]), 1)
    self.assertIn("ERROR", out.getvalue())
    with contextlib.redirect_stdout(io.StringIO()) as out:
      self.assertEqual(parse_pdf.main([str(tmp), "--import-dir", str(_study())]), 2)
    self.assertIn("--url is required", out.getvalue())


def _coverage_study(searches=(), evidence_sources=("S001", "S002", "S003")):
  d = _corpus_study()
  (d / "evidence.jsonl").write_text("".join(
      json.dumps({"id": f"E{i:03d}", "source": s}) + "\n" for i, s in enumerate(evidence_sources, 1)),
      encoding="utf-8")
  (d / "searches.jsonl").write_text("".join(json.dumps(s) + "\n" for s in searches), encoding="utf-8")
  return d


def _site(*sids):
  return [f"https://site.test/{s}" for s in sids]


class CoverageTest(unittest.TestCase):

  def test_chapman_estimate(self):
    est = corpus.chapman(10, 8, 5)
    self.assertAlmostEqual(est["n_hat"], 15.5)  # (11 * 9) / 6 - 1
    self.assertGreaterEqual(est["ci_low"], 13)  # never below the sources actually found
    self.assertGreater(est["ci_high"], est["n_hat"])
    self.assertAlmostEqual(corpus.chapman(5, 5, 5)["n_hat"], 5.0)  # full overlap: nothing missed

  def test_coverage_problems_are_explicit(self):
    cov = corpus.coverage(_coverage_study())
    self.assertIsNone(cov["coverage"])
    self.assertIn("linked to a logged search", cov["problem"])
    one = [{"id": "Q001", "purpose": "SQ1", "channel": "web", "opened": _site("S001", "S002", "S003")}]
    self.assertIn("only one discovery channel", corpus.coverage(_coverage_study(one))["problem"])
    disjoint = [{"id": "Q001", "purpose": "SQ1", "channel": "web", "opened": _site("S001", "S002")},
                {"id": "Q002", "purpose": "SQ1", "channel": "scholarly", "opened": _site("S003")}]
    cov = corpus.coverage(_coverage_study(disjoint))
    self.assertIsNone(cov["coverage"])
    self.assertIn("share no source", cov["problem"])

  def test_coverage_estimate_with_overlap(self):
    s = [{"id": "Q001", "purpose": "SQ1", "channel": "web", "opened": _site("S001", "S002")},
         {"id": "Q002", "purpose": "K1", "tool": "discover.py:openalex", "opened": _site("S002", "S003")},
         {"id": "Q003", "purpose": "SQ1", "channel": "corpus", "opened": ["S001", "S003"]}]
    cov = corpus.coverage(_coverage_study(s))
    self.assertEqual(cov["channel_counts"], {"web": 2, "scholarly": 2})  # corpus re-reads are not discovery
    self.assertAlmostEqual(cov["estimate"]["n_hat"], 3.5)  # (3 * 3) / 2 - 1
    self.assertAlmostEqual(cov["coverage"], 3 / 3.5)
    self.assertEqual(corpus.search_channel({"tool": "discover.py:snowball:both"}), "citation")

  def test_saturation_counts_new_decisive_keys_per_batch(self):
    d = _coverage_study()
    (d / "claims.jsonl").write_text("".join(json.dumps(c) + "\n" for c in (
        {"id": "CL001", "subject": "Firm", "attribute": "commission", "eids": ["E001"], "load_bearing": True},
        {"id": "CL002", "subject": "Firm", "attribute": "warning", "eids": ["E002"]},
        {"id": "CL003", "subject": "Firm", "attribute": "Commission ", "eids": ["E003"], "load_bearing": True},
    )), encoding="utf-8")
    sat = corpus.saturation(d, batch=2)
    self.assertEqual([(r["new_keys"], r["new_decisive"]) for r in sat["rows"]], [(2, 1), (0, 0)])
    self.assertTrue(sat["load_bearing_marked"])

  def test_stats_verdict(self):
    rows = lambda *n: [{"batch": i, "size": 10, "new_decisive": k} for i, k in enumerate(n, 1)]  # noqa: E731
    good = {"coverage": 0.9, "problem": ""}
    self.assertEqual(corpus.stats_verdict(good, {"batch": 10, "rows": rows(6, 0, 0)})[0], "SATURATED")
    verdict, why = corpus.stats_verdict(good, {"batch": 10, "rows": rows(6, 0, 1)})
    self.assertEqual(verdict, "CONTINUE")
    self.assertIn("still added decisive facts", why[0])
    verdict, why = corpus.stats_verdict({"coverage": 0.5, "problem": ""}, {"batch": 10, "rows": rows(6, 0, 0)})
    self.assertIn("< 80%", why[0])
    verdict, why = corpus.stats_verdict(good, {"batch": 10, "rows": rows(6)})
    self.assertIn("needs >= 2", why[0])
    verdict, why = corpus.stats_verdict({"coverage": None, "problem": "no channel"},
                                        {"batch": 10, "rows": rows(6, 0, 0)})
    self.assertIn("coverage not estimated: no channel", why[0])

  def test_stats_cli_saves_coverage_json(self):
    d = _coverage_study()
    with contextlib.redirect_stdout(io.StringIO()) as out:
      self.assertEqual(corpus.main(["stats", "--dir", str(d), "--save"]), 0)
    saved = json.loads((d / "coverage.json").read_text(encoding="utf-8"))
    self.assertEqual((saved["sources"], saved["verdict"]), (3, "CONTINUE"))
    self.assertIn("VERDICT: CONTINUE", out.getvalue())
    with contextlib.redirect_stdout(io.StringIO()):
      self.assertEqual(corpus.main(["stats", "--dir", str(d), "--channels", "web"]), 2)


def _work(wid, title, cites, doi=""):
  return {"id": f"https://openalex.org/{wid}", "title": title, "doi": doi, "publication_year": 2001,
          "cited_by_count": cites, "type": "article",
          "primary_location": {"landing_page_url": f"https://doi.org/10.1/{wid.lower()}",
                               "source": {"display_name": "J Fin", "type": "journal"}}}


class _Resp:
  def __init__(self, data, status=200, headers=None):
    self.data, self.status_code, self.headers = data, status, headers or {}

  def json(self):
    return self.data

  def raise_for_status(self):
    if self.status_code >= 400:
      raise discover.requests.HTTPError(f"HTTP {self.status_code}", response=self)


SEED = dict(_work("W1", "Seed paper", 2), referenced_works=["https://openalex.org/W2", "https://openalex.org/W3"],
            cited_by_api_url="https://api.openalex.org/works?filter=cites:W1")


class SnowballTest(unittest.TestCase):

  def setUp(self):
    self.urls = []
    p = unittest.mock.patch.object(discover, "OPENALEX_MIN_INTERVAL", 0)
    p.start()
    self.addCleanup(p.stop)

  def _get(self, url, headers=None, timeout=12):
    self.urls.append(url)
    if "/works/W1" in url or "/works/doi:10.1234/seed" in url:
      return _Resp(SEED)
    if "filter=openalex" in url:
      return _Resp({"results": [_work("W2", "Small ref", 5), _work("W3", "Big ref", 50)]})
    if "cites:W1" in url:
      return _Resp({"results": [_work("W4", "Citing paper", 1)]})
    return _Resp({}, 404)

  def test_backward_and_forward(self):
    with unittest.mock.patch.object(discover.requests, "get", self._get), \
         unittest.mock.patch.dict(os.environ, {}, clear=False):
      os.environ.pop("OPENALEX_MAILTO", None)
      res = discover.snowball("W1", "both", limit=5)
    self.assertEqual([(r["openalex_id"], r["direction"]) for r in res["results"]],
                     [("W3", "backward"), ("W2", "backward"), ("W4", "forward")])
    self.assertEqual((res["references_total"], res["cited_by_total"], res["seed_id"]), (2, 2, "W1"))
    self.assertTrue(any("sort=cited_by_count%3Adesc" in u for u in self.urls))
    self.assertFalse(any("mailto" in u for u in self.urls))  # no address unless the user sets one

  def test_mailto_only_from_environment(self):
    with unittest.mock.patch.object(discover.requests, "get", self._get), \
         unittest.mock.patch.dict(os.environ, {"OPENALEX_MAILTO": "me@example.org"}):
      discover.snowball("https://doi.org/10.1234/seed", "backward")
    self.assertTrue(all("mailto=me%40example.org" in u for u in self.urls))

  def test_bad_seed_and_http_errors(self):
    with self.assertRaises(ValueError):
      discover.resolve_seed("not a seed")
    calls = []

    def flaky(url, headers=None, timeout=12):
      calls.append(url)
      return _Resp({}, 429, {"Retry-After": "0"}) if len(calls) == 1 else _Resp(SEED)

    with unittest.mock.patch.object(discover.requests, "get", flaky), \
         unittest.mock.patch.object(discover.time, "sleep", lambda s: None):
      self.assertEqual(discover.resolve_seed("W1")["title"], "Seed paper")
      self.assertEqual(len(calls), 2)  # 429 is retried
      calls.clear()
      with unittest.mock.patch.object(discover.requests, "get",
                                      lambda url, headers=None, timeout=12: calls.append(url) or _Resp({}, 404)):
        with self.assertRaises(RuntimeError) as cm:
          discover.resolve_seed("W9")
      self.assertEqual(len(calls), 1)  # 404 is not retried
      self.assertIn("HTTP 404", str(cm.exception))

  def test_log_candidates_dedupes(self):
    d = _corpus_study()
    leads = [{"url": "https://a.test/x", "title": "A"}, {"url": "https://a.test/x", "title": "again"},
             {"fetch_url": "https://b.test/y", "url": "https://b.test/landing"}]
    self.assertEqual(discover.log_candidates(d, leads, "scholarly", "discover.py", "SQ1", "Q001"), 2)
    self.assertEqual(discover.log_candidates(d, leads, "scholarly", "discover.py", "SQ1", "Q002"), 0)
    rows = evidence._jsonl(d / "candidates.jsonl")
    self.assertEqual([(r["id"], r["url"]) for r in rows], [("L001", "https://a.test/x"), ("L002", "https://b.test/y")])

  def test_cli_contract(self):
    err = io.StringIO()
    with contextlib.redirect_stderr(err):
      self.assertEqual(discover.main(["q", "--snowball", "W1"]), 2)
      self.assertEqual(discover.main([]), 2)
    self.assertIn("not both and not neither", err.getvalue())
    d = _corpus_study()
    with unittest.mock.patch.object(discover.requests, "get", self._get), \
         contextlib.redirect_stdout(io.StringIO()):
      self.assertEqual(discover.main(["--snowball", "W1", "--direction", "backward", "--dir", str(d),
                                      "--purpose", "SQ1"]), 0)
    q = evidence._jsonl(d / "searches.jsonl")[-1]
    self.assertEqual((q["channel"], q["tool"], q["hits"]), ("citation", "discover.py:snowball:backward", 2))
    self.assertEqual(len(q["results"]), 2)
    self.assertEqual({c["channel"] for c in evidence._jsonl(d / "candidates.jsonl")}, {"citation"})


def _screening_study():
  d = _corpus_study()
  leads = [{"id": f"L{i:03d}", "url": f"https://lead.test/{i}", "purpose": "K1", "channel": "scholarly"}
           for i in range(1, 26)] + [{"id": "L026", "url": "https://site.test/S001", "purpose": "SQ1"}]
  (d / "candidates.jsonl").write_text("".join(json.dumps(r) + "\n" for r in leads), encoding="utf-8")
  (d / "searches.jsonl").write_text(
      json.dumps({"id": "Q001", "purpose": "K1", "channel": "web", "results": ["https://web.test/a", "S002"]}) + "\n"
      + json.dumps({"id": "Q002", "purpose": "SQ1", "channel": "corpus", "opened": ["https://corpus.test/x"]}) + "\n",
      encoding="utf-8")
  return d


def _screen(*argv):
  with contextlib.redirect_stdout(io.StringIO()) as out:
    code = screening.main(list(argv))
  return code, out.getvalue()


class ScreeningTest(unittest.TestCase):

  def test_rejected_candidates(self):
    d = _screening_study()
    rej = {c["url"] for c in screening.rejected(d)}
    self.assertEqual(len(rej), 26)  # 25 leads + the web result; fetched page and corpus re-reads excluded
    self.assertIn("https://web.test/a", rej)
    self.assertNotIn("https://site.test/S001", rej)
    self.assertNotIn("https://corpus.test/x", rej)

  def test_sample_is_seeded_and_bounded(self):
    d = _screening_study()
    self.assertEqual(_screen("sample", "--dir", str(d), "--n", "10")[0], 2)
    self.assertEqual(_screen("sample", "--dir", str(d), "--n", "20")[0], 0)
    first = screening.load(d)
    self.assertEqual((first["n"], first["population"]), (20, 26))
    self.assertTrue((d / "audit" / "screening_brief.md").exists())
    _screen("sample", "--dir", str(d), "--n", "20")
    self.assertEqual(screening.load(d)["items"], first["items"])  # same list -> same sample

  def test_record_validation(self):
    d = _screening_study()
    self.assertEqual(_screen("record", "--dir", str(d), "--item", "X01", "--verdict", "irrelevant",
                             "--note", "x")[0], 1)  # no sample yet
    _screen("sample", "--dir", str(d), "--n", "20")
    rec = lambda *a: _screen("record", "--dir", str(d), *a)  # noqa: E731
    self.assertEqual(rec("--item", "X99", "--verdict", "irrelevant", "--note", "x")[0], 1)
    self.assertEqual(rec("--item", "X01", "--verdict", "duplicate", "--note", "x")[0], 1)
    self.assertEqual(rec("--item", "X01", "--verdict", "relevant", "--source", "S999", "--note", "x")[0], 1)
    self.assertEqual(rec("--item", "X01", "--verdict", "irrelevant", "--note", "  ")[0], 1)
    self.assertEqual(rec("--item", "X01", "--verdict", "duplicate", "--source", "S002", "--note", "same text")[0], 0)
    self.assertEqual(screening.load(d)["verdicts"]["X01"]["source"], "S002")

  def test_bound_and_gate_e9(self):
    d = _screening_study()
    _screen("sample", "--dir", str(d), "--n", "20")
    g = gate.Gate(d)
    g._discovery_check(d, strict=False)
    self.assertTrue(any("unjudged" in f for f in g.fail))
    for i in range(1, 21):
      verdict = "relevant" if i == 3 else "irrelevant"
      _screen("record", "--dir", str(d), "--item", f"X{i:02d}", "--verdict", verdict, "--note", "n")
    s = screening.summary(d, screening.load(d))
    self.assertEqual((s["relevant"], s["relevant_not_fetched"], s["pending"]), (["X03"], ["X03"], []))
    self.assertAlmostEqual(s["cp_upper"], audit.clopper_pearson_upper(1, 20))
    self.assertLessEqual(s["hypergeom_upper"], s["cp_upper"] + 1e-9)  # finite population is tighter
    g = gate.Gate(d)
    g._discovery_check(d, strict=False)
    self.assertTrue(any(f.startswith("E9") and "X03" in f for f in g.fail))
    code, out = _screen("bound", "--dir", str(d))
    self.assertEqual(code, 0)
    self.assertIn("ACTION: fetch", out)

  def test_e9_in_strict_studies(self):
    d = _screening_study()
    g = gate.Gate(d)
    g._discovery_check(d, strict=False)
    self.assertEqual([w for w in g.warn if w.startswith("E9")], [])  # archives: nothing asked
    g = gate.Gate(d)
    g._discovery_check(d, strict=True)
    warns = [w for w in g.warn if w.startswith("E9")]
    self.assertTrue(any("no screening audit" in w for w in warns))
    self.assertTrue(any("coverage and saturation" in w for w in warns))
    (d / "coverage.json").write_text(json.dumps({"sources": 2, "verdict": "SATURATED"}), encoding="utf-8")
    g = gate.Gate(d)
    g._discovery_check(d, strict=True)
    self.assertTrue(any("computed on 2 sources" in w for w in g.warn))


class StudyDirTest(unittest.TestCase):

  def test_messages(self):
    root = Path(tempfile.mkdtemp())
    self.assertIn("does not exist", evidence.study_dir_error(root / "missing"))
    self.assertIn("not a study folder", evidence.study_dir_error(root))
    (root / "plan.md").write_text("| SQ1 | x |\n", encoding="utf-8")
    self.assertEqual(evidence.study_dir_error(root), "")

  def test_tools_refuse_wrong_dir_without_creating_it(self):
    missing = Path(tempfile.mkdtemp()) / "typo"
    for fn, argv in ((screening.main, ["bound"]), (corpus.main, ["stats"]), (claims.main, ["keys"]),
                     (audit.main, ["bound"]), (evidence.main, ["sources"])):
      with contextlib.redirect_stdout(io.StringIO()) as out:
        self.assertEqual(fn(argv + ["--dir", str(missing)]), 2, fn.__module__)
      self.assertIn("does not exist", out.getvalue())
    self.assertFalse(missing.exists())


class RetractTest(unittest.TestCase):

  def _retract(self, d, *argv):
    with contextlib.redirect_stdout(io.StringIO()) as out:
      code = evidence.main(["retract", "--dir", str(d), *argv])
    return code, out.getvalue()

  def test_retract_is_the_only_correction_path(self):
    d = GateTest._setup(None)
    (d / "report.md").write_text(GateTest.GOOD, encoding="utf-8")
    # an opposite-stance copy that slipped in (written by hand, as older agents did)
    bad = dict(evidence._jsonl(d / "evidence.jsonl")[0], id="E003", stance="contradicts")
    evidence._append(d / "evidence.jsonl", bad)
    g = gate.Gate(d)
    g.evidence_stage(min_searches=12, kill_share=0.3)
    self.assertTrue(any("opposite stance" in f for f in g.fail))
    self.assertEqual(next_step.next_step(d)["action"], next_step.HELP["E7dup"][0])
    self.assertEqual(self._retract(d, "--id", "E003", "--reason", " ")[0], 1)
    self.assertEqual(self._retract(d, "--id", "E099", "--reason", "x")[0], 1)
    code, out = self._retract(d, "--id", "E003", "--reason", "opposite-stance copy of E001")
    self.assertEqual(code, 0)
    self.assertNotIn("still cites", out)  # the report never cited E003
    self.assertEqual(self._retract(d, "--id", "E003", "--reason", "again")[0], 1)
    rows = evidence._jsonl(d / "evidence.jsonl")
    self.assertEqual(len(rows), 3)  # kept for the audit trail
    self.assertEqual([r["id"] for r in evidence.load_evidence(d)], ["E001", "E002"])
    g = gate.Gate(d)
    g.evidence_stage(min_searches=12, kill_share=0.3)
    self.assertFalse(any(f.startswith("E7") for f in g.fail))
    # a retracted record cannot be cited, and its id is never reused
    code, out = self._retract(d, "--id", "E002", "--reason", "wrong sq")
    self.assertIn("report.md still cites [E002]", out)
    g = gate.Gate(d)
    g.evidence_stage(min_searches=12, kill_share=0.3)
    g.report_stage(d / "report.md", min_coverage=0.9, min_urls=1)
    self.assertTrue(any("E002, which is not in evidence.jsonl" in f for f in g.fail))
    self.assertEqual(_add(d, sq="K1", stance="contradicts", quote="Commission is $3 per lot round turn"), 0)
    self.assertEqual(evidence._jsonl(d / "evidence.jsonl")[-1]["id"], "E004")

  def test_show_unknown_source_is_an_error_not_a_traceback(self):
    d = _study()
    with contextlib.redirect_stdout(io.StringIO()) as out:
      self.assertEqual(evidence.main(["show", "--dir", str(d), "--source", "S042"]), 1)
    self.assertIn("S042 is not in", out.getvalue())


class TrialFixesTest(unittest.TestCase):
  """Failures found by running a real study (2026-11-03-overnight-drift-trial) through the runbook."""

  def test_template_placeholders_are_not_a_plan(self):
    plan = ("| SQ1 | … | … | T1 | open |\n| K1 | <a T&C clause forbids …> | legal | x | pending | |\n"
            "| K2 | real kill | x | y | pending | |\n")
    self.assertEqual(gate.placeholder_rows(plan), ["SQ1", "K1"])
    d = _study()
    (d / "plan.md").write_text(PLAN + "| SQ2 | … | x | T1 | open |\n", encoding="utf-8")
    g = gate.Gate(d)
    g.evidence_stage(min_searches=12, kill_share=0.3)
    self.assertTrue(any("placeholder rows: SQ2" in f for f in g.fail))
    res = next_step.next_step(d)
    self.assertEqual(res["action"], "Fill plan.md")
    self.assertIn("SQ2", res["why"])

  def test_table_without_row_labels_is_flagged_and_empty_tables_dropped(self):
    lines = parse_pdf.render_table([[None, "SPY", "IVV"], [None, "$0.02", "$0.04"], [None, "0.27", "0.64"]], "p4.t1")
    self.assertTrue(any("no row labels" in x for x in lines))
    self.assertEqual(parse_pdf.render_table([[None, ""], ["", None]], "p3.t2"), [])

  def test_backward_snowball_prefers_related_references(self):
    seed = dict(_work("W1", "Overnight versus intraday expected returns", 2),
                referenced_works=["https://openalex.org/W2", "https://openalex.org/W3"])

    def get(url, headers=None, timeout=12):
      if "/works/W1" in url:
        return _Resp(seed)
      return _Resp({"results": [_work("W2", "Capital asset prices", 20000),
                                _work("W3", "Overnight and intraday price patterns", 40)]})

    with unittest.mock.patch.object(discover, "OPENALEX_MIN_INTERVAL", 0), \
         unittest.mock.patch.object(discover.requests, "get", get):
      res = discover.snowball("W1", "backward", limit=5)
    self.assertEqual([r["openalex_id"] for r in res["results"]], ["W3", "W2"])

  def test_audit_brief_shows_cited_calculations(self):
    d = GateTest._setup(None)
    with contextlib.redirect_stdout(io.StringIO()):
      calc.main(["eval", "--dir", str(d), "--label", "Double cap", "--expr", "2 * cap",
                 "--var", "cap=400000", "--cites", "E001", "--unit", "USD"])
    (d / "report.md").write_text(GateTest.GOOD.replace(
        "[E001].", "[E001]. Two traders: $800,000 [E001, C001]."), encoding="utf-8")
    with contextlib.redirect_stdout(io.StringIO()):
      audit.main(["sample", "--dir", str(d)])
    brief = (d / "audit" / "brief.md").read_text(encoding="utf-8")
    self.assertIn("[C001] Double cap: 2 * cap with cap=400000", brief)

  def test_fetch_never_uses_jina_unless_asked(self):
    d = _study()
    calls = []

    def fake(url, timeout=25, jina_fallback=False):
      calls.append(jina_fallback)
      return {"ok": False, "error": "HTTP 403"}

    with unittest.mock.patch.object(evidence, "fetch_page", fake), contextlib.redirect_stdout(io.StringIO()):
      self.assertEqual(evidence.main(["fetch", "--dir", str(d), "https://blocked.test/a"]), 1)
      evidence.main(["fetch", "--dir", str(d), "--jina", "https://blocked.test/b"])
    self.assertEqual(calls, [False, True])
    failed = evidence._jsonl(d / "sources" / "failed.jsonl")
    self.assertEqual([r["url"] for r in failed], ["https://blocked.test/a", "https://blocked.test/b"])

  def test_screening_brief_shows_earlier_fetch_failure(self):
    d = _screening_study()
    evidence._append(d / "sources" / "failed.jsonl", {"url": "https://web.test/a", "error": "HTTP 403"})
    _screen("sample", "--dir", str(d), "--n", "50")
    items = {it["url"]: it for it in screening.load(d)["items"]}
    self.assertEqual(items["https://web.test/a"]["fetch_error"], "HTTP 403")
    self.assertIn("Earlier fetch failed: HTTP 403", (d / "audit" / "screening_brief.md").read_text(encoding="utf-8"))

  def test_retracted_evidence_drops_dependent_claims_and_calcs(self):
    d = GateTest._setup(None)
    (d / "claims.jsonl").write_text(json.dumps(_claim("CL001", "400,000", ["E001"], "USD")) + "\n",
                                    encoding="utf-8")
    with contextlib.redirect_stdout(io.StringIO()):
      calc.main(["eval", "--dir", str(d), "--label", "x", "--expr", "2 * cap", "--var", "cap=400000",
                 "--cites", "E001"])
      evidence.main(["retract", "--dir", str(d), "--id", "E001", "--reason", "wrong scope"])
    self.assertEqual(evidence.load_claims(d), [])
    self.assertTrue(any("C001" in e for e in calc.verify_calculations(d, {"E002"})))
    with contextlib.redirect_stdout(io.StringIO()):
      self.assertEqual(calc.main(["retract", "--dir", str(d), "--id", "C001", "--reason", " "]), 1)
      self.assertEqual(calc.main(["retract", "--dir", str(d), "--id", "C001", "--reason", "input retracted"]), 0)
      self.assertEqual(calc.main(["retract", "--dir", str(d), "--id", "C001", "--reason", "again"]), 1)
    self.assertEqual(calc.verify_calculations(d, {"E002"}), [])
    self.assertNotIn("C001", calc.load_calculations(d))

  def test_next_step_points_to_sources_table(self):
    d = GateTest._setup(None)
    (d / "report.md").write_text(GateTest.GOOD.split("## Sources")[0] + "## Sources\n", encoding="utf-8")
    res = next_step.next_step(d)
    self.assertEqual(res["action"], "Paste the Sources table")
    self.assertIn("evidence.py sources", res["command"])


class NextStepTest(unittest.TestCase):

  def _main(self, d, *extra):
    with contextlib.redirect_stdout(io.StringIO()) as out:
      code = next_step.main([str(d), *extra])
    return code, out.getvalue()

  def test_not_a_study(self):
    code, out = self._main(Path(tempfile.mkdtemp()))
    self.assertEqual(code, 2)
    self.assertIn("not a study folder", out)

  def test_plan_first(self):
    code, out = self._main(_corpus_study())  # one SQ, no kill hypotheses
    self.assertEqual(code, 1)
    self.assertIn("NEXT: Fill plan.md", out)
    self.assertIn("RUN:", out)

  def test_evidence_failures_map_to_commands(self):
    d = _study()  # plan and searches fine, no evidence yet
    res = next_step.next_step(d)
    self.assertEqual(res["action"], "Capture evidence")
    self.assertIn(f"evidence.py fetch --dir {d.as_posix()}", res["command"])
    self.assertNotIn("{dir}", res["command"])
    _add(d, quote="limited to $400,000 per trader")
    res = next_step.next_step(d)  # SQ1 answered; refuted K1 still has no evidence
    self.assertEqual(res["action"], next_step.HELP["E5"][0])
    self.assertIn("K1", res["why"])
    code, out = self._main(d, "--json")
    self.assertEqual((code, json.loads(out)["status"]), (1, "ACTION"))

  def test_order_draft_then_audit(self):
    d = GateTest._setup(None)
    self.assertEqual(next_step.next_step(d)["action"], "Draft the report")
    (d / "report.md").write_text(GateTest.GOOD, encoding="utf-8")
    self.assertTrue(next_step.next_step(d)["why"].startswith("R1"))  # gate default: >= 5 source URLs
    with unittest.mock.patch.object(gate.Gate, "report_stage", lambda self, *a, **k: None):
      res = next_step.next_step(d)
    self.assertEqual(res["action"], "Run the blind claim audit")
    self.assertIn("audit.py sample", res["command"])

  def test_strict_study_requires_results_then_screening(self):
    d = GateTest._setup(None)
    (d / "study.json").write_text('{"protocol": "4.1"}', encoding="utf-8")
    self.assertEqual(next_step.next_step(d)["action"], next_step.HELP["E4"][0])
    rows = evidence._jsonl(d / "searches.jsonl")
    with (d / "searches.jsonl").open("w", encoding="utf-8") as f:
      for r in rows:
        r["opened"] = ["S001"]
        f.write(json.dumps(r) + "\n")
    res = next_step.next_step(d)
    self.assertEqual(res["action"], "Audit the leads you did not fetch")
    self.assertIn("screening.py sample", res["command"])


if __name__ == "__main__":
  unittest.main()
