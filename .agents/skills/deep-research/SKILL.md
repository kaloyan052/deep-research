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

# Deep Research Protocol (v4.0 — Institutional Decision & Epistemic Standard)

v4.0 adds scale and entailment on top of v3.0: read ranked passages, not pages (`corpus.py`);
normalise facts into a claim ledger whose contradictions must be confronted (`claims.py`, R11);
and measure what mechanical checks cannot see — whether the quotes really support the sentences —
with a blind, seeded audit and an error bound (`audit.py`, R12). Design rationale and measurements:
`docs/V4_ARCHITECTURE.md`.

The deliverable is a decision-grade report a hostile auditor can verify line by line, whose
quantitative conclusions are deterministically computed in `calculations.jsonl`, whose confidence
is mechanically capped by `formula.py`, and whose thesis survived a deliberate attempt to kill it.
Length, prose polish, and decorative diagrams earn nothing.

## RUNBOOK — mandatory order (every model, every study)

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
| 4 | Capture | `evidence.py fetch --dir D <url>` for every page you rely on → `evidence.py show --dir D --source S### --grep "<word>"` → `evidence.py add --dir D --source S### --sq SQn\|Kn --tier T1..T5 --kind ... --stance ... --quote "<copied from show>" --claim "..."` (`--kind empirical`: add `--sample-period` of the number's own table — `add` refuses without it when the page names a period near the quote, and lists those periods) | every SQ/K has evidence or is marked unresolved; ≥ 50% T1–T3 |
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
| Log verified quote | `python dr_engine/tools/evidence.py add --dir D --source S003 --sq SQ2\|K1 --tier T1..T5 --kind de_jure\|de_facto\|empirical\|context --stance supports\|contradicts\|context --quote "..." --claim "..."` |
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
