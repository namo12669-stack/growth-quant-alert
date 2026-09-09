# Validation status and reproduction

## What was actually run for this release

The build environment ran **97 offline tests**, all passing, plus a complete deterministic
`python main.py --mode demo --dry-run` pipeline. The demo produced 5 signal messages from
6 usable synthetic stocks. This is NOT a statement about live market performance.

The synthetic processes were deliberately constructed: a sharp then slower selloff for RSI
divergence, a volume-confirmed breakout, a stationary residual around a common stochastic trend,
and an explicitly lagged return-generating process. A fixed seed was selected for the pair unit
fixture to exercise the passing branch of its screens. None of this is an empirical stock backtest.

`TEST_RESULTS.txt` contains the actual test-run output. `BUILD_ENVIRONMENT.json` records the
libraries present in the offline environment. The code was exercised on Python 3.13.5 in that
environment. The included GitHub CI workflow targets Python 3.12 and will rerun tests there;
this package has not been executed on your actual GitHub repository by the builder.

Live Yahoo/Telegram network testing was **not possible** in the build environment. A dependency
installation/network attempt failed because DNS/network access was unavailable. yfinance and
curl_cffi were therefore not installed for the build tests; provider interface tests used a stub,
and the full data pipeline used synthetic or local CSV data. No live price availability, Telegram
delivery, or API-performance claim follows from these offline tests. Your first live manual
GitHub run is the integration check with your existing bot secrets and real upstream data.

## Test coverage

- Wilder RSI seed/edge cases; strict pivots; no pivot detection before right-side confirmation.
- Bullish and bearish divergence; confirmation age; breakout volume and close-position conditions.
- Relative-strength alignment and missing/stale benchmark rejection.
- Market holiday, daylight-saving, early-close and daily-finalization timing.
- Future/partial daily-bar exclusion; invalid OHLC; missing sessions; recent split guard.
- Same-clock intraday RVOL; incomplete bar exclusion; missing slots; stale/timezone-naive input.
- Cointegration held-out screening; frozen formation parameters; missing/degenerate pair rejection.
- Family multiple-testing adjustment, including failed/unavailable hypotheses.
- True chronological lead-lag simulation; no automatic reverse-direction assumption; benchmark dependence.
- Changing the latest leader observation affects only the future forecast, not its fitted training coefficient.
- No lead-lag publication after the target session has started; delivery timestamps used in the journal.
- Stable event IDs, cooldowns, per-run duplication, old/corrupt state rejection, safe artifact extraction.
- Telegram response simulation, rate-limit handling, redacted credentials and uncertain-send timeout behavior.
- Demo isolation, zero-price behavior, workflow/config structure and multiple yfinance column layouts.
- Pending forward outcomes, and never selecting an evaluation entry price from before an alert.

These tests verify software behavior, not alpha, calibration, execution quality, or future returns.

## Reproduce offline

```bash
python -m pip install -r requirements-dev.txt
python -m pytest tests_v2 -q
python main.py --mode demo --dry-run
```

A network connection is required to install missing packages, but not to run the tests/demo
once dependencies are present. Test mode does not require or send Telegram secrets.

## CSV data contract

Daily files: `SYMBOL_daily.csv` with Date, Open, High, Low, Close, Volume and optional Stock Splits.
Use consistently split/dividend-adjusted OHLC data for the whole history. Do not mix raw close
with adjusted high/low. Intraday files: `SYMBOL_15m.csv` with the same OHLCV fields. Each intraday
Date is the BAR START and must carry an explicit UTC Z or numeric timezone offset. Naive intraday
times are rejected rather than silently interpreted in the wrong zone.

To replay a downloaded snapshot without contacting Yahoo or sending Telegram:

```bash
python main.py --mode manual --dry-run --data-dir data_local --asof 2026-09-09T12:45:00+00:00
```

Use the same universe/config and include all required benchmark files. --asof is allowed only
with CSV input and --dry-run. A historical replay cannot accidentally send old events as live alerts.

## Forward monitoring

After live alerts accumulate, the workflow runs `scripts/evaluate_alerts.py` against the restored
successful-send journal and current input snapshots. Download `evaluation/forward_outcomes.csv`
and `evaluation/summary.json` from the reports artifact. No future data is fabricated; events with
insufficient data remain pending. The first run naturally has little or no measurable outcome data.

Manual equivalent:

```bash
python scripts/evaluate_alerts.py --journal state_v2/journal.jsonl --prices output/inputs
```

This is a descriptive prospective event study. Entry is the first regular-session open strictly
after the observed delivery time, or that day's upcoming open for preopen alerts. It excludes
fees, bid/ask spread, slippage, overnight fill uncertainty, borrow/funding cost, delisting effects,
and portfolio construction. Pair spread units are not comparable to unhedged equity returns.
Close-to-close lead-lag point forecasts have a different target from next-open entry proxies.
Do not call the fraction of positive observations a calibrated future win probability.

## Before claiming an edge

Freeze the universe/rules before examining results. Accumulate genuinely unseen observations,
compare against suitable simple baselines, inspect failures and adverse excursions, control
multiple experiments across time/configurations, and evaluate costs and capacity. The code's
statistical gates and academic references are not substitutes for that process. No profitability
result is bundled with V2, and no paper's historical returns are copied into its messages.
