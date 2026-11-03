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
