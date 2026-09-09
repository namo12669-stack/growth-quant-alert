# V2.0.0

- Replaced the fundamental composite ranking path with five explicit signal families.
- Removed the speculative +/-4% price-movement-only alert.
- Added confirmed daily RSI divergence, daily/intraday breakout-volume checks, and ratio-based relative strength.
- Added frozen-formation pair spread screens with separate holdout validation and multiple-testing adjustment.
- Added true one-session lead-lag models, chronological held-out predictions, baseline comparison, and horizon checks.
- No .info, financial-statement, analyst-revision or SEC requests in the live signal path.
- No fabricated fundamental/catalyst scores or inferred news events.
- Added point-in-time bar cutoff, missing-session controls, split review, same-clock intraday RVOL, and publication-time rechecks.
- Added all-candidate relationship audit, reason-level diagnostics, successful-send journal, and descriptive forward outcomes.
- Isolated V2 modules, tests and state from V1 remnants; retained the same workflow file path and Telegram secrets.
- Added deterministic synthetic demo fixtures and offline tests. Synthetic model outcomes are NOT live performance claims.
