# Research plan: <title>

- **As-of date:** YYYY-MM-DD
- **Question (precise):** …
- **Decision it serves (concrete action + capital/time at stake):** …
- **User's working thesis (what they hope is true — primary confirmation-bias hazard):** …
- **Mechanism hypothesis (counterparty physics / statutory / microstructure driver):** …
- **Constraints:** jurisdiction · time window · budget · technical context · languages
- **Assumptions made (instead of asking):** …
- **Search budget:** ≥ 12 searches total; ≥ 30% reserved for kill hypotheses (gate E4); ≥ 50% of logged evidence must be T1–T3 primary/peer-reviewed (gate E7).

## Sub-questions

| ID | Sub-question | Decision impact | Target source tier (T1–T3 preferred) | Status |
| :-- | :-- | :-- | :-- | :-- |
| SQ1 | … | … | T1 T&C / statute / spec | open |
| SQ2 | … | … | T2 regulator / official data | open |
| SQ3 | … | … | T3 peer-reviewed empirical | open |

## Kill hypotheses (written BEFORE searching; ≥ 3; gate E3)

Each is a concrete, falsifiable mechanism by which the thesis dies. Verdict ∈ `pending` → `confirmed` / `refuted` / `unresolved`.

| ID | Kill hypothesis (if true, the thesis fails) | Category | Kill threshold (what evidence counts as proof) | Verdict | Evidence |
| :-- | :-- | :-- | :-- | :-- | :-- |
| K1 | <a T&C clause / statute forbids or caps …> | contract / legal | verbatim clause in current T&C or statute | pending | |
| K2 | <regulator warning / enforcement / de_facto denial pattern …> | regulatory / practice | regulator register entry or ≥ 3 specific T5 reports | pending | |
| K3 | <frictions / slippage / taxes / drawdown lock make Net EV ≤ 0> | economics | `calc.py decision` Base or Regime-Weighted Net EV ≤ 0 | pending | |

## Quantitative & Decision Model (`calc.py`)

- **Key parameters to extract from T1–T3 sources:** gross payoff, upfront fee/cost, execution friction/slippage, haircut/split, tax rate, empirical win/survival rate (`n=...`).
- **Planned `[C###]` calculations:** Base / Bear / Stress Net EV + Breakeven Flip Thresholds ($p^*$, $C^*$) via `calc.py decision` and `calc.py eval`.

## Search log

Logged automatically via `discover.py --dir <dir> --purpose SQn|Kn` and `evidence.py log-search` into `searches.jsonl`.

## Load-bearing claims (for fresh-context adversarial verification)

1. …
