# Research basis and boundaries

This project turns broad research themes into a transparent **forward-observation prototype**.
It is not a replication package or a verified profitable strategy. None of the cited studies
validates this seed list, current weights, free-data fields, Telegram timing, thresholds or
transaction-cost assumptions. References were checked against primary publisher/institution
pages; no third-party ranking website is used as evidence for the scoring model.

## R1 - Financial analysis of growth stocks

Mohanram, Partha S. (2005). *Separating Winners from Losers among Low Book-to-Market Stocks
Using Financial Statement Analysis*. Review of Accounting Studies 10, 133-170.

Primary author/institution record:
https://business.columbia.edu/faculty/research/separating-winners-losers-among-low-book-market-stocks-using-financial-statement

The study motivates combining profitability, cash-flow information, growth stability and
investment information when examining low-book-to-market firms. This project does **not**
compute the original eight-point G_SCORE, and revenue-growth-filtered stocks are not the same
universe as low-book-to-market firms. The prototype omits original R&D/advertising/capex scores.

## R2 - Gross profitability

Novy-Marx, Robert (2013). *The Other Side of Value: The Gross Profitability Premium*.
Journal of Financial Economics 108(1), 1-28. Earlier NBER Working Paper 15940 (2010).

Primary NBER record:
https://www.nber.org/papers/w15940

Gross profits relative to assets motivate one profitability feature. The implemented latest
quarter-matched asset denominator and rolling four-quarter income numerator are practical
choices; do not call them an exact published-portfolio replication. The paper does not certify
that any individual high-profitability growth stock will outperform.

## R3 - Price momentum

Jegadeesh, Narasimhan, and Sheridan Titman (1993). *Returns to Buying Winners and Selling
Losers: Implications for Stock Market Efficiency*. Journal of Finance 48(1), 65-91.

Primary publisher issue record:
https://afajof.org/issue/volume-48-issue-1/

Intermediate-horizon momentum motivates a separate price family. Our 12-1 convention,
52-week-high ratio and continuity heuristic are implementation choices, not a claim that all
three independently replicate the study. Do not infer a next-hour edge from a months-horizon
research finding. Plain benchmark-subtracted return ranks are not counted again as independent
relative-strength ranks.

## R4 - Earnings information versus past returns

Chan, Louis K. C., Narasimhan Jegadeesh, and Josef Lakonishok (1996). *Momentum Strategies*.
Journal of Finance 51(5), 1681-1713. DOI: 10.1111/j.1540-6261.1996.tb05222.x.

Primary publisher issue record:
https://afajof.org/issue/volume-51-issue-5/

The paper provides motivation for distinguishing price momentum from earnings information
and analysts' forecast response. Our two Yahoo EPS revision fields are limited proxies; actual
EPS/revenue surprises, pre-release consensus and fiscal-year alignment are not implemented.
A current `+1y` snapshot is not a historical point-in-time analyst database. Fiscal-period
rollover can confound a change comparison; every such observation is flagged as unverified.

## Why several attractive ideas were not added as scores

High R&D, high capex, large volume, negative P/E or an AI-generated news interpretation are not
automatically beneficial. The code does not award a standalone permanent growth-quality score
for those narratives. Volume is a time-specific alert trigger. FCF/assets and margin changes are
explicitly named practical proxies rather than being mislabelled as exact cash-based-operating-
profitability research measures.

## Required validation before claiming an edge

The shipped tests check arithmetic and operations, not alpha. A future evaluation should
pre-register a target horizon, retain the complete contemporaneous eligible universe and
exclusions, compare to simple growth and momentum baselines, use chronological train/test
splits, assess incremental value with ablation, control correlated features and repeated tests,
and examine sector concentration, liquidity and extreme winners. Test multiple market regimes.

Use only data known at each decision time. Fiscal period end is not filing-publication time.
Yahoo statements can be restated, the seed list is selected now, and the snapshot service does
not establish historical information availability. Therefore, **do not pass today's fundamental
snapshots into old price history and call the result a valid historical backtest**.

The journal starts preserving what this installation observed going forward. For 20/60/120-
session diagnostics, define a common post-alert observation price rule before analysis, use
matching benchmark observations, account for overlapping labels and repeated alerts, and
include delisted/unavailable outcomes instead of silently dropping them. This evaluation engine
is not included. There is no claimed CAGR, Sharpe, hit rate or expected excess return.

The scalar score is a research-priority rank, never a calibrated probability of a gain.
