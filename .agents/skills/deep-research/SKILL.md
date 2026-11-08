---
name: deep-research
description: >-
  Due-diligence-grade deep research (v4.0): kill hypotheses written before searching, multi-registry
  scholarly & primary discovery (discover.py), every fact captured from a fetched page snapshot with
  a verbatim quote (evidence.py), deterministic AST-verified calculations & Base/Bear/Stress decision
  matrices (calc.py [C###]), mechanical confidence ceiling & Epistemic Index (formula.py), a BM25
  passage corpus for 100-500 sources (corpus.py), a claim ledger with contradiction axes (claims.py),
  a blind sampled claim audit with a statistical error bound (audit.py), discovery completeness
  (OpenAlex snowballing, Chapman coverage & saturation, screening audit of discarded leads), PDF
  tables as quotable rows, a one-command gate (gate.py) that must pass before delivery, and
  next_step.py, which prints the single next action so any model can follow the RUNBOOK. Use for "deep research", "дълбоко проучване",
  "проучи подробно", due diligence, literature reviews, and any high-stakes decision.
---

# Deep Research Protocol (v9.0 "The Ultimate Frontier")

v9.0 unites the alpha engineering and runnable code generation of frontier models with the deterministic capital-preservation, operational safety, and bullshit filtering of `dr_engine`. By replacing multi-turn CLI loops with a **2-Turn Declarative Compiler** ($T \le 2$) and enforcing five mechanical **Epistemic & Operational Bullshit Filters (`B1–B5`)**, v9.0 cuts token consumption by $>90\%$ while guaranteeing that every report is maximally useful, mathematically sound, and operationally safe.

---

## 1. The Zero-Waste Pipeline ($T = 2$ Ceiling)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ TURN 1 (Plan & Spec): Agent writes `research/<date>-<slug>/study_spec.json` │
│         - sub_questions (SQ1..SQ5)                                          │
│         - kill_hypotheses (K1..K3 with numeric disconfirmation thresholds)  │
│         - urls (primary academic/exchange sources) OR inline_sources text   │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ STAGE 1B: `python dr_engine/tools/lean_engine.py ingest --dir research/<dir>`│
│         - Concurrent fetching (16 workers) & SHA-256 snapshotting           │
│         - Lossless distillation: table flattening, VoC card extraction,     │
│           syndication deduplication, and number-density BM25 ranking        │
│         - Emits bounded context directly to `context_pack.md` (0 LLM tokens)│
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ TURN 2 (Synthesis & Code): Agent writes `research/<dir>/report.md`          │
│         - Reads `context_pack.md` (no raw HTML token waste)                 │
│         - Embeds executable AST math: ` ```python:model C001 `              │
│         - Embeds production-grade Python code (>= 35 LOC, zero stubs)       │
│         - Employs Depth-1 Algebraic Closure for natural derived numbers     │
│         - Embeds ` ```json:manifest ` (quotes, kills, and B1-B5 metadata)   │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ STAGE 2B: `python dr_engine/tools/lean_engine.py verify --dir research/<dir>`│
│         - Validates quotes verbatim against SHA-256 snapshots in < 50ms    │
│         - Executes deterministic AST models & binds derived algebra         │
│         - Enforces Rules B1–B5 via `dr_engine/tools/v9_bullshit_filters.py` │
│         - Computes DerSimonian-Laird I² pooling & Shingle-Jaccard N_eff     │
│         - Evaluates Epistemic Index (EI) and Information Density Index (IDI)│
│         - 0 LLM tokens consumed for verification                            │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. The Nine Epistemic & Operational Bullshit Filters (`B1–B9`)

Enforced deterministically by `v9_bullshit_filters.py` during verification:

1. **Rule B1 (No Fake EV & Unit Breakeven Mandate):**
   - Strictly BANS subjective scenario weights ($p_{\text{base}}, p_{\text{bear}}, p_{\text{stress}}$) unless backed by an empirical sample size $n \ge 30$ cited in `[E###]`.
   - In B2B/SaaS mode, mandates deterministic unit economics variables in `python:model`:
     * `required_clients_breakeven = target_mrr / net_price`
     * `monthly_churn_replacements = required_clients_breakeven * monthly_churn_rate`
2. **Rule B2 (Zero-Liability Solo Operational Physics — Product/SaaS Mode):**
   - Strictly REJECTS high-liability mutating architectures for solo founders: two-way real-time write-syncs, live order cancellations, and custodial funds routing.
   - MANDATES Zero-Liability Sentry architectures: `read_only_diff`, `preflight_validator`, `in_browser_byod_parser`, `offline_quota_sentry`, `deterministic_audit_report`.
3. **Rule B3 (Modern Microstructure, Jacobian Friction Gate & Runnable Code — Quant Mode):**
   - Rejects decayed pre-2023 textbook anomalies (overnight drift post-2021, naive TOTM, London 4 PM fix).
   - Enforces the **3.0% Jacobian Friction Limit**: $C_{\text{RT}} / \text{Stop}_{1R} \le 0.030$. If friction consumes $> 3.0\%$ of $1R$, verdict must be `NO-GO` / `KILL`.
   - Mandates $\ge 35$ LOC of clean, runnable, PEP 8 Python execution code with zero `TODO` or `pass` stubs.
4. **Rule B4 (The "ChatGPT Wrapper" Falsification Test — Product/SaaS Mode):**
   - Proves why the solution cannot be replicated by prompting standard ChatGPT/Claude (requires large local file parsing, multi-file schema diffing, or statutory XSD validation).
5. **Rule B5 (WTP vs. Complaint Separation & 14-Day Demand Test):**
   - Customer complaints (`review_pain`) prove incumbent supply weakness, NEVER willingness to pay a new entrant.
   - Mandates a pre-committed **14-Day Falsifiable Demand Test** with a numeric pass/kill threshold (e.g. $\ge 5$ paid checkouts at €29/mo).
6. **Rule B6 (Biotech & Clinical Physics — Clinical & Pharma Mode):**
   - Mandates Phase 2 $\to$ Phase 3 effect size shrinkage $\ge 30\%$, tolerability dropout rate $\le 25\%$, and prohibits murine / in-vitro extrapolation to clinical `GO`.
7. **Rule B7 (Legal & Tax Normative Hierarchy — Law/Tax Mode):**
   - Binds authority tier (statute vs administrative guidance), prohibits unmapped cross-jurisdiction conflation (e.g. US Section 1256 vs BG ЗДДФЛ), and models net after-tax savings.
8. **Rule B8 (Hardware & Thermodynamic Limits — DeepTech Mode):**
   - Enforces thermodynamic headroom $\le 0.95$ of theoretical Carnot/Betz/Shockley-Queisser limits, BOM unit economics, and manufacturing first-pass yield.
9. **Rule B9 (Temporal Recency & SOTA Benchmark Grounding — Tech & AI Mode):**
   - Forbids declaring deprecated models (e.g. BloombergGPT, FinGPT, GPT-3.5) or older generations as current SOTA without explicitly identifying their obsolescence.
   - Mandates citing measured Tier 2 independent benchmarks (such as **Artificial Analysis**, LMSYS / Chatbot Arena, SWE-bench) for any comparative superiority or "best model" claim, preventing Academic Citation Lag.

---

## 3. Fallback Operating Mode: Granular 14-Step CLI Workflow (v4.0–v7.0)

For complex multi-agent swarms using `next_step.py`:

This protocol is executed by models of very different strength. Do not interpret it; execute it.
`D` below is the folder printed by step 1 (`research/<YYYY-MM-DD>-<slug>`). `python` means
`.venv\Scripts\python.exe` (Windows) or `.venv/bin/python`.

**Rule 0 — the loop.** After EVERY step run
`python dr_engine/tools/next_step.py D` and do exactly the ONE action it prints (`NEXT` / `RUN` /
`WHY`). Exit code 0 = DONE, 1 = do the printed action, 2 = wrong folder. Never skip ahead of it,
never argue with it, never stop before it prints `DONE`.

| # | Step | Exact command(s) | Done when |
| :-- | :-- | :-- | :-- |
| 0 | Machine (once per clone) | `python dr_engine/tools/doctor.py` | prints `RESULT: READY`; otherwise run the printed `fix:` commands (installing packages needs the user's OK) |
| 1 | Start | `python dr_engine/tools/evidence.py init <slug>` | it printed `D` (contains `plan.md`, `study.json`) |
| 2 | Plan | edit `D/plan.md`: question, decision + stake, user's thesis, mechanism hypothesis, 4–8 rows `\| SQn \| ... \|`, ≥ 3 rows `\| Kn \| <how the thesis could be wrong> \| <kill threshold> \|` | `next_step.py` no longer says "Fill plan.md". STOP and ask the user if you cannot name the decision |
| 3 | Discover | per SQ/K: `discover.py "<query>" --dir D --purpose SQn\|Kn`; from the 1–3 best papers: `discover.py --snowball <W-id or DOI> --direction both --dir D --purpose SQn`; web: host search, then `evidence.py log-search --dir D --purpose Kn --query "..." --opened <EVERY result URL you saw> --channel web\|registry` | ≥ 12 searches, ≥ 30% for kills, ≥ 3 per Kn, each with its result URLs recorded |
| 4 | Capture | `evidence.py fetch --dir D <url>` for every page you rely on → `evidence.py show --dir D --source S### --grep "<word>"` → `evidence.py add --dir D --source S### --sq SQn\|Kn --tier T1..T5 --kind de_jure\|de_facto\|empirical\|context\|review_pain --stance ... --quote "<copied from show>" --claim "..."` (or batch register via `evidence.py add-batch --dir D --file batch.jsonl`; `--kind empirical`: add `--sample-period` of the number's own table — `add` refuses without it when the page names a period near the quote, and lists those periods) | every SQ/K has evidence or is marked unresolved; ≥ 50% T1–T3 (excluding review_pain) |
| 5 | Corpus (> 15 sources) | `corpus.py build --dir D` → `corpus.py triage --dir D` → `corpus.py query --dir D "<terms>" --log --purpose SQn\|Kn` | each SQ/K read through ranked passages |
| 6 | Claim ledger | `claims.py add --dir D ... --eids E### --load-bearing` per number/rule/status the decision rests on → `claims.py conflicts --dir D` | every conflict known |
| 7 | Completeness | `screening.py sample --dir D` → judge every `X##` in `D/audit/screening_brief.md` (fetch the relevant ones first) with `screening.py record` → `screening.py bound --dir D`; then `corpus.py stats --dir D --save` (rebuilds the corpus first) | stats says `SATURATED` (coverage ≥ 80% and < 1 new decisive fact in each of the last 2 batches of 10 sources), or `CONTINUE`/`UNKNOWN` is explained in the report's Limitations. On `CONTINUE` first go back to step 3 with the printed blind spots |
| 8 | Numbers | `calc.py eval` / `calc.py decision` for every derived number; `units.py` / `calc.py` for every unit conversion | no number in your head |
| 9 | Evidence gate | `gate.py D --stage evidence` | no `[FAIL]` line |
| 10 | Draft | copy `.agents/skills/deep-research/templates/report.md` to `D/report.md`, fill it from `claims.py table --dir D`; `formula.py D --markdown` | declared confidence ≤ the ceiling |
| 11 | Report gate | `gate.py D` | no `[FAIL]` line except R12 (audit not done yet) |
| 12 | Blind audit | `audit.py sample --dir D` → a FRESH verifier judges `D/audit/brief.md` → `audit.py record` → fix every non-`supported` sentence → `audit.py sample --dir D` again (keeps every verdict on unchanged sentences, keeps unfixed errors in the audit, sends each fix to the verifier) | no known error, bound ≤ 15% |
| 13 | Final gate | `gate.py D --live 5 --scorecard --require-audit` | prints `[PASS]`, exit code 0 |
| 14 | Deliver | copy `D/report.md` to `reports/<TOPIC>_<YYYY-MM-DD>.md`; `next_step.py D` | prints `DONE`; give the user the summary, Decision Card, path, scorecard and gate result |

**When a tool prints `ERROR` or the gate prints `[FAIL]`:** do exactly what the message says (each
message names the fix). Do not work around it, do not weaken the sentence, do not edit data files.
If the same error comes back 3 times, STOP and show the user the exact message.

**Never:**
- edit `evidence.jsonl`, `calculations.jsonl`, `searches.jsonl`, `candidates.jsonl`, `claims.jsonl`,
  `sources/`, `audit/*.json` or `coverage.json` by hand — the tools hash and validate them. A wrong
  evidence record (duplicate, opposite-stance copy, wrong tier, quote from a changed snapshot) is
  withdrawn with `evidence.py retract --dir D --id E### --reason "..."` and logged again correctly;
- type a quote from memory or from a search snippet — copy it from `evidence.py show`;
- write a number that is not in a cited quote or a `[C###]` record;
- mark a kill hypothesis `refuted` or `confirmed` without evidence recorded on that `Kn`;
- judge your own audit or screening sample in the same context that wrote the report — use a
  subagent (Claude Code `Agent`) or, if the host has none, a NEW chat given only the brief and `sources/`;
- put a finding in the Sources / Verification sections (R13) — findings go in the body with `[E###]`;
- deliver while `next_step.py` exits 1.

## HARD CONSTRAINTS — read before every study, re-read before writing

These are enforced by `dr_engine/tools/gate.py`. A report that fails the gate is not done.

1. **Search results are leads, never evidence.** The only way a fact enters the report is:
   `evidence.py fetch <url>` → read the snapshot → `evidence.py add --quote "<verbatim>"`.
   `add` refuses quotes that are not verbatim in a fetched snapshot.
2. **Fix misses at the source — never weaken a claim or slap `Извод:` to game the gate.**
   If a number or rule is missing from `evidence.jsonl`, go fetch the primary document (`T1`–`T3`)
   or compute it deterministically with `calc.py eval` (`[C###]`). Never delete load-bearing
   specifics or wrap numbers in `Inference:` / `Извод:` to evade audit.
3. **Strict Number & Calculation Binding (gates E8, R2, R3, R9).**
   - Every claim-bearing sentence or table row (including Row 1 of every Markdown table!) cites
     existing `[E###]` (and `[C###]` if derived).
   - **Qualitative vs Quantitative Separation:** `Inference:` / `Извод:` is strictly for qualitative
     deductions and **cannot introduce unbound numbers** (gate R3).
   - Quantitative derivations should be logged via `calc.py eval` or `calc.py decision` into
     `calculations.jsonl` and cited as `[E001, C001]` (verified by gate E8). Inline `Calculation:`
     prose requires an explicit mathematical equation/operator (`=`, `+`, `-`, `*`, `/`) and cannot
     exceed 40% of claim units (gate R9).
4. **Kill hypotheses come first (gates E3, E4).** ≥ 3 written in `plan.md` before the first search;
   ≥ 30% of logged searches spent trying to prove them true; ≥ 3 searches each.
5. **Contradicting evidence must be confronted (gate R4).** Every `--stance contradicts` record is
   cited in the report body. Stance-flipping the exact same quote as both `supports` and
   `contradicts` is prohibited (gate E7).
6. **Primary & Peer-Reviewed Depth Floor (gates E6, E7).**
   - Community platforms (Reddit, Substack, Medium, YouTube, Trustpilot, forums) and unofficial
     personal GitHub repos must be `T5` (gate E6).
   - Tertiary encyclopedias and retail explainers (Wikipedia, Investopedia, Britannica, BabyPips,
     CFI, NerdWallet) must be `T4` context/secondary, **never `T1`–`T3`** (gate E6).
   - At least **50% of logged evidence** in any study (with ≥ 4 items) must come from genuine
     `T1`–`T3` sources (statutes, contracts, regulators, official docs, peer-reviewed papers — gate E7).
7. **Deterministic Epistemic Formula & Mechanical Confidence Ceiling (gate R10).**
   `formula.py` computes the **Epistemic Index** $\text{EI} = 100 \cdot (0.35 A_E + 0.25 T_D + 0.20 S_K + 0.20 V_Q)$
   and caps overall confidence (`High` / `Medium` / `Low`). Every Decision & Sensitivity Matrix must be calibrated with deterministic `[C###]` calculations representing the **exact topic-specific economics** (holding period friction, holdout sample size $N$, expected $t$-stat, and deploy probability). **Never copy-paste generic €38.5k / 50-35-15 EV tables**, and never display positive net EV when the verdict is NONE FOUND or KILL. Declaring `Overall Confidence: High`
   when `formula.py` caps the study at `Medium` or `Low` fails gate R10.
8. **Calibrated Probabilities Only (gate R7).** Arbitrary probability intervals (`[0.02, 0.05, 0.12]`)
   and subjective Bayesian priors (`π = 0.55`) are forbidden unless backed by an explicit empirical
   sample size (`n=...`) or formal `Calculation:` / `[C###]` model.
9. **Lab Data Dominance & Known Traps (gate R8).** Internal empirical execution data strictly
   overrides published literature. All registered trap patterns in `dr_engine/tools/known_traps.json` are mechanically enforced:
   - *London 4 PM Fix Reversal:* refuted in lab ($t = -11.09$, P31/FXFIX01/FXFIX02).
   - *Multi-Asset Seasonality:* monthly (not daily), gross Sharpe 0.32–0.37 decays out-of-sample, zero in FX, swap (>0.60 Sharpe) turns net returns negative, $N_{eff} \approx 4.23$ breadth. Never grant conditional approval without post-pub survival.
   - *Holding Costs vs Floors:* never compare annual swap rates to per-trade hurdle floors (G9); compute $C_{hold} = \text{spread} + \text{nights} \times \text{daily\_swap}$.
   - *CFD Long-Short Financing:* long pays interest, short receives interest; net spread is $r_{long} - r_{short} \approx 6.0\%$ p.a. (1.64 bp/day), not 850 bp flat. A 20% earnings gap in a 20-stock book is 1.0% equity loss, not 5%.
   - *FX Geometry vs Multi-Day:* EURUSD under 10 bp stop has $0.070R$ friction failing S2 ($>0.030R$); multi-day holding friction on indices/gold does not bind ($0.004–0.016R$).
   - *Legal analogies:* Natural person KYC does not confer EU consumer protection; commercial terms override.
   - *Community sources:* Unofficial wrappers/repos are T5, not T1/T2.
10. **No self-assessment & zero fabrication (gate R6).** No "9/10" or rubric self-scores. Never
    fabricate a URL, quote, ID, or statistic.
11. **Log what a search found, not just that it ran (gate E4 — FAIL on protocol 4.1).** In 35 studies, 307 of 376
    kill searches recorded no results, and one study padded its kill budget with "Extra kill budget
    query" entries. A search with no result set proves nothing. Use `corpus.py query --log`,
    `discover.py --dir`, or `evidence.py log-search --opened <top result URLs or S###>` (list what came back even when nothing was relevant). Studies created by `evidence.py init` carry `study.json` (protocol 4.1): there only kill searches with a recorded result set count toward the 30% budget and the ≥ 3 per Kn. Archived studies get a warning.
12. **Every contradiction is confronted (gate R11).** Log load-bearing facts with `claims.py add`
    (same subject/attribute wording — `claims.py keys`). Every conflict that `claims.py conflicts`
    finds goes in the report's Conflicts section, citing evidence from BOTH sides, with its axis
    (scope / time / method / unit / authority / rule_vs_practice). An UNEXPLAINED conflict is
    investigated or explicitly marked unresolved.
13. **Entailment is audited, not assumed (gate R12).** Mechanical gates prove the quote is on the
    page and the number is in the quote; they cannot see a scoped rule stated as universal or a
    dropped "except under §12.2". Before delivery: `audit.py sample` → a fresh-context verifier
    (subagent with only `audit/brief.md` and the snapshots) → `audit.py record` → fix every error
    → `audit.py sample` again (unchanged verdicts carry over; fixes are re-judged) →
    `gate.py --require-audit`. A known error blocks the report whatever the bound says.
14. **Anti-Goodhart & Completeness Invariant (Zero-Truncation Policy — gate R14).** Never truncate
    or defensively compress analysis, tables, or candidate profiles to make verification gates
    pass faster. Precision must never destroy Recall.
    - Studies define mandatory breadth thresholds in `quotas.json` (`min_words`, `min_evidence`,
      `min_calculations`, `min_table_rows_by_section`, `min_deep_dives`, `min_deep_dive_words`).
    - Customer complaint quotes from verified platforms (G2, Capterra, Shopify App Store, Reddit)
      are first-class empirical Voice-of-Customer (`--kind review_pain`), excluded from the T1–T3
      academic denominator of E7b.
    - Batch evidence ingestion is performed via `evidence.py add-batch --dir <dir> --file <jsonl>`
      and multi-candidate scoring via `calc.py score-rubric --file <candidates.json>`.

## 0. Tools

| Need | Command / host tool |
| :-- | :-- |
| Start a study | `python dr_engine/tools/evidence.py init <slug>` → `research/<date>-<slug>/` |
| Is this machine ready | `python dr_engine/tools/doctor.py` → OK / FAIL / MISSING per dependency with the exact fix; exit 0 = ready. Never installs anything |
| What to do next | `python dr_engine/tools/next_step.py D [--json]` → ONE action with the exact command (exit 0 DONE / 1 action / 2 wrong folder). Run after every step |
| Multi-registry discovery | `python dr_engine/tools/discover.py "<query>" --dir D --purpose SQ1\|K1 [--sources openalex,crossref,arxiv,europepmc,semanticscholar]` (deduplicates DOI/title, surfaces `arxiv.org/html/...` full text, auto-logs to `searches.jsonl` with every result URL and to `candidates.jsonl` as `L###` leads) |
| Citation snowballing | `python dr_engine/tools/discover.py --snowball W2741809807\|10.xxxx/yyy --direction backward\|forward\|both --dir D --purpose SQ1 [--limit 25]` (OpenAlex `referenced_works` / `cited_by_api_url`, channel `citation`; ≥ 1 s between calls, `OPENALEX_MIN_INTERVAL`; set `OPENALEX_MAILTO` for the polite pool — never put anyone's address in code) |
| High-throughput scanner & miner | `python dr_engine/tools/scanner.py "<query>" --dir D --purpose SQ1\|K1 --limit 20 --auto-fetch --top-quotes 5` (federated web+scholarly parallel search, concurrent batch fetch, and PaperQA2-style Okapi BM25 verbatim quote mining) |
| Web leads | host search: Antigravity `search_web` · Claude Code `WebSearch` + `evidence.py log-search --dir D --purpose SQn\|Kn --query "..."` |
| Capture a page | `python dr_engine/tools/evidence.py fetch --dir D <url> ...` → `sources/S###.txt` + SHA-256 (full page text; title / `page_date` / author from the page metadata via trafilatura go into the index and evidence records — `page_date` is often "last updated", so set `--published` yourself when the publication date matters) |
| Academic / Legal PDF | `evidence.py fetch` handles PDF URLs; local file: `python dr_engine/tools/parse_pdf.py <pdf_path> --import-dir D --url <original url>`. Tables (pdfplumber) become self-describing lines inside the snapshot: `[TABLE p3.t1]`, `p3.t1 units: in USD millions`, `p3.t1 header: Item \| 2025 \| 2024`, `p3.t1 r2: Revenue \| 2025: 1,234 \| 2024: 1,100` — quote one row line verbatim. A scanned PDF (no text layer) is refused: find a text version or another source |
| JS / bot-walled page | browser tool → save full text → `evidence.py import --dir D --url <url> --file page.txt` (`via=manual`: capped at Medium confidence) |
| Read / grep snapshot | `python dr_engine/tools/evidence.py show --dir D --source S003 [--grep "sole discretion"]` |
| Long-doc extractor | `python dr_engine/tools/extract_doc.py <file> --type prop_rules\|legal_tax\|quant_alpha --evidence-dir D --source S001` |
| Passage corpus (any study > ~15 sources) | `python dr_engine/tools/corpus.py build --dir D` (FTS5/BM25 over every snapshot; passages are exact spans `S003@1200-1490`; menu/footer text repeated on one site is excluded) |
| Ranked reading per SQ/K | `python dr_engine/tools/corpus.py query --dir D "<terms>" [--k 12] [--digits] --log --purpose K2` (logs the query AND its result set) |
| Triage & blind spots | `python dr_engine/tools/corpus.py triage --dir D` → reading order per SQ/K, blind spots (search outside the corpus), surprise queue (uncited sources matching nothing), shared text across sites (syndication = ONE source for triangulation) |
| Withdraw a wrong calculation | `python dr_engine/tools/calc.py retract --dir D --id C004 --reason "input E001 retracted"` (needed when a retracted E### is an input; claims resting on retracted evidence drop out automatically and must be re-added) |
| Withdraw a wrong record | `python dr_engine/tools/evidence.py retract --dir D --id E009 --reason "duplicate of E004"` (kept in the file, marked; every tool ignores it; the corrected record gets a new id) |
| Log verified quote | `python dr_engine/tools/evidence.py add --dir D --source S003 --sq SQ2\|K1 --tier T1..T5 --kind de_jure\|de_facto\|empirical\|context\|review_pain --stance supports\|contradicts\|context --quote "..." --claim "..."` (or batch register via `python dr_engine/tools/evidence.py add-batch --dir D --file batch.jsonl`) |
| Candidate rubric scoring | `python dr_engine/tools/calc.py score-rubric --file <candidates.json> [--dir D]` (scores multi-candidate options across 9 weighted criteria, registers AST `[C###]` calculations, and renders markdown comparison tables) |
| Claim ledger | `python dr_engine/tools/claims.py add --dir D --subject X --attribute "..." --value 6 --unit "USD RT" --scope "Raw feed" --time 2026-10 --eids E002,E003 [--sample-period 2010-2019 --sample-type out_of_sample]` (numeric values must be in the cited quotes; units are normalised by `units.py`, so always state RT vs per side and p.a. vs per day) · `claims.py keys` · `claims.py table` |
| Units & conversions | `python dr_engine/tools/units.py parse "USD per side"` · `convert 3 "USD per side" "USD per lot RT"` · `hold --nights 3 --annual-bp 600 --spread-bp 1.5` (trap G9) · `ls --long-pct 8.5 --short-pct 2.5` (long pays, short receives) · `r --cost-bp 0.7 --stop-bp 10`. The same functions work inside `calc.py eval` (`hold_cost_bp`, `ls_net_bp_day`, `bp_to_r`, `side_to_rt`, `pct_to_bp`, ...) |
| Synonyms / acronyms | global `dr_engine/tools/aliases.json` + optional `research/<dir>/aliases.json` (`{"groups": [[...]], "disable": ["EMA"]}`); `corpus.py aliases --dir D "CySEC warning"` shows the expansion |
| Contradiction map | `python dr_engine/tools/claims.py conflicts --dir D` → conflicts with axes (scope, time, method, unit, authority, rule_vs_practice, interest, sample); each goes in the Conflicts section (R11). Tag evidence with `evidence.py add ... --interest academic\|regulator\|independent\|issuer\|affiliate\|vendor --sample-period 2000-2007 --sample-type in_sample\|out_of_sample\|post_publication\|live` so conflict-of-interest and sample splits are detected |
| Coverage & saturation | `python dr_engine/tools/corpus.py stats --dir D --save` → Chapman estimate $\hat N = (n_1+1)(n_2+1)/(m+1) - 1$ of the relevant sources across independent channels (web, registry, scholarly, citation; `--channels web,scholarly`), plus new load-bearing claim keys per batch of 10 sources; `SATURATED` = coverage ≥ 80% and < 1 new decisive fact in each of the last 2 full batches. Needs channels logged (`log-search --channel`) and `claims.py add --load-bearing` |
| Screening audit (discarded leads) | `python dr_engine/tools/screening.py sample --dir D [--n 20..50]` (seeded random sample of leads never fetched) → `screening.py record --dir D --item X07 --verdict relevant\|irrelevant\|duplicate\|unreachable [--source S###] --note "..."` → `screening.py bound --dir D` (Clopper-Pearson and hypergeometric bound on the share of relevant leads lost) |
| Blind claim audit | `python dr_engine/tools/audit.py sample --dir D [--n 30]` (the brief shows each quote inside its passage, marked ⟪ ⟫, with the periods the page names near it) → verifier judges `audit/brief.md` → `audit.py record --dir D --item A07 --verdict supported\|partial\|unsupported\|wrong_number\|misattributed --note "..."` → `audit.py bound --dir D` |
| Deterministic math `[C###]` | `python dr_engine/tools/calc.py eval --dir D --label "..." --expr "..." --var a=10 --cites E001 --unit USD` |
| Decision & sensitivity matrix | `python dr_engine/tools/calc.py decision --dir D --title "..." --cost C --base-prob P --base-payoff R --bear-prob P --bear-payoff R --stress-prob P --stress-payoff R --cites E001,E002` |
| Epistemic Index & cap | `python dr_engine/tools/formula.py D [--markdown]` (computes $\text{EI}/100$ + Mechanical Confidence Ceiling) |
| Sources table | `python dr_engine/tools/evidence.py sources --dir D --report D/report.md` |
| Full audit gate | `python dr_engine/tools/gate.py D [--stage evidence] [--live 5] [--scorecard] [--require-audit] [--max-error 0.15]` |
| Epistemic Evals | `python dr_engine/evals/eval_runner.py` (32-case regression harness across E6–E8, R3, R6–R10) |

Python: `.venv\Scripts\python.exe` (Windows) / `.venv/bin/python`.

## 1. Scope & Mechanism Hypothesis (before searching)

`evidence.py init <slug>`, then fill `plan.md`:
- Precise question, **concrete decision + stake**, **user's working thesis**, and **mechanism
  hypothesis** (counterparty revenue physics, statutory structure, or microstructure bottleneck).
- 4–8 sub-questions `SQ1..` targeting `T1`–`T3` sources (`≥ 50%` of evidence must be `T1`–`T3`).
- ≥ 3 kill hypotheses `K1..` across distinct failure categories with explicit kill thresholds.
- Planned quantitative parameters for `calc.py decision` (Base / Bear / Stress + flip triggers $p^*, C^*$).

## 2. Red-team disconfirmation engine

1. **Generate kills before evidence** across contract/legal, regulatory, counterparty, economics/microstructure, `de_facto` enforcement practice, tax, and statistical validity.
2. **Spend ≥ 30% of the search budget on kills** (≥ 3 distinct query families per `Kn`: primary T&C/statute text, regulator/court registries, and specific failure/denial reports).
3. **Assign evidence-backed verdicts in `plan.md`**: `confirmed` (threshold met → condition or reverse verdict), `refuted` (positive primary proof logged on `Kn`), or `unresolved` (lowers mechanical confidence ceiling via `formula.py`).

## 3. Primary-First Evidence & Deterministic Modeling

1. **Discover primary & peer-reviewed sources first:** Run `discover.py` for academic/empirical SQs (using `https://arxiv.org/html/<id>` or PMC full-text links for direct fetching) and search official domains (`dv.parliament.bg`, `eur-lex.europa.eu`, `nra.bg`, regulator registries, current T&C/fee schedules) for `de_jure` SQs. Never substitute Wikipedia or Investopedia (`T4`) for primary rules or peer-reviewed papers (`T1`–`T3`).
2. **Capture & log atomic verbatim quotes:** Fetch every page (`evidence.py fetch`), inspect full clauses (`evidence.py show --grep`), and add distinct facts (`evidence.py add`). Never log the same quote twice with opposite stances.
   - **At scale (> ~15 sources):** `corpus.py build`, then `corpus.py triage`. Read the ranked passages per SQ/K instead of whole pages; every passage is an exact span you can pass to `evidence.py add --quote`. Send blind-spot items back to discovery; skim the surprise queue; treat shared-text pairs as one source.
   - **Normalise load-bearing facts:** `claims.py add` for every number, rule or status the decision rests on, reusing the exact subject/attribute wording (`claims.py keys`). Draft the report from `claims.py table`, not from raw pages.
   - **Quote the whole clause:** keep exceptions ("except under §7.3 or §12.2") and scope ("for a $100,000 account") in the sentence you write. Dropping them is the commonest error the audit finds.
3. **Compute economics & flip thresholds deterministically:** Run `calc.py eval` for every derived quantity (after-tax yield, slippage drag, Wilson CI, Sharpe, Kelly fraction) and `calc.py decision` for any go/no-go allocation or comparison. Cite `[E###, C###]` directly in prose and tables.
4. **Completeness, then the pre-draft gate:** `screening.py sample/record/bound` and `corpus.py stats --save` (RUNBOOK step 7), then `gate.py D --stage evidence` and fix all `E1`–`E9` issues before writing `report.md`.

## 4. Decision-First Report Writing (`templates/report.md`)

1. **Executive Decision Card at the top:** Verdict (`GO` / `CONDITIONAL GO` / `NO-GO`), Overall Confidence (checked against `formula.py` before writing!), Net Economics across **Base / Bear / Stress**, exact **Flip / Invalidation Triggers** ($p^*, C^*$), and 2–3 concrete next actions.
2. **Mechanism & Counterparty Physics:** Explain *why* the system behaves this way (e.g., B-book simulation fee economics, statutory sourcing rules, queue-priority microstructure) backed by `[E###]`.
3. **Decision & Sensitivity Matrix:** Paste the verified `[C###]` Markdown table from `calc.py decision`.
4. **Strict Fact / Math / Inference discipline:**
   - Direct facts cite `[E###]`.
   - Derived numbers cite `[E###, C###]`.
   - Qualitative synthesis uses `Inference:` / `Извод:` with **zero unbound numbers**.

## 5. Gate, Scorecard & Delivery

1. Run `python dr_engine/tools/formula.py research/<dir> --markdown` and paste the Epistemic Scorecard under `## Verification`, ensuring declared overall confidence does not exceed `max_confidence`.
2. Run `python dr_engine/tools/claims.py conflicts --dir research/<dir>` and make sure every conflict is in the Conflicts section with evidence from both sides (R11).
3. **Blind claim audit (R12):** `audit.py sample --dir research/<dir>` (seeded by the report's SHA-256; n=30 or the whole report if smaller). Hand `audit/brief.md` to a fresh-context verifier — Claude Code: an `Agent` subagent told to open only `audit/brief.md`, `sources/index.jsonl` and `sources/S###.txt`, never report/plan/claims/evidence — which records each verdict with `audit.py record`. Fix every non-`supported` item at the source, then `audit.py sample` again: verdicts carry over only to sentences whose text and quotes are unchanged, an error sentence still in the report stays in the audit (and blocks) even when the new draw misses it, and the sentence that replaced a fixed error always goes to a NEW blind verifier. Re-running `sample` on an unchanged report keeps every verdict; `--fresh` re-sends unchanged `supported` sentences but never drops an error. Report the bound (`audit.py bound`) under `## Verification`.
4. Run `python dr_engine/tools/gate.py research/<dir> --live 5 --scorecard --require-audit` until it prints `[PASS]` with exit code 0. Paste the gate output under `## Verification`.
5. Copy the final report to `reports/<TOPIC>_<YYYY-MM-DD>.md` and keep `research/<dir>/` intact.

## 6. Failure Modes Stopped by v3.0 and v4.0

- **Markdown Table Row-1 Blind Spot (Fixed in v3.0):** GFM table separator rows previously caused Row 1 of every table to be skipped during audit. Every row of every table is now audited for R1–R10.
- **`Извод:` / `Inference:` Number-Smuggling (Closed in v3.0):** Prefixing bullets with `Извод:` previously bypassed R3 number-binding, letting unverified numbers slip through. `Inference:` / `Извод:` is now strictly qualitative; numbers must bind to `[E###]` quotes or `[C###]` calculations (gates E8, R3, R9).
- **Wikipedia / Retail Explainer Tier Inflation (Closed in v3.0):** Tagging `wikipedia.org` or `investopedia.com` as `T2` inflated source authority. Tertiary encyclopedias are strictly `T4`, and studies must maintain ≥ 50% genuine `T1`–`T3` evidence (gates E6, E7).
- **Stance-Flipping Duplicate Quotes (Closed in v3.0):** Logging the exact same quote as both `supports` and `contradicts` to manufacture fake red-teaming is blocked at `evidence.py add` and gate E7.
- **Unearned "High" Confidence (Closed in v3.0):** Declaring `High` confidence when kill hypotheses are unresolved or sources are mostly `T4`/`T5` is mechanically blocked by `formula.py` and gate R10.
- **Uncalibrated Priors & Dead Lab Edges (gates R7, R8):** Subjective priors (`π = 0.55`) without `n=...` or `[C###]` fail R7; lab-refuted edges (London 4 PM Fix Reversal P31, $t = -5.2$) and invalid consumer/VAT analogies fail R8.
- **Scope distortion passes every mechanical gate (v4.0, R12):** the FXIFY v2 report passed R1–R11 with EI 86.6, yet a blind audit found 5 of 27 claims only partially supported — a fee valid for one account size stated generally, a rule quoted without its "except under §7.3 or §12.2", "narrows" with no baseline, "is a software firm" from a self-declared SIC code. The numbers were all in the quotes; the scope was wrong. EI did not move after the fixes: it measures process, not truth.
- **Unverifiable kill budget (v4.0, E4 warning):** 307 of 376 kill searches across 35 studies recorded no results; padding entries satisfied the 30% rule on paper. Searches must carry their result sets.
- **Missing conflicts in the report (v4.0, R11):** the FXIFY v2 report omitted the EA conflict (allowed with pre-approval on 1/2/3-Phase vs prohibited on Instant) and cited the wrong evidence for the commission conflict; R11 caught both.
- **Syndicated evidence hidden as boilerplate (v4.0, corpus.py):** counting repeated sentences across all sources hid any press release or ruling reprinted on 3+ sites. Boilerplate is now counted per site; cross-site repeats are reported as shared text (one source, not several).
- **Findings smuggled into exempt sections (v4.0, R13):** gate and audit skipped any section whose heading merely contained "Sources/Verification/Проверка". An agent appended a "Verification Addendum" declaring a CNMV warning and a licence number "confirmed" with no evidence — contradicting the gated body — and rp16's whole "Проверка на убиващите хипотези" (kill) section escaped citation checks because of the word "проверка". Exempt sections now need an exact heading (`check_report.heading_exempt`), and an uncited verdict inside them fails R13. New facts go in the body with `[E###]`, never in Verification.
- **Unit and convention errors (v4.1, units.py):** an annual swap rate compared with a per-trade hurdle (G9), a long/short book charged a flat rate on both legs instead of long-pays/short-receives, "$3" per side read as RT. `claims.py` now normalises units before comparing and puts dimension mismatches and unstated sides on the `unit` axis; compute conversions with `units.py` / `calc.py` and cite `[C###]`.
- **Unmeasured discovery (v4.1 P2, E9):** nothing told a study whether it had found most of the relevant sources or stopped early; leads a search returned but nobody opened vanished. Every discovery step now writes its result set to `searches.jsonl` / `candidates.jsonl`; `screening.py` bounds the share of relevant leads discarded unread, `corpus.py stats` estimates coverage across channels and tracks saturation, and a lead judged relevant but never fetched fails E9.
- **PDF tables flattened into number soup (v4.1 P2, parse_pdf.py):** a financial table extracted as prose loses which number belongs to which row, column and unit, so a quoted "1,234" could be the wrong year or in thousands vs millions. Tables are now written as self-describing rows with their unit line; quote the row.
- **Weaker models skipping steps (v4.1 P2, next_step.py):** the protocol is executed by models of different strength. `next_step.py` turns the gate into one deterministic next action with the exact command; every tool rejects a wrong `--dir` with the folder to use instead of creating junk.
- **Found by the first runbook trial (2026-11-03-overnight-drift-trial):** template rows (`| SQ1 | … |`) counted as a filled plan (E3 now fails on placeholders); `evidence.py fetch` silently sent blocked URLs to the third-party reader r.jina.ai (now only with `--jina` / `DR_ALLOW_JINA=1`, and only when the user has allowed it); a backward snowball ranked CAPM and Fama-French first by citation count (now ranked by title overlap with the seed); a PDF table whose row labels are not in the text layer printed `r5: | SPY: 0.27` with no meaning (now flagged "do not cite"); the audit brief did not show the `[C###]` calculations a sentence cites (now it does); failed fetches are logged to `sources/failed.jsonl` and shown in the screening brief; calculations and claims built on a retracted record now have their own withdrawal path (`calc.py retract`, `load_claims`). The decisive catch was the blind audit's: the paper's 4.6% / 4.2% split was for 2004.1–2020.12, but the evidence record (and so every sentence) said 1998–2020, the paper's overall sample. Every mechanical gate passed it, because both years were in a cited quote. **Record the sample period of the exact table a number comes from, not of the paper.**
- **Main-text extractors drop the facts that matter (measured 2026-11-04):** trafilatura's article extraction lost 28 of 88 previously cited quotes still online — fee tables, drawdown rules, leverage lists. Snapshots keep the full page; boilerplate is handled per site in `corpus.py`. LLM scrapers (ScrapeGraphAI-type) return generated JSON, not page text, so their output can never be evidence. Paywalled DOI pages: `discover.py` now fetches the legal open copy (OpenAlex `best_oa_location`) first and flags preprint versions.
- **Right number, wrong period — now caught at capture (v4.1, 2026-11-04):** the trial's scope error passed every gate because both years were somewhere in the quote. `evidence.py add` now finds the quote in its snapshot, lists the periods named within 1,500 characters above and 500 below (`2004.1-2020.12 (above)`, `since 1993 (above)`, `1993-2020 (below)`), refuses `--kind empirical` without `--sample-period` when any are named, and notes a stated period that matches none of them. The audit brief shows the same passage and periods to the blind verifier.
- **Audit rounds that lost or hid verdicts (fixed 2026-11-04):** re-running `audit.py sample` on an unchanged report wiped every recorded verdict; after any edit the re-seeded draw could miss an unfixed error sentence (it vanished from the audit) or the rewritten sentence (the fix went unchecked). Verdicts are now kept, unfixed errors stay in the audit until fixed, and fixes are always judged; such kept items are excluded from the random-sample bound.
- **A friend's clean machine (fixed 2026-11-04):** the test suite did not start without the optional `langextract` (now imported lazily; the offline extractor and a static HTML view need nothing), trafilatura failed to import with lxml ≥ 5.2 unless `lxml_html_clean` is installed (now in requirements), and every CLI that printed Cyrillic through a pipe — how agents read tool output — crashed on Windows' cp1252 (all CLIs now write UTF-8; a test enforces it). `doctor.py` checks all of it in one command, and CI runs the tests on Linux and Windows.
- **Known error under the bound (v4.0, audit.py):** with 1 error in 30 the Clopper–Pearson bound is 14.9% < 15%, so a report with a known false sentence would have passed. Judged errors now block until fixed, whatever the bound.

## 7. External Document / LLM Fact-Checking Protocol

When supplied an external report (Gemini, Claude, analyst PDF): extract discrete claims → `evidence.py fetch` primary sources → verify verbatim quotes via `evidence.py add` → recompute numbers via `calc.py` → flag hallucinations/stale rules → re-run `gate.py --live 5 --scorecard`.

## 8. Autonomous Continuous Learning Invariant

Persist every newly discovered trap, primary registry, statutory nuance, or tooling enhancement immediately into `SKILL.md`, `references/`, `known_traps.json`, and `tests/` without waiting for user prompting.

## 9. v10.0 Epistemic Hardening (non-negotiable, enforced mechanically)

A 2026-11-06 architectural audit found that v9.0 could certify a false report. These
rules close those holes and apply to **every** study produced in this workspace.

### 9.1 Rule B0 — fail-closed verification
`lean_engine.verify_study` calls `epistemic_guard.run_filters_fail_closed`. An exception
in B1–B9 is a **hard FAIL** (`B0 (Filter Integrity / FAIL-CLOSED)`), never a warning.
Non-finite `python:model` values (NaN/Inf), malformed `sample_end_year`, and
`trial_phase` are rejected before the filters run. The AST evaluator now enforces a
deterministic resource budget (`|exponent| <= 64`, `|int| <= 1e15`).

### 9.2 Disclaimers are local, never global
B1, B2, B3, B7, B9, R8 and R11 use `unmitigated_spans` / `is_mitigated_locally`: a
qualifier only counts within 180–400 characters of the triggering claim and at most
one sentence boundary away. B1 additionally requires `n >= 30` attached to the EV
table. B7 requires a structured `normative_physics.treaty_article` — the word
"treaty" in prose is not a mapped legal basis. Verdicts are canonicalised
(`CONDITIONAL GO` → `CONDITIONAL_GO`), so a conditional verdict can no longer slip
past the 3% friction gate.

### 9.3 Rule B9 — claim-triggered, snapshot-verified, live-grounded
B9 fires on any SOTA / best-model claim or deprecated-model mention **regardless of
`manifest.domain`**. Only evidence IDs whose quotes passed verbatim SHA-256 snapshot
verification may ground a Tier-2 benchmark claim. `auto_spec` now classifies `ai`
(and `general` for unmatched prompts); OpenAlex is ranked by relevance + recency,
not `cited_by_count:desc`.

**The bundled `benchmark_radar.py` leaderboard is an unverified offline seed, not
evidence.** It renders with `[CITATION STATUS: NOT VERIFIED]`, appears in the spec's
`unverified_inline_sources`, is flagged `unverified_bundled` in `sources/index.jsonl`,
and is excluded from B9 grounding. Before citing any leaderboard:
```
python dr_engine/tools/benchmark_radar.py fetch --dir research/<dir> --category finance
```
then ingest the fetched page and cite its `[E###]`. Check freshness with
`benchmark_radar.py provenance <category>` (stale after 45 days).

### 9.4 Polyglot ingestion is lossless and honest
`http_resilience.py` handles cp1251 / Shift_JIS / GB18030, gzip, 429 `Retry-After`,
403 bot walls, byte caps and opt-in reader fallback (`DR_ALLOW_JINA=1`). Every result
carries `via`, `charset`, `sha256` and errors — **no `except: pass`**. `polyglot_text.py`
segments Han/Kana bigrams and folds only Latin diacritics; `context_ranker.py` uses
overlapping windows (no 800-char truncation), number-density BM25, syndication
dedup, per-source caps and a char budget. `trench_miner.py` emits a
`CollectorLedger`: if endpoints are bot-walled, the study's Limitations must say so.

### 9.5 Decision instruments
`decision_card.py build` refuses a study that did not pass verification. Cards include
exact breakeven **bisection**, seeded reproducible Monte Carlo (P5/P50/P95,
`P(value<0)`), deterministic joint stress presets and CDN-free inline SVG
histograms. These are sensitivity measurements, not subjective EV weights (B1).

### 9.6 New tools
| Need | Command / module |
| :-- | :-- |
| Fail-closed filter runner | `dr_engine.tools.epistemic_guard.run_filters_fail_closed` |
| Resilient HTTP read | `dr_engine.tools.http_resilience.resilient_fetch` / `fetch_json` / `fetch_xml` |
| Polyglot tokenisation | `dr_engine.tools.polyglot_text.tokenize` / `shingles` / `number_density` |
| Ranked context pack | `dr_engine.tools.context_ranker.rank_passages` |
| Live Tier-2 benchmark | `python dr_engine/tools/benchmark_radar.py fetch --dir D --category finance` |
| Collector telemetry | `trench_miner.py mine --json` → `collector_ledger` |
| v10.0 regression suite | `python -m unittest tests.test_v10_hardening -v` |

## 10. v11.0 Unfair Epistemic Dominance

Resolves all four residual limitations of the v10.0 audit (`reports/ENGINE_AUDIT_v10_2026-11-06.md` §6).

### 10.1 Keyless censorship evasion — with an authority downgrade
`http_resilience.fetch_with_fallbacks(url)` tries, in fixed order, **Memento
availability → Wayback CDX (newest 200 capture, raw `id_`) → syndication
(FxTwitter / PullPush / Redlib) → search mirage (DDG Lite / SearXNG)** after the
direct read fails. Every attempt is recorded in `fallback_chain`; the result
carries `via`, `evidence_class`, `source_url` and a SHA-256. `DR_DISABLE_MIRRORS=1`
forces direct-only. Calling the function is the consent; no keys are used.

**Non-negotiable:** a recovered body is a SECONDARY TRANSCRIPTION. It is written
to `sources/index.jsonl` as `secondary_transcription: true`, capped at T3, and
`verify_study` emits `W_SECONDARY_TRANSCRIPTION`. A `search_cache` hit is a
**lead only** — "search results are never evidence" still applies. Report
`coverage_pct` (any recovery) and `primary_coverage_pct` separately; never claim
100% primary coverage from a cache hit. Live v11 measurement: 100% endpoint
coverage (11/11, 2 rescues) / 81.8% primary-source coverage.

### 10.2 Correlated Monte Carlo, macro regimes, VaR/CVaR
`risk_engine.py` supplies pure-Python Cholesky (`Σ = LLᵀ`, with reported jitter
or shrinkage toward identity for indefinite declared matrices), named
correlation specs, and `z_c = L z + μ_r` joint shocks. Three declared regimes —
**Liquidity Crunch**, **High-Inflation Squeeze**, **Latency Breakdown** — apply
correlated mean shifts; they carry **no probability weight** (Rule B1). Tail
statistics are empirical: `VaR₉₉ = −Q₀.₀₁(Y)`, `CVaR₉₉ = −E[Y | Y ≤ Q₀.₀₁(Y)]`;
a negative VaR means even the 1% worst case is a gain.

`decision_card.compute_monte_carlo(..., correlation=, regime=, sigma_by_input=)`
is opt-in; the v10 independent-σ=10% default is preserved byte-for-byte. Cards
render an inline SVG risk canvas with VaR/CVaR markers and a shaded loss tail.
Every declared correlation, repair and mean shift is printed in the card.

### 10.3 Rule B10 — De Jure vs De Facto Dialectical Arbitration
When a Tier-1/2 `de_jure` "supports" record contradicts a Tier-3/5 `de_facto`
disconfirmation on the same `subject`:
- **Averaging / DerSimonian-Laird pooling is forbidden** (hard failure).
- The delta MUST be classified into `implementation_drag`,
  `undisclosed_microstructure_friction` or
  `regulatory_enforcement_asymmetry`. Unclassified or unreconciled → hard
  failure. Declare `manifest.dialectics[].axis` plus `resolution`.
- A reconciled but unverified conflict **caps `max_confidence` at Medium** until
  `dialectics[].verification.status == "verified"`. The full matrix is available
  on `VerificationReport.dialectical_arbitration`.
- Implemented in `dialectical_arbitration.py` — deliberately separate from the
  pre-existing v5.0 `dialectics.py` claim-ledger CLI.

### 10.4 Rule R17 — Anti-Fluff Information Density Gate
`density_gate.py` mechanically enforces `IDI >= 100` (v10 only computed it), a
verified-entity density `>= 3.0` per 100 words, and rejection of generic AI
prose. A single hard phrase (`"paves the way"`, `"a multifaceted approach"`,
`"delve into"`, …) or ≥2 distinct soft phrases fails the study. Fenced code is
excluded. Every failure names the exact phrases and measured numbers. Never pad
or truncate a report to satisfy a gate (R14 still applies).

### 10.5 v11.0 tools
| Need | Command / module |
| :-- | :-- |
| Recover a bot-walled URL | `dr_engine.tools.http_resilience.fetch_with_fallbacks` |
| Coverage benchmark | `http_resilience.benchmark_fallback_coverage` / `trench_miner.coverage_from_ledger` |
| Correlated risk math | `dr_engine.tools.risk_engine.cholesky` / `empirical_var_cvar` / `MACRO_REGIMES` |
| De jure/de facto matrix | `dr_engine.tools.dialectical_arbitration.run_b10_dialectical_arbitration` |
| Anti-fluff gate | `dr_engine.tools.density_gate.evaluate_r17_gate` |
| v11.0 regression suite | `python -m unittest tests.test_v11_dominance -v` (47 offline tests) |

## 11. v12.0 — Omniscient Golden Nugget & Zero-Lag Intelligence

Closes the **Premature Search Termination Trap** (stopping at the first
high-SEO answer, e.g. 510 kg when a 511 kg record was set in Birmingham) and
the **Golden Nugget Blindspot** (the decisive three-sentence disclosure by an
insider on a niche non-English forum). 36 new adversarial tests; full suite
**358 pass / 1 skipped, exit 0**; `doctor` READY. Pure stdlib, keyless.

### 11.1 Rule B11 — Active Dethroning (`O_dethrone`)

A superlative is a **perishable** claim. `auto_spec.generate` calls
`dethrone.detect_superlative_claims(prompt)`; on any hit it emits
`study_spec.dethroning` with 16 `DethroningVector`s (8 languages × 30/90-day
bands), each with computed `after:`/`before:` ISO dates from `dt.date.today()`
— **no hardcoded year**. The English 30-day vector is literally:
`"<metric> surpassed by" OR "beat <leader>" OR "new record" OR "defeated by" OR "outperformed <leader>" after:<since> before:<until>`.
`trench_miner.mine_dethroning_vectors` executes them against practitioner
trenches; `lean_engine.ingest` compiles them as BM25 queries.

`dethrone.adjudicate_dethroning` requires **fresh** evidence (date inside the
window; unknown dates never count), an upset phrase in one of 8 languages,
and a challenger name or a higher measured value. Negated statements
("no new record was ratified") are explicitly excluded. Status `dethroned`
is never certifiable: the report must name `superseded_by`.

**`verify_study` hard-fails** any superlative claim without
`manifest.dethroning[]` declaring `status: intact|dethroned`,
`vectors_run >= 8`, `window_days ∈ {30, 90}`, `checked_at` within 30 days,
`recency_verified: true`, and `evidence_ids` that passed verbatim snapshot
verification. Failures: `B11 (Premature Search Termination)`,
`B11 (Zero-Lag Window Violation)`, `B11 (Stale Dethroning Check)`, etc.

### 11.2 Golden Nugget — Insider Anomaly 3.0x BM25 Prior

`insider_anomaly.py` declares exact insider-witness phrases in 8 languages
(EN/RU/ZH/ES/DE/KO/JA/FR, plus BG defensive extras) including "I was there",
"на самом деле", "实测翻车", "en vivo vimos", "tatsächlich geschlagen",
"실제로는", "実際の測定値". Matching is NFKC-normalised, Latin-diacritic
folded, case-insensitive and whitespace-flexible; generic vendor prose never
matches. Shannon entropy is reported as a diagnostic, never as a gate.

Any hit sets `INSIDER_PRIOR_BOOST = 3.0`. `context_ranker.rank_passages`
applies exactly `score = BM25 × (1 + 0.35·number_density) × 3.0`, exposes
`bm25_base_score` / `insider_prior` / `insider_markers` / `insider_languages`,
admits zero-overlap insider passages on a bounded `0.05` prior-only floor,
and reserves one slot per query. `trench_miner` writes
`bm25_prior=x3.0`, `[INSIDER ANOMALY langs=…]` and
`[GOLDEN NUGGET / INSIDER ANOMALY]` into the immutable snapshot block, so the
boost survives re-parsing. `context_pack.md` prints
`[GOLDEN NUGGET prior=x3.0 langs=…]`.

### 11.3 Rule R18 — Mandatory Epistemic Alpha Delta (EAD)

Every v12 report MUST contain `## Epistemic Alpha Delta` with three parts:
**Superficial Consensus** (what a 5-second search / standard LLM says),
**Trench Ground-Truth (The Alpha)** (what our multilingual trenches and
verified snapshots proved), **Delta Impact** (financial / operational /
strategic loss of acting on the consensus). Template: `templates/report.md`;
`ingest` appends the scaffold and a compliance checklist to `context_pack.md`.

Enforcement is mechanical: missing heading / subsection / placeholder text is
a hard fail; the trench section must cite a **snapshot-verified `[E###]` not
cited by the consensus**; shingle-Jaccard between the two bodies must stay
`< 0.70` (a copy-paste "delta" fails); the impact must name a loss vector and
carry a number or `[E###]`/`[C###]`. See `ead_gate.validate_ead_section`.

### 11.4 Versioning, fail-closed B0 and hardening

`auto_spec` emits `protocol_version: "12.0"`. `verify_study` activates R18+B11
for v12-declared studies (or `verify --strict-v12`); pre-v12 studies keep the
v11 gate stack and receive `W_EAD_LEGACY_STUDY` — this is how the 322 legacy
tests remain green **without** allowing any new study to skip the alpha gate.
The v12 stack lives in `ead_gate.run_v12_gates_fail_closed`; any exception
becomes `B0 (v12 Gate Integrity / FAIL-CLOSED)`.

`http_resilience` is now total over malformed URLs (`None`, int, bytes,
`javascript:`, empty), malformed feed templates, non-mapping headers and XML
strings with an encoding declaration; unsafe targets never contact mirrors.
`trench_miner` coerces malformed prompts/queries and records every failure in
`CollectorLedger` (no `except: pass`).

### 11.5 v12.0 tools

| Need | Command / module |
| :-- | :-- |
| Detect a perishable leader claim | `dethrone.detect_superlative_claims` |
| Spawn 30/90-day dethroning vectors | `dethrone.build_dethroning_vectors` / `auto_spec.generate` |
| Adjudicate an upset | `dethrone.adjudicate_dethroning` / `run_b11_dethroning_filter` |
| Insider marker scan | `insider_anomaly.scan_insider_markers` / `insider_prior` |
| 3.0x BM25 prior | `context_ranker.rank_passages` (default on) |
| EAD validation / scaffold | `ead_gate.validate_ead_section` / `render_ead_template` |
| Force v12 gates on a legacy study | `python dr_engine/tools/lean_engine.py verify --dir D --strict-v12` |
| v12.0 regression suite | `python -m unittest tests.test_v12_golden_nugget -v` (36 tests) |

## 12. v13.0 — Multi-Hop Deep Digger, Anti-Truncation Quotas & Mandatory Claim-Link-Quote Ledger

Closes all four failure modes exposed by the `RP52A–H` postmortem (lazy 15–30 line
summaries bypassing `lean_engine`, missing URL/quote ledgers, shallow 1-page
skimming that missed Help Center/PDF T&Cs, and uncalculated hype labels like
`MAXIMUM CONVICTION GO` / `11.8x` / `~100-150 occurrences/year`). 14 new
adversarial tests; full suite **372 pass / 1 skipped, exit 0**; 32/32 epistemic
evals (`100.0%`); `doctor` READY.

### 12.1 Frontier 1 — Multi-Hop Deep Digger (`deep_digger.py` & `lean_engine.py ingest --deep`)
- **4-Vector Open-Web Discovery (`discover_web_leads`):** `auto_spec.generate` runs
  `deep_web_digger` alongside OpenAlex/arXiv/community/trench collectors across
  four vectors (`official_primary`, `terms_and_rules`, `fine_print_limits`,
  `adversarial_postmortem`) via `DDGS` + keyless DuckDuckGo HTML fallback.
- **Table- & Schema-Preserving HTML Snapshots (`html_to_structured_snapshot`):**
  renders HTML `<table>` pricing/rule matrices as pipe-delimited `Col1 | Col2 | Col3`
  rows and extracts JSON-LD (`FAQPage`, `Product`/`Offer`, `Article`) plus Next.js
  `__NEXT_DATA__` Q&A objects so collapsed accordion FAQs remain verbatim-quotable.
- **Automatic Multi-Hop Spidering & PDF Clause Extraction (`deep_dig_urls`):**
  follows internal `/terms`, `/faq`, `/rules`, `help.*`, Intercom/Zendesk helpdesks,
  and linked `.pdf` schedules (`parse_pdf.pdf_snapshot`) up to `max_depth=2` hops
  while skipping locale mirrors and login/cart noise. Enabled automatically for all
  v13 specs during `lean_engine.py ingest`.

### 12.2 Frontier 2 — Rule R19: Anti-Truncation & Deep-Digging Floor
v11's `R17` (`IDI = 1000 / word_count * ... >= 100`) divided by `word_count` with
no prose floor, creating a Goodhart loophole where a 20-line stub passed easily.
`depth_and_ledger_gate.validate_depth_quotas` pairs `R17` with a hard lower floor:
`>= 1,000` prose words, `>= 5` distinct snapshotted sources, `>= 8` verified
`[E###]` quotes, `>= 2` Markdown tables, `>= 5` `## ` sections, and `>= 4` finite
`python:model` variables. Reports can neither be truncated nor padded with fluff.

### 12.3 Frontier 3 — Rule R20: Mandatory `Claim → URL → Verbatim Quote` Ledger
Every v13 `report.md` MUST include an inline Markdown table (`Claim | Primary URL | Verbatim Quote | ID`
in English or Bulgarian `Твърдение | Източник / Линк | Дословен цитат | ID`) with
`>= 8` rows. Every row's `[E###]` must be snapshot-verified, its clickable URL's
registrable domain must match `sources/index.jsonl`, and its quote cell must appear
verbatim in `sources/S###.txt`.

### 12.4 Frontier 4 — Rule B12 & Deliverable Attestation Guard (Rule R21)
- **Rule B12 (`run_b12_anti_hallucination_filter`):** hard-fails marketing hype
  verdicts (`MAXIMUM CONVICTION GO`, `GUARANTEED EDGE`), standalone numeric
  multipliers (`11.8x`, `10.4x`) not computed in `python:model` or quoted in a
  locally cited `[E###]`, and empirical frequency claims (`~100-150 occurrences/year`)
  lacking a paragraph-local `[E###]` quote or `[C###]` dataset count variable.
- **Rule R21 (`lean_engine.py export` & `audit-deliverables`):** `verify` writes a
  tamper-evident `verification_receipt.json` (SHA-256 of `report.md` + `sources/index.jsonl`).
  Deliverables enter `reports/` ONLY via `lean_engine.py export --dir <study> --out reports/<NAME>.md`,
  which re-runs `verify --strict-v13` and stamps `<!-- DR-ATTESTATION -->`. Writing
  raw `.md` files straight into `reports/` or editing numbers post-export fails
  `lean_engine.py audit-deliverables`.

### 12.5 v13.0 tools

| Need | Command / module |
| :-- | :-- |
| Crawl seed URLs + T&C/FAQ/PDF subpages into a study | `python dr_engine/tools/deep_digger.py dig --dir research/<dir> --discover-web --query "<topic>"` |
| Deep ingest (multi-hop + PDF + tables + BM25) | `python dr_engine/tools/lean_engine.py ingest --dir research/<dir> --deep` |
| Verify study with full v13 R19/R20/B12 stack | `python dr_engine/tools/lean_engine.py verify --dir research/<dir> --strict-v13` |
| Export verified & attested deliverable to `reports/` | `python dr_engine/tools/lean_engine.py export --dir research/<dir> --out reports/<NAME>.md --strict-v13` |
| Scan `reports/` for unverified bypass files or tampering | `python dr_engine/tools/lean_engine.py audit-deliverables` |
| v13.0 regression suite | `python -m unittest tests.test_v13_deep_digging -v` (14 offline tests) |

## 13. v14.0 — The Unbreakable Epistemic Pipeline, Pre-Synthesis Locking & Executable Cloud Verification

Built after forensic audits exposed the core reasons why autonomous agents fail:
1. **The Semantic Illusion / Premature Synthesis Trap:** Agents authoring prose before locking quotes hallucinate quotes and external institutions.
2. **The Desk Graveyard Blindness:** Agents rediscovering and proposing strategies that the trading desk already killed.
3. **Passive Text Bias:** Numerical models locked in markdown prose instead of being interactively verifiable by an independent runtime.

### 13.1 Frontier 1 — Turn -1: Desk Memory & Graveyard Pre-Flight Scanner
`dr_engine/tools/desk_memory.py` and `lean_engine.py preflight`:
- Automatically scans `CLAUDE_PROJECT_KNOWLEDGE_MASTER.md` and `known_traps.json`.
- Enforces Rule B13: hard-blocks any proposal of killed edges (Gold LBMA ORB, Crude Oil displacement, DAX40/UK100 cash open, MES/MNQ pairs, FTMO single-stock CFDs, synthetic regulatory citations) with exit code 1 BEFORE research begins.

### 13.2 Frontier 2 — Turn 1.5: Pre-Synthesis Evidence Locker
`dr_engine/tools/evidence_locker.py` and `lean_engine.py lock-evidence`:
- Before authoring `report.md`, quotes are extracted and mechanically validated against downloaded snapshots in `sources/S###.txt`.
- Emits immutable `evidence_ledger.json` and human-readable `evidence_pack.md`.
- Report authors may ONLY cite pre-locked `[E###]` IDs. Any citation outside the ledger triggers an immediate gate error.

### 13.3 Frontier 3 — Turn 3.5: Deterministic Google Colab Executable Notebook
`dr_engine/tools/colab_exporter.py` and `lean_engine.py colab`:
- Compiles all AST models (`python:model`), statistical power analysis, and broker spread friction analytics into an executable Jupyter notebook `research_notebook.ipynb`.
- Includes direct Google Colab badge (`[![Open In Colab]...]`).
- Allows the user or auditor to execute all calculations in Python runtime with one click. Eliminates backtest and mathematical hallucinations.

### 13.4 Frontier 4 — Cloud Agent Sandboxing (Simular Box & Google Cloud Trajectory Evaluation)
- **Google Cloud Trajectory Evaluation:** Evaluates the entire research trajectory (tool calls, snapshot SHA-256 hashes, AST executions) rather than grading passive text.
- **Simular Box (`box.simular.ai`):** Used as a persistent 24/7 cloud sandbox for long-running scrapers, anti-bot web crawling, and native MT5 desktop terminal automation.

### 13.5 v14.0 tools

| Need | Command / module |
| :-- | :-- |
| Pre-flight check prompt & plan against desk graveyard | `python dr_engine/tools/lean_engine.py preflight --dir research/<dir> [--prompt "<text>"]` |
| Lock verified evidence quotes into immutable ledger | `python dr_engine/tools/lean_engine.py lock-evidence --dir research/<dir>` |
| Export executable Google Colab notebook | `python dr_engine/tools/lean_engine.py colab --dir research/<dir> [--out <path>]` |
| Full v14.0 regression suite | `python -m unittest tests.test_v14_epistemic_pipeline -v` (6 offline tests) |
