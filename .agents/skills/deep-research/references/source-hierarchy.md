# Source tiers, claim kinds and conflict resolution

Every evidence record carries a **tier** (T1–T5) and a **kind** (`de_jure`, `de_facto`,
`empirical`, `context`). Authority depends on both: the T&C is the best source for what
the rule *says* and one of the worst for what the firm *does*.

## 1. Tiers

| Tier | What it is | Examples |
| :-- | :-- | :-- |
| **T1 — binding text** | The document that legally or contractually governs | Statute / regulation text, court judgment or docket, the current T&C / fee schedule / rulebook / help-centre rule page of the provider, exchange contract specs, official software docs and source code for the exact version |
| **T2 — official records & measured data** | Records kept by an authority, or data measured directly | Regulator register, warning list, enforcement release; company registry; filings and audited accounts; official statistics; tax-authority guidance (НАП); broker/exchange APIs and symbol specs; independent benchmark indices (Artificial Analysis, LMSYS / Chatbot Arena); your own logged data or backtest **with code and inputs in the workspace** |
| **T3 — peer-reviewed research** | Methodologically reviewed empirical work | Journal articles, systematic reviews / meta-analyses, conference papers with review, NBER / RePEc / official institutional working papers (unedited arXiv/SSRN preprints without journal publication count as T4) |
| **T4 — professional secondary & tertiary reference** | Edited journalism, named experts, preprints, encyclopedias | Financial press (Reuters, Bloomberg, FT, Capital.bg), law-firm or Big-4 briefings, recognised analysts, preprints, tertiary encyclopedias & retail explainers (Wikipedia, Investopedia, Britannica, BabyPips, CFI — **strictly T4 context only, never T1–T3**; enforced by gate E6) |
| **T5 — community & commercial** | Unedited or conflicted | Reddit, forums, Discord, Trustpilot, YouTube, Substack/Medium/personal blogs, unofficial/personal GitHub repos & wrappers, affiliate "review" sites, marketing pages making performance claims, LLM output (**strictly T5, never T1–T3**; enforced by gate E6) |

Independence: two records are independent only if they come from different authors /
organisations and neither copies the other or a common upstream (same press release, same
affiliate feed, same dataset). Reposts and syndicated copies count once.

## 2. Which tiers can establish which kind of claim

| Kind | Meaning | Ranked authority (left wins) | Cannot establish it alone |
| :-- | :-- | :-- | :-- |
| `de_jure` | What the rule / law / contract says | T1 > T2 > T4 | T3, T5 |
| `de_facto` | What actually happens: enforcement, payout behaviour, fills, slippage, processing times | T2 (enforcement records, court cases, own measurements) > T4 investigation > T5 *pattern* (§4) > T1 | T1 alone (a rule says what should happen) |
| `empirical` | A measured quantity / effect | T2 own data with code ≈ T3 > T4 > T5 | T5 |
| `context` | Background, definitions, history | any tier, prefer T1–T4 | — |

## 3. Confidence caps (apply mechanically)

| Confidence | Requires |
| :-- | :-- |
| **High** | `de_jure`: a T1 record. `de_facto`: T2, or a T5 pattern + T4 corroboration. `empirical`: T2/T3. And no unresolved same-kind conflict, and not resting only on a manual capture |
| **Medium** | One T2–T4 record, or T1 that is undated / older than 12 months, or a T5 pattern (§4), or a manual capture |
| **Low** | Single T4/T5 record, inference from indirect evidence, unresolved conflict |
| **Unverified** | Could not fetch or confirm. Say so; do not drop the caveat |

## 4. Community (T5) data: pattern threshold

A T5 `de_facto` claim ("this firm denies payouts for X") becomes a **credible pattern**
only if there are **≥ 3 independent reports**, each **specific** (date, amount or account
type, what was cited as the reason), with **≥ 2 from the last 12 months**. Below that it is
**anecdotal**: mention it only in Conflicts / Limitations, never in Key findings.
Affiliate review sites never count toward the threshold.

## 5. Conflict resolution algorithm

Run for every pair of records that disagree about the same subject:

1. **Different kinds → not a contradiction.** Report both and make the gap the finding:
   "The T&C says X [E4]; N independent traders report Y in practice [E9][E11][E12]."
   A rule-vs-practice gap is often the most decision-relevant result (hidden enforcement).
2. **Same kind, different tiers → higher tier wins** for the stated value. Put the
   lower-tier dissent in the Conflicts table.
   - Exception — **staleness check:** if the lower-tier source is dated > 90 days *after*
     the higher-tier source, the rule may have changed: re-fetch the primary
     (`evidence.py fetch --refresh`) and look for a version date / changelog. Current
     primary text still says X → X wins; it changed → the new version wins.
3. **Same kind, same tier:**
   - versions of the same document (T&C editions, statute amendments) → the newest
     version in force on the as-of date wins;
   - independent measurements/studies → report the range with each source; do not average
     unless methods are comparable (and say so); confidence ≤ Medium.
4. **Dated beats undated** at equal tier. An undated T1 page gets its fetch date and a
   note.
5. **Every conflict is written down** in the report's Conflicts table: claim, each side
   with evidence IDs, likely cause (date, definition, account type, jurisdiction, method),
   and which rule above decided it.

## 6. Domain notes

**Finance / prop firms / brokers** — rules, fees, commission → T1 page for the *specific
plan/account type*; check units (per side vs round turn, per lot vs per contract, point
value). Licences/warnings → regulator's own site: FCA register (register.fca.org.uk),
CySEC (cysec.gov.cy), ESMA (esma.europa.eu), IOSCO I-SCAN (iosco.org/i-scan), SEC EDGAR
(sec.gov/edgar), CFTC (cftc.gov), NFA BASIC (nfa.futures.org), FINRA BrokerCheck
(brokercheck.finra.org), КФН (fsc.bg), БНБ (bnb.bg). Company identity → official registry
(Търговски регистър portal.registryagency.bg; Companies House). Backtests → T2 only with
code + data in the workspace; report n, period, costs, and uncertainty; never
"guaranteed"/"proven".

**Tax / law (BG / EU)** — statute: Държавен вестник (dv.parliament.bg), parliament.bg,
EUR-Lex (eur-lex.europa.eu); consolidated portals (lex.bg, ciela.net) are T4 — confirm
article and version date. НАП guidance (nra.bg) is T2. Cite the article ("чл. 35 ЗДДФЛ")
and the URL; state the tax year; flag pending amendments. Treaties → minfin.bg text.

**Medicine** — systematic reviews / meta-analyses (Cochrane, PubMed filters) > RCTs >
observational; guidelines (WHO, EMA, FDA, NICE). Effect sizes with CIs; absolute vs
relative risk; preprints are T4.

**Science / ML** — peer-reviewed paper + official code; benchmark version, split, metric
and setup must match before numbers are compared; use OpenAlex citations to find
replications and critiques.

**Software** — docs for the exact version, changelogs, source, issue tracker, NVD
(nvd.nist.gov). Vendor benchmarks are T5 claims until independently reproduced.

**App-marketplace ratings** — Shopify's displayed overall rating is a weighted score, not the arithmetic mean of its star counts. Record the platform's definition and capture date; calculate any requested arithmetic average from the underlying counts. A lifetime star distribution does not establish the share of low ratings in the last 12 months: filter reviews by date and show the denominator. An install or review also does not establish that the merchant pays. Primary source: https://shopify.dev/docs/apps/launch/marketing/manage-app-reviews

### Product-research attribution traps (2026-11-04)

- App pages contain recommendations for OTHER products. Attribute price/count/rating using the product heading and structured SoftwareApplication record, never a nearby recommended-app card.
- A correctly reproduced competitor price does not establish paid conversion, future subscribers, CAC, processor approval or a calibrated success probability. Scenario weights without observed frequencies are assumptions, not expected-value evidence.
- Compare current fee schedules with dated announcements. Atlassian postponed its announced increases; the original May 2025 post is not sufficient for the November 2026 rate.
- Vendor legal disclaimers do not establish legality, regulated-provider status, liability immunity or payment-provider acceptance.
- A data-reporting fine is not interchangeable with a registration or system-participation fine. Preserve obligation-specific scope, dates and exemptions.
- Explicit Assumption:/Hypothetical:/?????????:/??????: units may use verified C calculations without irrelevant E citations. Their numbers still bind to the calculation, and calculation-only units enter the blind audit. Changing the calculation invalidates carried audit verdicts.
