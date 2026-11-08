# Deep Research Workspace — Agent Instructions

This workspace exists to produce deep research reports that hold up under audit. These
instructions apply to any AI agent working here (Antigravity, Claude Code, Codex, Cursor, …).

## When the user asks for research

Any request for deep research, an in-depth analysis, due diligence, a literature review, a
comparison of options, or "проучи / направи deep research за …" in ANY domain (finance, law,
tax, medicine, science, software) → **read and follow `.agents/skills/deep-research/SKILL.md`
end to end automatically and by default.** Do not answer from memory, and do not deliver a report
that has not passed the quality gates below.

First time on a machine: `python dr_engine/tools/doctor.py` must print `RESULT: READY` (it names
the fix for anything missing; ask the user before installing packages).

Workflow options (details in `.agents/skills/deep-research/SKILL.md`):

### Option A (DEFAULT & MANDATORY FOR DIRECT RESEARCH): Deep Research v9.0 The Ultimate Frontier
Cuts token consumption by >90% and eliminates multi-step CLI bureaucracy via a declarative pipeline with mechanical bullshit filtering (`B1–B9`):
1. **Turn 0 (Auto-Spec, Skeptic Swarm & Benchmark Radar):** Run `.venv\Scripts\python.exe dr_engine\tools\auto_spec.py generate --prompt "<objective>" --out research/<dir>/study_spec.json` to autonomously classify domain, query `benchmark_radar.py` for live Tier 2 benchmarks (Artificial Analysis / LMSYS), generate orthogonal SQ1..SQ4, deploy the Adversarial Skeptic Swarm for K1..K3 disconfirmation vectors, and optimize Inverse-HHI lead diversity ($N_{\text{eff}} \ge 4.0$) with zero LLM tokens.
2. **Turn 1 (Concurrent Ingestion & BM25 Distillation):** Run `.venv\Scripts\python.exe dr_engine\tools\lean_engine.py ingest --dir research/<dir>` to snapshot sources and compile top-k BM25 passages to `context_pack.md` (0 LLM tokens).
3. **Turn 2 (Synthesis & Code):** Author `report.md` adhering strictly to Rules `B1–B9`:
   - **B1 (No Fake EV):** Enforce unit breakeven math (`required_clients_breakeven`, `monthly_churn_replacements`) in `python:model`. No arbitrary subjective scenario weights.
   - **B2 (Zero-Liability Solo Physics):** In product/SaaS research, reject mutating 2-way real-time write-syncs; mandate Read-Only Diffs, Preflight File Validators, or In-Browser BYOD parsers.
   - **B3 (Modern Microstructure & Friction Gate):** In quant research, sample end >= 2023, friction/1R <= 3.0%, and >= 35 LOC of clean, runnable, zero-stub Python code.
   - **B4 (ChatGPT Falsification Test):** Prove structural defensibility against raw LLM prompt pasting.
   - **B5 (WTP vs Complaint Separation):** Complaints prove incumbent weakness, never newcomer WTP; require pre-committed 14-day falsifiable demand test.
   - **B6 (Biotech & Clinical Physics):** Enforce Phase 2->3 shrinkage ($\ge 30\%$), tolerability dropout ($\le 25\%$), and reject murine/in-vitro extrapolation to clinical GO.
   - **B7 (Legal & Tax Normative Hierarchy):** Bind authority tier (statute vs administrative guidance), prohibit unmapped US/BG cross-jurisdiction conflation, and model net after-tax savings.
   - **B8 (Hardware & Thermodynamic Limits):** Enforce thermodynamic headroom $\le 0.95$ of theoretical limits, BOM unit economics, and manufacturing first-pass yield.
   - **B9 (Temporal Recency & SOTA Benchmark Gate):** Forbid citing deprecated models as current leaders; mandate Tier 2 measured benchmarks (`Artificial Analysis`, `LMSYS`) and recent sample periods ($\ge 2026$) to eliminate Academic Citation Lag.
   - Embedded ` ```python:model ` AST block and ` ```json:manifest ` cryptographic evidence record.
4. **Call 2 (Single-Pass Verification):** Run `.venv\Scripts\python.exe dr_engine\tools\lean_engine.py verify --dir research/<dir>` (validates quotes, executes AST math, enforces B1–B9 via `v9_bullshit_filters.py`, evaluates DerSimonian-Laird $I^2$ and Shingle-Jaccard $N_{\text{eff}}$, and scores EI and IDI in < 100 ms).
5. **Turn 3 (Executable Decision Card):** Run `.venv\Scripts\python.exe dr_engine\tools\decision_card.py build --dir research/<dir>` to compile AST models into a zero-dependency offline HTML5 Decision Card with live interactive sliders, numerical Jacobian sensitivity, and break-even tipping point analytics.

### v10.0 Hardening (2026-11-06, read before authoring any report)
An autonomous audit found that v9.0 could certify a false report. These are now
mechanically enforced; see `.agents/skills/deep-research/SKILL.md` §9 and `CHANGELOG.md`.
- **Rule B0:** any B1–B9 exception is a hard FAIL, not a warning. Non-finite model values
  and malformed sample periods are rejected up front.
- **Disclaimers are local:** `"avoid"` / `"refuted"` / `"treaty"` / `"n=30"` buried in an
  unrelated appendix no longer disarms B1, B2, B3, B7, B9, R8 or R11.
- **B9 is claim-triggered** (fires in any domain) and only snapshot-verified evidence may
  ground a SOTA claim. The bundled `benchmark_radar.py` table is an explicitly
  **unverified offline seed**: run `benchmark_radar.py fetch --dir <study> --category finance`
  before citing a leaderboard.
- **Polyglot ingestion is lossless and charset-correct** (`http_resilience.py`,
  `polyglot_text.py`, `context_ranker.py`), and every trench collector reports its outcome
  through `CollectorLedger` instead of `except: pass`.
- **AI/SOTA is a first-class `auto_spec` domain**; OpenAlex discovery is recency-ranked,
  not citation-ranked. Run `python -m unittest tests.test_v10_hardening -v` for the
  adversarial regression suite.

### v11.0 Unfair Epistemic Dominance (2026-11-06)
See `.agents/skills/deep-research/SKILL.md` §10 and `CHANGELOG.md`.
- **Keyless mirrors:** `http_resilience.fetch_with_fallbacks` recovers bot-walled
  URLs via Memento → Wayback CDX → FxTwitter/PullPush/Redlib → DDG Lite/SearXNG.
  `DR_DISABLE_MIRRORS=1` forces direct-only. **Recovered bodies are SECONDARY
  transcriptions**, never T1; search-cache hits are LEADS ONLY. Live measurement:
  100% endpoint coverage / 81.8% primary-source coverage (both reported).
- **Rule B10 (Dialectical Arbitration):** a Tier-1 `de_jure` claim contradicted by
  a Tier-3/5 `de_facto` postmortem may NOT be averaged or pooled. Declare
  `manifest.dialectics[].axis` = `implementation_drag` /
  `undisclosed_microstructure_friction` / `regulatory_enforcement_asymmetry`.
  Unverified conflicts cap `max_confidence` at **Medium**.
- **Rule R17 (Anti-Fluff):** `IDI >= 100` is now enforced, plus verified-entity
  density `>= 3.0` per 100 words and boilerplate-phrase rejection.
- **Correlated risk:** `risk_engine.py` (Cholesky, 3 macro regimes, empirical
  VaR₉₉/CVaR₉₉) and the Decision Card's correlated Monte Carlo. The v10
  independent-σ default remains available and reproducible.
- Verify with `python -m unittest tests.test_v11_dominance -v` (47 tests) and the
  full `python -m unittest discover -s tests` (322 tests, exit 0).

### v12.0 The Omniscient Golden Nugget & Zero-Lag Intelligence Engine (2026-11-06)
See `.agents/skills/deep-research/SKILL.md` §11, `CHANGELOG.md` and
`reports/ENGINE_AUDIT_v12_2026-11-06.md`. All four frontiers are mechanically
enforced; **358 tests pass (1 skipped), exit 0**, `doctor` READY.

- **Rule B11 — Active Dethroning (`O_dethrone`).** Any "#1" / "world record" /
  "leading model" / "fastest" / "cheapest" / "standard consensus" claim is
  perishable. `auto_spec.generate` detects it and spawns **16 adversarial
  vectors** (8 languages × 30/90-day bands) with COMPUTED `after:` / `before:`
  dates — `"<metric> surpassed by" OR "beat <leader>" OR "new record" OR
  "defeated by" OR "outperformed <leader>"` plus translations. `trench_miner`
  mines them; `dethrone.py` adjudicates a fresh upset phrase + challenger /
  higher measured value as `dethroned`. **A stale, thin or missing check is a
  hard FAIL**, never a warning. Certification requires
  `manifest.dethroning[]` with `status: intact|dethroned`, `vectors_run >= 8`,
  `window_days` in `30|90`, `checked_at` within 30 days, `recency_verified:
  true` and snapshot-verified `evidence_ids`. If dethroned, name
  `superseded_by` in the prose (the 510 → 511 kg upset).
- **Golden Nugget / Insider Anomaly Scorer.** `insider_anomaly.py` declares
  exact insider-witness phrases in 8 languages (EN/RU/ZH/ES/DE/KO/JA/FR + BG).
  Matching is NFKC/diacritic/whitespace-safe. Every matching passage gets a
  fixed **3.0x BM25 prior** in `context_ranker.py`, a bounded prior-only floor
  for zero lexical overlap, and one **reserved slot per query** so obscure
  comments reach `context_pack.md`. `trench_miner` writes
  `bm25_prior=x3.0` and `[GOLDEN NUGGET / INSIDER ANOMALY]` into the snapshot.
- **Rule R18 — Mandatory Epistemic Alpha Delta.** Every v12 report MUST have
  `## Epistemic Alpha Delta` with **Superficial Consensus**, **Trench
  Ground-Truth (The Alpha)** (citing a snapshot-verified `[E###]` NOT cited in
  the consensus) and **Delta Impact** (financial / operational / strategic loss
  with a number or `[E###]`/`[C###]`). Copy-pasting the consensus fails a
  shingle-Jaccard `< 0.70` contrast gate. Template: `templates/report.md`.
- **Protocol versioning & B0.** `auto_spec` emits `protocol_version: "12.0"`;
  `verify_study` applies R18 + B11 only to v12-declared studies (or
  `--strict-v12`), so the 322 pre-v12 tests stay green while NO new study can
  skip the alpha gate. Legacy studies get `W_EAD_LEGACY_STUDY`. The v12 stack
  runs in `ead_gate.run_v12_gates_fail_closed`: any exception is
  `B0 (v12 Gate Integrity / FAIL-CLOSED)`.
- **Zero-fluff hardening.** `http_resilience` is now total over `None` / int /
  bytes / malformed URLs, bad feed templates, non-mapping headers and
  XML-with-encoding-declaration; mirrors are skipped for unsafe targets.
- Verify with `python -m unittest tests.test_v12_golden_nugget -v` (36 tests)
  and the full `python -m unittest discover -s tests` (**358 tests, exit 0**).

### v13.0 Deep Digger, Anti-Truncation Quotas & Mandatory Claim-Link-Quote Ledger (2026-11-07)
See `.agents/skills/deep-research/SKILL.md` §12, `CHANGELOG.md` and
`reports/ENGINE_AUDIT_v13_2026-11-07.md`. Built after the `RP52A–H` audit exposed
lazy 15–30 line unverified stubs, missing quote ledgers, 1-page surface skimming,
and uncalculated hype multipliers; **372 tests pass (1 skipped), exit 0**, 32/32
epistemic evals (`100.0%`), `doctor` READY.

- **Multi-Hop Deep Digger (`deep_digger.py` + `lean_engine.py ingest --deep`).**
  `auto_spec.generate` emits `protocol_version: "13.0"` and queries 4 open-web
  vectors (`official_primary`, `terms_and_rules`, `fine_print_limits`,
  `adversarial_postmortem`) via `DDGS` + keyless DDG HTML fallback alongside
  doubled OpenAlex/arXiv/community/trench budgets. `ingest` preserves HTML
  `<table>` columns as `Col1 | Col2 | Col3`, extracts JSON-LD `FAQPage`/`Product`
  + Next.js `__NEXT_DATA__` Q&As, parses `.pdf` T&Cs (`parse_pdf.pdf_snapshot`),
  and recursively crawls internal `/terms`, `/faq`, `/rules` and `help.*`
  subpages up to `max_depth=2` hops.
- **Rule R19 — Anti-Truncation & Deep-Digging Floor.** Closes the R17
  (`IDI = 1000/word_count`) truncation Goodhart loophole: every v13 report MUST
  contain `>= 1,000` prose words, `>= 5` distinct snapshotted sources, `>= 8`
  verified verbatim `[E###]` quotes, `>= 2` Markdown tables, `>= 5` `## `
  sections, and `>= 4` finite `python:model` variables — while simultaneously
  passing R17 (`IDI >= 100`, `>= 3.0` verified entities/100w, zero boilerplate).
- **Rule R20 — Mandatory `Claim → URL → Verbatim Quote` Ledger.** Every v13
  report MUST include a human-auditable Markdown table (`Твърдение | Източник / Линк | Дословен цитат | ID`)
  with `>= 8` rows where each `[E###]`, registrable domain URL, and verbatim
  quote are mechanically verified against `sources/index.jsonl` and `sources/S###.txt`.
- **Rule B12 — Hyperbolic Verdict, Fake Multiplier & Frequency Guess Ban.**
  Hard-fails hype labels (`MAXIMUM CONVICTION GO`), standalone multipliers
  (`11.8x`, `10.4x`) missing from `python:model` or verified `[E###]` quotes,
  and unbacked rate guesses (`~100-150 occurrences/year`), plus new lab traps in
  `known_traps.json` (`funding dip rebound` dead anomaly, false Pillar 1
  secondary window, unverified prop rules).
- **Rule R21 — Deliverable Attestation & `reports/` Anti-Bypass Guard.** NEVER
  write raw `.md` files directly into `reports/`. Export ONLY via
  `.venv\Scripts\python.exe dr_engine\tools\lean_engine.py export --dir research\<dir> --out reports\<NAME>.md --strict-v13`
  (which re-verifies, writes `verification_receipt.json`, and stamps
  `<!-- DR-ATTESTATION -->`), then run `lean_engine.py audit-deliverables` (`0 violations`).
- Verify with `python -m unittest tests.test_v13_deep_digging -v` (14 tests) and
  the full `python -m unittest discover -s tests` (**373 tests, exit 0**).

### v13.1 Strict Source Grounding & Anti-Graveyard Invariant (2026-11-08)
- **Rule B13 (Anti-Synthetic Citation & Desk Graveyard Prohibition):**
  1. Under NO circumstances shall synthetic, summarized, or local placeholder text files be authored into `sources/` with invented quotes or attributed to external institutions (e.g. BIS, CFTC). Every quoted passage must originate from genuine, pre-existing or publicly downloaded primary documents. Attributing concepts like R-multiples or retail prop firms to macroeconomic/regulatory bodies is a hard, immediate violation.
  2. In trading and quantitative finance research, NEVER propose or resurrect strategies that are already documented as killed in the desk's master architecture directive (`CLAUDE_PROJECT_KNOWLEDGE_MASTER.md`), cost screens, or failure autopsies (e.g. Gold London/LBMA ORB, Crude Oil NY displacement, European DAX/UK100/EU50 cash opens) unless explicit new microstructure or venue physics are proven.
- Enforced mechanically via 4 new traps in `known_traps.json` (`KILLED_EDGE_GOLD_INTRADAY_ORB_LBMA`, `KILLED_EDGE_CRUDE_OIL_INTRADAY`, `KILLED_EDGE_EUROPEAN_CASH_OPEN_ORB`, `SYNTHETIC_REGULATORY_CITATION_BAN`). All 373 unit tests pass.

### v14.0 The Unbreakable Epistemic Pipeline, Pre-Synthesis Locking & Executable Cloud Verification (2026-11-08)
Solves the root causes of agent hallucination, graveyard resurrections, and passive text bias:
- **Turn -1 (Desk Memory & Graveyard Pre-Flight):** Run `.venv\Scripts\python.exe dr_engine\tools\lean_engine.py preflight --dir research/<dir> --prompt "<prompt>"`. Scans the prompt, spec, and plan against `CLAUDE_PROJECT_KNOWLEDGE_MASTER.md` and `known_traps.json` before any research begins. Hard-blocks with exit code 1 if any forensically killed strategy is proposed.
- **Turn 1.5 (Pre-Synthesis Evidence Locking):** Run `.venv\Scripts\python.exe dr_engine\tools\lean_engine.py lock-evidence --dir research/<dir>`. Mechanically verifies all quotes against `sources/S###.txt` before authoring `report.md`. Compiles `evidence_ledger.json` and `evidence_pack.md`. Authors may ONLY cite pre-locked `[E###]` IDs; any unverified quote triggers an immediate failure.
- **Turn 3.5 (Deterministic Executable Google Colab Notebook):** Run `.venv\Scripts\python.exe dr_engine\tools\lean_engine.py colab --dir research/<dir>`. Compiles all AST models (`python:model`), statistical power functions, and friction comparisons into a reproducible `research_notebook.ipynb` runnable in Google Colab with 1 click (`[![Open In Colab]...]`). Math is executed deterministically by a Python runtime, eliminating backtest and numerical hallucinations.
- **Cloud Agent Architecture & Sandboxes (Simular Box & Google Cloud Tech):**
  - **Google Cloud Trajectory Evaluation:** Verification does not evaluate the final text in isolation; it inspects the entire trajectory (tools called, SHA-256 snapshot hashes, AST mathematical models, and zero unrefuted traps).
  - **Simular Box (`box.simular.ai`):** Used as an optional persistent cloud sandbox for 24/7 long-running scrapers, bot-wall bypasses (anti-scraping bypasses), and native MT5 desktop terminal backtest execution.
- All 379 unit tests pass, exit 0.

### Option B (FALLBACK): Granular 14-Step CLI Workflow (v4.x–v7.0)
For complex multi-agent swarms using `next_step.py`:
1. `evidence.py init <slug>` → `research/<date>-<slug>/`; fill `plan.md`
   (question, decision, mechanism hypothesis, user's thesis, SQ1.., **≥ 3 kill hypotheses K1..**)
2. Discover primary & peer-reviewed leads (`discover.py "<query>" --dir <dir> --purpose SQn|Kn`,
   citation snowballing `discover.py --snowball <W-id|DOI> --dir <dir> --purpose SQn`, web search +
   `evidence.py log-search --opened <result URLs> --channel web|registry`), `evidence.py fetch` each page you rely on, `evidence.py add --quote "<verbatim>"`
   per fact (`--kind empirical` also needs `--sample-period` of the number's own table) — ≥ 30% of searches go to kills; ≥ 50% of evidence must be T1–T3 (no Wikipedia/forum inflation)
3. Log all quantitative math & Base/Bear/Stress + breakeven flip thresholds via `calc.py eval` and
   `calc.py decision` (`calculations.jsonl` → `[C###]`). At > ~15 sources: `corpus.py build` +
   `corpus.py triage`, read ranked passages per SQ/K (`corpus.py query --log --purpose SQn|Kn`), not
   whole pages; log load-bearing facts with `claims.py add` and confront every `claims.py conflicts`
   hit in the report's Conflicts section (gate R11)
4. Completeness (protocol 4.1): `screening.py sample` → judge the discarded leads → `screening.py bound`;
   `corpus.py stats --save` (Chapman coverage + saturation; stop discovery at `SATURATED` or explain
   why not in Limitations). Then `gate.py <dir> --stage evidence` (E1–E9) → fix → draft `report.md` citing `[E###]` and `[C###]` from
   `.agents/skills/deep-research/templates/report.md` (check `formula.py <dir>` mechanical confidence cap)
5. Blind claim audit: `audit.py sample --dir <dir>` → a fresh-context verifier subagent judges
   `audit/brief.md` (it sees only the brief and `sources/`) → `audit.py record` → fix every error →
   `audit.py sample` again (fixes are re-judged). Then the gate & Epistemic Scorecard (must PASS):
   ```
   .venv\Scripts\python.exe dr_engine\tools\gate.py research\<dir> --live 5 --scorecard --require-audit
   ```
6. Copy the final report to `reports/` in this workspace (`DR project`); give the user a short
   summary + Executive Decision Card + path + EI scorecard & gate result. Reports stay in `DR project`.
7. **External document / LLM report provided:** If the user supplies an external analysis or
   report (e.g. from Gemini Web, Claude, or a PDF), automatically execute the **Fact-Check
   Protocol**: extract discrete claims, `evidence.py fetch` the underlying primary sources,
   verify verbatim quotes, recompute math with `calc.py`, audit hallucinations, update the report, and re-run the gate.

Search snippets are never evidence; `evidence.py add` rejects quotes that are not
verbatim in a fetched snapshot, and the gate rejects numbers that are not in the cited quotes.

Answer in the user's language (the user usually writes in Bulgarian).

## What is in this folder

| Path | Use it? | What it is |
| :-- | :-- | :-- |
| `.agents/skills/` | **Yes — Installed Skills** | Core protocols (`deep-research`, `doubt-driven-development`, `source-driven-development`; these are in the git repo), plus optional `skills.sh` ecosystem skills installed locally with `npx skills add` (not in the repo): `backtest-expert`, `macro-regime-detector`, `position-sizer`, `crypto-regime-analyzer`, `trader-memory-core`, `grounded-vault`, `session-guard`, `ai-debt-detector`, `paper-context-resolver`, `safe-debug`, `analyze-project`, `python-performance-optimization`, `python-testing-patterns`, `python-error-handling`, `async-python-patterns`, `mcp-builder`, `xlsx` |
| `.agents/rules/deep-research.md` | Yes | Always-on short rules |
| `dr_engine/tools/` | **Yes** | `evidence.py` (fetch → snapshot → verified quote), `causal.py` (Pearl Causal DAGs, Backdoor Criterion d-separation, do-calculus counterfactual simulation), `dialectics.py` (Cochran's Q & DerSimonian-Laird I² meta-analysis, anti-pooling & regime partitioning), `frontier.py` (v6.0 Frontier Engine: Bayesian EVSI optimal stopping, adversarial epistemic tournaments, tipping-point Jacobian dynamics & critical slowing down, topological claim manifolds & Tarjan bridges), `swarm.py` (5-phase subagent dispatch, file-lock sharding & atomic merge), `discover.py` (OpenAlex/CrossRef/arXiv-HTML/EuropePMC discovery, OpenAlex forward/backward snowballing, polite rate-limited client; logs result sets + `candidates.jsonl`), `calc.py` (deterministic AST `[C###]` calculations & Base/Bear/Stress decision + breakeven matrix), `formula.py` (Epistemic Index EI/100, semantic entropy, Shingle Jaccard, N_eff clusters & mechanical confidence ceiling), `extract_doc.py` (LangExtract grounded extractor), `parse_pdf.py` (pdfplumber PDF → snapshot; hierarchical multi-headers forward-fill, section spanners, regression t-stats as quotable rows), `corpus.py` (FTS5/BM25 passage index for 100–500 sources: triage, blind spots, syndication; `stats` = Chapman coverage + saturation curve), `claims.py` (claim ledger + contradiction axes incl. interest & sample), `units.py` (bp/%, RT/per-side, annual→holding cost, long/short financing, bp→R; also inside `calc.py`), `aliases.json` (acronym/synonym groups for corpus query expansion; per-study override), `audit.py` (seeded blind claim audit + error bound), `screening.py` (seeded sample of discarded leads + Clopper-Pearson loss bound), `next_step.py` (prints the single next action with its exact command), `doctor.py` (is this machine ready: dependencies, FTS5, workspace; exact fix per problem), uto_spec.py (Turn 0: autonomous domain classification, SQ1..SQ4 synthesis, Adversarial Skeptic Swarm K1..K3 disconfirmation vectors, Inverse-HHI N_eff >= 4.0 diversity optimizer), community_engine.py (keyless practitioner & community discovery: Reddit, X/Twitter syndication, HN Algolia, StackExchange, Discourse, generic forums; Anti-Goodhart noise gate, B5 epistemic classification), decision_card.py (Turn 3: AST-to-JavaScript reactive transpiler, numerical Jacobian sensitivity & break-even tipping point solver, single-file HTML5 Decision Card), `gate.py` (full E1–E11 & R1–R16 audit), plus `check_report.py` / `verify_citations.py` |
| `dr_engine/evals/` | **Yes** | `eval_runner.py` (openai/evals harness with 32-case epistemic benchmark covering E6–E8 and R3/R6–R10 with automated scorecards) |
| `dr_engine/quant/` | **Yes** | `alpha_miner.py` (Symbolic formulaic alpha generator, turnover filter & cross-alpha orthogonality engine) |
| `dr_engine/science/` | **Yes** | arXiv, OpenAlex, PubMed CLIs (working; stdlib HTTP fallback) |
| `research/` | Yes | One working folder per study (plan, evidence log, drafts) |
| `reports/` | Read for context | Final reports. Older ones (≤ 2026-10-28) predate the gates and are mostly uncited — do not treat their contents as verified facts |
| `dr_engine/core/`, `dr_engine/cli.py` | **No (experimental; local only, not in the git repo)** | Autonomous engine. Audits in `docs/AUDIT_*.md` found the stance classifier and VoI gate unreliable. Do not run it in place of doing the research yourself, and never cite its output as evidence |
| `docs/V4_ARCHITECTURE.md` | Read when changing the protocol | v4.0 design (Bulgarian): ingestion & triage, extraction, contradiction axes, three verification layers, EI critique & EI v2, roadmap |
| `docs/AUDIT_*.md`, `docs/*BLUEPRINT.md` | Only if working on the engine | Engine design and audit history — large; skip for research tasks. **Local only: not in the shared repo; skip if missing** |
| `references/` | Only if asked | Third-party repos kept for reference (~35 MB). **Local only: skip if missing** |
| `scratch/` | No | Old probe/patch scripts and intermediate files. **Local only: skip if missing** |
| `CHANGELOG.md` | Read when updating | What changed in the protocol and tools, newest first |
| `.venv/` | Run tools with it | Project Python environment |

## Agent Skills Management (`skills.sh`)

This workspace integrates with the global open-standard skills registry (https://skills.sh):
- **Search skills:** `npx skills find <keyword>`
- **Install skills to project:** `npx skills add <repo> -s <skill-name> -y` (Antigravity is auto-detected and installs to `.agents/skills/<skill-name>/SKILL.md`)
- **List installed:** `npx skills list`
- Installed skills provide specialized procedural workflows mid-task through progressive disclosure.

## Standards (non-negotiable)

- **Grounding:** every number, date, name, fee, rule and legal statement is cited inline
  with a URL to a source you opened. No fabricated URLs, quotes, IDs or statistics.
  "Not found in the sources checked" is an acceptable answer.
- **Source hierarchy:** primary/official > reputable secondary > community. See
  `.agents/skills/deep-research/references/source-hierarchy.md` (finance, tax/law,
  medicine, science, software rules).
- **Triangulation:** cross-check load-bearing numbers across independent sources; report
  conflicts with their likely cause instead of picking one silently.
- **Disconfirmation:** actively search for evidence against the emerging conclusion
  (`.agents/skills/doubt-driven-development/` describes the general discipline).
- **Calibration:** High / Medium / Low / Unverified confidence; no "guaranteed",
  "proven", "certain". Statistics with their uncertainty.
- **Decisions with money, tax, legal or health consequences:** add a brief "not
  professional advice" note and state what the user should verify themselves.
- **Anti-Goodhart & Completeness Invariant (Zero-Truncation Policy):** Never truncate or shrink
  analysis, tables, or candidate profiles to make verification gates pass faster. Precision
  must never destroy Recall. In product and market due diligence, customer complaint quotes from
  verified platforms (G2, Capterra, Shopify App Store, Reddit) are first-class empirical
  Voice-of-Customer (`--kind review_pain`), excluded from the T1–T3 academic denominator of E7b.
  Use `quotas.json` and rule R14 to enforce mandatory breadth (tables, word count, candidate
  matrices) before passing gates. Batch evidence ingestion is performed via `evidence.py add-batch`
  and candidate scoring via `calc.py score-rubric`.

## Autonomous Self-Improvement Protocol

The agent operating in this workspace is strictly self-improving. You MUST automatically update
the workspace rules, skills, and reference files whenever new knowledge or tooling is discovered:
- **New Failure Modes / Trap Patterns:** If an inquiry uncovers a hidden barrier (e.g. withdrawal locks,
  consistency layers, regulatory transitions, edge decay drivers), immediately record it in
  `SKILL.md` or domain reference files.
- **New Primary Sources & Endpoints:** If a valuable registry, scientific endpoint, or statutory
  source is identified (e.g. RePEc, IDEAS, SSRN, Държавен вестник, Eur-Lex), add it to the tools/skills.
- **New Tooling & Workflow Enhancements:** When new libraries (e.g. `langextract`) or scripts are
  introduced, document them in `SKILL.md`, integrate them with the pipeline, and add tests.
- **Never wait for user instructions to retain lessons:** Persisting improvements into the system's
  knowledge base is an autonomous, standing invariant.

## Working on the code

- Python: `.venv\Scripts\python.exe` (Windows) / `.venv/bin/python`. Tests:
  `python -m unittest tests.test_report_tools -v` (the shared repo's suite; CI runs it on Linux
  and Windows for every push) and `python dr_engine/evals/eval_runner.py`. Local-only extra tests:
  `python -m unittest discover -s tests -v` (`tests/test_tier3_frontier.py` needs `pytest`).
  v10.0 adversarial regression: `python -m unittest tests.test_v10_hardening -v` (39 offline tests
  covering fail-closed B0, scoped disarms, charset/BOM/gzip fetch, CJK BM25, benchmark provenance,
  trench telemetry, bisection and Monte Carlo).
- A new CLI must write UTF-8 (`sys.stdout.reconfigure(encoding="utf-8", errors="replace")` in its
  `__main__` block — Windows pipes are cp1252) and print commands as `python dr_engine/...`, not
  with a Windows-only venv path; a test enforces the first.
- Record each change that alters what a study must do in `CHANGELOG.md`.
- Keep `dr_engine/tools/` and `dr_engine/science/` dependency-light (stdlib + requests/bs4).
- When changing the gates, run them on `reports/` to see the effect, and add a test in
  `tests/test_report_tools.py`.
