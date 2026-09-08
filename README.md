# Growth Quant Alert

**Research-oriented US growth-stock alerts for GitHub Actions and Telegram. No broker, no orders, no automatic trading.**

**Thai setup guide: [START_HERE_TH.md](START_HERE_TH.md)**

Version 1.0 | 8 September 2026 | Research hypothesis, not a validated alpha model.

## What this project actually does

Scans an editable 40-name seed universe, applies price/liquidity/growth/data-quality filters, computes 13 transparent factors, and sends up to 5 new or changed research candidates. A separate 3-name speculative watchlist gets price-movement notices without a quant score. The seed list is not an exhaustive market universe, a current listing certification, or an investment recommendation.

Default scoring families: growth 25%, profitability/cash quality 25%, expectations 20%, momentum 20%, valuation 10%. Weights differ slightly from the conceptual research proposal to reflect this free-data implementation. They have not been optimized or backtested. Exact feature definitions, peer pools and proxy limitations are documented in [docs/FACTOR_REGISTRY.md](docs/FACTOR_REGISTRY.md).

This implementation includes a replaceable Yahoo/yfinance adapter, not SEC extraction, paid consensus feeds, news sentiment, revenue/earnings-surprise verification, event calendars, broker connectivity or a historical point-in-time backtest. EPS revisions are provisional Yahoo snapshots with an unverified fiscal-year-rollover limitation. Cash-flow metrics are practical proxies, not exact replications of every research paper.

## Setup in seven steps

1. Create a NEW Telegram bot using the official `@BotFather` and `/newbot`. Send `/start` to your new bot in a private chat.
2. Create a **private** GitHub repository and upload the CONTENTS of the extracted project. `main.py` and `.github/` must be at repository root. Do not upload only the ZIP or put the whole project inside another directory.
3. Open repository **Settings > Secrets and variables > Actions > New repository secret**. Save `TELEGRAM_BOT_TOKEN`.
4. Open **Actions > Telegram Setup > Run workflow**. The helper sends your chat ID privately to your Telegram. It refuses shared/private-chat ambiguity and existing webhooks.
5. Save the received value as a second repository secret, `TELEGRAM_CHAT_ID`.
6. Open **Actions > Growth Alerts > Run workflow**. Choose `mode: demo`, leaving `dry_run` unchecked. You should receive a clearly labelled **SYNTHETIC DATA - NOT LIVE** message. Demo is not a live-data test and never changes production alert history.
7. Run again with `mode: manual` for a live scan. Check the workflow run, Telegram and report artifacts. Schedule entries are already included; scheduled workflows must be on your default branch.

If `.github/` did not upload through your browser, create `.github/workflows/alerts.yml`, `telegram_setup.yml`, and `tests.yml` with **Add file > Create new file**, copying the corresponding contents. GitHub Desktop is another way to preserve all dot-folders.

No GitHub or Telegram account has been connected by the delivered files. You must complete setup yourself. Do not send bot tokens to other people or commit them. Rotate exposed tokens with BotFather.

## Schedule and delivery boundaries

The workflow is written for **GitHub.com**, with `timezone: America/New_York`:

| NY start time | Purpose |
|---|---|
| 08:37, weekdays | Pre-open scan |
| 12:07, weekdays | Early-close scan; ordinary full sessions skip it |
| 15:07, weekdays | Ordinary pre-close scan; early-close sessions skip it |

Calendar gate: event is 10-75 minutes away. Scheduled scans therefore start about 53 minutes before a normal open/close; actual delivery depends on queueing and data retrieval. No polling every five minutes. At most two scheduled candidate reports per trading day under normal state operation.

`exchange_calendars` XNYS handles supported holidays, DST and half days. Unexpected exchange closures may require an updated package; it is not a live halt service. The runner rechecks the event window before sending and refuses a late candidate report. GitHub scheduling is best-effort, can be delayed/dropped, and is not a real-time trading timer. Public repository schedules can be disabled after inactivity. Check Actions quotas, billing and storage for your account.

`display_timezone: Asia/Bangkok` changes the message display only. Change to `Asia/Singapore` if appropriate; New York scheduling is unchanged.

## Commands

Use Python 3.12 or 3.13. From the repository root:

```bash
python -m pip install -r requirements.txt
python main.py --mode demo --dry-run
python main.py --mode manual --dry-run
python main.py --mode auto
```

For local sending, set `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` in your process environment. `.env.example` is documentation; this project deliberately does not auto-load `.env`. Do not put secrets into shell commands that will be committed or published.

`auto` observes the calendar/window and per-session deduplication. `manual` runs now and labels the message MANUAL. `demo` uses only synthetic fixtures, although sending still contacts Telegram unless `--dry-run` is used. Dry-run never sends Telegram or changes alert history; a live dry-run may refresh the fundamental cache.

## Reports and state

Each live/demo scan writes `output/ranking.csv`, `snapshot.json`, `telegram_preview.txt` and `summary.md`. GitHub also records installed package versions. Detailed JSON contains raw factor values, normalized factor scores, coverage, ranking scopes, exclusions, quote timestamps and limitations.

State includes recent confirmed sessions, previous alerts, a forward-observation journal and the most recent cached statements. It is passed between runs using an Actions artifact named `growth-alert-state`, not commits to the repository. Permissions are `contents: read` and `actions: read`; no repository write token is needed. Only the matching default-branch alert workflow's artifact is restored. Restore failures stop the workflow rather than silently restarting empty.

Reports default to 30-day retention; state to 90 days subject to account policies. **Artifacts are not a permanent database.** Back up `journal.jsonl` periodically. After inactivity, expiration or deletion, the history can restart and old candidates may be treated as new. The state restore safety limit is 100 MB uncompressed; archive older journal data before that point.

The workflow serializes runs; the application records a session after Telegram confirms all chunks. This is not an exactly-once messaging guarantee. An ambiguous timeout, partial multi-message delivery, or state upload failure can create missed/duplicate notifications. Connection failures are not blindly retried for `sendMessage`; explicit 429 rate limits are retried. No token-bearing URLs are logged.

## Reading scores responsibly

A score is a relative research ranking in the eligible seed universe, not a probability, fair value, target price or a buy instruction. Missing factors receive neutral 50, stay at their original weight, reduce weighted coverage, and incur an additional penalty. Missing data is not represented as evidence of strong fundamentals. This method does not mathematically eliminate every possible missing-data advantage; coverage floors and inspection remain important.

Most factors use sector peers when at least five valid peers exist; otherwise they disclose a growth-universe fallback. Valuation never falls back across sectors. The default data-success gate withholds candidate alerts if fewer than 70% of requested core names have a current completed-session price and a statement observation. A minimum eight-name eligible peer pool is required. It is normal for a tiny custom list to yield no ranked candidates.

Daily features exclude the current unfinished regular session. Intraday alerts use only completed five-minute bars, with age checked again at send time. Same-time RVOL compares cumulative volume at the same New York clock time against historical sessions; missing-bar coverage and half days are checked. A recent bar timestamp still does not guarantee an exchange-real-time price. No fresh bar means **PRIOR CLOSE ONLY**, not a made-up premarket move.

Cash-runway-under-four-quarters is a blocking heuristic; dilution, negative FCF, large drawdowns and volatility are flags. None of these constitutes complete financial due diligence. Speculative tickers never enter the core rank pool.

## Troubleshooting

| Symptom | What to check |
|---|---|
| No Actions workflows | `.github/workflows/` is missing, nested, or not on the default branch |
| Telegram Setup finds no chat | Send a fresh `/start` to the NEW bot, then rerun; do not run another bot poller |
| Telegram 401 | Incorrect/revoked BotFather token |
| Telegram 400/403 | Wrong chat ID, bot not started/blocked, or chat permissions |
| Setup sees webhook/multiple private chats | Use a separate bot; the helper deliberately does not disconnect another service |
| Manual live scan shows no candidates | Inspect `exclusions`, `coverage`, seed pool size and data errors; do not assume the code failed |
| Many provider failures | Yahoo may block/throttle cloud IPs. Reduce the seed list cautiously or replace the provider adapter |
| No intraday price | Extended-hours data may be missing or too old; prior-close-only is intentional |
| No automatic message | Holiday, late/skipped queue, disabled schedule, quota limit, expired secret or failed run |
| Duplicate candidates after long inactivity | State artifact may have expired; check the fresh-state warning |
| State restore permission failure | Keep `actions: read` and repository Actions/artifact access enabled |

## Testing and research

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

See [docs/VALIDATION.md](docs/VALIDATION.md) for the actual delivered test results and remaining live checks, and [docs/RESEARCH.md](docs/RESEARCH.md) for primary references and the distinction between academic evidence and implementation hypotheses.

The initial environment could not reach package/data endpoints. Offline logic tests and synthetic runs were executed, but the Yahoo adapter, dependency installation on a fresh GitHub runner and Telegram delivery were NOT exercised end-to-end. The provided CI runs the tests on GitHub; Demo then Manual are your acceptance checks.

## Operational references

- GitHub scheduling syntax: https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#onschedule
- GitHub schedule caveats: https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule
- Repository secrets: https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-secrets
- Telegram BotFather: https://core.telegram.org/bots/features#botfather
- Telegram Bot API: https://core.telegram.org/bots/api
- yfinance documentation and data-use disclaimer: https://ranaroussi.github.io/yfinance/
- Exchange calendar library: https://github.com/gerrymanoim/exchange_calendars

Yahoo/yfinance is unofficial and intended for research/personal use subject to the provider's terms. Keep data artifacts private and verify redistribution rights independently. Software license does not grant market-data rights.
