# Changelog

Newest first. **Study** lists what an agent must now do differently in a research folder;
**Tools** lists everything else.

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
