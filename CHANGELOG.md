# Changelog

Newest first. **Study** lists what an agent must now do differently in a research folder;
**Tools** lists everything else.

## 2026-11-06 — Deep Research v12.0: Omniscient Golden Nugget & Zero-Lag Intelligence

Closes the two failure modes an adversarial live probe exposed: **premature
search termination** (stopping at the first high-SEO answer, e.g. 510 kg while
a 511 kg record was set in Birmingham / citing an announced model instead of a
live staged preview) and the **golden-nugget blindspot** (the decisive three
sentences from an insider on a niche Korean, Russian, German, Japanese, Spanish
or Chinese forum). Baseline 322 tests → **358 pass (1 skipped), exit 0**;
17/17 module selftests; `doctor` READY. Pure Python 3.10+ stdlib, keyless,
cp1252-safe.

**Frontier 1 — Active Dethroning Protocol (Rule B11, `O_dethrone`).**
- New `dr_engine/tools/dethrone.py`. Phrase-based superlative detection
  (`world record`, `#1`, `leading model`, `fastest`, `cheapest`, `SOTA`,
  `standard consensus`, plus RU/ZH/JA/KO/DE/ES record terms). A bare "best
  practice" does not trigger it.
- `build_dethroning_vectors` spawns **16 vectors** = 8 languages × {30, 90}-day
  bands, each with `after:`/`before:` dates computed from `as_of` (default
  `dt.date.today()`), never hardcoded. The literal English vector is
  `"<metric> surpassed by" OR "beat <leader>" OR "new record" OR "defeated by" OR "outperformed <leader>"`.
- `adjudicate_dethroning` requires **fresh** dated evidence, an upset phrase
  in one of 8 languages AND a challenger name or higher measured value.
  Negated statements ("no new record was ratified") are excluded. Stale /
  unknown dates, thin vector coverage or zero evidence produce
  `unverified` / `insufficient_evidence`, which is **fail-closed**.
- `auto_spec.generate` emits `study_spec.dethroning` + `dethrone_30d_en` /
  `dethrone_90d_en` search vectors and a warning; `trench_miner` mines the
  vectors; `lean_engine.ingest` compiles them as BM25 queries.
- `run_b11_dethroning_filter` hard-fails any superlative prose without a
  `manifest.dethroning[]` record with `status intact|dethroned`,
  `vectors_run >= 8`, `window_days ∈ {30,90}`, `checked_at` within 30 days,
  `recency_verified: true` and snapshot-verified `evidence_ids`. A
  `dethroned` leader must name `superseded_by` in the report prose.

**Frontier 2 — Golden Nugget / Insider Anomaly Scorer.**
- New `dr_engine/tools/insider_anomaly.py`: exact insider-witness markers in
  8 languages (EN/RU/ZH/ES/DE/KO/JA/FR) plus BG extras; NFKC + Latin
  diacritic folding, case/whitespace-flexible matching; Shannon-entropy
  diagnostic (reported, never gating).
- `context_ranker.rank_passages` applies a fixed **3.0x BM25 prior**
  (`score = BM25 × (1 + 0.35·density) × 3.0`), a bounded `0.05` prior-only
  floor for zero lexical overlap, one **reserved slot per query**, and returns
  `bm25_base_score`, `insider_prior`, `insider_markers`, `insider_languages`,
  `reserved_slot`. Non-insider ranking is byte-for-byte unchanged.
- `trench_miner.TrenchEvidenceItem` gains `insider_prior`,
  `insider_markers`, `insider_languages`, `dethroning_vector_id`,
  `is_golden_nugget`, a +15 signal bonus, and writes
  `bm25_prior=x3.0` / `[GOLDEN NUGGET / INSIDER ANOMALY]` into the snapshot.
  `context_pack.md` prints `[GOLDEN NUGGET prior=x3.0 langs=…]`.

**Frontier 3 — Epistemic Alpha Delta (Rule R18).**
- New `dr_engine/tools/ead_gate.py` + `templates/report.md` section. Every v12
  report MUST contrast **Superficial Consensus** vs **Trench Ground-Truth (The
  Alpha)** vs **Delta Impact**. The trench section must cite a
  snapshot-verified `[E###]` NOT cited by the consensus; shingle-Jaccard
  between the two bodies must be `< 0.70`; the impact must name a financial /
  operational / strategic loss and carry a number or `[E###]`/`[C###]`.
  Missing headings, placeholders, unverified IDs and copy-paste deltas are
  hard failures. `verify_study` gains `ead_diagnostics`,
  `dethroning_diagnostics`, `v12_protocol_active`; `cmd_verify` prints
  `v12=ON|legacy`, `EAD=PASS|n/a`, `O_dethrone_claims`.
- `ingest` appends the EAD scaffold + compliance checklist + compiled
  `O_dethrone` query IDs to `context_pack.md`.

**Frontier 4 — Zero-fluff & fail-closed polish.**
- `auto_spec` emits `protocol_version: "12.0"`; `verify_study` applies R18+B11
  to v12-declared studies (or `verify --strict-v12`). Pre-v12 studies keep the
  v11 gate stack and get `W_EAD_LEGACY_STUDY`, preserving the 322-test
  invariant without weakening any NEW study.
- `ead_gate.run_v12_gates_fail_closed` converts any gate exception into
  `B0 (v12 Gate Integrity / FAIL-CLOSED)` — Rule B0 remains 100% fail-closed.
- `http_resilience` is total over malformed URLs (`None`, int, bytes,
  `javascript:`, empty host), malformed feed templates, non-mapping headers,
  unbounded/NaN numeric parameters and XML strings with an encoding
  declaration; unsafe targets never contact third-party mirrors.
  `trench_miner` coerces malformed prompts, queries and feed templates and
  records every outcome in `CollectorLedger`.

**Docs / tests:** `AGENTS.md` §v12.0, `SKILL.md` §11,
`tests/test_v12_golden_nugget.py` (36 offline adversarial tests),
`reports/ENGINE_AUDIT_v12_2026-11-06.md`.

## 2026-11-06 — Deep Research v11.0: Unfair Epistemic Dominance

Resolves all four residual limitations from `reports/ENGINE_AUDIT_v10_2026-11-06.md` §6.
Baseline 275 tests → **322 tests pass (1 skipped), exit 0**; 14/14 module selftests;
32/32 epistemic evals. Pure stdlib, keyless, cp1252-safe.

**Frontier 1 — Keyless censorship / bot-wall evasion (81.8% → measured 100%).**
- `http_resilience.py` adds a deterministic ordered fallback chain after direct
  fetch fails: **Memento availability → Wayback CDX (newest 200 capture, raw
  `id_` copy) → syndication (FxTwitter / PullPush deleted-comment archive /
  Redlib) → search mirage (DDG Lite + SearXNG public instances)**.
- New `fetch_with_fallbacks()` returns `via`, `evidence_class`, `source_url`
  and a complete `fallback_chain` audit. `benchmark_fallback_coverage()`
  measures `coverage = recovered/attempted` with a `meets_95pct_target` flag.
- Calling the function IS consent to contact public mirrors; `DR_DISABLE_MIRRORS=1`
  forces direct-only. No API keys, no browser automation, no paid proxy.
- **Epistemic constraint:** recovered bodies are SECONDARY transcriptions, never
  primary T1. `cmd_ingest` records `evidence_class` /
  `secondary_transcription` / `fallback_chain` in `sources/index.jsonl`;
  `verify_study` emits `W_SECONDARY_TRANSCRIPTION`. Search-cache hits are
  LEADS ONLY ("search results are never evidence").
- `trench_miner` adds `enable_mirrors`, `max_rescues`, `coverage_from_ledger()`
  (reporting `coverage_pct`, `primary_coverage_pct`, `lead_only_recoveries`
  separately) and downgraded `MirrorRescue` items. **Live measurement: 11/11
  endpoints = 100% coverage (target ≥95%), 2 mirror rescues; 9/11 = 81.8%
  PRIMARY-source coverage.** The distinction is mechanical, not narrative.

**Frontier 2 — Correlated Monte Carlo & regime-aware stress.**
- New `dr_engine/tools/risk_engine.py`: pure-Python **Cholesky** (`Σ = LLᵀ`)
  with deterministic diagonal jitter and reported **shrinkage toward identity**
  for indefinite declared matrices; named pair/group/matrix correlation specs;
  `correlated_shocks(z_c = L z + μ_r)`; empirical **VaR₉₉ = −Q₀.₀₁(Y)** and
  **CVaR₉₉ = −E[Y | Y ≤ Q₀.₀₁(Y)]** (no normality assumption).
- Three declared **Macro Stress Regimes**: Liquidity Crunch, High-Inflation
  Squeeze, Latency Breakdown (joint mean-shift vectors + equicorrelation, no
  subjective probability weights — B1 intact). Longest-pattern-first name
  matching so `volume` is not swallowed by generic `vol`.
- `decision_card.compute_monte_carlo(..., correlation=, regime=,
  sigma_by_input=)`; the v10 independent-σ=10% default path is preserved
  byte-for-byte. New `compute_regime_stress_scenarios()` and
  `render_risk_svg()` (inline CDN-free SVG with VaR/CVaR markers and a shaded
  loss tail). Two new Decision Card panels expose the tail risk and regimes.

**Frontier 3 — De jure vs de facto Dialectical Arbitration (Rule B10).**
- New `dr_engine/tools/dialectical_arbitration.py` (deliberately separate from
  the pre-existing v5.0 `dialectics.py` claim-ledger CLI).
- Detects a Tier-1/2 `de_jure` "supports" contradiction with a Tier-3/5
  `de_facto` disconfirmation on the same `subject` (scoped — different subjects
  are never conflated). **Forbids simple averaging / DerSimonian-Laird pooling**
  across authority tiers (hard failure).
- Mechanically classifies the delta into `implementation_drag`,
  `undisclosed_microstructure_friction` or
  `regulatory_enforcement_asymmetry`; unclassified / unreconciled deltas are
  hard failures. Structured override: `manifest.dialectics[].axis`.
- Reconciled but unverified conflicts **cap `max_confidence` at Medium** until
  `dialectics[].verification.status == "verified"`. The full matrix is stored
  on `VerificationReport.dialectical_arbitration`.
- Wired through `v9_bullshit_filters.run_b10_dialectical_filter()` and the
  fail-closed `epistemic_guard.run_filters_fail_closed(arbitration_out=...)`;
  any B10 exception is a B0 hard failure.

**Frontier 4 — R17 Anti-Fluff Information Density Gate.**
- New `dr_engine/tools/density_gate.py`: `IDI >= 100` is now **enforced** (v10
  only computed it); verified-entity ratio `D = 100·(2E + 5M + U)/W >= 3.0`
  per 100 words; hard-boilerplate phrases (1 occurrence) and soft-boilerplate
  clusters (≥2 distinct) are rejected. Fenced code is stripped from prose.
- `VerificationReport` gains `empirical_density_per_100w` and
  `boilerplate_hits`; `cmd_verify` prints Density and B10 conflict count.
- Every rejection names the offending phrases and measured numbers — no LLM
  judgement, no tunable subjective weight.

**Docs / tests:** `AGENTS.md` §v11.0, `SKILL.md` §10,
`tests/test_v11_dominance.py` (47 offline adversarial tests),
`reports/ENGINE_AUDIT_v11_2026-11-06.md`.

## 2026-11-06 — Deep Research v10.0: Autonomous Architectural Audit & Institutional Hardening

An unconstrained first-principles audit found five defects that could each let a false
report pass institutional verification. All are now closed. Baseline 229 tests + 39 new
v10.0 tests pass (268 total).

**Study / Protocol (what a study must now do differently):**
- **Rule B0 (Fail-Closed Filter Integrity):** an exception anywhere in B1–B9 is now a hard
  verification FAILURE, never a warning. v9.0 wrapped the filter stack in
  `except Exception -> warnings.append(...)`; since `passed = len(failures)==0`, any
  malformed manifest value silently certified the study with no filter evaluation.
- **Disclaimers must be local.** A single `"avoid"`, `"refuted"`, `"decayed"`, `"scope"`,
  `"treaty"` or `"n=30"` in an unrelated appendix no longer disarms B2/B3/R8/R11/B7/B1.
  A qualifier must be within 180–400 characters of the triggering claim and separated by
  at most one sentence boundary. B1 additionally requires `n >= 30` attached to the EV table.
- **B7 legal conflation now needs structured authority evidence:** declare
  `normative_physics.treaty_article`; a free-text "treaty" keyword is not a legal basis.
- **B9 is claim-triggered, not domain-gated.** It fires on any SOTA/best-model claim or
  deprecated-model mention regardless of `manifest.domain`. Only quotes already verified
  verbatim against immutable SHA-256 snapshots may ground a Tier-2 benchmark claim.
- **Bundled benchmark leaderboards are NOT evidence.** `benchmark_radar.py`'s hardcoded
  table is explicitly `verified: false / citation_allowed: false` with a staleness age.
  A study spec lists such URLs in `unverified_inline_sources`; ingest marks them
  `unverified_bundled: true`; verify excludes them from B9 grounding. Before citing a
  leaderboard, run `benchmark_radar.py fetch --dir <study> --category finance|coding`.
- **Unknown dates are unknown.** Missing publication dates are `"unknown"` with
  `date_known: false` and never receive a recency bonus (v9.0 fabricated `2026-01-01`).
  `counterparty_physics.sample_end_year` may no longer be omitted silently.
- **AI/SOTA is now a first-class domain** (`auto_spec` domain `ai`, plus `general` for
  unmatched prompts). An AI study gets benchmark-staleness, vendor-self-report and
  inference-cost kills instead of quant microstructure kills.
- **Decision Cards are fail-closed:** `decision_card.py build` refuses a study whose
  verification did not pass (override: `--allow-failed`, renders a FAIL-marked card).

**Tools:**
- **New `dr_engine/tools/epistemic_guard.py`:** `is_mitigated_locally`,
  `unmitigated_spans`, finite-only `safe_number`/`safe_int`, `normalize_verdict`,
  `validate_inputs`, `run_filters_fail_closed` (rule B0).
- **New `dr_engine/tools/http_resilience.py`:** BOM/header/meta charset detection
  (cp1251, Shift_JIS, GB18030), gzip/deflate, bounded retry with `Retry-After`,
  bot-wall detection, 2 MB byte cap, scheme validation, opt-in reader fallback
  (`DR_ALLOW_JINA=1`), and a structured `FetchResult` carrying `via`/`sha256`/`status`.
- **New `dr_engine/tools/polyglot_text.py`:** NFKC + script-selective diacritic folding,
  Latin/Cyrillic/Hangul word runs and Han/Kana **bigrams**, 2-letter acronym retention,
  number density. Fixes `[a-zа-я0-9]{3,}` discarding 6 of 8 mined languages.
- **New `dr_engine/tools/context_ranker.py`:** overlapping passage windows (no 800-char
  truncation), number-density BM25 prior, cross-query dedup, shingle-Jaccard syndication
  suppression, per-source diversity cap, hard char budget. `lean_engine.rank_bm25_passages`
  now delegates to it.
- **New `dr_engine/tools/benchmark_radar.py` provenance API:** `provenance()`,
  `staleness()`, strict `resolve_category()`/`get_leader()` metric validation,
  `fetch_live_snapshot()`, `attach_live_snapshot()` writing `benchmark_provenance.json`.
- **`trench_miner.py` v10.0:** `CollectorLedger` fail-loud telemetry for every endpoint
  (no `except: pass`), content-SHA-256 dedup, platform-normalised `signal_score`,
  English concept expansion, GitHub rate-limit gate, `github_query()` precision
  trimming (GitHub ANDs bare terms, so 20-token polyglot queries returned random
  repos), generic RSS/Atom collector, SHA-256-anchored snapshots. Live smoke test:
  11 collectors, 9 OK, 2 structured failures, 1 bot wall, 81.8% coverage.
- **`auto_spec.py` v10.0:** recency/relevance OpenAlex ranking instead of
  `cited_by_count:desc` (the Academic Citation Lag the mission exists to kill),
  `collector_provenance`, `warnings`, `unverified_inline_sources`, honest `pub_year=0`.
- **`lean_engine.py` v10.0:** provenance columns in `sources/index.jsonl`,
  verdict-based R8, scoped R8/R11, no fabricated default sample year, corrected
  normalised-coordinate quote fallback, bounded ellipsis gap, and a deterministic
  AST resource budget (`|exponent| <= 64`, `|int| <= 1e15`).
- **`decision_card.py` v10.0:** true breakeven **bisection** on the executed model
  (v9.0 used a single linear Newton step despite the protocol claiming bisection),
  seeded reproducible Monte Carlo (P5/P50/P95, `P(value<0)`, CDN-free inline SVG
  histograms), deterministic joint stress presets, scheme-sanitised source links.
- **New `tests/test_v10_hardening.py`:** 39 offline adversarial/regression tests;
  `scratch/apply_v10_*_patch.py` retain the auditable transformation record.

## 2026-11-06 — Deep Trench & Obscure Practitioner Mining Engine (v9.0)

Tools / Protocols:
- **`trench_miner.py`:** Dedicated multi-trench miner hunting for high-alpha practitioner evidence across Hacker News comments (Algolia), Quant.StackExchange (LaTeX-preserved bodies), GitHub Issues & PR reviews, and niche forums.
- **Multilingual Semantic Translation Bridge:** Automatically maps Bulgarian/local technical queries into high-precision English search tokens so global practitioner communities (Reddit, HN, GitHub, StackExchange) are mined thoroughly.
- **Mandatory Trench Quota (>= 50%):** Enforces in `auto_spec.py` that at least 50% of ingested evidence sources originate from real practitioner trenches and live measured benchmark tables, preventing sterile academic abstract domination.

## 2026-11-06 — Artificial Analysis Benchmark Grounding & Frontier Model Protocol

Study / Tools:
- **Artificial Analysis & Live Benchmark Grounding:** Hardcoded requirement in `source-hierarchy.md` and discovery protocols to evaluate current AI models via live independent industry benchmarks (`Artificial Analysis Finance & Accounting Index`) rather than relying on citation-lagged academic papers or obsolete 2024 model generations.
- **Systemic Trap Registration:** Added `TRAP_ACADEMIC_CITATION_LAG_FAST_FRONTIER` to `known_traps.json`, forbidding the citation of two-generation-old models (e.g. OpenAI o1/o3-mini, Gemini 2.0, BloombergGPT) as frontier SOTA.
- **SOTA Finance AI Benchmark Study:** Completed verified deep research study on the Artificial Analysis Finance & Accounting Index (118 models evaluated): Gemini 4 Carbon (#1, Score 63, Non-Hallucination 93) vs Claude Opus 5.5 (#2, Score 59, Reasoning 68) vs GPT-6 Astra (#3, Score 57) / GPT-6.1 Sol (#4, Score 56). Generated interactive Decision Card and delivered to Desktop.

## 2026-11-06 — Deep Research v9.0 Next-Level Architecture: Turn 0 (Auto-Spec), Rules B6–B8, and Turn 3 (Decision Card)

Tools:
- **`auto_spec.py` (Turn 0 Pre-Compiler):** Autonomous zero-token spec generation from a 1-sentence prompt. Deterministic domain classification (`quant`, `saas`, `biotech`, `legal`, `deeptech`), entity extraction, orthogonal SQ1..SQ4, Adversarial Skeptic Swarm K1..K3 disconfirmation vectors, OpenAlex inverted-index abstract reconstruction, and Inverse-HHI hostname diversity optimization ($N_{\text{eff}} \ge 4.0$). Selftest executes in < 1 ms.
- **Rules B6–B8 in `v9_bullshit_filters.py`:**
  - **B6 (Biotech/Clinical):** Rejects murine/in-vitro extrapolation to clinical GO; enforces Winner's Curse effect size shrinkage ($\ge 30\%$) and dropout thresholds ($\le 25\%$).
  - **B7 (Legal/Tax):** Enforces normative authority hierarchy (statutes vs administrative guidance) and prohibits unmapped cross-jurisdiction conflation (US IRC vs BG ЗДДФЛ/ЗКПО).
  - **B8 (Hardware/DeepTech):** Enforces first-principles thermodynamic headroom ($\le 0.95$ of Carnot, Shockley-Queisser, etc.), BOM unit costs, and manufacturing yield.
- **`decision_card.py` (Turn 3 Executable Deliverables):** AST-to-JavaScript compiler transforming `python:model` blocks into live interactive HTML5 Decision Cards with zero external CDN dependencies. Features numerical Jacobian elasticity calculation, break-even tipping point bisection, and an expandable SHA-256 cryptographic evidence ledger.

## 2026-11-06 — Keyless Community & Practitioner Engine (v9.0 Integration)

Tools:
- **`community_engine.py` Integration:** Keyless discovery and deterministic ingestion for Reddit (nested JSON, upvote thresholds), X/Twitter (syndication API proxies with link stripping), Hacker News (Algolia API), StackExchange (API v2.3 with LaTeX preserved), Discourse, and generic forums (XenForo, phpBB, Forex Factory).
- **Anti-Goodhart Noise Gate & B5 Rule Enforcement:** Drops negative/low karma and promo shill bots; automatically classifies comments into `review_pain` (`proves="incumbent_weakness"`) vs `technical_lead` (`proves="architectural_workaround"`).
- **Lean Engine Routing:** `_fetch_single_url` in `lean_engine.py` automatically detects community URLs and routes them through `community_engine.fetch_community_url`, splitting comments into BM25 paragraph-aligned passages in `context_pack.md`.

## 2026-11-05 — Frontier Engine v6.0: EVSI Optimal Stopping, Epistemic Tournaments, Tipping Points, Claim-Space Topology

Study:
- **Bayesian EVSI / Optimal Stopping (`frontier.py evsi` / Gate E11):** Discovery now has a
  mathematical stop rule. A Beta-Bernoulli posterior over P(thesis true) is updated by every
  evidence record weighted by source-tier reliability; the analytic EVSI of the next source is
  compared to a cost threshold — `STOP_SATURATED` when the information space is saturated,
  `CONTINUE` otherwise. E11 rejects a saturation verdict that contradicts the E4 search floor.
- **Adversarial Epistemic Tournament (`frontier.py tournament`):** PROPONENT vs SKEPTIC vs
  RED_TEAM score the claim ledger deterministically with Kelly belief bets; convergence is an
  exact Nash check (no profitable unilateral deviation).
- **Non-Linear Dynamics & Tipping Points (`frontier.py dynamics`):** The causal DAG is
  linearized into a Jacobian; the dominant eigenvalue (power iteration) detects critical slowing
  down (|λ| ≥ 0.9), a Gaussian-elimination bifurcation scan locates the parameter flip point,
  and a threshold cascade simulates contagion.
- **Topological Claim Space (`frontier.py topology`):** Citation + conflict graph with Tarjan
  articulation points/bridges, unchallenged-claim blind spots, and a spectral (power-iteration)
  narrative-manifold layout — no external embedding models.
- **Gate R16 / next_step.py:** When v6.0 artifacts exist (or `quotas.json` sets
  `require_v6_frontier`), `gate.py` verifies their sha256 integrity and requires the report to
  discuss the EVSI verdict, tournament equilibrium, tipping point/eigenvalue, and blind spots.

Tools:
- New `dr_engine/tools/frontier.py` (stdlib only, cp1252-safe stdout) with subcommands
  `evsi | tournament | dynamics | topology | verify | render`, writing sha256-stamped
  `evsi.json` / `tournament.json` / `dynamics.json` / `topology.json` into the study folder.
- `gate.py` gains gates E11 (evidence stage) and R16 (report stage); `next_step.py` orders them
  with exact fix commands. Full backward compatibility with E1–E10 / R1–R15 study folders.
- `tests/test_v6_frontier.py`: 13 unit tests covering posterior math, EVSI/EVPI bounds, Nash
  deviation sweep, eigenvalue/bifurcation/cascade correctness, Tarjan topology, tamper
  detection, and gate E11/R16 integration. Blueprint: `docs/V6_ARCHITECTURE.md`.

## 2026-11-05 — Frontier Causal & Dialectical Engine (v5.0)

Study:
- **Pearl Structural Causal Models & Counterfactuals (`causal.py` / Gate E10):** Studies define mechanism
  DAGs in `causal_dag.json` with baseline metrics, sign, elasticity betas, physical mechanisms, and explicit
  confounder forks or selection colliders. Pearl's d-separation verifies Backdoor Criterion identifiability
  before simulating counterfactual `do(X = x')` shocks.
- **Dialectical Conflict Synthesis & Heterogeneity (`dialectics.py` / Gate R15):** Contradictions from
  `claims.py` undergo structured thesis/antithesis debate with automated 8-axis divergence classification.
  DerSimonian–Laird random-effects meta-analysis and Cochran's Q / I² tests strictly prohibit naive
  averaging/pooling when I² > 50%, enforcing non-empty regime-partitioning rules.
- **Multi-Agent Swarm Orchestration (`swarm.py`):** 5-phase subagent dispatch (Planner -> Scouts ->
  Extractor -> Synthesizers -> Blind Auditor) with file-lock sharding (`swarm/shards/*.jsonl`) preventing
  write contention and context rot.
- **Hierarchical Table Extraction (`parse_pdf.py`):** Academic regression tables with parenthesized
  standard errors/t-stats and multi-level headers with forward-fill are flattened into quotable rows.
- **Epistemic Index v5.0 (`formula.py`):** Triangulation T_D upgrades to an information-theoretic model
  measuring Shingle Jaccard overlap, rare numeric syndication signatures, Inverse-HHI effective clusters N_eff,
  and normalized Shannon entropy to penalize echo chambers.
- **Protocol 5.0 Initialization:** `evidence.py init` now stamps `protocol: "5.0"` and automatically initializes
  `quotas.json` requiring both Causal DAG and Dialectics verification.

## 2026-11-04 — Anti-Goodhart Architecture & Completeness Engine (v4.2)

Study:
- **Zero-Truncation Policy:** High-stakes research must satisfy breadth and recall quotas without
  defensively compressing analysis or deleting candidate tables to bypass gates.
- **`quotas.json` & Gate R14:** Studies define explicit completion thresholds (word count, table rows,
  unique review quotes, deep-dive section length). `gate.py` and `next_step.py` enforce these quotas
  before final sign-off.
- **Voice-of-Customer (`review_pain`):** User complaint quotes from verified app stores and B2B directories
  (G2, Capterra, Shopify, Chrome Web Store, Atlassian, Reddit) are treated as first-class empirical
  data (`--kind review_pain`), excluded from the academic T1–T3 denominator of E7b.
- **Structural Whitelisting & Table Row-Scope Binding (R3):** Table rows are evaluated by row-scope union;
  structural tokens (row indices, SQ1–SQ5, K1–K5, rating scales 1–5★, template deadlines) do not trigger
  unbound number failures. Heuristic candidate scoring is supported via `[I]` / `[EST]` accompanied by
  deterministic `[C###]` calculations.
- **Batch Evidence Ingestion:** `evidence.py add-batch --file <jsonl>` allows rapid batch registration of
  verified candidate cards and complaint quotes.
- **Rubric Scoring Engine:** `calc.py score-rubric --file <candidates.json>` computes 9-criterion candidate
  evaluations, registers deterministic AST calculations, and renders compliant markdown comparison tables.

## 2026-11-04 — marketplace review measurement

Study:
- Shopify's displayed score is weighted; record its definition and date, calculate arithmetic
  averages only from star counts, date-filter recent complaints, and distinguish reviews from
  paying customers. See `.agents/skills/deep-research/references/source-hierarchy.md`.
## 2026-11-04 — clean install, period sentinel, audit rounds

Study:
- `evidence.py add --kind empirical` is refused without `--sample-period` when the page names a
  period near the quote (1,500 characters above, 500 below). The message lists those periods,
  nearest first, tagged `(above)` / `(below)` / `(in quote)`; use the period of the number's own
  table or paragraph, or `--sample-period unknown`. A stated period that matches none of them
  prints a NOTE. Records keep the list as `context_periods`. (The first trial cited a table's
  4.6% with the paper's overall period; every mechanical gate passed it.)
- `audit.py sample` on an unchanged report keeps every verdict (it used to wipe them). After an
  edit, an error sentence still in the report stays in the audit even when the new draw misses
  it, and the sentence that replaced a fixed error always goes to the verifier. Items kept this
  way count as verdicts but not toward the random-sample bound. `--fresh` re-sends unchanged
  `supported` sentences and never drops an error.
- The audit brief shows each quote inside its passage in the saved page (marked ⟪ ⟫) with the
  periods named near it.
- `next_step.py` also asks for a Limitations line when the screening loss bound is above 20%
  (`screening.MAX_LOSS`, the same threshold as gate E9's warning).
- `extract_doc.py` prints evidence command templates that leave `--stance` and `--claim` to the
  agent (it used to pre-fill `--stance supports` for every extraction).

Tools:
- New `dr_engine/tools/doctor.py`: checks Python ≥ 3.10, the required packages, SQLite FTS5 and
  the workspace files, and prints the exact fix for each problem.
- `lxml_html_clean` added to `requirements.txt`: on a fresh install with lxml ≥ 5.2, trafilatura
  failed to import and page metadata was silently empty.
- `langextract` is optional again: the test suite and the offline extractor run without it, and
  `--html` writes a static view.
- Every CLI writes UTF-8. Printing Cyrillic through a pipe (how agents read tool output) crashed the
  science CLIs, `extract_doc.py` and `alpha_miner.py` on Windows (cp1252); a test enforces it.
- CI (`.github/workflows/tests.yml`): the test suite and the epistemic evals on Ubuntu
  (Python 3.10 and 3.13) and Windows (3.13) on every push.

## 2026-11-04 — open-access copies first, page metadata (1cd2616)

- `discover.py` fetches the legal open copy (OpenAlex `best_oa_location`) before the DOI landing
  page and flags preprints and accepted manuscripts.
- `evidence.py fetch` records title, page date, author and publisher from page metadata
  (trafilatura, metadata only: its main-text extraction lost 28 of 88 previously cited quotes).

## 2026-11-03 — first shared version (3db6303)

- Protocol 4.1: the RUNBOOK and `next_step.py`; P1 (units, strict kill-search results, aliases,
  interest and sample conflict axes); P2 (PDF tables as quotable rows, Chapman coverage and
  saturation, OpenAlex snowballing, screening with a loss bound, gate E9); `evidence.py retract`
  and `calc.py retract`; the third-party reader r.jina.ai only with `--jina`.
