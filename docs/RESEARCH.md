# Research and implementation sources

These are sources for concepts and APIs, NOT proof that the exact V2 rules are profitable.
The project does not reproduce published portfolios, claim their returns, or assert that any
configured present-day ticker pair is valid. Research descriptions below refer to the source
abstracts/documentation consulted; no claim is made to have replicated the full studies.

## Technical pattern recognition

Lo, Mamaysky and Wang (2000), *Foundations of Technical Analysis: Computational Algorithms,
Statistical Inference, and Empirical Implementation*.
https://www.nber.org/papers/w7613

The paper supports defining chart patterns algorithmically and evaluating conditional outcomes
rather than relying only on visual labels. Its pattern-recognition method is not V2's RSI-pivot
algorithm. It does not establish profitability for the exact divergence/breakout thresholds here.

## Relative-value pairs

Gatev, Goetzmann and Rouwenhorst, *Pairs Trading: Performance of a Relative Value Arbitrage Rule*,
NBER working paper 1999; published version 2006.
https://www.nber.org/papers/w7032

The paper's matching rule uses distance in normalized historical price space. V2 instead uses
an Engle-Granger/frozen-spread screening approach with a holdout. Thus it is conceptually related,
not a replication, and the original returns must not be transferred to this package.

## Lead-lag versus same-time correlation

Lo and MacKinlay, *When Are Contrarian Profits Due to Stock Market Overreaction?*, working paper
1989; published version 1990.
https://www.nber.org/papers/w2977

Cross-autocovariances and lead-lag relations motivate testing chronological dependencies.
They do not establish a current NVDA -> MRVL or OKLO -> SMR effect. V2 uses a predeclared
one-session return regression and held-out prediction checks, not a causality claim.

## Statistical implementation

Statsmodels augmented Engle-Granger cointegration test:
https://www.statsmodels.org/stable/generated/statsmodels.tsa.stattools.coint.html

The null is NO cointegration; the method assumes I(1) inputs. High return correlation is not
a substitute for testing spread behavior. Finite-sample and time-series specification risks remain.

Statsmodels multiple-testing implementation:
https://www.statsmodels.org/stable/generated/statsmodels.stats.multitest.multipletests.html

V2 defaults to Benjamini-Yekutieli (`fdr_by`) across the configured candidate family within one
scan. This does not cover unlimited rescanning, subjective universe selection, parameter search,
or misspecified p-values. Holdouts and multiple-testing adjustments reduce some failure modes,
but cannot establish a usable economic edge by themselves.

## Operational sources

GitHub workflow syntax, location, scheduling and timezone:
https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax

GitHub scheduled-event behavior and queue-delay limitations:
https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows

GitHub secrets:
https://docs.github.com/en/actions/security-for-github-actions/security-guides/using-secrets-in-github-actions

Telegram Bot API:
https://core.telegram.org/bots/api

Yfinance download API, multi-index shape, adjustment parameters and intraday constraints:
https://ranaroussi.github.io/yfinance/reference/api/yfinance.download.html

Yfinance status and data-use disclaimer:
https://ranaroussi.github.io/yfinance/

Exchange-calendar library:
https://github.com/gerrymanoim/exchange_calendars

Consult provider licensing before redistributing market data. Keep this personal research
repository and its artifacts private. API availability and third-party service terms can change.
