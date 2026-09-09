# Quant Signals V2 - Growth Watchlist / Telegram

**Research-only signal detector. No broker connection, no orders, no claimed win probability.**

V2 replaces the V1 fundamental ranking flow with separate, inspectable signal engines.
It does **not** wait for Yahoo financial statements. It does **not** alert merely because
OKLO or another speculative stock has moved +/-4%.

## What it detects

| Family | Operational definition | Data / status |
|---|---|---|
| RSI divergence | Lower confirmed price low with higher RSI, or the bearish mirror; latest-close confirmation | Completed daily bars; waits 3 bars to confirm a pivot |
| Breakout + volume | Close above prior 20-session high, volume >=1.5x prior mean, close in upper part of range | Daily confirmed; 15m preclose variant is explicitly PROVISIONAL |
| Relative-strength breakout | Stock/proxy ratio above prior 63-session high, positive absolute return, >=3 percentage points of 20-session outperformance, above SMA50 | Completed daily bars; proxy is configured, not auto-verified |
| Pair spread | Frozen 252-session model, cointegration + stationarity screens, 63-session holdout stability, newly crossing 2 sigma, below 3.5 sigma | EXPERIMENTAL relative-value watch; not a buy call on either leg |
| Lead-lag | Today's leader return used to forecast next-session follower return, controlling for lagged follower and market returns; walk-forward validation and multiple-testing screens | EXPERIMENTAL one-session model; never inferred from same-day correlation alone |

Prior volatility compression is extra breakout context, not a sixth independent edge.
The complete formulas and caveats are in [docs/SIGNAL_RULES.md](docs/SIGNAL_RULES.md).

**HIGH/WATCH is a deterministic display priority, not calibrated confidence.**
No signal family has been validated for profitability on your live watchlist by this package.
The demo is deliberately constructed synthetic data, including a synthetic lead-lag process.

## Upgrade an existing V1.2 repository

Keep the same private GitHub repository and the same two Actions secrets:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

Unzip and upload the **contents**, with `main.py` at repository root. Replace the existing
`.github/workflows/alerts.yml`; its displayed name becomes **Quant Signals V2**.
Do not upload just the ZIP. Do not put an extra project folder around `main.py`.

Required layout:

```text
.github/workflows/alerts.yml
.github/workflows/telegram_setup.yml
.github/workflows/tests.yml
quant_alert/
scripts/
tests_v2/
main.py
config.yaml
universe.yaml
requirements.txt
requirements-dev.txt
pyproject.toml
```

If `.github` disappears during browser upload, open `WORKFLOW_COPY_FOR_GITHUB.txt`, copy its
contents, and use GitHub **Add file -> Create new file** with the exact filename
`.github/workflows/alerts.yml`. Replace an existing file through its edit button instead.
A root-level `workflows/alerts.yml` is not recognized by GitHub Actions.

V2 uses a NEW Python package (`quant_alert`) and a NEW state artifact
(`quant-signals-v2-state`). Old `growth_alert/` source, V1 reports, and V1 state are not used.
`tests_v2` is the only test directory invoked by the new workflow. Old unused code may be
removed later, but do not remove `.github` or your repository settings/secrets.
Disable any extra custom V1 scheduled workflows that you previously created, to avoid two
separate programs sending alerts. No SEC secret is required for V2; an existing one is ignored.

Detailed setup and troubleshooting: [docs/SETUP.md](docs/SETUP.md).
Thai quick start: [START_HERE_TH.md](START_HERE_TH.md).

## First run

1. Actions -> **Quant Signals V2** -> **Run workflow** -> `mode: demo`, `dry_run: false`.
2. Verify that Telegram says `DEMO - SYNTHETIC DATA - NOT LIVE` and `quant-signals-v2.0.0`.
3. Start a NEW run with `mode: manual`, `dry_run: false` for a live scan. Do not use
   **Re-run all jobs**, which reuses the old mode.

`dry_run: true` writes reports only and does not send messages or mutate alert history.
Demo mode never reads or changes live alert history, even when it sends a Telegram test.
A live scan may correctly produce zero new signals. The reports distinguish no pattern,
rejected models, bad data, expired prediction horizons, and deduplication.

## Default schedule

Schedules use `America/New_York`, plus an exchange-calendar check:

| Start | Meaning |
|---|---|
| 08:37 weekdays | Pre-open scan, 53 minutes before a normal open |
| 12:07 weekdays | Early-close check; skipped on normal full-session days |
| 15:07 weekdays | Pre-close scan, 53 minutes before a normal close |

Runs must start in the 65-to-10-minute window before the relevant session boundary. There is
a second check before sending. GitHub scheduling is best effort; queue delays or dropped
runs are possible. No realtime or second-accurate SLA is implied. Daily bars are only accepted
after the exchange session is complete plus a 20-minute finalization buffer.

Pre-open scans use **the last completed regular session**, not premarket quotes/news.
Preclose scans may add **completed 15-minute intraday breakout checks**, comparing cumulative
volume with the exact same elapsed-session time on prior days. They do not manufacture a
final daily close. Pair and divergence checks remain daily models.

## Reports and forward monitoring

Each run uploads a reports artifact containing:

- `telegram_preview.txt` and `summary.md`: readable messages and Actions summary.
- `signals.csv` / `signals.json`: detected signals, including those not selected for delivery.
- `diagnostics.json`: per-engine checks, price problems, and suppression reasons.
- `price_diagnostics.csv`: every symbol's latest session, liquidity, and exclusions.
- `relationships.csv`: every predeclared pair and every tested lead-lag direction, including failures.
- `inputs/`: consistently adjusted OHLCV input snapshots for inspection/reproduction.
- `installed_versions.txt`: actual dependencies installed on that GitHub runner.
- `evaluation/`: descriptive outcomes of earlier delivered alerts, when observations are available.

Successful sends are recorded in the separate `quant-signals-v2-state` artifact:
`state.json` and `journal.jsonl`. Forward evaluation uses that journal, not invented historical alerts.
The evaluation assumes a later session open, excludes transaction costs, and is **not a trading
backtest**. Missing future data stays pending. Overlapping alerts are not independent samples.

## Local execution

Use Python 3.12+ in a virtual environment. Export the two Telegram secrets to your shell for
non-dry-run sends. `.env` is an example only and is not loaded automatically.

```bash
python -m pip install -r requirements-dev.txt
python -m pytest tests_v2 -q
python main.py --mode demo --dry-run
python main.py --mode manual --dry-run
python main.py --mode manual
```

Offline CSV replay at a known timestamp, with **no Telegram delivery**:

```bash
python main.py --mode manual --dry-run --data-dir data_local --asof 2026-09-09T12:45:00+00:00
```

CSV format and validation details: [docs/VALIDATION.md](docs/VALIDATION.md).

## Important limitations

This is a **fixed seed watchlist**, not an all-market screener or verified current growth classification.
Peer pairs are test candidates only: no pair is assumed to be predictive or cointegrated.
Statistical p-value screens do not establish an economic edge or causation. Repeated testing
across time and user parameter tuning can still produce false discoveries.

Yahoo/yfinance is an unofficial, personal-research data route and may be throttled, delayed,
revised, or unavailable. Intraday bars can be incomplete. This code cannot bypass provider
restrictions and does not guarantee cloud-IP access. CSV input is an offline alternative,
not a live paid-feed fallback. Provider errors are exposed; stale data is never silently
promoted to a current signal. Official earnings, news, regulatory catalysts, dilution,
funding runway, and borrow availability are **not** independently verified.

[Research basis and exact distinctions from published papers](docs/RESEARCH.md).
[Security, state retention, and data-use considerations](SECURITY.md).
