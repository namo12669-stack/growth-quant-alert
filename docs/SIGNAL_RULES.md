# Signal definitions and chronology

All thresholds below are starting hypotheses configured in `config.yaml`. They have NOT been
optimized or validated for profits on this watchlist. Detecting a pattern is not proving an edge.

## Input and quality gates

Yahoo is requested with `auto_adjust=True`. Daily OHLC values and return relationships therefore
use the provider's adjustment basis, not executable bid/ask quotes. Snapshots retain that basis.
Volumes are provider volumes; the dollar-volume screen is an adjusted-close turnover proxy.
Symbols are assumed to be US-listed, USD-quoted stocks in the editable seed list. There is no
metadata endpoint that verifies a user-added foreign symbol's currency or current listing status.

Daily requirements: at least 100 bars; exact last completed exchange-session date; >=98% of
expected sessions in the last 120-session window; valid OHLC ordering; nonnegative volume;
price >=$5; average close*volume over 20 sessions >=$10 million. Recent reported splits cause
a five-session review exclusion. This is NOT a complete corporate-action risk system.

The overall price gate requires at least half the stock universe and at least three stocks
(or all stocks when the universe is smaller). Benchmark data must also be fresh, but a missing
benchmark only disables the engines that need it. Fundamentals are not fetched and do not gate signals.

No forward fill is used. Pair/lead-lag formation additionally requires a contiguous exchange-session
history with exact timestamp alignment. Missing history is an explicit rejected hypothesis.

## 1. Confirmed RSI divergence

RSI(14) uses Wilder smoothing, initialized with the mean of the first 14 gains/losses.
A price swing is a strict local low/high compared with 3 bars to its left and 3 to its right.
Ties are not swings. **The detector cannot know the swing until the three right-hand bars close.**

Choose the latest confirmed pivot, then the nearest earlier confirmed pivot 5-45 sessions away.
A bullish candidate requires:

- Second low <= first low * 0.995.
- RSI at second price low >= RSI at first price low + 5 points.
- At least one of the two RSI readings <=40.
- Latest close above the second pivot's close and above the preceding close.
- No later low touches/breaks the second price low.
- Confirmation is no more than 2 sessions old.

The bearish mirror requires price highs up >=0.5%, RSI down >=5 points, at least one RSI >=60,
a lower latest close, and no later breach of the second high. Bearish alerts are warnings, not
short-selling instructions. `allow_bearish: false` disables them.

RSI is sampled at the **price pivot dates**; the algorithm does not separately choose favorable
oscillator pivots. The alert logs both pivot prices/RSIs and the later confirmation date. It is
never backdated to the low/high date. The displayed review level is not a stop-loss order.

## 2. Breakout + volume

Completed daily bar:

```text
level = max(High[t-20 : t-1])
RVOL = Volume[t] / mean(Volume[t-20 : t-1])
range_position = (Close[t] - Low[t]) / (High[t] - Low[t])
```

Require close > level * 1.001, RVOL >=1.5, and range_position >=0.70. The current bar never
enters its own breakout threshold or volume denominator. Zero-range bars get neutral position 0.5.

Compression context is based on 14-session average true range / close at t-1, ranked against
the prior 120 observations. A bottom-20% observation adds context; it does not independently
validate the breakout and is not used as another numeric "confidence" vote.

### Intraday variant

Only regular-session 15-minute bars whose **end time is <= analysis time** are included. Yahoo
bar timestamps are interpreted as bar starts. At least 60 minutes of completed bars are required.
The latest complete bar may be no older than 25 minutes, checked again before publication.

Current cumulative volume is divided by the median cumulative volume to the **same elapsed-session
cutoff** over up to 20 prior sessions. At least eight comparable sessions are required. Every
15-minute slot from open to cutoff must exist. Short days without enough elapsed time and gappy
days are excluded, not treated as zero-volume observations.

Require latest bar close > prior 20 completed-session high * 1.001, same-clock RVOL >=1.5,
current session range position >=0.75, and close above an approximate session VWAP. That VWAP
is volume-weighted (high+low+close)/3 over 15m bars, **not tick-level VWAP**.

The alert is PROVISIONAL: the daily session is unfinished and may reverse. It is not a daily
close confirmation. No premarket gap or premarket RVOL engine is included in V2.

## 3. Relative-strength breakout

The benchmark is a configured ETF/proxy, not a discovered causal driver or necessarily a precise
industry classification. After timestamp alignment:

```text
ratio[t] = stock_adjusted_close[t] / proxy_adjusted_close[t]
excess20 = stock_return_20_sessions - proxy_return_20_sessions
```

Require ratio > prior 63-session maximum; excess20 >=3 percentage points; positive stock
20-session return; stock close above its 50-session moving average. This is a ratio breakout
condition, not giving a second score to the identical cross-sectional momentum ranking.

## 4. Frozen-formation pair spread (EXPERIMENTAL)

The **order** of each candidate pair in universe.yaml is fixed. We do not try both cointegration
orientations and pick the better p-value. Candidate pairs are hypotheses, not approved hedges.

Use 252 formation sessions, followed by 63 holdout sessions, followed by ONE current observation.
Fit the formation regression:

```text
log(A) = alpha + beta*log(B) + residual
Z[t] = (log(A[t]) - alpha - beta*log(B[t]) - formation_residual_mean)
       / formation_residual_sample_std
```

Formation alpha, beta, mean and standard deviation are frozen for the holdout and current bar.
The current dislocation cannot pull its own regression or Z baseline toward itself.

Screens: positive reasonable beta 0.1-5; non-degenerate spread; level ADF p>=0.05 for both log
prices and difference ADF p<=0.05; augmented Engle-Granger p-value adjusted over the full configured
candidate family <=0.05. Failure to reject a unit root is a **screen**, not proof that a series is I(1).

Estimate AR(1) residual persistence phi in formation. Require 0<phi<1 and discrete half-life
`-ln(2)/ln(phi)` between 2 and 45 sessions. Reject unstable holdouts: residual ADF p>0.10,
beta drift >35%, residual standard deviation outside 0.5-2.0x formation, or mean drift >1 sigma.
These are heuristics, not guaranteed structural-break detection.

Alert only on a new crossing: abs(previous Z)<2 and 2<=abs(current Z)<=3.5. A value beyond 3.5
is withheld rather than promoted as an even better bargain. If Z<0, A is relatively low; if Z>0,
B is relatively low under the fitted relationship. **Neither statement predicts that the low leg
will rise in absolute terms.** No hedge, financing, borrow, stop, or execution engine exists.

## 5. One-session lead-lag (EXPERIMENTAL)

Both directions of every predeclared candidate pair are tested. Only one lag is tested; there
is no automatic search over dozens of lag lengths. With log returns:

```text
Baseline: follower_return[t] = a + b1*follower_return[t-1] + b2*market_return[t-1] + error
Full:     same baseline + b3*leader_return[t-1]
```

Initialize with 252 training observations. On each of 63 subsequent validation observations,
fit on **earlier observations only**, predict that next observation, then expand training.
Compare full-model squared errors against the baseline on the exact same held-out dates.

Require >=2% relative reduction in out-of-sample MSE, >=0.10 correlation between the full model's
incremental prediction and the baseline residual, positive leader coefficients on >=80% of
walk-forward fits, and positive final leader coefficient. The final coefficient uses a HAC
covariance estimate (5 lags), and its two-sided p-value is corrected over all configured directions.
The current feature vector is rejected if any standardized component exceeds 5 in absolute value.

Then require the latest completed-session leader return >=2%, full model's next-session
plug-in return estimate >=0.5%, and increment over baseline >=0.3 percentage points.
`expm1(predicted log return)` is a plug-in point estimate, not a fully specified arithmetic
conditional expectation or a confidence interval. Validation RMSE is shown separately.

The latest leader return is used ONLY as a feature for the future target session, not to fit
its own still-unknown outcome. The alert is sent only before the target session opens; this is
checked again before publication. V2 intentionally does not substitute partial intraday returns
into a model trained on completed daily returns. Therefore preclose may show no lead-lag alerts.

There is no statement that NVDA actually leads MRVL, or that OKLO and SMR are cointegrated.
Those are candidate relationships to test; rejections are retained in relationships.csv.

## Multiple testing and what remains unproven

Default correction is Benjamini-Yekutieli (`fdr_by`) separately across the pair family and the
lead-lag-direction family. Unavailable/rejected hypotheses remain in the family with p=1 where
no valid test could be computed. BY is designed for dependence under valid marginal p-values;
it does not make misspecified financial time-series p-values exact.

The adjustment does **not** cover repeated daily scanning, choosing a universe after seeing
results, trying many configurations, all possible model specifications, or nonstationarity.
A passed screen is an experimental candidate, NOT a confirmed economic edge or causal relationship.
No paper cited by this project proves that these exact rule combinations work today.

## Selection, delivery, and evaluation

HIGH is assigned to breakout+volume signals; other families are WATCH. This is display priority,
not probability. Default limits: 8 signals per run, 2 per ticker, 48-hour same-kind/direction/pair
cooldown, plus a stable event fingerprint. New intraday and next-day confirmed daily breakouts
have distinct identities. There is no rule forcing a minimum number of alerts.

Only acknowledged Telegram sends are journaled with delivery-time timestamps. Exact-once delivery
cannot be guaranteed across Telegram and GitHub artifacts, especially after timeouts or canceled runs.
Forward evaluation uses delivered events, not retrospective pivot dates. Preopen observations use
that upcoming open; intraday/postclose observations use the next session open. Outcomes at 1/5/20
sessions are descriptive proxies, not realized trades. Pair outcomes are directional frozen
log-spread changes, not portfolio returns. Lead-lag close-to-close forecasts are a different target
from next-open entry-return proxies. No overlapping-event independence or transaction-cost claim
is made. Missing outcomes stay pending and small samples are labeled.
