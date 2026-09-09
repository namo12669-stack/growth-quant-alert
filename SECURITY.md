# Security and operational scope

This program reads public market data and sends research messages to your configured Telegram
chat. It does not request broker credentials, place orders, or automatically change repository settings.
It requires no SEC secret and no personal access token. The GitHub-provided token is used read-only
for retrieving previous state artifacts.

Keep `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` only in repository Actions secrets or private
local environment variables. Never commit them. The code deliberately avoids echoing token-bearing
Telegram URLs and does not blindly retry uncertain sendMessage network timeouts.

Use a dedicated bot and private repository. Artifact data includes your watchlist, selected events,
input snapshots and model diagnostics; raw public price data can still have redistribution restrictions.
Downloaded state artifacts are treated as untrusted: fixed allowlist, path-traversal checks,
size limit, and workflow/default-branch checks before restoration.

Telegram delivery and GitHub artifact persistence are separate systems. Exactly-once delivery is
not guaranteed under partial sends, unknown timeout outcomes, canceled workflows, artifact expiry,
or manual deletion of state. Acknowledged sends are journaled individually. Check Telegram before
retrying a failed/uncertain run.

Workflows serialize V2 scans, use read-only permissions and bounded job timeouts, and do not expose
secrets to pull-request test jobs. Action dependencies use maintained major versions; Python
requirements are bounded and actual runner versions are recorded. Review dependency updates before
merging. This project is not a security-audited application.

The builder could execute offline tests, not live Yahoo/Telegram calls or a real GitHub workflow.
No bot was connected and no repository was modified as part of preparing this downloadable package.
