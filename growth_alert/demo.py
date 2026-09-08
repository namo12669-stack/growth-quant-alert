"""Explicit synthetic fixtures; no real ticker prices or recommendations."""
from __future__ import annotations

from datetime import datetime

from .calendar import last_completed_session


def demo_records(now: datetime, cfg: dict) -> list[dict]:
    records = []
    for i in range(16):
        q = i / 15
        records.append({
            "symbol": f"DEMO{i + 1:02d}", "name": "SYNTHETIC COMPANY - NOT A REAL SECURITY",
            "sector": "Demo Software" if i % 2 else "Demo Consumer", "industry": "Synthetic",
            "quote_currency": "USD", "financial_currency": "USD", "market_cap": 2e9 + i * 1e9,
            "previous_close": 20 + i * 4, "daily_price_valid": True,
            "price_date": str(last_completed_session(now, cfg["calendar"])),
            "statement_period": "SYNTHETIC_PERIOD", "statement_age_days": 65,
            "fundamental_fetched_at": now.isoformat(), "source_warnings": [],
            "dollar_volume_20d": 20e6 + i * 2e6, "revenue_yoy": .12 + .6 * q,
            "revenue_per_share_yoy": .09 + .55 * q, "revenue_acceleration": -.02 + .15 * q,
            "gross_profit_assets": .15 + .8 * q, "cfo_assets": -.03 + .35 * q,
            "operating_margin_change": -.01 + .09 * q, "fcf_margin": -.1 + .4 * q,
            "eps_revision_30d": -.05 + .18 * q, "revision_breadth_30d": -.5 + 1.3 * q,
            "momentum_12_1": -.05 + .8 * q, "near_52w_high": .7 + .3 * q,
            "path_continuity": -.02 + .15 * q, "sales_to_ev": .03 + .12 * q,
            "volatility_60d": .38, "drawdown_252d": -.1, "dilution_yoy": .02,
            "above_sma200": True, "intraday_available": False,
        })
    return records
