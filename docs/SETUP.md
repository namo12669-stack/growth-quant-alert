# Setup and troubleshooting

## Existing user: upgrade without a new bot

Upload the extracted V2 contents into the existing repository and replace the matching files.
The ZIP has no extra enclosing directory: `main.py` and `.github` are at its top level.
Your repository Actions secrets are settings, not source files, and need not be deleted or changed.

Check that these NEW items exist in the repository:

```text
quant_alert/app.py
quant_alert/single.py
quant_alert/relationships.py
tests_v2/
```

Check that these EXISTING files were REPLACED:

```text
main.py
config.yaml
universe.yaml
requirements.txt
requirements-dev.txt
pyproject.toml
scripts/restore_state.py
scripts/telegram_setup.py
.github/workflows/alerts.yml
.github/workflows/tests.yml
.github/workflows/telegram_setup.yml
```

Do not put `workflows` at root. Do not put `.github` under another project directory. Use the
actual default branch (often `main`), since scheduled runs use the default-branch version.
The display name of the primary workflow must be **Quant Signals V2**. If you still see only
**Growth Alerts**, inspect `.github/workflows/alerts.yml` before changing Telegram settings.

A plain-text copy, `WORKFLOW_COPY_FOR_GITHUB.txt`, is provided in case folder upload omits `.github`.
Paste it into a file with the exact path `.github/workflows/alerts.yml` through GitHub's editor.
The `.txt` helper at root is not itself an active workflow.

Go to Actions -> Quant Signals V2 -> Run workflow. Use `demo`, uncheck `dry_run`, run.
After the synthetic messages arrive, go BACK to the workflow's run list and start a NEW run:
`manual`, `dry_run` unchecked. "Re-run all jobs" on a demo run will run demo again.

## New Telegram setup only

Create a dedicated bot through the official `@BotFather` in Telegram using `/newbot`.
Open that bot's private chat and send `/start`. Store its token as `TELEGRAM_BOT_TOKEN` under:
Repository -> Settings -> Secrets and variables -> Actions -> New repository secret.

Run **Telegram Setup**. With exactly one private chat in the bot's pending updates and no
existing webhook, it sends the chat ID privately to that Telegram chat. Save that number as
`TELEGRAM_CHAT_ID`. The setup log intentionally does not print it. Shared bots or bots already
connected to another service are not automatically disconnected; use a dedicated bot instead.

Never paste a token into an issue, screenshot, repository file, ChatGPT conversation, or browser
URL. A URL containing a token can be retained in browser history. Revoke exposed tokens using BotFather.

## Common results

| Result | Meaning / next step |
|---|---|
| No workflow listed | Check the exact `.github/workflows/alerts.yml` path and default branch; check Actions is enabled |
| Demo arrives but manual does not | Confirm a NEW run was created, not a rerun of old demo; inspect failed job logs and secrets |
| `Price usable: 0/...` | Download `diagnostics.json` and `price_diagnostics.csv`; distinguish EMPTY, STALE, GAP, PRICE, LIQUIDITY conditions |
| Zero pairs pass | A legitimate result. Candidate relationships were not pre-approved. Inspect raw/adjusted p-values and holdout rejection reasons |
| No lead-lag preclose alert | Its next-session model is only actionable before that target session starts; partial daily data is not substituted |
| `ALREADY_SENT_EVENT` / `COOLDOWN` | Pattern exists but was already notified or is within the 48h cooldown |
| `INSUFFICIENT_SAME_CLOCK_HISTORY` | Not enough complete same-time historical intraday sessions for a valid RVOL comparison |
| `DAILY_SESSION_CHANGED_DURING_SCAN` | A slow manual scan crossed the daily data boundary; run again for the now-required session |
| `SKIPPED_LATE` | Workflow queue/runtime exceeded the before-open/before-close sending window |
| `FAILED_OR_PARTIAL_CHECK_TELEGRAM` | Delivery is not certain; inspect actual messages before retrying |

Changing statistical thresholds merely to force signals is not a repair for missing data.
A fundamental count of zero is not relevant to V2: those endpoints are intentionally not queried.

## Artifacts

Open Actions -> select a completed run -> scroll to **Artifacts** -> download
`quant-signals-v2-reports-...`. The entire diagnostic history for that run is there.
State is a separate artifact named `quant-signals-v2-state`. Download/back it up periodically;
GitHub artifacts expire and are not a permanent research database.

Reports are retained for 30 days and state artifacts for 90 days, subject to repository policy.
The newest state artifact includes the accumulated successful-alert journal. Losing all eligible
state artifacts resets deduplication/history; backup the latest state periodically.

The restore tool validates the workflow path, event type, default branch, and a strict file allowlist.
A restore API failure stops the run rather than silently restarting with empty history.
No personal access token or repository write permission is required.

## Configuration changes

`universe.yaml` defines the stock list, rough grouping, ETF proxies, and fixed candidate pairs.
Edit candidates deliberately before evaluation, not after seeing attractive p-values.
`config.yaml` defines thresholds and signal switches. Invalid minimum histories are rejected.
Changing the YAML does not itself change the workflow cron times; those live in `alerts.yml`.

If you intend to change just the number of Telegram messages, change `alerts.max_signals`.
If you intend to silence bearish divergence, change `alerts.allow_bearish` to `false`.
Neither change proves the remaining signals are profitable.
