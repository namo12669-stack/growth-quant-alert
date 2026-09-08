# Factor registry - implementation 1.0

All weights below are **unvalidated starting hypotheses**, not estimated optimal weights.
Academic papers motivate factor families, not this exact set of formulas, windows,
filters, growth seed list or intraday alert conditions. References R1-R4 are in RESEARCH.md.

## Scored features (13)

| Family; weight | Feature | Implemented formula | Internal weight | Status |
|---|---|---|---:|---|
| Growth; 25% | revenue_yoy | Latest quarterly revenue / same quarter one year ago - 1 | 45% | Growth-quality hypothesis; R1 motivation |
| Growth | revenue_per_share_yoy | (Revenue / basic average shares) latest / year-ago - 1; diluted average shares fallback | 35% | Per-share growth proxy, not a paper replication |
| Growth | revenue_acceleration | Latest quarterly YoY growth minus preceding quarter's YoY growth | 20% | Research hypothesis; missing without enough comparable quarters |
| Quality; 25% | gross_profit_assets | Four consecutive quarterly gross profits / latest matching total assets | 30% | R2-inspired; denominator differs from some academic implementations |
| Quality | cfo_assets | Four consecutive quarterly operating cash flows / latest matching total assets | 25% | Cash-flow proxy; NOT exact cash-based operating profitability |
| Quality | operating_margin_change | Operating income / revenue latest minus same-quarter year-ago margin | 25% | Improvement proxy, usable for loss-making firms |
| Quality | fcf_margin | (TTM operating cash flow - absolute TTM capex) / TTM revenue | 20% | Practical proxy; not standardized across all industries |
| Expectations; 20% | eps_revision_30d | (Next-year current consensus EPS - 30daysAgo EPS) / abs(30daysAgo EPS) | 70% | R4-inspired snapshot; fiscal-period rollover NOT independently verified |
| Expectations | revision_breadth_30d | (Up revisions - down revisions) / (up + down); zero if both observed as zero | 30% | Analyst-revision count proxy, not unique analyst breadth |
| Momentum; 20% | momentum_12_1 | Adjusted close t-21 / adjusted close t-252 - 1 | 60% | R3-motivated 12-to-1 convention; not a full replication |
| Momentum | near_52w_high | Last completed-session close / maximum daily high over trailing 252 observations | 25% | Price-position heuristic; minimum 200 observations |
| Momentum | path_continuity | Sign(12-1 return) x (fraction of positive days - fraction negative) in that window | 15% | Experimental path proxy; not an independent proven edge |
| Valuation; 10% | sales_to_ev | TTM sales / current provider enterprise value | 100% | Within-sector cheapness proxy; NOT growth-adjusted valuation |

Higher is the configured preferred direction for all features. Positive EV and matching
USD financial/quote currencies are required for sales_to_ev. Earnings revisions require
current EPS > 0 and prior consensus EPS >= $0.10; negative/near-zero bases are missing.
Observed zero revisions means no recorded directional change, not proof of analyst unanimity.

The quarterly reader finds the prior-year comparable date within 15 days, so 52/53-week
fiscal calendars can be handled without assuming exact calendar-quarter dates. Four-quarter
TTM requires successive intervals of 65-115 days and an endpoint within 15 days. Restatements,
mergers, split-adjusted share comparability and vendor accounting mappings still require review.

## Ranking / missing data

1. Apply price, dollar-volume, market-cap, currency, statement-age and growth filters.
2. Exclude Financial Services and Real Estate by default. Block very short proxy cash runway.
3. Require at least 8 eligible peers for a rank. Speculative names are not peers.
4. For each feature, use at least 5 valid sector peers; otherwise use all valid growth peers.
   Valuation has no all-universe fallback. The scope is written to snapshot.json.
5. Percentile = 100 x (average ascending tied rank - 1) / (N - 1).
   Equal observations all score 50. Missing data / too few peers score neutral 50.
6. Compute family weighted averages, then the five-family weighted average.
7. Coverage = sum of effective weights for usable observations. Do NOT renormalize to the
   available features. Final score = max(0, raw score - 12 x (1 - coverage)).
8. Coverage below 60% excludes a candidate. Excluded candidates have score null, not a fake rank.

Neutral imputation can still help a genuinely poor missing feature relative to observing its
bad value; it is not a statistical cure. Coverage and the underlying missingness must be audited.
Group comparisons use sector, not a full industry/lifecycle adjustment. Profitable and scaling
firms share this prototype's core pool; only the explicit speculative list is fully separated.

## Unscored risk/context variables

Median daily close x volume over 20 completed sessions (liquidity); market cap; raw price;
statement age; share-count YoY change; 60-session annualized return volatility; current
drawdown from 252-session adjusted-close high; approximate cash runway; negative FCF;
net cash; daily/5-minute timestamps; QQQ relative to its 200-day average.

Cash runway proxy = matching cash and near-cash / (-TTM FCF / 4), only when FCF < 0.
This is not available credit, restricted-cash analysis, debt-maturity analysis, financing
forecast, or a going-concern opinion. A value below 4 quarters blocks core alerts by default.

## Alert selection separate from rank

Score >= 70, adequate coverage, and a new qualifying candidate / score improvement of at
least 5 / newly appearing price trigger / periodic re-review after 5 calendar days.
Maximum 5 core names and 2 per sector. Alert recurrence is separately tracked for each mode.

Premarket trigger: fresh completed 5m-bar move >= +2%, or <= -4% as a risk-review label.
Preclose trigger: return >= +1.5% and same-time RVOL >= 1.5x, or a quote at/above the prior
52-week high. These thresholds are engineering hypotheses, not estimates from the cited papers.

RVOL uses cumulative completed bars from 04:00 NY (premarket) or regular open (regular),
through the most recent completed bar start. The denominator is the median same-clock-time
volume from up to 20 prior sessions, with at least 5 acceptable days. At least 90% of expected
5m intervals must be present, and early closes missing the needed interval are excluded.
This may suppress RVOL for thin extended-hours trading; suppression is preferable to fabrication.

No fresh intraday data: a new high-scoring research candidate may still be reported with
PRIOR CLOSE ONLY, but no gap/RVOL price confirmation is claimed. A recent bar is not a
licensed real-time quote or executable price.

## Not implemented

Actual-versus-pre-announcement revenue/EPS surprises; guidance changes; verified fiscal-year
consensus histories; historical point-in-time universes; original full G_SCORE; news catalysts;
AI sentiment; short interest; options flow; insider activity; bid-ask spread; audited financing
announcements; lifecycle-specific scoring; original cash-based profitability specification;
sector/beta-residual momentum; backtest, target prices, stops, position sizing or order execution.

These omissions are deliberate and must not be represented as implemented features.
