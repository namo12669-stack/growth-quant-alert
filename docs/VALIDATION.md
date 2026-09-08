# Delivered validation record

Date: 8 September 2026

## Executed in the authoring environment

- `python -m pytest -q`: **60 passed**.
- Synthetic end-to-end application smoke run: **dry_run**, 16 synthetic inputs, 4 selected
  under the score and sector-cap rules, output JSON/CSV/text generated.
- Python source compilation: passed.
- Workflow YAML parsing, New York timezone settings, and read-only permissions: checked in tests.
- ZIP structure and checksums: checked at packaging.

Tests cover supported market holidays, weekends, summer/winter DST offsets, early closes,
late-window suppression, prior completed trading sessions, exclusion of unfinished daily
and five-minute bars, comparable-period revenue growth, dilution, margin improvement,
TTM interval checks, no fabrication from missing quarterly data, negative/near-zero EPS
bases, currency mismatch, percentile ties, weight sums, neutral missing-data treatment,
coverage penalties, insufficient peer pools, blocking short cash runway, sector fallbacks,
same-time RVOL, stale quotes, no premarket substitution from yesterday, manual post-close
behavior, alert cooldown, session deduplication, successful mocked Telegram delivery,
rate-limit handling, ambiguous-send failure redaction, chunking including UTF-16 emoji,
provider failure reports, JSON null/atomic writes, payload cache serialization, artifact
path traversal rejection and valid state extraction.

The included `examples/DEMO_TELEGRAM.txt` contains only labelled SYNTHETIC observations.
It is not a real stock ranking or evidence of investment performance.

## NOT executed or established

- Real Yahoo/yfinance data downloads: NOT tested here. The environment could not resolve
  external package/data hosts; yfinance was not installed locally. The adapter follows the
  documented methods but remains to be verified with a live provider.
- Real Telegram messages / authentication: NOT tested; no user token or chat ID was provided.
- GitHub Actions deployment/scheduling/artifact upload/download: NOT run in the user's account.
- Fresh dependency installation and Python 3.12 execution: NOT tested locally; provided CI is
  configured to check Python 3.12 and 3.13 on GitHub.
- Prediction accuracy, historical alpha, transaction costs or economic utility: NOT established.
- Security audit, availability SLA or exactly-once delivery guarantee: NOT provided.

Mocks verify application behavior under controlled responses; they do not verify the external
service's current schema, access rights, rate limits, network availability or data correctness.

## Acceptance sequence on your GitHub account

1. Confirm the **Tests** workflow passes after uploading to the default branch.
2. Create the new bot and save TELEGRAM_BOT_TOKEN.
3. Run **Telegram Setup**; receive the chat ID privately and save TELEGRAM_CHAT_ID.
4. Run **Growth Alerts / demo** with dry_run off; confirm the SYNTHETIC label arrives.
5. Run **Growth Alerts / manual**; review provider errors, coverage, source timestamps and
   exclusions in the report artifact. A no-candidates report can be legitimate.
6. Verify the first real scheduled run, then verify a subsequent run restores the state artifact.
7. Keep position decisions manual and independently check important market/company information.

## Installed local test environment

```text
Python 3.13.5
pandas==2.2.3
numpy==2.3.5
requests==2.32.5
PyYAML==6.0.3
pytest==9.0.2
exchange-calendars==4.13.1
yfinance: not installed; live adapter not executed
```
