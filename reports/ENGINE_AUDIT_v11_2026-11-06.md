# Deep Research Engine v11.0 — Unfair Epistemic Dominance

**Date:** 2026-11-06 · **Workspace:** `DR project` · **Status:** COMPLETE, VERIFIED
**Baseline:** 275 tests pass / 1 skip, exit 0 · **Final:** **322 pass / 1 skip, exit 0** (3.8–5.5 s)
**Selftests:** 14/14 modules PASS · **Epistemic evals:** 32/32 (100%) · **doctor.py:** `RESULT: READY`

---

## 1. Executive conclusion

v11.0 resolves **all four residual limitations** documented in
`reports/ENGINE_AUDIT_v10_2026-11-06.md` §6. The engine now recovers bot-walled
practitioner sources without keys, models correlated tail risk instead of
independent noise, arbitrates theoretical-vs-production contradictions instead
of averaging them, and mechanically rejects academic fluff.

Two deliberate non-goals, stated up front:

* **Mirror recovery is not primary evidence.** The live coverage target is met
  (100% endpoint coverage), but 2 of 11 recoveries were search-cache leads and
  9/11 were primary fetches. The engine reports both numbers separately and
  downgrades every mirror body in `sources/index.jsonl`.
* **Correlation is declared, not estimated.** The Cholesky matrix and regime
  shifts are explicit, reproducible assumptions printed on the Decision Card.
  They are sensitivity measurements, not forecasts and not subjective weights.

---

## 2. Frontier 1 — Keyless censorship & bot-wall evasion

### Specification
Deterministic ordered chain after direct fetch fails:

| # | Path | Endpoint | Fidelity |
|---|---|---|---|
| 1 | Memento | `archive.org/wayback/available` → closest 200 snapshot | `archival_copy` |
| 2 | Wayback CDX | `web.archive.org/cdx/search/cdx` (newest distinct 200, raw `id_`) | `archival_copy` |
| 3 | Syndication | FxTwitter (`api.fxtwitter.com`), PullPush deleted-comment archive, Redlib mirrors | `syndicated_transcription` |
| 4 | Search mirage | DuckDuckGo Lite HTML + SearXNG public instances | `search_snippet` (LEADS ONLY) |

`C = recovered / attempted`, target ≥ 0.95. Each result carries `via`,
`evidence_class`, `source_url`, `sha256` and a complete `fallback_chain`.
`DR_DISABLE_MIRRORS=1` forces direct-only; calling the function is the consent.

### Measured result (live, 2026-11-06)
```
v10.0 baseline            81.8% endpoint coverage (2 failures, 1 bot wall)
v11.0 live               11/11 endpoints = 100.0% coverage, meets_95pct_target=True
                         2 mirror rescues (search_cache)
                         9/11 = 81.8% PRIMARY-source coverage
                         2 lead-only cache recoveries
```
The distinction is **mechanical** (`primary_coverage_pct`,
`lead_only_recoveries`), not a narrative caveat. A search snippet can never
become a quoted `[E###]`: `cmd_ingest` writes `secondary_transcription: true`
and `verify_study` emits `W_SECONDARY_TRANSCRIPTION` requiring a primary
re-fetch before citation.

### Adversarial coverage
47 offline tests simulate: a 403 bot wall, Memento recovery, CDX newest-capture
selection (3 timestamps out of order), FxTwitter JSON, PullPush deleted-comment
filtering, Redlib fallback, DDG/SearXNG cache, a full 5-path chain, env-disabled
mirrors, and a 95.0% vs 90.0% coverage boundary.

---

## 3. Frontier 2 — Correlated Monte Carlo & regime-aware stress

### Mathematics
* **Cholesky:** `L[i][j] = (Σ[i][j] − Σₖ<ⱼ L[i][k]L[j][k]) / L[j][j]`,
  `L[i][i] = √(Σ[i][i] − Σₖ L[i][k]²)`; verified `L Lᵀ = Σ` to 1e-9.
* **Indefinite declared matrices** are not silently accepted: deterministic
  diagonal jitter → **shrinkage toward identity** `Σ_λ = (1−λ)Σ + λI`, with the
  repair type and λ returned in `cholesky_info`. `jitter=False` refuses.
* **Joint shocks:** `z_c = L·z + μ_r`, clamped ±3σ; `xᵢ = x̄ᵢ(1 + σᵢ·z_c,ᵢ)`.
* **Tail risk (empirical, no distribution assumption):** for gain `Y`,
  `VaR₉₉ = −Q₀.₀₁(Y)`, `CVaR₉₉ = −E[Y | Y ≤ Q₀.₀₁(Y)]`; `CVaR ≥ VaR` is
  asserted. Negative VaR means even the 1% worst case is still a gain.

### Declared regimes (no probability weight — Rule B1 intact)
| Regime | Joint shock | Group ρ | σ multiplier |
|---|---|---|---|
| Liquidity Crunch | spread/slippage/fees ↑1.6σ, volume/liquidity ↓1.2σ, volatility ↑1.3σ | 0.85 | 1.8 |
| High-Inflation Squeeze | rates/inflation/costs ↑1.4σ, margins ↓1.0σ | 0.75 | 1.5 |
| Latency Breakdown | latency/timeouts/queues ↑1.8σ, throughput ↓1.4σ | 0.80 | 1.7 |

Longest-pattern-first matching prevents generic `vol` from swallowing specific
`volume`. Default `compute_monte_carlo()` (independent σ=10%) is preserved
byte-for-byte, so every v10 Decision Card remains reproducible.

### Deliverable
Two new Decision Card panels: **Correlated Regime Stress & Empirical Tail Risk**
(inline CDN-free SVG with VaR/CVaR markers + shaded loss tail, baseline vs
stress VaR/CVaR, `P(loss)`, tail n) and **Declared Macro Stress Regimes** (per-
regime metric values, ρ, σ multiplier, shocked input names).

---

## 4. Frontier 3 — Rule B10, Dialectical Reconciliation Matrix

**Conflict predicate:** ∃ `de_jure` (T1/T2, `supports`) ∧ ∃ `de_facto`
(T3–T5, `contradicts`/failure `proves`) on the **same subject**. Differently
scoped subjects are not conflated — reproducing the scope-distortion error the
blind audit exists to catch would be unacceptable.

**Three hard prohibitions:**
1. Averaging / pooling / "on balance" language near the conflict, or a
   DerSimonian-Laird pooled estimate on the conflicting subject →
   `B10 (Forbidden Averaging)`.
2. No `manifest.dialectics` reconciliation entry →
   `B10 (Unreconciled De Jure/De Facto Conflict)`.
3. No unique dominant axis → `B10 (Unclassified Dialectical Delta)`. The engine
   refuses to guess.

**Axes:** `implementation_drag` (engineering/latency/ops),
`undisclosed_microstructure_friction` (spread/fees/queue/fill),
`regulatory_enforcement_asymmetry` (enforcement/discretion/practice).
Classification scores de_facto quotes 3×, de_jure quotes 1×, local prose 1×;
structured `manifest.dialectics[].axis` overrides.

**Confidence cap:** a classified but unverified conflict sets
`confidence_cap = "Medium"`; `verify_study` downgrades `High → Medium` and emits
`W_B10_CONFIDENCE_CAP` **without changing EI** — process metrics measure rigour,
not truth. `verification.status == "verified"` lifts the cap. The complete
matrix is stored on `VerificationReport.dialectical_arbitration`.

All B10 exceptions are caught by the fail-closed wrapper and become B0 hard
failures. The module is `dialectical_arbitration.py`, deliberately **separate**
from the pre-existing v5.0 `dialectics.py` claim-ledger CLI (unchanged).

---

## 5. Frontier 4 — Rule R17, Anti-Fluff Information Density Gate

| Check | Threshold | v10 behaviour |
|---|---|---|
| `IDI = (1000/W)·(2E + 5M + 8F)` | **≥ 100 enforced** | computed, never enforced |
| `D = 100·(2E + 5M + U_bound)/W` | **≥ 3.0 / 100 words** | absent |
| Hard boilerplate (1 hit) | reject | absent |
| Soft boilerplate (≥2 distinct) | reject | absent |

Hard phrases: `paves the way`, `a multifaceted approach`, `delve into`,
`testament to`, `unlock the full potential`, `game-changer`, `in today's
fast-paced world`, `a paradigm shift`, `navigate the complexities`,
`the ever-evolving landscape`, `it is worth noting that`, `a nuanced
understanding`. Soft cluster phrases include `in conclusion`,
`it is important to remember`, `overall`, `further research is needed`, ….
Fenced code and display math are stripped before measurement, so a code sample
cannot be counted as prose or smuggle boilerplate.

`VerificationReport` gains `empirical_density_per_100w` and `boilerplate_hits`;
`cmd_verify` prints Density and the B10 conflict count. Every rejection names
the exact offending phrases and the measured numbers — no LLM judgement.

---

## 6. Verification evidence

```
doctor.py                             RESULT: READY
unittest discover -s tests            Ran 322 tests — OK (skipped=1), exit 0
tests/test_v11_dominance.py           47 / 47 PASS (0.112 s, fully mocked)
tests/test_v10_hardening.py           42 / 42 PASS (regression)
tests/test_report_tools.py            4 v10 gate tests PASS (CI-visible)
module selftests                      14 / 14 PASS
epistemic evals                       32 / 32 PASS (0 false positives/negatives)
lean_engine selftest                  EI=93.8, IDI=101.1, MaxConf=High, N_eff=3.0
full pipeline                         verify PASS (EI=61.3) → decision_card.html 28 638 chars
live trench mining                    100% endpoint / 81.8% primary coverage
```

The adversarial suite explicitly simulates: 403/429/200 responses, CDX out-of-
order timestamps, deleted PullPush comments, DDG blocked → SearXNG fallback,
env-disabled mirrors, an indefinite correlation matrix, longest-pattern name
collisions, `CVaR ≥ VaR`, a negative VaR, de_jure/de_facto averaging, an
unclassified delta, an unverified-evidence-ID injection, a verified cap lift,
`High → Medium` confidence downgrade, IDI < 100, word-padded density collapse,
and boilerplate inside fenced code.

---

## 7. Residual limitations (stated honestly, v11.0)

1. **Lead-only recoveries are not primary evidence.** 100% endpoint coverage
   does not mean 100% primary-source coverage. The engine reports both; a study
   whose only Reddit evidence is a search snippet must re-fetch a primary page
   or mark the claim unresolved. This is a feature, not a gap.
2. **Public mirrors are third parties.** Only the URL is sent, mirroring the
   existing `DR_ALLOW_JINA` consent model, but Wayback/DDG uptime, CDX rate
   limits and Redlib instance churn are outside our control. `DR_DISABLE_MIRRORS=1`
   restores direct-only behaviour deterministically.
3. **Correlation is declared, not estimated.** No historical covariance matrix
   is inferred from data. A reviewer can reject the declared ρ; it is printed in
   full. σ=10% remains a fixed sensitivity assumption, not measured volatility.
4. **Regime mean shifts are lexical.** They map variable *names* to shock
   families. A model with opaque input names (`x1`, `x2`) will receive zero
   regime shift; the card reports `shocked_inputs: none`. Explicit `correlation`
   and `sigma_by_input` specs are available for that case.
5. **B10 axis classification is lexical, not semantic.** Ambiguous deltas are
   refused (`unclassified`) rather than guessed; the structured
   `manifest.dialectics[].axis` is the authoritative override. The blind claim
   audit (R12) remains the human-in-the-loop control for entailment.
6. **R17 is a density heuristic, not a truth detector.** A dense but wrong
   report still passes R17; it fails only the binding/filter/audit gates. R14
   (Zero-Truncation Policy) still forbids padding or compressing a report to
   satisfy a gate.
7. **`benchmark_radar.py`'s bundled table remains an unverified offline seed**
   (v10 finding A5). It is explicitly flagged and excluded from B9 grounding;
   a live `fetch` is still required before citing a leaderboard.

---

## 8. Files changed

**New modules:** `dr_engine/tools/{risk_engine,density_gate,dialectical_arbitration}.py`
**Extended:** `http_resilience.py` (4-path fallback + coverage benchmark),
`trench_miner.py` (mirror rescue + coverage split), `decision_card.py`
(correlated MC, regimes, VaR/CVaR SVG), `lean_engine.py` (B10 cap, R17 gate,
secondary-source downgrade, index provenance), `v9_bullshit_filters.py`
(B10 entry point), `epistemic_guard.py` (B10 inside the fail-closed wrapper).
**Unchanged / preserved:** `dialectics.py` (v5.0 CLI), all 275 legacy tests,
the v10 independent-σ Monte Carlo default.

**Docs:** `CHANGELOG.md`, `AGENTS.md` §v11.0,
`.agents/skills/deep-research/SKILL.md` §10.
**Tests:** `tests/test_v11_dominance.py` (47 new offline adversarial tests).
**Deliverable:** this report.
