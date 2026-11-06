# <Title>

**As of:** YYYY-MM-DD · **Question:** <one line> · **Decision:** <what concrete choice this informs>

> Not professional advice (finance / tax / legal / medical topics). Verify with a licensed
> adviser for your specific facts and jurisdiction.

## Executive Decision Card

- **Verdict:** <GO / CONDITIONAL GO / NO-GO / HOLD>
- **Overall Confidence:** <High | Medium | Low> *(must not exceed `formula.py` mechanical ceiling — gate R10)*
- **Net Economics (Base / Bear / Stress):** <Base Net EV> / <Bear Net EV> / <Stress Net EV> [E001, C001, C002, C003]
- **Flip / Invalidation Trigger:** <exact threshold where verdict flips, e.g. win rate $p^* < \dots$ or fee $C^* > \dots$> [E001, C005]
- **Immediate Next Steps:**
  1. <concrete action 1 with verification step>
  2. <concrete action 2 / pre-commitment stop rule>

## Bottom line

<2–5 sentences: the direct answer, the operational recommendation, and why alternatives lose.
Every number, date, fee, clause, or statistic carries [E###] (and [C###] if computed).>

## Epistemic Alpha Delta

> Mandatory for every v12.0 study (Rule R18). A report that merely repeats the
> first search-engine answer has **zero epistemic alpha**. The trench ground-truth
> must cite a snapshot-verified `[E###]` that the consensus section does NOT cite,
> and the two bodies must be genuinely different (shingle-Jaccard < 0.70).

### Superficial Consensus

<What a 5-second generic search or a standard LLM answers today: name the stale
leader, the published record, the vendor claim or the "standard consensus". State
it plainly so the delta is measurable.>

### Trench Ground-Truth (The Alpha)

<What our multilingual trench miners / O_dethrone / immutable snapshots actually
proved: the silent breaking change, the 511 kg upset reported by an eyewitness,
the unreleased flash preview, the undisclosed fee. Cite `[E###]` verbatim here —
at least one evidence ID not used above.>

### Delta Impact

<Why acting on the superficial consensus would have caused a financial,
operational or strategic loss. Quantify it with a measured number, `[E###]` or
`[C###]`: e.g. "settling at 510 kg would have mispriced a 250000 USD sponsorship
and cost the operator a full production incident [E007, C001]".>

### Active Dethroning Log (Rule B11, only when a superlative is asserted)

| Leader | Metric | 30/90-day vectors run | Status | Checked at | Evidence |
| :-- | :-- | :-- | :-- | :-- | :-- |
| <leader> | <metric> | >= 8 | intact / dethroned | YYYY-MM-DD | [E###] |

<Mirror this record into `manifest.dethroning[]`: `status`, `vectors_run`,
`window_days` (30 or 90), `checked_at`, `recency_verified`, `evidence_ids`.
If O_dethrone found an upset, name `superseded_by` in prose and above.>

## Key findings

| # | Finding | Kind & Tier | Confidence | Evidence |
| :-- | :-- | :-- | :-- | :-- |
| 1 | <specific claim whose numbers appear in cited quotes or [C###]> | `de_jure` T1 | High | [E001] |
| 2 | <measured / derived economic result> | `empirical` T2 | Medium | [E003, C001] |

## Mechanism & Counterparty Physics

<Explain *why* the rule, edge, tax treatment, or technical bottleneck behaves this way:
counterparty revenue model (A-book vs B-book / simulation fees), statutory intent, market
microstructure, or physical constraint. Cite primary sources [E###].>

## Decision & Sensitivity Matrix

<paste output of: `python dr_engine/tools/calc.py decision --dir research/<dir> ...`>

## Analysis

### SQ1 — <sub-question>

<Prose citing [E###] in every claim-bearing sentence. Never weaken a claim to dodge a missing
quote — fetch the primary source (`evidence.py fetch`) or register the math (`calc.py eval`).>

- Verified quantitative derivation: <statement citing both inputs and calculation> [E003, E005, C002].
- Inference: <qualitative judgment drawn from the evidence above — NO unbound numbers allowed in `Inference:` / `Извод:` (gate R3)> [E003, E005].

## Kill hypotheses

| ID | Kill hypothesis | Verdict | Evidence | Effect on decision |
| :-- | :-- | :-- | :-- | :-- |
| K1 | … | confirmed / refuted / unresolved | [E010] | … |
| K2 | … | confirmed / refuted / unresolved | [E011] | … |
| K3 | … | confirmed / refuted / unresolved | [E012, C004] | … |

## Conflicts (`de_jure` vs `de_facto`)

<One row per conflict from `claims.py conflicts` (gate R11): cite evidence from BOTH sides and name the
axis (scope / time / method / unit / authority / rule_vs_practice). A conflict with no explaining axis
is investigated or marked "unresolved".>

| Subject | Rule / Side A | Practice / Side B | Axis · Kinds / Tiers | Resolution rule (hierarchy §5) | Operational outcome |
| :-- | :-- | :-- | :-- | :-- | :-- |
| … | … [E002] | … [E011] | rule_vs_practice · `de_jure` T1 vs `de_facto` T5 pattern | 1 — rule vs practice gap | price both into Stress case |

## What would change this conclusion

- <observable metric / clause change / threshold $x^*$> → <exact alternative action>.

## Confidence

<State overall confidence (must match or sit below `formula.py` mechanical ceiling) and identify
which specific sub-question carries the widest residual uncertainty.>

## Limitations

- Unresolved sub-questions / kill hypotheses, manual captures (`via=manual`), jurisdiction or sample boundaries.

## Sources

<paste output of: `python dr_engine/tools/evidence.py sources --dir research/<dir> --report research/<dir>/report.md`>

## Verification

<paste output of: `python dr_engine/tools/formula.py research/<dir> --markdown`>

Claim audit: <paste output of: `python dr_engine/tools/audit.py bound --dir research/<dir>`>
(judged n, errors found and fixed in earlier rounds, upper bound on the unsupported-claim rate at 95%).

```text
<paste output of: python dr_engine/tools/gate.py research/<dir> --live 5 --scorecard --require-audit>
```
