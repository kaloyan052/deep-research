# Prop-firm and trading research: pitfalls seen in real reports (Claude, 2026-10-28)

These come from auditing 14 deep-research reports (RP01–RP14, 2026-10-27/28) against firm pages and our own engine. Read this before any study on prop firms, trading strategies, brokers or trading taxes.

## Probability and statistics
1. **A conditional probability is not a correlation.** "P(firm B fails | firm A fails) = 0.94" must not be plugged into a correlation formula: no N_eff = 1/(1+(N−1)ρ) and no multivariate Kelly with ρ = 0.94. When the stake is a fixed fee (limited liability), expected values add across accounts whatever the dependence. Dependence changes the spread of outcomes and the timing, not the sum of EVs.
2. **Ruin of independent attempts (q^N) does not apply** when every attempt trades the same edge. If the edge is zero, all attempts fail together. Model a shared edge drawn from a posterior.
3. **t > 5 from a simple rule on daily or intraday data is a bug until shown otherwise.** Look for lookahead, duplicated rows, a wrong time zone or a bar timestamp convention. Report lag-0 / lag-1 / lag-2 results.
4. **A filter is judged by the difference between the trades it keeps and the trades it drops**, not by the t of the kept subset.
5. **Power:** state how many trades the claimed edge needs for t = 2 (≈ (2σ/μ)²). A few live trades prove mechanics and cost, never edge.
6. **Published anomalies decay** (McLean & Pontiff 2016). Require post-publication evidence: post-sample data, a replication, live tracking.

## Firm rules
7. **Rules come from the firm's own plan page, T&C, help centre or a written support answer**, quoted verbatim with the date read. Review sites (PropFirmMatch, TheGodFunded, Lune, LuxAlgo, FXEmpire) summarise, often wrongly or out of date. Use them only as leads. Example: one review said BrightFunded's 15% reward is "paid before funding"; the help centre says it joins the next funded balance after 10% of payouts.
8. **The same firm sells several products with different rules** (1-Step / 2-Step / Instant / "Bright" / "Classic"). Always name the product and the account size.
9. **FAQ and T&C can disagree** (e.g. The5ers 4% / 8% on the plan table vs 5% / 10% in an FAQ). Report both, with dates. The contract (T&C) and the plan table outrank an FAQ.
10. **"Sole discretion", "trade idea", "one-sided bet", "account rolling", "consistency", "best day", "news window", "copy trading", "third-party EA"**: grep the full T&C for each before concluding that a strategy is allowed.
11. **Sessions vs calendar days:** 14 calendar days ≈ 10 trading sessions. Payout timers count from the first trade, not from funding, at several firms. Say which.
12. **Promotions change prices weekly.** Quote the code, the price, the date and whether it applies to add-ons.

## Evidence hygiene
13. **Anecdotes** (Reddit, Trustpilot, Discord, YouTube) are labelled ANECDOTE and counted as a distribution (n, quartiles), never as rules.
14. **Do not advise detection evasion** (jitter, VPS hopping or comment stripping to defeat similarity filters). It breaks firm terms and exposes the account.
15. **Tax:** quote the statute (ZDDFL / ZDDS article and paragraph) and НАП practice. A December→January payout shift does not defer Art. 29 tax: the quarterly advance falls due by 30 April of the same year.
