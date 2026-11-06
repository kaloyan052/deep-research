# Deep Research Engine v10.0 — Autonomous Architectural Audit & Upgrade

**Date:** 2026-11-06 · **Workspace:** `DR project` · **Status:** COMPLETE, VERIFIED
**Baseline:** `doctor.py` → `RESULT: READY`; `unittest discover -s tests` → 229 pass / 1 skip
**Final:** 275 pass / 1 skip, exit 0, 3.9s · 10/10 module selftests pass · 32/32 epistemic evals pass

---

## 1. Executive conclusion

The engine's *architecture* was sound but its **epistemic enforcement was fail-open**. Five
independent defects could each have certified a false report at `High` confidence. All five
are now closed with deterministic, stdlib-only, auditable code. The most consequential
finding is that a single exception inside the B1–B9 filter stack silently disabled *all*
nine filters while `res.passed` remained `True`.

This audit did not add features to a working system; it removed the ability of a confident
but wrong report to survive verification.

---

## 2. Findings (adversarial, first-principles)

| # | Severity | Defect | Root cause |
|---|---|---|---|
| A1 | **Critical** | B1–B9 unevaluable ⇒ study still PASS | `lean_engine.verify_study` wrapped `run_v9_bullshit_filters` in `except Exception → res.warnings.append(...)`; `res.passed = len(failures)==0` |
| A2 | **Critical** | Global keyword disarm switches | One `"avoid"`, `"refuted"`, `"decayed"`, `"treaty"`, `"scope"`, `"kill"` or `"n=30"` anywhere in a report disabled B1/B2/B3/B7/R8/R11. `NaN > 0.95` is False ⇒ B8 accepted NaN |
| A3 | **High** | B9 unreachable from the real pipeline | `auto_spec.classify_prompt_domain` could only emit 5 domains and defaulted all unmatched prompts to `quant`; B9 and `is_model_query` gated on `"ai"/"tech"/"software"/"finance"` — dead branches. The engine's flagship anti-citation-lag rule never fired on an AI study |
| A4 | **High** | Polyglot ingestion self-defeating | BM25 tokenizer `[a-zа-я0-9]{3,}` discarded all CJK/Hangul/accented-Latin text (6 of 8 mined languages invisible); paragraphs hard-truncated at 800 chars; no dedup/diversity/budget; UTF-8-only decode ignored cp1251/Shift_JIS/GB18030 and gzip; 7 collectors used `except Exception: pass` and fabricated `2026-01-01` dates |
| A5 | **High** | "Live benchmark radar" was a frozen table | `benchmark_radar.py` imported `urllib` but made zero network calls; unknown categories silently returned the finance leaderboard; `get_leader` returned rank-1 for metrics absent from the registry; B9 accepted a self-declared manifest quote string as Tier-2 grounding |

**Additional confirmed defects:** `auto_spec` sorted OpenAlex by `cited_by_count:desc` —
the exact Academic Citation Lag the mission exists to eliminate; `decision_card` used a
single linear Newton step while the protocol claimed bisection; `ast.Pow` had no bound
(`2 ** 100000000` could hang verification); the quote matcher applied normalised-text
offsets to the raw snapshot; unbounded ellipsis gaps allowed splicing distant sentences
into a fabricated quote; `sample_end_year` defaulted to the current year when absent.

---

## 3. What was transformed

### Pillar 1 — Fail-closed epistemic gate
- **New `dr_engine/tools/epistemic_guard.py`**: `is_mitigated_locally` / `unmitigated_spans`
  (qualifier must be within 180–400 chars AND ≤1 sentence boundary of the trigger),
  finite-only `safe_number` / `safe_int`, `normalize_verdict`, `validate_inputs`, and
  `run_filters_fail_closed` (new **Rule B0**).
- `v9_bullshit_filters.py`: B1/B2/B3/B7/B9/R8/R11 rewritten to scoped mitigation; B7
  now requires a structured `normative_physics.treaty_article`; B8 rejects NaN/Inf;
  B3 canonicalises verdicts so `CONDITIONAL_GO` cannot slip past the 3% friction gate;
  **B9 is claim-triggered** (any domain) and accepts only snapshot-verified evidence IDs.
- `lean_engine.verify_study`: B0 hard failure on any filter exception; verdict read from
  the manifest rather than guessed from prose keywords; no fabricated default sample year;
  corrected quote-matching coordinates; `MAX_ELLIPSIS_GAP = 2000`; deterministic AST
  resource budget (`|exponent| ≤ 64`, `|int| ≤ 1e15`, container ≤ 10 000).

### Pillar 2 — Resilient polyglot ingestion
- **New `http_resilience.py`**: BOM/header/meta charset detection, gzip/deflate, bounded
  retry honouring `Retry-After`, bot-wall detection (403 vs retryable 429 are distinct),
  2 MB byte cap, scheme validation, opt-in reader fallback (`DR_ALLOW_JINA=1`), structured
  `FetchResult` with `via` / `charset` / `sha256` / `attempts` / `error`. Never raises.
- **New `polyglot_text.py`**: NFKC + script-selective Latin diacritic folding (Cyrillic
  `й` and Hangul are preserved), Han/Kana bigrams, 2-letter acronym retention (`AI`,
  `ML`, `FX`), number density.
- **New `context_ranker.py`**: overlapping windows (no truncation), number-density BM25
  prior, cross-query dedup, shingle-Jaccard syndication suppression, per-source caps,
  48 000-char budget. `lean_engine.rank_bm25_passages` delegates to it.
- `sources/index.jsonl` now records `via`, `charset`, `bot_wall`, `fetch_warnings`,
  `unverified_bundled`.

### Pillar 3 — Trench miner honesty layer
`CollectorLedger` telemetry for every endpoint (no silent failures), content-SHA-256
dedup, platform-normalised 0–100 `signal_score`, English concept expansion (the v9
dictionary was dead code for English prompts), GitHub rate-limit gate + `github_query()`
precision trimming, generic RSS/Atom collector, honest `"unknown"` dates, hash-anchored
snapshots. **Live smoke test:** 11 collectors → 9 OK, 2 structured failures, 1 bot wall,
81.8% coverage, all reasons recorded.

### Pillar 4 — Benchmark provenance & reachable AI domain
`benchmark_radar.py`: `provenance()`, `staleness()` (45-day limit), strict
`resolve_category()` / metric validation, `fetch_live_snapshot()` /
`attach_live_snapshot()` writing `benchmark_provenance.json`; bundled table demoted to an
explicitly `verified: false` seed with a `[CITATION STATUS: NOT VERIFIED]` banner.
`auto_spec.py`: new `ai` domain + `general` default, recency/relevance OpenAlex ranking,
`collector_provenance`, `warnings`, `unverified_inline_sources`, honest `pub_year=0`.
Ingest flags bundled seeds; verify excludes them from B9 grounding.

### Pillar 5 — Executive decision instruments
`decision_card.py`: true breakeven **bisection** on the executed model (verified against a
non-linear case where the v9 Newton step was wrong), seeded reproducible Monte Carlo
(P5/P50/P95, `P(value<0)`, CDN-free inline SVG histograms), deterministic joint stress
presets, scheme-sanitised links, and **fail-closed build** (refuses unverified studies).

### Knowledge base (autonomous self-improvement invariant)
`CHANGELOG.md`, `AGENTS.md` §v10.0, `.agents/skills/deep-research/SKILL.md` §9, and
both `tests/test_report_tools.py` (4 CI-visible gate tests) and the new
`tests/test_v10_hardening.py` (42 offline adversarial tests) were updated without being
asked.

---

## 4. Verification evidence

```
doctor.py                          RESULT: READY
unittest discover -s tests         Ran 275 tests in 3.923s — OK (skipped=1), exit 0
module selftests                   10 / 10 PASS
epistemic evals                    32 / 32 PASS (100%, zero false positives/negatives)
lean_engine selftest               EI=93.8/100, IDI=101.1, MaxConf=High, N_eff=3.0
full pipeline                      verify PASS (EI=61.3) → decision_card.html 19 206 chars
live trench mining                 11 collectors, 81.8% coverage, failures recorded
```

New adversarial tests explicitly simulate: a filter crash, a distant disarm word, a
`CONDITIONAL_GO` friction bypass, a NaN thermodynamic ratio, an unverified SOTA quote,
a 403 bot wall, a 429 retry, cp1251/Shift_JIS/GB18030 bodies, a 2 500-char paragraph
whose tail was previously discarded, a CJK-only query, `file://` injection, and a
`javascript:` URL in the evidence table.

---

## 5. How v10.0 outperforms a standard AI research agent

| Failure mode | Generic LLM / legacy v9 | v10.0 |
|---|---|---|
| Fabricated numbers | smooth prose, no binding | every number bound to a verbatim SHA-256 snapshot quote or executed `[C###]` AST model |
| Confident but stale SOTA | cites a 2024 paper | claim-triggered B9 requires a *live fetched* Tier-2 benchmark; bundled seeds are refused |
| Hallucinated qualifier | one "refuted" in an appendix disarms a rule | qualifier must be locally attached to the claim |
| Silent tool failure | `except: pass`, looks like "no evidence" | structured `CollectorOutcome` + coverage % + explicit warning |
| Non-English alpha | regex drops CJK, mojibake on cp1251 | 8-script tokenisation with CJK bigrams, charset-correct decoding |
| Long documents | hard 800-char truncation | overlapping windows, syndication dedup, char budget |
| Executive deliverable | static summary | exact tipping points, seeded Monte Carlo, deterministic stress, fail-closed gate |

---

## 6. Residual limitations (stated honestly)

1. **Bundled benchmark data is retained** for backward compatibility and is still a
   hardcoded snapshot. It is now loudly unverified and excluded from B9, but a study must
   run `benchmark_radar.py fetch` to obtain genuinely current numbers. Network access to
   `artificialanalysis.ai` may itself be bot-walled; the fetch reports that explicitly.
2. **Monte Carlo perturbations are independent per input** within a joint draw; no
   correlation matrix is modelled. σ = 10% of baseline is a declared, fixed sensitivity
   assumption, not an empirically estimated volatility. It must not be read as a forecast.
3. **Scoped mitigation is lexical**, not semantic entailment. A deliberately adversarial
   author could still place a disclaiming phrase within 180 characters of a false claim.
   The workspace's blind claim audit (`audit.py` / R12) remains the necessary human-in-
   the-loop defence; B0–B9 are mechanical filters, not truth detectors.
4. **Trench coverage depends on external endpoints.** The live smoke test showed 81.8%
   coverage with 2 failures and 1 bot wall; a study's Limitations section must disclose
   the ledger summary when coverage is below 100%.
5. **Algebraic closure (Depth-1) is intentionally permissive** to allow natural derived
   numbers. It can still bind a number that is arithmetically derivable from cited ones
   but rhetorically unrelated. Tightening it would break legitimate reports; the blind
   audit is the correct control for entailment.
6. **Reader fallback (`r.jina.ai`) is opt-in** and, when used, produces a third-party
   transcription that is explicitly flagged as lower-fidelity. It should not be treated
   as a primary T1 source.

---

## 7. Files changed

**New modules:** `dr_engine/tools/{epistemic_guard,http_resilience,polyglot_text,context_ranker}.py`
**Rewritten:** `trench_miner.py`
**Hardened:** `lean_engine.py`, `v9_bullshit_filters.py`, `benchmark_radar.py`, `auto_spec.py`,
`decision_card.py`
**Docs:** `CHANGELOG.md`, `AGENTS.md`, `.agents/skills/deep-research/SKILL.md`
**Tests:** `tests/test_v10_hardening.py` (new), `tests/test_report_tools.py` (4 gate tests)
**Audit trail:** `scratch/apply_v10_lean_patch.py`, `scratch/apply_v10_autospec_patch.py`
