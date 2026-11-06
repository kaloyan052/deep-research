# Engine Audit — Deep Research v12.0
## The Omniscient Golden Nugget & Zero-Lag Intelligence Engine

**Date:** 2026-11-06 · **Workspace:** `DR project` · **Status:** COMPLETE
**Baseline:** 322 tests pass / 1 skipped · **Final:** **358 tests pass / 1 skipped, exit 0**
**Module selftests:** 17/17 · `doctor.py`: `RESULT: READY`
**Constraints honoured:** Python 3.10+ stdlib only, zero paid API keys, Windows cp1252-safe, Rule B0 100% fail-closed.

---

## 1. Executive summary

Two residual failure modes were targeted by this upgrade:

| Failure mode | v11 behaviour | v12 mechanism |
| :-- | :-- | :-- |
| **Premature Search Termination** — first high-SEO answer is certified (510 kg; an announced model rather than a live staged preview) | B9 checked *citation recency* but never actively searched for a successor | Rule **B11** / operator `O_dethrone`: 16 adversarial, 30/90-day, 8-language vectors designed to *break* the leader; fresh upset ⇒ `dethroned`; no fresh check ⇒ **hard fail** |
| **Golden Nugget Blindspot** — a 3-sentence insider disclosure in Korean/Russian/German/Japanese/Spanish/Chinese is diluted by generic text | Polyglot BM25 existed, but no prior distinguished a witness disclosure from a press release | **Insider Anomaly Scorer** ⇒ fixed **3.0× BM25 prior**, prior-only floor and one reserved slot per query; provenance written into the immutable snapshot |
| **Zero-alpha deliverable** — report repeats a 5-second search | No gate on report *novelty* | Rule **R18**: mandatory **Epistemic Alpha Delta** section with mechanically enforced contrast |

A fourth frontier hardened the whole transport against malformed inputs and preserved fail-closed behaviour for every new gate.

**Verification (measured, not asserted):**
```
$ python -m unittest discover -s tests
Ran 358 tests in 5.9s — OK (skipped=1)

$ python scratch/v12_e2e_demo.py
[E2E DEMO PASS] v12.0 R18/B11 gates behave exactly as specified.
```
No existing test was modified to achieve this.

---

## 2. Frontier 1 — Active Dethroning (`O_dethrone`)

### 2.1 Operator definition

For an identified leader $L$ on metric $M$, the engine spawns a vector set

$$\mathcal{O}_{\text{dethrone}}(L,M) = \Big\{ q_{\ell,w} \;\Big|\; \ell \in \{\text{en,ru,zh,es,de,ko,ja,fr}\},\; w \in \{30,90\}\ \text{days} \Big\}, \quad |\mathcal{O}| = 16 .$$

Each vector $q_{\ell,w}$ carries computed `after: as_of − w` and `before: as_of` ISO dates (from `dt.date.today()`; **no hardcoded year**). The English 30-day vector is verbatim:

```
"<metric> surpassed by" OR "beat <leader>" OR "new record" OR "defeated by" OR "outperformed <leader>" after:2026-10-07 before:2026-11-06
```

Seven translations preserve the *adversarial intent* (not the literal English words). `infer_leader()` extracts a named person from the prompt ("Hafþór Björnsson") and otherwise falls back to the honest label `"the current leader"` instead of fabricating an entity from an interrogative.

### 2.2 Adjudication state machine

`adjudicate_dethroning` classifies each dated passage $e$:

1. **Freshness gate:** $e.\text{date} \in [\text{as\_of}-w,\ \text{as\_of}]$. Unknown or stale dates contribute **zero** fresh checks — zero-lag is fail-closed, not assumed.
2. **Upset language:** a supersession phrase in one of 8 languages, with a **negation guard** ("no new record was ratified" is excluded).
3. **Corroboration:** a challenger proper name *or* a measured value $> L.\text{value}$.

$$
\text{status} =
\begin{cases}
\text{dethroned} & \exists\ \text{fresh } e:\ \text{upset}(e) \land (\text{challenger}(e) \lor v_e > v_L) \\
\text{intact} & \text{fresh checks} \ge 1 \land |\mathcal{V}_{\text{run}}| \ge 8 \land \neg\exists\ \text{upset} \\
\text{unverified} / \text{insufficient} & \text{otherwise}
\end{cases}
$$

Only `intact` is certifiable. `dethroned` forces the report to name `superseded_by`.

### 2.3 Rule B11 (verification-time)

A superlative in report prose requires `manifest.dethroning[]` with: `status ∈ {intact, dethroned}`, `vectors_run ≥ 8`, `window_days ∈ {30,90}`, `checked_at` ≤ 30 days old, `recency_verified = true`, and `evidence_ids` that passed verbatim SHA-256 snapshot verification. Failures include `B11 (Premature Search Termination)`, `B11 (Insufficient Dethroning Coverage)`, `B11 (Zero-Lag Window Violation)`, `B11 (Stale Dethroning Check)`, `B11 (Leader Superseded)`.

The 510 → 511 kg upset is now detected from a fresh multilingual eyewitness passage; a stale 2020 article cannot dethrone *or* certify.

---

## 3. Frontier 2 — Golden Nugget / Insider Anomaly Scorer

`insider_anomaly.py` declares **exact phrases**, not loose keywords. A corpus-wide "in production" is not a witness; "in production we saw" is. Inventory: 8 trench languages (EN/RU/ZH/ES/DE/KO/JA/FR) plus BG defensive extras, including every phrase in the mandate ("I was there", "на самом деле", "实测翻车", "en vivo vimos", "tatsächlich geschlagen", "실제로는", "実際の測定値", …).

Matching is `NFKC` → script-selective Latin diacritic folding → lowercase → whitespace-flexible regex, so `nuevo récord` ≡ `NUEVO   RECORD` ≡ `ＮＵＥＶＯ ＲＥＣＯＲＤ`. Shannon entropy over tokens is reported as a diagnostic but **never gates** the boost: a 3-sentence comment is precisely the target.

Ranking (`context_ranker.rank_passages`) is now:

$$
\text{score}(p,q) = \underbrace{\text{BM25}(p,q)\cdot\big(1 + 0.35\,d_p\big)}_{\text{bm25\_base\_score}} \times \Pi_p,\qquad
\Pi_p = \begin{cases}3.0 & p \text{ has an insider marker}\\ 1.0 & \text{otherwise}\end{cases}
$$

Additional mechanics: a bounded `0.05` prior-only floor admits a zero-lexical-overlap insider passage into the candidate set, and **one reserved slot per query** guarantees it reaches `context_pack.md` even when a high-BM25 press release occupies every normal slot. `trench_miner` writes `bm25_prior=x3.0`, `[INSIDER ANOMALY langs=…]` and `[GOLDEN NUGGET / INSIDER ANOMALY]` into the snapshot block, so the prior survives text re-parsing. Non-insider ranking is unchanged (all 322 legacy tests green).

---

## 4. Frontier 3 — Epistemic Alpha Delta (Rule R18)

Every v12 report must contain `## Epistemic Alpha Delta` with three subsections. Enforcement is mechanical:

| Check | Rule |
| :-- | :-- |
| Heading / all 3 subsections present, ≥ 40 chars, no `<placeholder>` / `TODO` / `…` | `R18 (… Missing)` / `R18 (EAD Placeholder)` |
| Trench cites ≥ 1 `[E###]` that passed verbatim snapshot verification | `R18 (Trench Alpha Uncited)` / `R18 (Unverified Trench Evidence)` |
| Trench cites an ID **not** cited by the consensus | `R18 (No Epistemic Delta)` |
| $J(\text{shingles}_3(\text{consensus}), \text{shingles}_3(\text{trench})) < 0.70$ | `R18 (Contrast Collapse)` |
| Delta Impact names a financial / operational / strategic loss **and** carries a number or `[E###]`/`[C###]` | `R18 (Delta Impact …)` |

`templates/report.md` gained the section (plus an Active Dethroning log table); `ingest` appends the EAD scaffold, a compliance checklist and the compiled `O_dethrone` query IDs to `context_pack.md`. `VerificationReport` gains `ead_diagnostics`, `dethroning_diagnostics`, `v12_protocol_active`; `cmd_verify` prints `v12=ON|legacy`, `EAD=PASS|n/a`, `O_dethrone_claims`.

---

## 5. Frontier 4 — Zero-fluff, protocol versioning and B0

- **Protocol versioning.** `auto_spec` emits `protocol_version: "12.0"`. `verify_study` applies R18+B11 to v12-declared studies (or `verify --strict-v12`). Pre-v12 studies stay on the v11 gate stack and receive `W_EAD_LEGACY_STUDY`. This preserves the 322-test invariant **without** allowing any new study to skip the alpha gate.
- **Fail-closed.** `ead_gate.run_v12_gates_fail_closed` wraps R18+B11; any exception becomes `B0 (v12 Gate Integrity / FAIL-CLOSED)`. Proven by mocking `validate_ead_section` to raise.
- **Transport totality.** `http_resilience` now handles `None`/int/bytes/empty/`javascript:` URLs, malformed IPv6 literals, malformed feed templates (`{query}/{bad}`), non-mapping headers, NaN/negative/unbounded numeric parameters, and unicode XML strings with an encoding declaration. Unsafe targets never contact third-party mirrors. Every outcome is a structured `FetchResult` with provenance; there is no `except: pass`.
- **Collector totality.** `trench_miner` coerces malformed prompts, GitHub queries and RSS templates and records every failure in `CollectorLedger`.

---

## 6. End-to-end CLI demonstration (`scratch/v12_e2e_demo.py`)

Reproducible offline run with a Spanish eyewitness disclosure of a 511 kg upset:

```
STEP 1  auto_spec.generate --offline
        WARN SUPERLATIVE CLAIM DETECTED (world_record, number_one):
             O_dethrone spawned 16 adversarial vectors over the most recent 30/90 days.
        protocol_version=12.0 | leader=the current leader | leader_value=510.0 kg | vectors=16

STEP 2  lean_engine.py ingest
        GOLDEN NUGGET in pack: True | EAD checklist: True | O_dethrone IDs: True

STEP 3  verify WITHOUT EAD  -> [FAIL] v12=ON | EAD=n/a
        FAIL R18 (Epistemic Alpha Delta Missing): report.md has no
             '## Epistemic Alpha Delta' section ...

STEP 4  verify WITH EAD + manifest.dethroning[]  -> [PASS]
        EI=85.7/100 | IDI=115.4 | MaxConf=High | v12=ON | EAD=PASS |
        O_dethrone_claims=2
        WARN W_EAD_PASS: contrast verified (Jaccard=0.0, trench evidence=['E002'])
```

The `W_B11_PARTIAL_COVERAGE` warning in step 4 is deliberate and visible: two distinct superlative kinds were detected but one dethroning record was declared. It is informational, not a bypass.

---

## 7. Honest limitations (not "omniscience")

1. **Keyless discovery is bounded by public endpoints.** Adversarial vectors execute against Algolia / RSS / public search caches. When all are bot-walled, `CollectorLedger` records the blackout and B11 returns `unverified` → **fail-closed**, never "no upset exists". Zero-lag means *no hardcoded recency lag and no stale certification*, not knowledge of an event no public source has published.
2. **Adjudication is lexical, not semantic.** Sarcasm, a quoted historical upset, or an upset stated without a number/named challenger may be missed. Mitigations: fresh-dated evidence only, 8-language phrase inventory, negation guard, and the requirement of corroboration. No LLM judgement was introduced (deliberate, to keep gates reproducible).
3. **EAD contrast is shingle-Jaccard.** A clever paraphrase could pass the 0.70 threshold; the independent structural requirement of a *novel, snapshot-verified* `[E###]` limits that bypass.
4. **`infer_leader` is Latin/Cyrillic-oriented.** CJK/Hangul proper names are not captured; the engine falls back to `"the current leader"` rather than guessing.
5. **The 3.0× prior is a fixed mandated constant**, not an empirically tuned weight. A passage *quoting* an insider phrase (e.g. in a quotation or a code sample inside a snapshot) could be over-promoted; snapshot provenance and verbatim quote verification are the downstream controls.
6. **Legacy studies are not retroactively gated.** Use `lean_engine.py verify --strict-v12` to force the gates on a pre-v12 folder.

---

## 8. Files changed / added

**New modules** (`dr_engine/tools/`): `insider_anomaly.py`, `dethrone.py`, `ead_gate.py`.
**Modified modules**: `auto_spec.py`, `trench_miner.py`, `context_ranker.py`, `lean_engine.py`, `http_resilience.py`.
**Templates**: `.agents/skills/deep-research/templates/report.md` (EAD section + dethroning log).
**Tests**: `tests/test_v12_golden_nugget.py` (36 offline adversarial tests).
**Docs**: `CHANGELOG.md`, `AGENTS.md` §v12.0, `.agents/skills/deep-research/SKILL.md` §11.
**Reproducible demo**: `scratch/v12_e2e_demo.py`.

### Verification commands

```bash
.venv/Scripts/python.exe dr_engine/tools/doctor.py
.venv/Scripts/python.exe -m unittest discover -s tests                 # 358 pass / 1 skip
.venv/Scripts/python.exe -m unittest tests.test_v12_golden_nugget -v  # 36 tests
.venv/Scripts/python.exe scratch/v12_e2e_demo.py                      # E2E gate demo
.venv/Scripts/python.exe dr_engine/tools/lean_engine.py verify --dir <study> --strict-v12
```
