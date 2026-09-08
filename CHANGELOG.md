# Changelog

## 1.1.0

- Added SEC EDGAR Company Facts fallback for filed income statement, cash-flow and balance-sheet fields when Yahoo statement tables are missing.
- Added yfinance `fast_info` fallback for market cap/currency when full `get_info()` is unavailable.
- Changed whole-run data-quality gate to current price availability instead of requiring a current statement for every ticker.
- Missing optional fundamentals now reduce per-stock factor coverage and confidence instead of automatically excluding the whole universe.
- Added HIGH / MEDIUM / LOW / INSUFFICIENT confidence labels based on factor coverage.
- Missing market cap, quote currency, analyst revisions and statements are surfaced as explicit data warnings.
- Incompatible V1.0 fundamental caches are invalidated automatically.
- Telegram/GitHub summary now reports Price usable and Fundamental usable separately and identifies the fundamental source.
- No broker/order functionality was added.
