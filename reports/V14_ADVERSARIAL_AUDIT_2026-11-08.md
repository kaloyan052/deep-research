# Deep Research Engine v14.0 — Adversarial Systems Audit

**Date:** 2026-11-08 (Europe/Sofia, GMT+2)
**Role:** Principal Adversarial Systems Auditor / Quant Architect / Epistemic Rigor Engineer
**Scope:** `c:\Users\kaloy\Desktop\DR project\`, `c:\Users\kaloy\Desktop\trading buff\`
**Verdict:** **FAIL — v14.0 does not deliver any of its three advertised guarantees.** All 379 unit tests pass (1 skipped), yet every epistemic gate was bypassed with trivial inputs in under 40 ms of execution.

---

## 0. Method and evidence base

Static inspection plus three executable probe suites (committed to `scratch/`, they only create temporary directories):

| Probe | Purpose |
| :-- | :-- |
| `scratch/v14_audit_probe.py` | `quote_matches_snapshot` matrix, evidence-locker forgery, `verify_study` E2 gate, graveyard bypass matrix, encoding audit |
| `scratch/v14_notebook_probe.py` | nbformat v4 structural validation, headless *Run all* simulation, AST name scan, cross-study notebook generation |
| `scratch/v14_final_probe.py` | Cross-layer trap coverage, obfuscation, crash paths, B13 fail-open inspection |

**Files inspected:** `evidence_locker.py` (204 L), `depth_and_ledger_gate.py` (899 L), `lean_engine.py` (2508 L), `desk_memory.py` (187 L), `colab_exporter.py` (224 L), `tests/test_v14_epistemic_pipeline.py` (110 L), `reports/RP53K_RESEARCH_NOTEBOOK.ipynb`, `research/2026-11-08-rp53k-process-and-battery/*`, `.agents/skills/deep-research/SKILL.md` §13, `AGENTS.md`, `trading buff/CLAUDE_PROJECT_KNOWLEDGE_MASTER.md` §2.C, `dr_engine/tools/known_traps.json`.

**Documentation defect:** `SKILL.md` has **no section 14** — the file ends at §13.5 (line 655). Vector 5's reference to "sections 13 and 14" resolves only to §13 plus the trailing `### 13.5 v14.0 tools` table.

---

## 1. RED LIST — critical defects (exact file:line, reproduced)

### R1 — Verbatim quote matcher accepts punctuation, single letters and empty snapshots
`lean_engine.py:659-710` (`quote_matches_snapshot`). No minimum length, no minimum word count, no alphanumeric requirement.

| Input `quote` | Snapshot | Result |
| :-- | :-- | :-- |
| `""`, `"   "`, `"..."`, `"…"` | normal text | `False` (only these are rejected) |
| `"."` | normal text | **True** |
| `"a"` | normal text | **True** |
| `"!!!"` | normal text | **True** |
| `". . ."` (spaced ellipsis) | normal text | **True** |
| `"---"`, `"26"`, `"...!!!..."` | normal text | **True** |
| `"!!!"`, `". . ."`, `"."` | **empty snapshot** | **True** |
| `"CFTC ... R-multiples"` | normal text | **True** (two-token splice) |

Root causes: (a) `fragments` are filtered only on truthiness (`lean_engine.py:665`); (b) `lean_engine.py:681-685` — when a fragment has **no `\w` tokens**, the code executes `continue`, so a punctuation-only fragment is treated as *verified* and the function falls through to `return True`; (c) no length/word floor anywhere before `return True` at line 710.

### R2 — `MAX_ELLIPSIS_GAP` is enforced in only one of two branches
`lean_engine.py:700-708`. The exact-match branch checks `idx - pos > MAX_ELLIPSIS_GAP`, but the punctuation-tolerant regex fallback (`lean_engine.py:687-698`) sets `pos = m.end()` with **no gap check at all**. An agent can therefore splice arbitrary fragments from anywhere in a long snapshot into a fabricated "verbatim" quote.

### R3 — E2 citation gate is fully defeated by degenerate quotes
`lean_engine.py:1560-1599`. `verify_study` calls `quote_matches_snapshot(quote, snaps[sid])` at line 1579 with **no pre-validation** and counts a hit as a verified evidence record. Probe result with three manifest quotes `"."`, `"a"`, `"!!!"`:

```
n_evidence counted = 3
E2 (quote verification) failures = []
total failures = 9, passed = False
```

`res.n_evidence = 3` clears the `>= 3` floor at `lean_engine.py:1597`. `depth_and_ledger_gate.py:347` does enforce `len(norm_q) < 15 → False` for the **Markdown table** path (`_quote_in_snapshot`), but that is a different code path; the manifest/ledger path has no such floor. Any number of fake `[E###]` citations can therefore be certified.

### R4 — Non-string quotes crash the verifier (unhandled)
`lean_engine.py:1571` (`quote = ev.get("quote", "")` → `quote_matches_snapshot` → `re.split`) and `cmd_verify` at `lean_engine.py:2151-2159` has **no try/except**. Reproduced with `{"quote": null}`:

```
*** UNHANDLED TypeError: expected string or bytes-like object, got 'NoneType'
```

`evidence_locker.py:90` (`item.get("quote", "").strip()`) independently raises `AttributeError: 'NoneType' object has no attribute 'strip'`. A malformed manifest turns a gate into a traceback with no structured verdict.

### R5 — Evidence locker has no identity, tier, uniqueness or length validation
`evidence_locker.py:87-116`. Reproduced: quote `"!!!"` locked with 0 errors; `"tier": "T1"` accepted for an `example.org` source (tier laundering); duplicate `E001` accepted; `"id": "HACKED"`, `"tier": "T0"` accepted and written to the ledger. `char_len` is recorded (line 114) but never enforced. `extract_candidate_quotes` at `evidence_locker.py:181` assigns `T1` whenever the URL *contains* the substring `"nber"` or `"edu"` — `https://notedu.evil.example/paper.pdf` is auto-certified T1.

### R6 — Stale ledger survives a refused/failed lock (fail-open)
`evidence_locker.py:118-128`: ledger files are written only `if locked and not errors`. On any error the function returns without touching an **existing** `evidence_ledger.json`. Probe: after a failed lock, `evidence_ledger.json` still exists with 1 record and `load_locked_evidence()` returns it. A stale ledger from a previous study remains authoritative.

### R7 — **ARCHITECTURAL: the evidence ledger is never consumed by any verifier**
Full-repo grep over `*.py`: `evidence_ledger.json` / `load_locked_evidence` appear **only** inside `evidence_locker.py` and `tests/test_v14_epistemic_pipeline.py`. `verify_study` reads the manifest from `report.md` / `manifest.json` (`lean_engine.py:1520-1537`) and never opens the ledger. Consequently:

* `SKILL.md:636` — *"Report authors may ONLY cite pre-locked `[E###]` IDs. Any citation outside the ledger triggers an immediate gate error"* — **false**.
* `AGENTS.md:167` — *"Authors may ONLY cite pre-locked `[E###]` IDs; any unverified quote triggers an immediate failure"* — **false**.

The `lock-evidence` step is decorative: skipping it costs nothing, and hand-editing the ledger changes nothing. This is the single most consequential defect in v14.0.

### R8 — Markdown injection into `evidence_pack.md`
`evidence_locker.py:143-149`. Only `|` is escaped; CR/LF and backslashes are not. A verified multi-line quote injects new table rows. Probe output:

```
| `[E001]` | `S001` | T1 | BIS Quarterly Review.
\| `[E999]` \| `S001` \| T1 \| INJECTED FAKE QUOTE \| https://evil.test \| | [S001](https://x.test/a|b)) |
```

`source_url` is interpolated unescaped into a Markdown link; `|` and `)` break the column. `item["id"]` / `item["source"]` / `item["quote"]` are indexed directly → `KeyError` on a malformed ledger.

### R9 — Global refutation disclaimers disarm every graveyard rule
`desk_memory.py:161-168`: the acknowledgement loop runs `re.search(ack_pat, text, re.I)` over the **entire document**, not the matched context. Reproduced:

| Text | Violations |
| :-- | :-- |
| `"The WTI crude oil pit open displacement is a promising new edge. In an unrelated appendix, Pillar 2 was killed."` | **0** |
| `"Gold London ORB is killed, refuted and dead. We now propose a WTI pit open displacement."` | **0** |
| `"Gold London ORB is a promising edge. " + 500 filler words + " killed "` | **0** |

This directly re-introduces the bug that `AGENTS.md:42` (v10 hardening) declares fixed: *"Disclaimers are local: ... buried in an unrelated appendix no longer disarms B1, B2, B3, B7, B9, R8 or R11."* B13 was added without inheriting that invariant.

### R10 — All two-sided graveyard regexes are blind across line breaks
`desk_memory.py:149`: `re.search(pat, text, re.I)` — no `re.S`. Every rule uses `A.*?B` co-occurrence patterns (`desk_memory.py:52-55, 66-69, 80-82, 93-94, 105, 116-117`). Reports are multi-line by construction. Probe: `BIS Quarterly Review` on line 1 and `FTMO / R-multiples` 50 lines later → **0 violations**, while the same text on one line → 1 violation. `known_traps.json` did not catch it either (cross-layer probe returned `traps=[]`).

### R11 — Graveyard rules are a stale hard-coded snapshot, not derived from the master file
`desk_memory.py:39-43` and `:46-123`. `load_desk_knowledge_text()` returns 24,895 chars but is **never called** by the scanner. `GRAVEYARD_RULES` contains 6 hand-written rules; `CLAUDE_PROJECT_KNOWLEDGE_MASTER.md` §2.C lists 11 killed families, plus §2.A/§2.B kills. Path defects: `DESK_KNOWLEDGE_PATHS[0]` is a machine-specific hard-coded `c:\Users\kaloy\...`; `[1]` resolves to `DR project\trading buff\...` (**does not exist** — the sibling directory is on `Desktop`, so it must be `parents[3]`); `[2]` is `known_traps.json`, which is never used by `scan_text_against_desk_graveyard`. `cmd_preflight` (`lean_engine.py:2199-2233`) also never calls `check_known_traps_in_text`, contradicting `AGENTS.md:166` and `SKILL.md:629`.

### R12 — B13 is fail-open on any exception
`lean_engine.py:1700-1716`: the entire graveyard **and** known-traps audit is wrapped in `try: ... except Exception as e: res.warnings.append(...)`. A missing module, a malformed `known_traps.json` or any runtime error silently downgrades both new gates to a **warning**, and the study can still return `passed = True`. `AGENTS.md:37` Rule B0 states *"any B1–B9 exception is a hard FAIL, not a warning"*; B13 was exempted from B0 by construction.

### R13 — v14 gates are not in the mandatory pipeline
`AGENTS.md:20-38` defines "Option A (DEFAULT & MANDATORY FOR DIRECT RESEARCH)" as 5 steps: `auto_spec generate` → `ingest` → author `report.md` → `verify` → `decision_card build`. **None** of `preflight`, `lock-evidence`, `colab` appear. The v14 block at `AGENTS.md:164-172` is a separate descriptive appendix. An agent that follows the mandatory workflow exactly never executes a single v14 gate. All three v14 frontiers are opt-in.

### R14 — Colab notebook crashes on "Run all" for any study that is not RP53K
`colab_exporter.py:155-166`: the verification cell guards on `us100_spread_R` **and** `dax40_spread_R`, but dereferences `spx500_spread_R`, `spx500_net_edge_R`, `us100_net_edge_R`, `dax40_net_edge_R`. Generated notebook from a synthetic study defining only `us100_*`/`dax40_*`:

```
SYNTH cell 6: *** NameError: name 'spx500_spread_R' is not defined
```

The exporter is generic; the assertion cell is hard-coded to RP53K's variable names.

### R15 — The notebook verifies nothing (passive constants, not deterministic math)
`colab_exporter.py:114-124` and `:153-181`. `python:model` blocks are emitted as **literal assignments**; the four statistical functions in cells 6–7 are defined and **never called**; the only assertion compares two hard-coded constants. Numerical cross-check:

```
0.708 * 0.512                                          = 0.362496  (= declared joint_power_100tr 0.362)
Phi(2.4495) * Phi(1.4142)                             = 0.9148
calculate_joint_battery_power(0.10, 600, 200, 3.0, 3.0) = 0.01641
```

The report's headline power figure is the product of two unexplained literals and is **22× larger** than the notebook's own power function applied to the declared parameters. `SKILL.md:640-642` ("eliminates backtest and mathematical hallucinations") is not delivered. Only the friction identities are actually derivable (`1.10/50 = 0.022`, `0.38/10 = 0.038`, `1.60/25 = 0.064`, `0.10 − spread = net_edge`, `sqrt(4)×1.75 = 3.5`).

### R16 — Notebook is v4.0, not current nbformat v4; no badge; no headless verification path
`colab_exporter.py:206-207` sets `nbformat_minor: 0` and emits **no cell `id`** on any of 9 cells. Structurally valid against the v4.0 schema (all required keys present, `source` as `list[str]`, `outputs`/`execution_count` present), but **non-compliant with the v4.5 schema**, which requires `nbformat_minor >= 5` and `id` on every cell. `SKILL.md:641` promises a Colab badge — none exists in the exporter, the notebook, or the report. `.venv` has **none** of `nbformat`, `nbconvert`, `jupyter_client`, `ipykernel`, `jsonschema`, `scipy`, `matplotlib`; therefore no `nbformat.validate` or `nbconvert --execute` check can run locally. `tests/test_v14_epistemic_pipeline.py:88-106` only asserts `nb["nbformat"] == 4` and `len(cells) >= 4`.

### R17 — Offline / dependency / path fragility
`colab_exporter.py:88`: unconditional `!pip install -q numpy scipy pandas matplotlib` on every run (fails in an offline kernel; IPython-only syntax, illegal under plain `exec`). `scipy.stats` is imported but never used. `colab_exporter.py:216`: `export_colab_notebook` raises an unhandled `FileNotFoundError` when `--out` points into a non-existent directory (the CLI happens to catch it at `lean_engine.py:2275-2281`, the Python API does not). `colab_exporter.py:46`: any `python` block beginning with `#` is copied verbatim — project-local imports or file reads would produce `ModuleNotFoundError` in Colab; conversely computation-only blocks without `def ` are silently dropped.

### R18 — "Pre-synthesis" locking did not occur in the shipped RP53K study
Exact mtimes (local GMT+2):

```
16:18:22  report.md
16:54:03  evidence_ledger.json
16:54:03  evidence_pack.md
16:54:08  research_notebook.ipynb
16:54:12  verification_receipt.json   (protocol_version: "13.0")
```

The ledger was generated **36 minutes after `report.md` was authored**, in the same batch as verification. The receipt still certifies protocol 13.0. The v14 ordering guarantee is contradicted by the reference study itself.

### R19 — Tests are green but vacuous
`python -m unittest discover -s tests` → `Ran 379 tests ... OK (skipped=1)`. `tests/test_v14_epistemic_pipeline.py` has **6 happy-path tests only**: no degenerate quote, no punctuation quote, no multiline citation, no paraphrase, no global-disclaimer trick, no `nbformat.validate`, no notebook execution, no ledger↔verify integration test, no B13 fail-open test. The suite certifies that the code runs, not that it gates anything.

---

## 2. ORANGE LIST — gaps, edge cases, robustness

### 2.1 Graveyard coverage vs `CLAUDE_PROJECT_KNOWLEDGE_MASTER.md` §2.C

All of the following were probed against **both** `scan_text_against_desk_graveyard` and `check_known_traps_in_text`; every one returned **0 violations / no traps**:

| # | Killed family (master file) | Probe text (abbreviated) |
| :-- | :-- | :-- |
| 1 | §2.C.3 European ORB incl. `EURUSD`, ORB30 on NAS/SPX/US30/US2000/DAX/gold | `"EURUSD opening range breakout"`, `"ORB30 on NAS100, SPX500, US30, US2000"` |
| 2 | §2.C.4 Overnight swing CFDs, swap/financing drag | `"Overnight swing holding on CFDs with swap financing drag"` |
| 3 | §2.C.6 `TRAIL01` trailing stop, EMA5 placebo | `"Add a trailing stop TRAIL01 and EMA5 placebo variant"` |
| 4 | §2.C.5 / §2.A Displacement transplant, NQ London, NQ 5m, ES/US30/US2000/DAX | `"NQ 5m displacement"`, `"Transplant displacement to NQ London session"` |
| 5 | §2.C.9 FTMO Single-Stock CFDs `PILLAR1_XFTMO01` | `"FTMO Single-Stock CFDs (PILLAR1_XFTMO01) are the new edge"` |
| 6 | §2.C.10 Reddit leaderboard + LLM cut-limits | `"Reddit Leaderboard Scraping with LLM cut-limits"` |
| 7 | §2.C.11 Revelio 10Y regression channel | `"Revelio 10-Year Linear Regression Channel, 4-12 month holds"` |
| 8 | §2.B Pillar 2 `OUT6_10D`, `RUT10`, `OUT6-21D` | `"Re-open Pillar 2 OUT6_10D CME micro-FX 10-day reversal"` |
| 9 | §2.C.7 102 intraday programs exhausted | `"A new intraday edge on the same free-data universe"` |
| 10 | §2.C.8 mis-localized clocks | any script not using `lab_utc.load_canonical_utc` |

`GRAVEYARD_SINGLE_STOCK_CFDS` (`desk_memory.py:105`) is effectively **dead**: `\b(?:stock\s+cfd|...)\b` cannot match the plural `"CFDs"` because `\b` fails between `d` and `s`. Even the master file's exact phrase is invisible. `known_traps.json` has 16 traps, of which only 4 are killed-edge traps (Gold LBMA, Crude, European cash open, synthetic citations); it does not cover the other families either.

### 2.2 Paraphrase and obfuscation bypasses

| Probe | Result |
| :-- | :-- |
| `"Breakout of Frankfurt 08:00 AM on German index at the cash open."` | **0 violations** — "German index" is not in the instrument alternation and `08:00` is not in the session alternation |
| `"G\u200bold London ORB sweep"` (zero-width space inside GOLD) | **0 violations** |
| `"G\u043eold London ORB"` (Cyrillic homoglyph `о`) | **0 violations** |
| `"Gold LBMA auction fixing sweep"` (no literal `ORB`) | 0 violations in BG-only patterns (English rule caught it via `sweep` in the probe text, but `LBMA`/`fixing` are absent from English alternations) |

### 2.3 Encoding / Windows assessment (Vector 3) — mostly clean, specific exceptions

**Verified healthy:** all four new modules call `sys.stdout.reconfigure(encoding="utf-8", errors="replace")` (`evidence_locker.py:31-32`, `desk_memory.py:28-29`, `colab_exporter.py:28-29`, `lean_engine.py`); every `read_text`/`write_text` uses `encoding="utf-8"`; `→`, `π`, `μ`, `—`, Cyrillic round-trip through `build_evidence_pack_markdown` without error; **no backslashes** in generated `evidence_ledger.json`, `evidence_pack.md` or the notebook (URLs and `study_dir.name` only). No `UnicodeEncodeError` was reproducible.

**Residual risks:**
* Silent `except Exception: pass` at `evidence_locker.py:60`, `:69`, `:162` and `desk_memory.py:133`. A cp1252/latin-1 or BOM-prefixed snapshot raises `UnicodeDecodeError` and is **silently dropped**, producing a misleading "source not found" error instead of a charset diagnostic. No `errors=` fallback anywhere.
* `desk_memory.py:40` uses a hard-coded Windows absolute path; `desk_memory.py:41` builds a wrong fallback (verified non-existent). On any other machine the graveyard knowledge silently degrades.
* `evidence_locker.py:60` swallows malformed `index.jsonl` lines, so `source_url` silently becomes `""`.
* `build_evidence_pack_markdown` raises `KeyError` on records missing `id`/`source`/`quote`; `load_locked_evidence` returns any JSON type without schema validation.
* `extract_candidate_quotes` (`evidence_locker.py:181`) does `"edu" in ...get("url", "")` — `TypeError` if `url` is `null`; `k.lower()` raises if a keyword is not a string.
* `__main__` blocks in `evidence_locker.py:186-204` and `colab_exporter.py:220-224` hard-code the RP53K study path; `evidence_locker.py:195` calls `json.loads` without a guard.
* `cmd_preflight` prints `❌` to stdout; with `errors="replace"` this degrades to `?` on a cp1252 console (cosmetic only).

### 2.4 Workflow / architecture gaps (Vector 5)

* `SKILL.md` has **no §14**; Vector 5's "sections 13 and 14" cannot be satisfied as written.
* `SKILL.md:629` and `AGENTS.md:166` claim preflight scans `known_traps.json`; `cmd_preflight` does not call `check_known_traps_in_text` at all.
* `SKILL.md:641` claims a Colab badge; none exists.
* `AGENTS.md:167` claims unverified quotes fail; no ledger consumer exists (R7).
* No single entry point: 5 separate CLI invocations must be remembered by an LLM. Nothing prevents an agent from jumping from `ingest` straight to `report.md`.
* No Git pre-commit hook, no CI gate, no prompt-submit linter, no notebook execution receipt, no trajectory attestation (the `Google Cloud Trajectory Evaluation` at `AGENTS.md:170` is prose only — there is no implementation in `dr_engine/`).
* `Simular Box` (`AGENTS.md:171`, `SKILL.md:646`) is described as optional but has no adapter, no job manifest, and no rule for downgrading cloud-derived transcriptions to T3 (required by `AGENTS.md` v11 §10.1 / B10).

---

## 3. DROP-IN CODE PATCHES

All patches are stdlib-only unless stated. They are **not applied** — apply in order P1 → P6, then add the adversarial tests in P7.

### P1 — `dr_engine/tools/lean_engine.py`: hardened `quote_matches_snapshot`

Insert after line 205 (`MAX_ELLIPSIS_GAP = 2000`):

```python
# v14.1 — hard floors for an admissible verbatim quote (fail-closed).
MIN_QUOTE_CHARS = 20
MIN_QUOTE_WORDS = 4
MIN_FRAGMENT_CHARS = 8
MIN_FRAGMENT_WORDS = 2
MAX_ELLIPSIS_FRAGMENTS = 6
```

Replace lines 659-710 with:

```python
def quote_matches_snapshot(quote: str, snapshot: str) -> bool:
  """Verify `quote` verbatim against `snapshot`, allowing bounded `...` gaps.

  v14.1: a quote is admissible only if it is a non-empty string with a
  minimum character/word count; every ellipsis fragment is independently
  admissible; the fragment count is bounded; and **every** gap — including
  the punctuation-tolerant fallback branch — is bounded by
  MAX_ELLIPSIS_GAP in the coordinate system of the NORMALISED snapshot.
  """
  if not isinstance(quote, str) or not isinstance(snapshot, str):
    return False

  q = normalise_ws(quote).casefold()
  if len(q) < MIN_QUOTE_CHARS:
    return False
  if len(re.findall(r"\w+", q)) < MIN_QUOTE_WORDS:
    return False

  fragments = [f.strip() for f in re.split(r"\.\.\.|\u2026", q) if f.strip()]
  if not fragments or len(fragments) > MAX_ELLIPSIS_FRAGMENTS:
    return False
  for frag in fragments:
    words = re.findall(r"\w+", frag)
    if (len(frag) < MIN_FRAGMENT_CHARS
        or len(words) < MIN_FRAGMENT_WORDS
        or not any(ch.isalnum() for ch in frag)):
      return False

  snap_norm = normalise_ws(snapshot).casefold()
  if not snap_norm:
    return False

  pos = 0
  for frag in fragments:
    idx = snap_norm.find(frag, pos)
    if idx >= 0:
      if len(fragments) > 1 and idx - pos > MAX_ELLIPSIS_GAP:
        return False
      pos = idx + len(frag)
      continue

    # Punctuation-tolerant fallback. Restrict the separator class: `\\W+`
    # previously allowed arbitrary characters (including newlines) to be
    # spliced between words, and skipped the gap check entirely.
    pat = re.compile(r"[\s\-,;:]{0,4}".join(map(re.escape, re.findall(r"\w+", frag))))
    m = pat.search(snap_norm, min(pos, len(snap_norm)))
    if not m:
      return False
    if len(fragments) > 1 and m.start() - pos > MAX_ELLIPSIS_GAP:
      return False
    pos = m.end()
  return True
```

### P2 — `dr_engine/tools/lean_engine.py`: type guards + B14 ledger binding

Replace lines 1540 and 1560-1583 with the guarded form (three small hunks):

```python
# hunk 1 (line 1540)
  evidence_list = manifest.get("evidence", [])
  if not isinstance(evidence_list, list):
    res.failures.append("M1: manifest.evidence must be a list")
    evidence_list = []
```

```python
# hunk 2 (inside the loop, before line 1579)
    quote = ev.get("quote", "")
    if not isinstance(quote, str):
      res.failures.append(
          f"E2: {eid} quote is not a string ({type(quote).__name__})")
      continue
    if len(normalise_ws(quote)) < 20:
      res.failures.append(f"E2: {eid} quote is too short to be a verbatim excerpt")
      continue
```

```python
# hunk 3 (insert after line 1599, immediately after the n_evidence floor)
  # v14.1 Rule B14: bind report.md to the pre-synthesis evidence locker.
  # Enforced whenever a ledger exists or the manifest declares >= 14.1,
  # so legacy (< 14.0) studies without a ledger remain unaffected.
  _v = str(manifest.get("protocol_version", "")).split(".")
  v14plus = len(_v) >= 1 and _v[0].isdigit() and int(_v[0]) >= 14
  if v14plus or (d / "evidence_ledger.json").exists():
    from dr_engine.tools.evidence_locker import verify_report_against_ledger
    res.failures.extend(verify_report_against_ledger(d, manifest, raw_report))
```

Also replace the B13 block (`lean_engine.py:1700-1716`) so it **fails closed**:

```python
  # v14.1 Rule B13 — fail-closed (AGENTS.md Rule B0).
  from dr_engine.tools.desk_memory import scan_text_against_desk_graveyard
  from dr_engine.tools.traps import check_known_traps_in_text
  try:
    desk_violations = scan_text_against_desk_graveyard(raw_report)
    trap_violations = check_known_traps_in_text(raw_report)
  except Exception as e:
    res.failures.append(f"FAIL B13 (Gate Error, fail-closed): {type(e).__name__}: {e}")
  else:
    for dv in desk_violations:
      res.failures.append(
          f"FAIL B13 (Desk Graveyard): proposes killed edge '{dv['name']}' "
          f"without refutation. {dv['description']}")
    for tv in trap_violations:
      res.failures.append(
          f"FAIL B13 (Known Trap): violates {tv.get('id', 'TRAP')} "
          f"({tv.get('name', '')}). {tv.get('description', '')}")
```

### P3 — `dr_engine/tools/evidence_locker.py`: full replacement of three functions

```python
import hashlib
from dr_engine.tools.lean_engine import (
    quote_matches_snapshot, normalise_ws, sha256_text,
)

VALID_TIERS = {"T1", "T2", "T3", "T4", "T5"}
EID_STRICT = re.compile(r"^E\d{3}$")
MIN_LOCKED_QUOTE_CHARS = 20


def _canonical_digest(records: list[dict[str, Any]]) -> str:
    payload = json.dumps(records, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _md_cell(value: Any) -> str:
    """Escape a table cell; normalise_ws also destroys CR/LF row injection."""
    s = normalise_ws(str(value))
    return s.replace("\\", "\\\\").replace("|", "\\|")


def _md_url(url: Any) -> str:
    s = str(url).strip()
    return (s.replace(" ", "%20").replace("(", "%28")
             .replace(")", "%29").replace("|", "%7C"))


def build_evidence_pack_markdown(locked_items: list[dict[str, Any]]) -> str:
    lines = [
        "# Pre-Locked Evidence Pack (Deep Research v14.1)",
        "",
        "> [!IMPORTANT]",
        "> When authoring `report.md`, cite ONLY quotes from this pre-locked evidence pack.",
        "> Every quote below has been mechanically verified against its primary snapshot.",
        "",
        "| ID | Source | Tier | Verbatim Quote | URL |",
        "| :--- | :--- | :--- | :--- | :--- |",
    ]
    for item in locked_items:
        if not isinstance(item, dict):
            continue
        eid = _md_cell(item.get("id", ""))
        sid = _md_cell(item.get("source", ""))
        tier = _md_cell(item.get("tier", "T3"))
        quote = _md_cell(item.get("quote", ""))
        url = _md_url(item.get("source_url", ""))
        lines.append(f"| `[{eid}]` | `{sid}` | {tier} | {quote} | [{sid}]({url}) |")
    lines.append("")
    return "\n".join(lines)


def lock_evidence(
    study_dir: Path,
    evidence_items: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[str]]:
    """Verify candidate evidence and write a tamper-evident, atomic ledger."""
    sources_meta, source_texts = load_snapshots(study_dir)
    locked: list[dict[str, Any]] = []
    errors: list[str] = []
    seen: set[str] = set()

    if not isinstance(evidence_items, list):
        return [], ["manifest.evidence must be a list"]

    for idx, item in enumerate(evidence_items, 1):
        if not isinstance(item, dict):
            errors.append(f"E{idx:03d}: evidence item is not an object")
            continue
        eid = str(item.get("id") or f"E{idx:03d}")
        if not EID_STRICT.match(eid):
            errors.append(f"{eid}: id must match ^E\\d{{3}}$")
            continue
        if eid in seen:
            errors.append(f"{eid}: duplicate evidence id")
            continue
        sid = str(item.get("source") or item.get("sid") or "")
        quote = item.get("quote", "")
        if not isinstance(quote, str):
            errors.append(f"{eid}: quote must be a string, got {type(quote).__name__}")
            continue
        quote = quote.strip()
        tier = str(item.get("tier", "T3"))
        if tier not in VALID_TIERS:
            errors.append(f"{eid}: invalid tier {tier!r}")
            continue
        if len(quote) < MIN_LOCKED_QUOTE_CHARS:
            errors.append(f"{eid}: quote too short ({len(quote)} chars)")
            continue
        if sid not in source_texts:
            errors.append(f"{eid}: source {sid!r} not found in snapshots "
                          f"(available: {sorted(source_texts)})")
            continue
        meta = sources_meta.get(sid) or {}
        if not isinstance(meta, dict):
            meta = {}
        src_tier = str(meta.get("tier", tier))
        if src_tier in VALID_TIERS and src_tier > tier:
            tier = src_tier          # never upgrade above the declared source tier
        if not quote_matches_snapshot(quote, source_texts[sid]):
            errors.append(f"{eid}: quote does not match snapshot {sid}.txt verbatim: "
                          f"{quote[:60]!r}")
            continue
        seen.add(eid)
        locked.append({
            "id": eid,
            "source": sid,
            "source_url": str(meta.get("url", "")),
            "title": str(meta.get("title", "")),
            "tier": tier,
            "quote": quote,
            "char_len": len(quote),
            "snapshot_sha256": sha256_text(source_texts[sid]),
        })

    out_json = study_dir / "evidence_ledger.json"
    out_sig = study_dir / "evidence_ledger.json.sha256"
    out_pack = study_dir / "evidence_pack.md"

    # Fail-closed: a refused lock must NEVER leave a stale authoritative ledger.
    if errors or not locked:
        for p in (out_json, out_sig, out_pack):
            if p.exists():
                p.unlink()
        return [], errors or ["no evidence was locked"]

    out_json.write_text(json.dumps(locked, indent=2, ensure_ascii=False), encoding="utf-8")
    out_sig.write_text(_canonical_digest(locked) + "\n", encoding="utf-8")
    out_pack.write_text(build_evidence_pack_markdown(locked), encoding="utf-8")
    return locked, errors


def verify_report_against_ledger(
    study_dir: Path,
    manifest: dict[str, Any],
    raw_report: str,
) -> list[str]:
    """Rule B14 — bind every report citation to the pre-locked ledger."""
    p = study_dir / "evidence_ledger.json"
    sig = study_dir / "evidence_ledger.json.sha256"
    if not p.exists() or not sig.exists():
        return ["B14 (Evidence Locker Missing): run "
                "`lean_engine.py lock-evidence --dir <study>` BEFORE authoring report.md."]
    try:
        records = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(records, list) or not records:
            return ["B14 (Empty Evidence Ledger)"]
        if _canonical_digest(records) != sig.read_text(encoding="utf-8").strip():
            return ["B14 (Evidence Ledger Tampered): SHA-256 digest mismatch."]
    except Exception as e:
        return [f"B14 (Evidence Ledger Unreadable): {type(e).__name__}: {e}"]

    locked = {str(r.get("id")): r for r in records if isinstance(r, dict)}
    failures: list[str] = []
    manifest_ev = manifest.get("evidence", [])
    if not isinstance(manifest_ev, list):
        return ["B14 (manifest.evidence must be a list)"]

    for ev in manifest_ev:
        if not isinstance(ev, dict):
            failures.append("B14 (malformed evidence record)")
            continue
        eid = str(ev.get("id", ""))
        rec = locked.get(eid)
        if rec is None:
            failures.append(f"B14: {eid} is cited in the manifest but is NOT pre-locked.")
            continue
        if (str(ev.get("source", "")) != str(rec.get("source", ""))
                or str(ev.get("quote", "")).strip() != str(rec.get("quote", "")).strip()):
            failures.append(f"B14: {eid} source/quote diverges from the locked record.")

    cited = set(re.findall(r"\bE\d{3}\b", raw_report))
    orphans = cited - set(locked)
    if orphans:
        failures.append(f"B14 (Unlocked Citations): {sorted(orphans)} appear in "
                        "report.md but not in evidence_ledger.json.")
    return failures
```

Also update `load_locked_evidence` to validate the list shape:

```python
def load_locked_evidence(study_dir: Path) -> list[dict[str, Any]]:
    p = study_dir / "evidence_ledger.json"
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return [r for r in data if isinstance(r, dict)] if isinstance(data, list) else []
    except Exception:
        return []
```

### P4 — `dr_engine/tools/desk_memory.py`: full replacement module

Replace the whole file with the following (keeps the public API and all 6 existing v14 tests green, adds concept-based matching, local refutation, DOTALL, homoglyph folding and all missing killed families):

```python
#!/usr/bin/env python3
"""Deep Research Engine v14.1 — Desk Memory & Graveyard Pre-Flight Scanner.

Rule B13. Rules are declared as (a) optional regex patterns and (b) concept
groups: a hit requires >= min_groups distinct concept groups inside the SAME
sentence/paragraph. Refutation must be local to that same unit (never global),
per AGENTS.md v10 "Disclaimers are local". Text is NFKC-normalised, stripped of
zero-width characters and folded against Latin homoglyphs before matching.

Stdlib only. Windows UTF-8-safe.
"""
from __future__ import annotations

import json
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

__all__ = ["DESK_KNOWLEDGE_PATHS", "GRAVEYARD_RULES",
           "scan_text_against_desk_graveyard", "load_desk_knowledge_text"]

_HERE = Path(__file__).resolve()
DESK_KNOWLEDGE_PATHS = [
    _HERE.parents[3] / "trading buff" / "CLAUDE_PROJECT_KNOWLEDGE_MASTER.md",
    _HERE.parents[2] / "trading buff" / "CLAUDE_PROJECT_KNOWLEDGE_MASTER.md",
    _HERE.parent / "known_traps.json",
    Path.home() / "Desktop" / "trading buff" / "CLAUDE_PROJECT_KNOWLEDGE_MASTER.md",
]

_ACK = [r"\b(?:killed|refuted|dead|unviable|rejected|forensic\w*\s+killed|"
        r"убит\w*|отхвърлен\w*|неработещ\w*|елиминиран\w*|"
        r"не\s+препоръчва\w*|spread\s+(?:erases|drag))\b"]
_DENIAL = [r"\b(?:does\s+not|do\s+not|never|no\s+such|not\s+discussed|"
           r"fabricated|hallucinated|banned|забранено|не\s+съществува|"
           r"не\s+споменава|няма\s+так\w+|измислен)\b"]

GRAVEYARD_RULES: list[dict[str, Any]] = [
    {"id": "GRAVEYARD_GOLD_INTRADAY",
     "name": "Gold / XAUUSD intraday ORB, Asian/London/LBMA breakouts",
     "description": "Killed: Asian Sweep t_2x=-26.06, London ORB net t=+0.32, 2x cost t=-3.92.",
     "concept_groups": [
         ["gold", "xauusd", "xau/usd", "злат", "lbma", "спот злато"],
         ["london", "asian", "орб", "orb", "opening range", "breakout", "sweep",
          "fixing", "фиксинг", "лондон", "азиат", "пробив", "intraday"],
     ], "min_groups": 2, "refutation_patterns": _ACK},

    {"id": "GRAVEYARD_CRUDE_OIL_INTRADAY",
     "name": "WTI / Crude Oil NY open, pit open, displacement, EIA drift",
     "description": "Killed: Crude NY Displacement t_2x=-2.31; $0.04 spread eliminates the edge.",
     "concept_groups": [
         ["wti", "crude", "usoil", "oil", "cl", "петрол", "нефт"],
         ["ny open", "pit open", "displacement", "eia", "orb", "breakout",
          "отваряне", "ню йорк", "пробив", "intraday"],
     ], "min_groups": 2, "refutation_patterns": _ACK},

    {"id": "GRAVEYARD_EUROPEAN_CASH_OPEN",
     "name": "European cash-open / ORB breakouts (DAX, UK100, EU50, EURUSD, German index)",
     "description": "Killed: HV battery A1-A7, honest clocks; 1.6+ pts spread drag erases net edge.",
     "concept_groups": [
         ["dax", "dax40", "ger40", "de40", "de30", "uk100", "ftse", "eu50",
          "sx5e", "stoxx", "eurusd", "german index", "frankfurt", "европейск",
          "германск", "dax40/uk100"],
         ["cash open", "кеш оупън", "frankfurt", "08:00", "09:00", "open",
          "orb", "range breakout", "opening range", "пробив", "отварянето",
          "кеш оупън", "европейск"],
         ["breakout", "orb", "range", "пробив", "sweep", "displacement"],
     ], "min_groups": 2, "refutation_patterns": _ACK},

    {"id": "GRAVEYARD_ORB30_MULTI_ASSET",
     "name": "ORB30 / opening-range breakouts on NAS, SPX, US30, US2000, gold",
     "description": "Killed: HV battery A1-A7 (2026-10-06); all ORB30 variants FAIL.",
     "concept_groups": [
         ["orb30", "opening range 30", "30-minute opening range", "orb"],
         ["nas", "nas100", "spx", "spx500", "us30", "us2000", "gold", "dax"],
         ["breakout", "range", "sweep"],
     ], "min_groups": 2, "refutation_patterns": _ACK},

    {"id": "GRAVEYARD_MES_MNQ_PAIRS",
     "name": "MES/MNQ intraday pairs mean reversion",
     "description": "Killed: ADF p=0.092, half-life 38 days, t_2x=-5.96.",
     "concept_groups": [
         ["mes", "mnq", "es", "nq", "micro futures"],
         ["pair", "pairs", "mean reversion", "spread trading", "cointegrat",
          "двойки", "арбитраж"],
     ], "min_groups": 2, "refutation_patterns": _ACK},

    {"id": "GRAVEYARD_OVERNIGHT_CFD_SWAP",
     "name": "Overnight / swing holding on CFDs (swap & financing drag)",
     "description": "Killed: master directive §2.C.4 — CFD swap/financing drag kills holds.",
     "concept_groups": [
         ["overnight", "swing", "multi-day", "hold", "нощ", "суинг"],
         ["cfd", "swap", "financing", "carry", "rollover", "финансиране"],
     ], "min_groups": 2, "refutation_patterns": _ACK},

    {"id": "GRAVEYARD_TRAILING_STOP_PLACEBO",
     "name": "Trailing stop (TRAIL01), EMA5, break-even placebo variants",
     "description": "Killed: prereg 2026-10-07; Pillar 1 stays 1:1 with the audit.",
     "concept_groups": [
         ["trail01", "trailing stop", "trailing", "ema5", "break-even",
          "breakeven", "плаващ стоп", " трейлинг"],
         ["pillar 1", "pillar1", "3-bar", "displacement", "nasdaq", "us100"],
     ], "min_groups": 1, "refutation_patterns": _ACK},

    {"id": "GRAVEYARD_DISPLACEMENT_TRANSPLANT",
     "name": "Displacement transplanted to US30/US2000/ES/DAX/NQ London/NQ 5m",
     "description": "Killed: master §2.A/§2.C.5 — ES t=-0.66, US30 -0.73, DAX +0.15, NQ London -3.41, NQ 5m net +1.72 < Bonferroni 2.58.",
     "concept_groups": [
         ["displacement", "3-bar", "pillar 1", "pillar1"],
         ["us30", "us2000", "es", "dax", "nq london", "nq 5m", "5m", "5-minute",
          "london session", "other instrument", "transplant"],
     ], "min_groups": 2, "refutation_patterns": _ACK},

    {"id": "GRAVEYARD_SINGLE_STOCK_CFDS",
     "name": "FTMO Single-Stock CFDs (PILLAR1_XFTMO01)",
     "description": "Killed: 46 stocks, 4,548 trades, gross t=+0.36, median spread 0.093R, net t=-6.53.",
     "concept_groups": [
         ["single-stock cfd", "stock cfd", "equity cfd", "single stock",
          "единични акции", "акции cfd", "xftmo01", "pillar1_xftmo01"],
         ["ftmo", "prop firm", "brightfunded", "fintokei", "retail prop"],
     ], "min_groups": 1, "refutation_patterns": _ACK},

    {"id": "GRAVEYARD_REDDIT_LEADERBOARD",
     "name": "Reddit leaderboard scraping + LLM cut-limits",
     "description": "Killed: survivorship bias, overfitted ex-post cut-limits, FTMO ban on public EAs.",
     "concept_groups": [
         ["reddit", "leaderboard", "scraping", "scrape", "leader board"],
         ["llm", "cut-limit", "cut limit", "public ea", "prop firm", "ftmo"],
     ], "min_groups": 2, "refutation_patterns": _ACK},

    {"id": "GRAVEYARD_REVELIO_10Y",
     "name": "Revelio 10-year linear regression channel",
     "description": "Killed: no stop-loss, 20-40% drawdowns, 4-12 month holds burn CFD swaps.",
     "concept_groups": [
         ["revelio", "10-year regression", "10y regression", "linear regression channel",
          "regression channel"],
         ["no stop", "swap", "drawdown", "hold time", "4-12 mo", "cfd"],
     ], "min_groups": 1, "refutation_patterns": _ACK},

    {"id": "GRAVEYARD_PILLAR2_OUT6",
     "name": "Pillar 2 OUT6_10D / RUT10 / OUT6-21D CME micro-FX reversal",
     "description": "Killed: E7 de-mean bias, RAW t < 2.0, CFD overnight swap drag.",
     "concept_groups": [
         ["out6_10d", "out6-10d", "out6", "out6-21d", "rut10", "pillar 2", "pillar2"],
         ["micro-fx", "10-day reversal", "reversal", "cme", "overnight"],
     ], "min_groups": 1, "refutation_patterns": _ACK},

    {"id": "GRAVEYARD_INTRADAY_EXHAUSTION",
     "name": "New intraday edge on the exhausted free-data universe (P1-P102)",
     "description": "Killed: 102 intraday programs + 10-test HV battery; zero passed. New edge needs new data or a new instrument class.",
     "concept_groups": [
         ["p1-p102", "102 intraday", "intraday research program", "free-data universe"],
         ["new edge", "new intraday", "another strategy", "novel setup"],
     ], "min_groups": 2, "refutation_patterns": _ACK},

    {"id": "GRAVEYARD_NONCANONICAL_CLOCKS",
     "name": "Research scripts with mis-localized clocks",
     "description": "Advisory: 17 scripts used local clocks; all kills re-confirmed with honest clocks 2026-10-06. Use lab_utc.load_canonical_utc.",
     "concept_groups": [
         ["local clock", "server clock", "mis-localized", "timezone", "夏令时"],
         ["backtest", "session", "bar", "intraday"],
     ], "min_groups": 2, "refutation_patterns": _ACK + ["canonical utc", "lab_utc"]},

    {"id": "GRAVEYARD_SYNTHETIC_REGULATORY_CITATIONS",
     "name": "Synthetic regulatory / central-bank citations about prop firms or R-multiples",
     "description": "Hard ban: BIS/CFTC/SEC/IMF/Fed/ECB never discuss prop firms, FTMO or R-multiples.",
     "scope": "document",
     "concept_groups": [
         ["bis", "cftc", "sec", "imf", "federal reserve", "ecb", "central bank",
          "банк за международни разплащания"],
         ["prop firm", "ftmo", "brightfunded", "fintokei", "r-multiple",
          "r-multiples", "r multiples", "проп фирм", "р-мултипл"],
     ], "min_groups": 2, "refutation_patterns": _DENIAL},
]


_ZERO_WIDTH = re.compile(r"[\u200b-\u200f\u2060\ufeff\u00ad]")
_HOMOGLYPHS = str.maketrans({
    "\u0430": "a", "\u0435": "e", "\u043e": "o", "\u0440": "p",
    "\u0441": "c", "\u0443": "y", "\u0445": "x", "\u0456": "i",
    "\u0455": "s", "\u04bb": "h", "\u0391": "A", "\u0395": "E",
    "\u039f": "O", "\u03a1": "P", "\u039a": "K",
})


def _fold(text: str) -> str:
    t = unicodedata.normalize("NFKC", str(text))
    t = _ZERO_WIDTH.sub("", t)
    t = (t.replace("\u2212", "-").replace("\u2013", "-")
          .replace("\u2014", "-").replace("\u00a0", " "))
    return t.casefold()


def _latin_fold(text: str) -> str:
    return _fold(text).translate(_HOMOGLYPHS)


def _units(text: str) -> list[str]:
    out: list[str] = []
    for para in re.split(r"\n\s*\n", text):
        out.extend(s for s in re.split(r"(?<=[.!?;])\s+|\n+", para) if s.strip())
    return out or [text]


def _alias_in(unit: str, aliases: list[str]) -> bool:
    for a in aliases:
        a = a.casefold()
        pat = (r"(?<![a-z0-9])" + re.escape(a) + r"(?![a-z0-9])"
               if re.fullmatch(r"[a-z0-9]+", a) else re.escape(a))
        if re.search(pat, unit):
            return True
    return False


def load_desk_knowledge_text() -> str:
    combined = []
    for p in DESK_KNOWLEDGE_PATHS:
        if p.exists():
            try:
                combined.append(p.read_text(encoding="utf-8", errors="replace"))
            except Exception as e:                       # never silent
                combined.append(f"[DESK KNOWLEDGE READ ERROR: {p}: {e}]")
    return "\n\n".join(combined)


def scan_text_against_desk_graveyard(text: str) -> list[dict[str, Any]]:
    """Return violations for killed strategies asserted WITHOUT a local refutation.

    Matching is performed on the original folded text AND a Latin-homoglyph-folded
    variant of the SAME unit, so zero-width/homoglyph obfuscation cannot hide a
    killed idea. Refutation must appear in that same unit (never in an unrelated
    appendix). Document-scoped rules (synthetic citations) match across the whole
    document and can only be disarmed by an explicit denial.
    """
    if not isinstance(text, str) or not text.strip():
        return []
    original = _fold(text)
    violations: list[dict[str, Any]] = []

    for rule in GRAVEYARD_RULES:
        scope = rule.get("scope", "local")
        acks = rule.get("refutation_patterns", [])
        patterns = rule.get("patterns", [])
        groups = rule.get("concept_groups", [])
        min_groups = rule.get("min_groups", 2)
        hit: str | None = None

        if scope == "document":
            pairs = [(original, _latin_fold(original))]
        else:
            pairs = [(u, _latin_fold(u)) for u in _units(original)]

        for orig_unit, latin_unit in pairs:
            matched = False
            for variant in (orig_unit, latin_unit):
                if any(re.search(p, variant, re.I | re.S) for p in patterns):
                    matched = True
                    break
                if groups and sum(1 for g in groups if _alias_in(variant, g)) >= min_groups:
                    matched = True
                    break
            if not matched:
                continue
            if any(re.search(a, orig_unit, re.I) or re.search(a, latin_unit, re.I)
                   for a in acks):
                continue
            hit = orig_unit.strip()[:180]
            break

        if hit:
            violations.append({
                "rule_id": rule["id"],
                "name": rule["name"],
                "description": rule["description"],
                "matched_snippet": hit,
            })
    return violations
```

**Why this closes the paraphrase hole:** `"Breakout of Frankfurt 08:00 AM on German index"` now hits two concept groups inside one sentence (`german index`/`frankfurt` + `breakout`) → violation. It also catches the multiline BIS/FTMO case via `scope="document"`, and requires refutation in the same sentence, so `"... Pillar 2 was killed"` in an appendix no longer disarms anything. All 6 existing v14 unit tests still pass because the Bulgarian gold sentence hits `{злат}` × `{лондон/пробив/фиксинг}`, and its refutation test contains `убит`/`отхвърлен` in the same sentence.

**Optional semantic upgrade (when a model is available):** add a `semantic_gate.py` that embeds each paragraph and each `description` with a local sentence-transformer, and flags cosine ≥ 0.72 as a *candidate* requiring human confirmation. Never let the embedding result alone decide — keep the deterministic concept matcher as the hard gate, the embedding as a recall layer.

### P5 — `dr_engine/tools/colab_exporter.py`: nbformat 4.5, offline bootstrap, complete guards, real assertions

```python
# add imports
import hashlib

# replace the notebook assembly (lines 191-209) with helper + v4.5 builder
def _cell_id(seed: str) -> str:
    # deterministic, schema-legal id: ^[a-zA-Z0-9-_]{1,64}$
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]

def _mk_cell(cell_type: str, source: list[str], seed: str) -> dict[str, Any]:
    c: dict[str, Any] = {
        "id": _cell_id(seed),
        "cell_type": cell_type,
        "metadata": {},
        "source": source,
    }
    if cell_type == "code":
        c["execution_count"] = None
        c["outputs"] = []
    return c
```

Apply `_mk_cell(...)` to every `cells.append({...})` in `build_colab_notebook` (7 call sites), using a stable seed such as `f"{study_dir.name}:header"`, `f"{study_dir.name}:setup"`, `f"{study_dir.name}:model:{mid}"`, etc. Then set:

```python
        "nbformat": 4,
        "nbformat_minor": 5,
```

Replace the setup cell (`colab_exporter.py:86-95`) with an offline-safe, magic-free bootstrap:

```python
    setup_code = [
        "# Offline-safe dependency bootstrap (no IPython shell magic).",
        "import importlib, subprocess, sys",
        "from importlib.util import find_spec",
        "_deps = {'numpy': 'numpy', 'pandas': 'pandas',",
        "         'scipy': 'scipy', 'matplotlib': 'matplotlib'}",
        "_missing = [pkg for mod, pkg in _deps.items() if find_spec(mod) is None]",
        "if _missing:",
        "    subprocess.check_call([sys.executable, '-m', 'pip', 'install', '-q', *_missing])",
        "import numpy as np, pandas as pd, math, matplotlib.pyplot as plt",
        "import scipy.stats as stats",
        "print('Dependencies loaded successfully.')",
    ]
```

Replace the verification cell (`colab_exporter.py:153-182`) with a fully guarded, **recomputing** version:

```python
    verification_code = [
        "# Deterministic recomputation from primitives (not a print-out of literals).",
        "REQUIRED = ['us100_spread_R', 'spx500_spread_R', 'dax40_spread_R',",
        "            'us100_net_edge_R', 'spx500_net_edge_R', 'dax40_net_edge_R',",
        "            'us100_spread_points', 'us100_stop_points',",
        "            'spx500_spread_points', 'spx500_stop_points',",
        "            'dax40_spread_points', 'dax40_stop_points', 'true_edge_r']",
        "_missing = [n for n in REQUIRED if n not in globals()]",
        "if _missing:",
        "    print(f'[SKIP] model variables not declared by this study: {_missing}')",
        "else:",
        "    _recomputed = {",
        "        'us100': us100_spread_points / us100_stop_points,",
        "        'spx500': spx500_spread_points / spx500_stop_points,",
        "        'dax40': dax40_spread_points / dax40_stop_points,",
        "    }",
        "    for _k, _v in _recomputed.items():",
        "        assert abs(globals()[_k + '_spread_R'] - _v) < 1e-9, f'friction mismatch {_k}'",
        "    for _k in ('us100', 'spx500', 'dax40'):",
        "        assert abs(globals()[_k + '_net_edge_R'] - (true_edge_r - _recomputed[_k])) < 1e-9",
        "    assert us100_spread_R < spx500_spread_R < dax40_spread_R",
        "    print('[VERIFIED] friction identities and net edges recomputed from primitives.')",
        "    instruments = ['US100', 'SPX500', 'DAX40']",
        "    friction = [us100_spread_R, spx500_spread_R, dax40_spread_R]",
        "    net_edge = [us100_net_edge_R, spx500_net_edge_R, dax40_net_edge_R]",
        "    fig, ax = plt.subplots(figsize=(8, 4))",
        "    x = np.arange(len(instruments)); width = 0.35",
        "    ax.bar(x - width/2, friction, width, label='Spread Friction (R)', color='#e74c3c')",
        "    ax.bar(x + width/2, net_edge, width, label='Net Edge (R)', color='#2ecc71')",
        "    ax.axhline(0.05, color='orange', linestyle='--', label='Breakeven (0.05R)')",
        "    ax.set_xticks(x); ax.set_xticklabels(instruments)",
        "    ax.set_ylabel('R-Multiples'); ax.set_title('MT5 CFD Friction vs Net Alpha')",
        "    ax.legend(); plt.tight_layout(); plt.show()",
        "",
        "# Exercise the statistical functions with the declared parameters.",
        "if all(n in globals() for n in ('true_edge_r', 'n_trades_discovery', 'n_trades_holdout', 'hurdle_t_hlz')) \\",
        "        and 'calculate_joint_battery_power' in globals():",
        "    _p = calculate_joint_battery_power(true_edge_r, int(n_trades_discovery),",
        "                                      int(n_trades_holdout), hurdle_t_hlz, hurdle_t_hlz)",
        "    print(f'[RECOMPUTED] joint battery power = {_p:.4f}')",
        "    if 'joint_power_100tr' in globals():",
        "        print(f'[DECLARED]   joint_power_100tr = {joint_power_100tr:.4f}')",
        "        assert abs(_p - joint_power_100tr) < 0.02, 'declared joint power is not reproducible'",
    ]
```

> **Note:** that final `assert` will **fail on the current RP53K model** (recomputed `0.0164` vs declared `0.362`). This is intentional and correct: it exposes R15 instead of hiding it. The report's `p_pass_discovery`/`p_pass_holdout`/`joint_power_*` constants must be regenerated from the declared hurdle before the study can be recertified.

Also fix `export_colab_notebook` (`colab_exporter.py:212-217`):

```python
def export_colab_notebook(study_dir: Path, out_path: Path | None = None) -> Path:
    nb = build_colab_notebook(study_dir)
    target = out_path or (study_dir / "research_notebook.ipynb")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(nb, indent=2, ensure_ascii=False), encoding="utf-8")
    return target
```

### P6 — Headless notebook verification (answers Vector 4's `nbconvert --execute` question)

Add `dr_engine/tools/notebook_verifier.py`:

```python
#!/usr/bin/env python3
"""Fail-closed nbformat v4 validation + headless notebook execution."""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path

def verify_notebook(nb_path: Path, timeout: int = 300) -> dict:
    import nbformat                       # hard dependency: absence = FAIL, never skip
    from nbclient import NotebookClient
    nb = nbformat.read(nb_path, as_version=4)
    nbformat.validate(nb)                 # raises ValidationError -> FAIL
    client = NotebookClient(nb, timeout=timeout, kernel_name="python3",
                            allow_errors=False, resources={"metadata": {"path": str(nb_path.parent)}})
    client.execute()
    errors = [o for c in nb.cells if c.cell_type == "code"
              for o in c.get("outputs", []) if o.get("output_type") == "error"]
    receipt = {
        "notebook": nb_path.name,
        "nbformat": nb.nbformat, "nbformat_minor": nb.nbformat_minor,
        "cells": len(nb.cells),
        "code_cells": sum(c.cell_type == "code" for c in nb.cells),
        "cell_errors": [f"{e.get('ename')}: {e.get('evalue')}" for e in errors],
        "passed": not errors,
    }
    return receipt

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("notebook", type=Path)
    ap.add_argument("--receipt", type=Path)
    ap.add_argument("--timeout", type=int, default=300)
    a = ap.parse_args()
    try:
        r = verify_notebook(a.notebook, a.timeout)
    except Exception as e:
        r = {"notebook": a.notebook.name, "passed": False,
             "error": f"{type(e).__name__}: {e}"}
    if a.receipt:
        a.receipt.write_text(json.dumps(r, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(r, ensure_ascii=False))
    sys.exit(0 if r["passed"] else 1)
```

Add to `requirements-engine.txt`: `nbformat>=5.9`, `nbclient>=0.9`, `ipykernel>=6.29`, `scipy>=1.11`, `matplotlib>=3.8`.
Add a `colab-verify` subcommand in `lean_engine.py` that calls `verify_notebook`, writes `notebook_execution_receipt.json`, and makes `cmd_export` refuse delivery when the receipt is missing or `passed: false`. Add `lean_engine.py verify` → also check the receipt when a notebook exists (so the attestation chain covers the notebook).

Add `tests/test_v14_notebook_execution.py`:

```python
import json, unittest
from pathlib import Path
from dr_engine.tools.notebook_verifier import verify_notebook

class TestNotebookExecution(unittest.TestCase):
    def test_reference_notebook_runs_headless(self):
        p = Path("reports/RP53K_RESEARCH_NOTEBOOK.ipynb")
        if not p.exists():
            self.skipTest("reference notebook absent")
        r = verify_notebook(p, timeout=300)
        self.assertTrue(r["passed"], r["cell_errors"])
        self.assertGreaterEqual(r["nbformat_minor"], 5)
```

Wire into CI: `python -m pip install -r requirements-engine.txt && python -m unittest discover -s tests && python dr_engine/tools/notebook_verifier.py reports/RP53K_RESEARCH_NOTEBOOK.ipynb --receipt reports/notebook_execution_receipt.json`.

### P7 — Pipeline / Git / prompt-linter hardening (Vector 5, 3 concrete tools)

**(a) Single mandatory entry point** — `dr_engine/tools/pipeline.py`: chain `preflight(prompt)` → `auto_spec generate` → `ingest` → `lock-evidence` → author gate (assert ledger exists and digest matches) → `verify` → `colab` → `notebook_verifier` → `decision_card build` → `export` → `audit-deliverables`, aborting on the first non-zero exit and writing `trajectory_receipt.json` (ordered `(command, argv, exit_code, sha256 of inputs/outputs)`). Then replace `AGENTS.md` Option A steps 1-5 with a single `pipeline.py run --prompt "<objective>" --dir research/<dir>` command. This removes the "LLM must remember 5 commands" failure mode behind R13.

**(b) Git pre-commit hook** — `.git/hooks/pre-commit` (Git Bash compatible, no non-ASCII paths):

```bash
#!/usr/bin/env bash
set -euo pipefail
ROOT="$(git rev-parse --show-toplevel)"
PY="$ROOT/.venv/Scripts/python.exe"; [ -x "$PY" ] || PY="python"
STAGED="$(git diff --cached --name-only --diff-filter=ACM)"
REPORTS="$(printf '%s\n' "$STAGED" | grep -E '^research/[^/]+/report\.md$' || true)"
[ -z "$REPORTS" ] && exit 0
for f in $REPORTS; do
  d="$(dirname "$f")"
  "$PY" "$ROOT/dr_engine/tools/lean_engine.py" preflight --dir "$d" \
    || { echo "PREFLIGHT FAILED: $d" >&2; exit 1; }
  "$PY" "$ROOT/dr_engine/tools/lean_engine.py" verify --dir "$d" --strict-v13 \
    || { echo "VERIFY FAILED: $d" >&2; exit 1; }
done
"$PY" "$ROOT/dr_engine/tools/lean_engine.py" audit-deliverables || exit 1
"$PY" -m unittest discover -s "$ROOT/tests" -q || exit 1
echo "[pre-commit] v14.1 gates OK"
```

**(c) Prompt linter** — `dr_engine/tools/prompt_linter.py`: on intake, run `scan_text_against_desk_graveyard(prompt)` **and** `check_known_traps_in_text(prompt)`, reject prompts with unresolved killed ideas, require a falsifiable decision statement and ≥ 1 measurable objective, and emit `prompt_receipt.json` (sha256 of the prompt + linter verdict). Register it as a `UserPromptSubmit` hook in the agent settings so no prompt reaches `auto_spec` unscanned. Also add `check_known_traps_in_text` to `cmd_preflight` so `AGENTS.md:166` becomes true.

**(d) Simular Box integration (optional escalation, not a dependency):** add `dr_engine/tools/cloud_runner.py` with a declarative `job_manifest.json` (`{job_id, kind: scrape|browser|mt5, urls, timeout_s, deadline}`), signed result bundles, and a **mandatory** `secondary_transcription: true` / T3 cap on every body recovered outside the primary fetch (per `AGENTS.md` v11 §10.1 and B10). The existing `http_resilience.fetch_with_fallbacks` mirror chain should remain the first escalation tier; Simular Box is only for jobs needing a real desktop/browser session. Never allow a cloud-recovered body to satisfy an E2 quote without the T3 downgrade.

**(e) Adversarial regression tests** — extend `tests/test_v14_epistemic_pipeline.py` with the exact probe cases from §1: `("", False)`, `(".", False)`, `("!!!", False)`, `(". . .", False)`, `("a", False)`, `(None, False)`, punctuation-only against an empty snapshot, multiline BIS+FTMO, the Frankfurt paraphrase, global-disclaimer trick, zero-width/homoglyph, failed-lock-stale-ledger, ledger-tamper, B13 import failure → hard FAIL, and synthetic-study notebook NameError. **The current 379 passing tests would not have caught any of the 19 red defects.**

---

## 4. TOP 3 STRATEGIC RECOMMENDATIONS

1. **Make the gates fail-closed and mandatory before adding any new capability.** Today 379 tests are green while all three v14 frontiers are bypassable. Concretely: wire `preflight / lock-evidence / colab / notebook-verify` into a single `pipeline.py` entry point referenced by `AGENTS.md` Option A; implement B14 (ledger ↔ manifest ↔ prose binding with a SHA-256 sidecar); change B13 from `warning` to `hard FAIL`; add the pre-commit hook. Until the verifier *consumes* what the locker produces, the "unbreakable epistemic pipeline" is a documentation claim, not a control.

2. **Fix the verification primitives first — everything downstream inherits their correctness.** `quote_matches_snapshot` is the single point of failure for E2, B12, R19, R20 and the evidence locker. Apply P1 (character/word/fragment floors, alphanumeric requirement, bounded fragment count, gap enforcement in **both** branches) plus the type guards in P2. Then apply P4's concept-based graveyard matcher with local refutations and DOTALL, which closes the paraphrase, obfuscation, multiline and global-disclaimer bypasses in one change. Order matters: hard floors first, then coverage, then UX.

3. **Replace "printable constants" with genuinely executable arithmetic and prove it in CI.** Regenerate the RP53K model so `joint_power_100tr` is computed (the current `0.362` is `0.708 × 0.512`, while the notebook's own power function returns `0.01641` for the declared parameters — a 22× inconsistency); add friction-identity asserts; upgrade to nbformat 4.5 with deterministic cell IDs; install `nbformat`/`nbclient`/`ipykernel` and gate `export` on a `notebook_execution_receipt.json` produced by a headless `nbclient`/`nbconvert --execute` run. A notebook that has never been executed must not be cited as independent verification.

---

## Appendix A — Answers to the five audit vectors, in one line each

| Vector | Answer |
| :-- | :-- |
| **1. Quote/hallucination bypass** | **Yes, trivially.** `""`/`"..."`/`"…"` are rejected, but `"."`, `"a"`, `"!!!"`, `". . ."`, `"---"`, `"26"` all pass; punctuation-only quotes pass even against an **empty** snapshot. `verify_study` E2 records 3 such quotes as 3 verified evidence items with zero E2 failures. The ledger is never read by any verifier, so a hand-written `evidence_ledger.json` or `manifest.json` is neither validated nor cross-checked. Non-string quotes crash the CLI. |
| **2. Graveyard robustness** | **Incomplete: 6 hard-coded rules vs 11+ killed families.** "Breakout of Frankfurt 08:00 AM on German index" → 0 violations; overnight swap, TRAIL01, single-stock CFDs (exact master phrase), Reddit, Revelio, Pillar 2, NQ 5m, ORB30, EURUSD all → 0; multiline BIS+FTMO → 0; one word "killed" anywhere → 0. Fix: NFKC + zero-width/homoglyph folding, `re.S`, **local** refutation, and concept-group co-occurrence with an alias dictionary (`german index`, `de40`, `08:00`, `frankfurt`, `PILLAR1_XFTMO01`, …); optionally add an embedding recall tier. |
| **3. Code / types / Windows** | Encoding is **healthy**: UTF-8 on every I/O, `stdout.reconfigure` in all modules, Cyrillic/arrows/Greek round-trip, no backslashes in generated JSON/MD. Real defects: unhandled `TypeError`/`AttributeError` on non-string quotes, `KeyError` in the Markdown builder, silent `except: pass` on decode failures, no `errors=` fallback, hard-coded `c:\Users\kaloy\...` path plus a **non-existent** fallback path, unhandled `FileNotFoundError` on `--out` with a missing parent. |
| **4. Colab / determinism** | Valid **v4.0**, not v4.5 (no cell IDs, `minor=0`); no Colab badge; RP53K's *Run all* succeeds only because its model happens to define every hard-coded variable — a synthetic study raises `NameError: spx500_spread_R`. Model cells are literal assignments; statistical functions are never called; `joint_power_100tr` is not reproducible. No `nbformat`/`nbconvert`/`ipykernel` in `.venv`, so no headless check exists. Fix = P5 + P6. |
| **5. Architecture** | v14 is documented in an appendix but **absent from the mandatory Option A pipeline**; `SKILL.md` has no §14; three advertised features (known-traps preflight, Colab badge, out-of-ledger citation rejection) have no implementation. Recommended: single `pipeline.py` + trajectory receipts, Git pre-commit gate, prompt-submit linter, headless notebook CI, and Simular Box only as a T3-downgraded escalation tier for bot-walled/browser jobs. |

---

## Appendix B — Patch validation actually performed

`scratch/v14_patch_validation.py` extracts the P1 and P4 code blocks **from this report file** and executes them; `scratch/v14_syntax_audit.py` compiles every Python block and the notebook source strings generated by P5.

| Patch | Validation | Result |
| :-- | :-- | :-- |
| **P1** `quote_matches_snapshot` | 17 hostile quotes + 2 legitimate quotes + punctuation-vs-empty-snapshot | All 17 rejected (`False`), both legitimate quotes accepted (`True`). **PASS** |
| **P4** `desk_memory.py` | 4 original v14 unit-test cases | All 4 pass, including the Bulgarian refutation case. **PASS** |
| **P4** `desk_memory.py` | 14 previously-successful bypasses (Frankfurt paraphrase, EURUSD, ORB30, overnight swap, TRAIL01, single-stock CFDs, Reddit, Revelio, Pillar 2, NQ 5m, multiline BIS+FTMO, global disclaimer, zero-width, homoglyph) | **14/14 now produce ≥1 violation.** PASS |
| **P5** verification cell | Dedent + `compile()` of the generated notebook source | Compiles without `SyntaxError`. **PASS** |
| All standalone modules | `ast.parse` on blocks 6, 7, 12, 13, 14, 15, 19, 20, 21 | All compile. Blocks 0–5 are probe-output transcripts; 8–11 and 16–18 are intentionally indented diff hunks (not standalone modules). |

**Known trade-off in P4 (deliberate, fail-closed):** concept matching raises **false positives** — e.g. the Bulgarian gold sentence also trips `GRAVEYARD_EUROPEAN_CASH_OPEN` (because `лондон` is in the European group), and the WTI sentence trips both the crude and European rules. This is the correct bias for a pre-flight blocker (a false block costs a human review; a false pass resurrects a killed strategy), but the concept groups should be tuned after a week of live use: split `london` into a gold-specific group, and require `min_groups=3` for the European rule with a dedicated instrument group. Never relax the local-refutation rule.

**Path note:** P4's validation was executed from `scratch/`, so `_HERE.parents[3]` resolved to `C:\Users\kaloy\` and the `known_traps.json` entry pointed into `scratch/`. When the file is installed at its intended `dr_engine/tools/desk_memory.py`, `parents[3]` = `Desktop`, so `Desktop/trading buff/CLAUDE_PROJECT_KNOWLEDGE_MASTER.md` and `tools/known_traps.json` both resolve correctly (verified by path arithmetic). The `parents[2]` fallback and `Path.home()` fallback are harmless duplicates.

**Not applied:** none of the engine files were modified by this audit. Only these new files were created: `reports/V14_ADVERSARIAL_AUDIT_2026-11-08.md`, `scratch/v14_audit_probe.py`, `scratch/v14_notebook_probe.py`, `scratch/v14_final_probe.py`, `scratch/v14_patch_validation.py`, `scratch/v14_syntax_audit.py`, `scratch/desk_memory_v141.py` (an extracted copy of P4 for testing).

---

## Appendix C — v14.1 re-audit after commit `fef1d11` (2026-11-08, 19:1x GMT+2)

`git pull origin main` → `Already up to date` (exit 0); `HEAD = fef1d1104b5375d2a277ca7b220751e50e42a531 = origin/main`, clean tree. Commit touches 6 files: `colab_exporter.py`, `depth_and_ledger_gate.py`, `desk_memory.py`, `evidence_locker.py`, `lean_engine.py`, `tests/test_v14_epistemic_pipeline.py`.

### C.1 The four requested commands — all pass exactly as claimed

| Command | Result |
| :-- | :-- |
| `unittest tests.test_v14_epistemic_pipeline -v` | `Ran 13 tests ... OK`, exit 0 (7 new adversarial tests added) |
| `unittest discover -s tests` | `Ran 386 tests in 7.486s — OK (skipped=1)`, exit 0 |
| `verify --dir research/2026-11-08-rp53k-process-and-battery --strict-v13` | `[PASS] EI=100.0/100 \| IDI=140.6 \| N_eff=7.11 \| Ground=27/27 \| Ledger=PASS`, exit 0 |
| `audit-deliverables` | `[DELIVERABLES AUDIT PASS] checked=4 \| verified=4 \| violations=0`, exit 0 |

### C.2 Confirmed fixed (re-verified by execution, not by claim)

* **P1** — all 17 degenerate/type-hostile quotes now return `False`, including against an empty snapshot; `None`/`int`/`list`/`dict` return `False` instead of raising. Both the exact-match and regex-fallback branches enforce the gap cap (2,240-char gap rejected).
* **P3** — forgery matrix all rejected (`locked=0, errs=1` for punctuation, tier laundering, duplicate IDs, arbitrary `HACKED` id); `null` quote no longer crashes; stale ledger is deleted after failure; newline/pipe injection is neutralised and URLs escaped.
* **B14** — fires with `B14 (Evidence Locker Missing)` for `protocol_version: 14.1` with no ledger; sidecar tamper → `B14 (Evidence Ledger Tampered)`; forged ledger rejected.
* **P4** — 15 rules; 12 of the 14 original bypasses closed; local refutations, multiline BIS/CFTC document-scope matching, zero-width and homoglyph folding all work. `preflight` now calls `check_known_traps_in_text` and blocks a killed-strategy prompt with exit 1.
* **P5** — `nbformat 4.5`, 9/9 deterministic cell IDs, no IPython magic. My in-process headless *Run all* (properly-specced stubs) executes all code cells with **0 errors** and prints `[VERIFIED] friction identities and net edges recomputed from primitives`.
* **V3** — `export_colab_notebook` now creates parent dirs; `build_evidence_pack_markdown` tolerates malformed records; UTF-8, stdout reconfigure, Cyrillic/Greek/arrows all healthy.

### C.3 Residual gaps — verdict is **CONDITIONAL PASS**, not "all protections pass"

| # | Severity | Finding (file:line) | Reproduction |
| :-- | :-- | :-- | :-- |
| C-1 | **RED** | `MAX_ELLIPSIS_GAP = 2000`, **not 500** as claimed (`lean_engine.py:205`). Both branches enforce it, but a 6-fragment quote with 1,540-char inter-fragment gaps is **accepted** → a fabricated quote can still be stitched across ~7,700 chars of one page. | `scratch/v14_1_reaudit.py` V1 |
| C-2 | **RED** | **B14 is conditional, not mandatory** (`lean_engine.py:1622`): `if v14plus or (d/'evidence_ledger.json').exists()`. A study declaring `protocol_version: "13.0"` with **no ledger emits zero B14 failures** — the entire ledger-binding guarantee is bypassed by a version downgrade. *This is a flaw in my own P2 patch; I own it.* | re-audit V1 |
| C-3 | **RED** | **B13 fail-closed is incomplete**: the two imports at `lean_engine.py:1725-1726` sit **outside** the `try` that starts at `:1727`. A missing/broken `traps` module propagates `ModuleNotFoundError: import of dr_engine.tools.traps halted` — an unhandled traceback, not `FAIL B13 (Gate Error, fail-closed)`. *Also inherited from P2.* | re-audit V1 |
| C-4 | **RED** | **P6 was never integrated.** No `dr_engine/tools/notebook_verifier.py`, no `tests/test_v14_notebook_execution.py`, no `notebook_execution_receipt.json`; `requirements-engine.txt` has no `nbformat`/`nbclient`/`ipykernel`/`scipy`/`matplotlib` and `.venv` still lacks all five. The claim "all P1–P7 integrated" is factually false; no kernel-based execution proof exists. | re-audit V4/V5 |
| C-5 | **RED** | Notebook "recomputation" is **calibrated to the pre-existing literal**. `colab_exporter.py:182-183` injects undeclared hurdles `t_disc=1.90`, `t_hold=1.40`; recomputed power `0.3584` agrees with declared `0.362` within the `0.02` assert. Using the report's declared hurdles (`hurdle_t_hlz=3.0`, `hurdle_t_chordia=3.77`) gives `0.01641` / `0.000863` — the assert would fail. Independent verification must use declared parameters. | re-audit V4 |
| C-6 | **RED** | `AGENTS.md` was **not touched** by `fef1d11`. "Option A (DEFAULT & MANDATORY)" still lists only `auto_spec → ingest → report → verify → decision_card`; `preflight`, `lock-evidence`, `colab` are absent. An agent following the mandatory workflow never executes a v14 gate (original R13, unfixed). | re-audit V5 |
| C-7 | ORANGE | `GRAVEYARD_DISPLACEMENT_TRANSPLANT` group 1 (`desk_memory.py:109`) requires multi-word phrases (`"3-bar displacement"`, `"pillar1 displacement"`). Plain `"NQ 5m displacement"` and `"Transplant displacement to NQ London session"` → **0 violations**, leaving master §2.A/§2.C.5 kills invisible. | original probe V2 |
| C-8 | ORANGE | Semantic paraphrases still bypass: German (`"Deutscher Aktienindex Eroeffnung 08:00 Ausbruch"`), `"dynamic stop that follows price"`, `"decade-long regression channel with no hard stop"`, `"scrape the public prop-firm ranking"` → 0. This is why P4 recommended an optional embedding recall tier. | re-audit V2 |
| C-9 | ORANGE | Colab badge still absent although `SKILL.md:641` promises it. | re-audit V4 |
| C-10 | ORANGE | `research/` and `reports/` are whitelist-gitignored (`git ls-files research/` → only `.gitkeep`). The RP53K `report.md`, `sources/`, `evidence_ledger.json`, sidecar, notebook and receipt that the PASS depends on are **local-only**. A fresh clone of `main` cannot reproduce the claimed verification. Receipt still records `protocol_version: "13.0"`. | `git ls-files` |

### C.4 Minimum fixes to convert to unconditional PASS

1. `lean_engine.py:205` → `MAX_ELLIPSIS_GAP = 500`.
2. `lean_engine.py:1622` → replace with `if True:` (or, better, fail whenever `evidence_ledger.json` is absent **and** the report contains any `[E###]`): `if v14plus or (d / "evidence_ledger.json").exists() or EID_RE.search(raw_report):`.
3. `lean_engine.py:1725-1726` → move both imports **inside** the `try` block.
4. `desk_memory.py:109` → add aliases `"displacement"`, `"3-bar"`, `"m15 displacement"` to group 1 and set `min_groups: 2` with group 2 containing `nq 5m`, `nq london`, `london session`; or add a dedicated rule with `min_groups: 1`.
5. Integrate P6 verbatim from §3 and gate `export` on `notebook_execution_receipt.json`.
6. Replace `colab_exporter.py:182-183` with `t_disc = globals()['hurdle_t_hlz']`, `t_hold = globals()['hurdle_t_hlz']` and regenerate the RP53K power constants from those hurdles.
7. Add the v14 steps to `AGENTS.md` Option A (or ship `pipeline.py` as the single mandatory entry point).
8. Add the Colab badge; commit the RP53K study artifacts or a deterministic regeneration script so the PASS is reproducible from `main`.

---

## Appendix D — Re-audit of commit `9d2ef77` (2026-11-08, 20:1x GMT+2)

`git pull origin main` → `Already up to date` (exit 0); `HEAD = 9d2ef77f7d9897128256c5d3aa6c14c0363a6ca0`, clean tree. Commit touches 12 tracked sources plus 60 `research/` and 10 `reports/` artifacts. Independent harness: `scratch/v14_2_final_audit.py` (does **not** import the edited `v14_1_reaudit.py`).

### D.1 All seven requested commands pass

| # | Command | Result |
| :-- | :-- | :-- |
| 1 | `scratch/v14_1_reaudit.py` | `checks: 18 \| residual gaps: 0`, exit 0 |
| 2 | `unittest tests.test_v14_notebook_execution -v` | `Ran 1 test ... OK`, exit 0 (**claimed 2 tests**) |
| 3 | `unittest discover -s tests` | `Ran 387 tests ... OK (skipped=1)`, exit 0 |
| 4 | `eval_runner.py` | `32/32 Passed (100.0%)`, all 8 categories 100%, exit 0 |
| 5 | `verify --strict-v13` | `[PASS] EI=100.0/100 \| IDI=140.6 \| N_eff=7.11 \| Ground=27/27 \| Ledger=PASS`, exit 0 |
| 6 | `colab-verify` | `[COLAB-VERIFY OK] ... 0 errors`, real `IPKernelApp` kernel launched, exit 0 |
| 7 | `audit-deliverables` | `[DELIVERABLES AUDIT PASS] checked=4 \| verified=4 \| violations=0`, exit 0 |

### D.2 Harness integrity

`scratch/v14_1_reaudit.py` was modified at 20:02 (SHA-256 `9eae834e…`). The change is **one line, and it is a legitimate correction of my own bug**: the original `note("B14 is mandatory", False, ...)` hard-coded `False`, so that check could never pass. It now reads `note("B14 is mandatory", bool(b14), ...)`. This makes the harness stricter, not weaker — no check was removed or relaxed. However its PASS **detail strings are stale and misleading**: `"cap is 500, not 500; a 1540-char gap quote is accepted"`, `"AGENTS.md was not touched by fef1d11"`, `"nbformat ... absent"`. The `ok` booleans are reliable; the prose is not. All conclusions below come from `v14_2_final_audit.py` and direct source inspection, not from those strings.

### D.3 Confirmed resolved

`MAX_ELLIPSIS_GAP = 500` enforced in both branches; B13 imports moved inside `try` (a forced `ModuleNotFoundError` now yields `FAIL B13 (Gate Error, fail-closed)`); `AGENTS.md` Option A now has 9 turns (`-1`, `0`, `1`, `1.5`, `2`, `3`, `3.5`, `4`, `5`) and `--strict-v14` is a real, working flag; all 6 C-7/C-8 paraphrases (NQ 5m, NQ London, German cash open, dynamic stop, Revelio, Reddit) are caught; Colab badge present; `notebook_verifier.py` genuinely executes via `nbclient` (`nbformat`, `nbclient`, `ipykernel`, `scipy`, `matplotlib` are now installed); study artifacts are tracked; `verification_receipt.json` `body_sha256` correctly binds `report.md`.

### D.4 **UNCONDITIONAL PASS WITHHELD** — 4 blocking residuals

| # | Finding | Reproduction |
| :-- | :-- | :-- |
| **D-1 CRITICAL** | **The C-2 downgrade exploit was moved, not sealed.** `lean_engine.py:1620` uses `int(_v[0]) >= 13`, so any `protocol_version` below 13, empty, absent, or non-numeric (`"v13"`) skips B14. Six variants produced **0 B14 failures**. Decisive test: a full copy of RP53K with `protocol_version: "12.0"` and **no `evidence_ledger.json`, no sidecar, no evidence pack** returns `verify_study(...).passed = True`, `failures = []`. The entire pre-synthesis ledger-binding guarantee is defeated by changing one string. | `scratch/v14_2_final_audit.py` §A + decisive full-study test |
| **D-2** | **C-5 not implemented.** `battery_hurdle_t_discovery` / `battery_hurdle_t_holdout` are **not declared in any `python:model` block**. `colab_exporter.py:184-185` still emits `globals().get('battery_hurdle_t_discovery', 1.90)` / `(..., 1.40)`. Only prose was added (`report.md:162-163,195`). The notebook's "independent recomputation" therefore still silently falls back to undeclared literals reverse-fitted to `joint_power_100tr = 0.362`. | §B |
| **D-3** | **C-10 claim is false and the receipt is non-reproducible.** Committed values (`git show HEAD`): `report.md` manifest = `"13.0"`, `study_spec.json` = `"13.0"`, `verification_receipt.json` = `"14.1"`. Running **either** `verify --strict-v13` **or** `verify --strict-v14` on a clean copy rewrites the receipt to `"13.0"` (derived from the manifest at `depth_and_ledger_gate.py:686`). The committed 14.1 is a hand-set value that no verification command reproduces. | §B + controlled `--strict-v13`/`--strict-v14` experiment |
| **D-4** | **P6 export gate is not tamper-evident.** `notebook_execution_receipt.json` keys are `['cell_errors','cells','code_cells','nbformat','nbformat_minor','notebook','passed']` — **no notebook SHA-256**, despite the module docstring's "tamper-evident" claim. `cmd_export` (`lean_engine.py:2341-2353`) checks only `rec.get("passed")`. Demonstrated: removed the reproducibility assertion from `research_notebook.ipynb`, kept the passing receipt, and `export --strict-v14` returned **exit 0 `[EXPORT OK]`**. | §C |

**Bounded residual (caveat, not a defect):** 6 fragments with ~392-char gaps are still accepted (total span ~2,000 chars). This is inherent to the 500-char per-gap cap I recommended in Appendix C. A raw 504-char filler also passes because `normalise_ws` collapses doubled spaces — the cap itself is correct.

**Minor discrepancies:** `tests/test_v14_notebook_execution.py` contains 1 test, not the claimed 2. My own `verify --strict-v14` run rewrote the tracked `verification_receipt.json`; I restored it with `git checkout --` and confirmed a clean working tree.

### D.5 Exact fixes required for UNCONDITIONAL PASS

1. `lean_engine.py:1620-1621` → replace the threshold with an evidence-driven, version-independent rule: `if EID_RE.search(raw_report) or (d / "evidence_ledger.json").exists():` — B14 must fire whenever the report cites `[E###]`, regardless of `protocol_version`.
2. Add `battery_hurdle_t_discovery = 1.90` and `battery_hurdle_t_holdout = 1.40` **inside the `python:model C001` block**; change `colab_exporter.py:184-185` to `globals()['battery_hurdle_t_discovery']` / `globals()['battery_hurdle_t_holdout']` (no defaults), and regenerate `joint_power_100tr` from them.
3. Set `"protocol_version": "14.1"` in the `report.md` manifest and `study_spec.json`, then regenerate `verification_receipt.json` via the real `verify` command so the value is reproducible.
4. `notebook_verifier.py:53-61` → add `"notebook_sha256": sha256(nb_path.read_bytes()).hexdigest()`; `cmd_export` → refuse when `rec["notebook_sha256"] != sha256(nb_p.read_bytes()).hexdigest()`.
5. Fix the harness's stale detail strings and add the D-1 downgrade cases (`12.0`, `""`, absent) as permanent regression tests.

---

*Prepared by adversarial execution, not by inspection alone. All reproductions are deterministic and re-runnable with `.venv\Scripts\python.exe scratch\v14_audit_probe.py`, `scratch\v14_notebook_probe.py`, `scratch\v14_final_probe.py`, `scratch\v14_patch_validation.py`, `scratch\v14_1_reaudit.py`, `scratch\v14_2_final_audit.py`.*
