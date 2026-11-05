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

Workflow summary (details in the skill; its **RUNBOOK** table is the mandatory order). After every
step run `python dr_engine/tools/next_step.py research/<dir>` and do exactly the one action it
prints, until it prints `DONE` (exit 0). Never edit `*.jsonl`, `sources/` or `audit/*.json` by hand.
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
| `dr_engine/tools/` | **Yes** | `evidence.py` (fetch → snapshot → verified quote), `causal.py` (Pearl Causal DAGs, Backdoor Criterion d-separation, do-calculus counterfactual simulation), `dialectics.py` (Cochran's Q & DerSimonian-Laird I² meta-analysis, anti-pooling & regime partitioning), `frontier.py` (v6.0 Frontier Engine: Bayesian EVSI optimal stopping, adversarial epistemic tournaments, tipping-point Jacobian dynamics & critical slowing down, topological claim manifolds & Tarjan bridges), `swarm.py` (5-phase subagent dispatch, file-lock sharding & atomic merge), `discover.py` (OpenAlex/CrossRef/arXiv-HTML/EuropePMC discovery, OpenAlex forward/backward snowballing, polite rate-limited client; logs result sets + `candidates.jsonl`), `calc.py` (deterministic AST `[C###]` calculations & Base/Bear/Stress decision + breakeven matrix), `formula.py` (Epistemic Index EI/100, semantic entropy, Shingle Jaccard, N_eff clusters & mechanical confidence ceiling), `extract_doc.py` (LangExtract grounded extractor), `parse_pdf.py` (pdfplumber PDF → snapshot; hierarchical multi-headers forward-fill, section spanners, regression t-stats as quotable rows), `corpus.py` (FTS5/BM25 passage index for 100–500 sources: triage, blind spots, syndication; `stats` = Chapman coverage + saturation curve), `claims.py` (claim ledger + contradiction axes incl. interest & sample), `units.py` (bp/%, RT/per-side, annual→holding cost, long/short financing, bp→R; also inside `calc.py`), `aliases.json` (acronym/synonym groups for corpus query expansion; per-study override), `audit.py` (seeded blind claim audit + error bound), `screening.py` (seeded sample of discarded leads + Clopper-Pearson loss bound), `next_step.py` (prints the single next action with its exact command), `doctor.py` (is this machine ready: dependencies, FTS5, workspace; exact fix per problem), `gate.py` (full E1–E11 & R1–R16 audit), plus `check_report.py` / `verify_citations.py` |
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
- A new CLI must write UTF-8 (`sys.stdout.reconfigure(encoding="utf-8", errors="replace")` in its
  `__main__` block — Windows pipes are cp1252) and print commands as `python dr_engine/...`, not
  with a Windows-only venv path; a test enforces the first.
- Record each change that alters what a study must do in `CHANGELOG.md`.
- Keep `dr_engine/tools/` and `dr_engine/science/` dependency-light (stdlib + requests/bs4).
- When changing the gates, run them on `reports/` to see the effect, and add a test in
  `tests/test_report_tools.py`.
