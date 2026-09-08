"""Transparent live-snapshot features; these are not a point-in-time backtest."""
from __future__ import annotations

from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd

from .calendar import NY, last_completed_session

# Within-family weights; all signs are oriented so larger is preferred.
FEATURES = {
    "growth": {"revenue_yoy": .45, "revenue_per_share_yoy": .35, "revenue_acceleration": .20},
    "quality": {"gross_profit_assets": .30, "cfo_assets": .25,
                "operating_margin_change": .25, "fcf_margin": .20},
    "expectations": {"eps_revision_30d": .70, "revision_breadth_30d": .30},
    "momentum": {"momentum_12_1": .60, "near_52w_high": .25, "path_continuity": .15},
    "valuation": {"sales_to_ev": 1.0},
}


def finite(x: Any) -> bool:
    try:
        return bool(np.isfinite(float(x)))
    except (TypeError, ValueError):
        return False


def number(x: Any) -> float:
    return float(x) if finite(x) else np.nan


def divide(a: Any, b: Any, positive_denominator: bool = True) -> float:
    if not finite(a) or not finite(b) or float(b) == 0:
        return np.nan
    if positive_denominator and float(b) <= 0:
        return np.nan
    return float(a) / float(b)


def row(frame: pd.DataFrame, *names: str) -> pd.Series:
    for name in names:
        if frame is not None and not frame.empty and name in frame.index:
            result = pd.to_numeric(frame.loc[name], errors="coerce").dropna()
            if isinstance(result, pd.DataFrame):
                return pd.Series(dtype=float)
            result.index = pd.to_datetime(result.index, utc=True).tz_localize(None)
            return result[~result.index.duplicated()].sort_index(ascending=False)
    return pd.Series(dtype=float)


def at(series: pd.Series, date: pd.Timestamp, tolerance: int = 7) -> float:
    if series.empty:
        return np.nan
    distances = abs((series.index - date).days)
    pos = int(np.argmin(distances))
    return number(series.iloc[pos]) if distances[pos] <= tolerance else np.nan


def year_ago(series: pd.Series, date: pd.Timestamp) -> float:
    return at(series, date - pd.DateOffset(years=1), tolerance=15)


def ttm(series: pd.Series, end: pd.Timestamp) -> float:
    values = series[series.index <= end].iloc[:4]
    if len(values) < 4 or not all(65 <= gap <= 115 for gap in -np.diff(values.index.values).astype('timedelta64[D]').astype(int)):
        return np.nan
    if abs((values.index[0] - end).days) > 15:
        return np.nan
    return float(values.sum())


def price_features(prices: pd.DataFrame, now: datetime, calendar: str = "XNYS") -> dict:
    expected = last_completed_session(now, calendar)
    empty = {"daily_price_valid": False, "price_date": None}
    if prices is None or prices.empty or "Close" not in prices:
        return empty
    prices = prices.sort_index().copy()
    idx = pd.DatetimeIndex(prices.index)
    dates = idx.tz_convert(NY).date if idx.tz is not None else idx.date
    prices = prices.loc[dates <= expected]
    prices = prices.loc[prices["Close"].notna() & (prices["Close"] > 0)]
    if prices.empty:
        return empty
    last_day = pd.Timestamp(prices.index[-1]).date()
    adj = pd.to_numeric(prices.get("Adj Close", prices["Close"]), errors="coerce").dropna()
    if adj.empty or (adj <= 0).any():
        return empty
    raw = prices["Close"].astype(float)
    high = prices.get("High", raw).astype(float)
    out = {
        "daily_price_valid": last_day == expected,
        "price_date": str(last_day), "previous_close": number(raw.iloc[-1]),
        "dollar_volume_20d": number((raw * prices["Volume"]).tail(20).median()) if len(prices) >= 20 else np.nan,
        "near_52w_high": divide(raw.iloc[-1], high.tail(252).max()) if len(raw) >= 200 else np.nan,
        "prior_52w_high": number(high.tail(252).max()) if len(raw) >= 200 else np.nan,
        "volatility_60d": number(adj.pct_change().tail(60).std() * np.sqrt(252)) if len(adj) >= 61 else np.nan,
        "drawdown_252d": divide(adj.iloc[-1], adj.tail(252).max()) - 1 if len(adj) >= 200 else np.nan,
        "above_sma200": bool(adj.iloc[-1] > adj.tail(200).mean()) if len(adj) >= 200 else None,
    }
    if len(adj) >= 253:
        out["momentum_12_1"] = divide(adj.iloc[-22], adj.iloc[-253]) - 1
        changes = adj.iloc[-253:-21].pct_change().dropna()
        sign = np.sign(out["momentum_12_1"])
        out["path_continuity"] = float(sign * ((changes > 0).mean() - (changes < 0).mean()))
    return out


def financial_features(payload: dict, now: datetime) -> dict:
    info = payload.get("info", {})
    inc = payload.get("income", pd.DataFrame())
    cf = payload.get("cashflow", pd.DataFrame())
    bs = payload.get("balance", pd.DataFrame())
    rev = row(inc, "Total Revenue", "Operating Revenue")
    shares = row(inc, "Basic Average Shares", "Diluted Average Shares")
    gp = row(inc, "Gross Profit")
    op = row(inc, "Operating Income")
    cfo = row(cf, "Operating Cash Flow", "Cash Flow From Continuing Operating Activities")
    capex = row(cf, "Capital Expenditure")
    assets = row(bs, "Total Assets")
    cash = row(bs, "Cash Cash Equivalents And Short Term Investments", "Cash And Cash Equivalents")
    debt = row(bs, "Total Debt")
    out = {"sector": info.get("sector") or "Unknown", "industry": info.get("industry") or "Unknown",
           "name": info.get("shortName") or info.get("longName") or "",
           "quote_currency": info.get("currency"), "financial_currency": info.get("financialCurrency"),
           "market_cap": number(info.get("marketCap")),
           "fundamental_fetched_at": payload.get("fetched_at"),
           "fundamental_source": payload.get("source", "Unknown"),
           "source_warnings": payload.get("warnings", []), "statement_period": None}
    if not rev.empty:
        end = rev.index[0]
        current = rev.iloc[0]
        prior = year_ago(rev, end)
        out.update(statement_period=str(end.date()),
                   statement_age_days=(now.astimezone(NY).date() - end.date()).days,
                   revenue_yoy=divide(current, prior) - 1)
        out["revenue_ttm"] = ttm(rev, end)
        prior_end = rev.index[1] if len(rev) > 1 else None
        if prior_end is not None and 65 <= (end - prior_end).days <= 115:
            last_growth = divide(rev.iloc[1], year_ago(rev, prior_end)) - 1
            out["revenue_acceleration"] = out["revenue_yoy"] - last_growth
        sh_now, sh_old = at(shares, end), year_ago(shares, end)
        out["revenue_per_share_yoy"] = divide(divide(current, sh_now), divide(prior, sh_old)) - 1
        out["dilution_yoy"] = divide(sh_now, sh_old) - 1
        out["operating_margin"] = divide(at(op, end), current)
        out["operating_margin_change"] = out["operating_margin"] - divide(year_ago(op, end), prior)
        # Latest balance-sheet assets are a proxy, not exact academic denominator replication.
        latest_assets = at(assets, end)
        gp_ttm, cfo_ttm, capex_ttm = ttm(gp, end), ttm(cfo, end), ttm(capex, end)
        out["gross_profit_assets"] = divide(gp_ttm, latest_assets)
        out["cfo_assets"] = divide(cfo_ttm, latest_assets)
        fcf = cfo_ttm - abs(capex_ttm) if finite(cfo_ttm) and finite(capex_ttm) else np.nan
        out["fcf_margin"] = divide(fcf, out["revenue_ttm"])
        latest_cash, latest_debt = at(cash, end), at(debt, end)
        out["net_cash"] = latest_cash - latest_debt
        out["cash_runway_quarters"] = divide(latest_cash, -fcf / 4) if finite(fcf) and fcf < 0 else np.nan
        ev = number(info.get("enterpriseValue"))
        # No implicit FX conversion. Unknown currency is not assumed to be USD.
        if info.get("currency") == info.get("financialCurrency") == "USD":
            out["sales_to_ev"] = divide(out["revenue_ttm"], ev)
    trend = payload.get("eps_trend", pd.DataFrame())
    revisions = payload.get("eps_revisions", pd.DataFrame())
    # Yahoo's next-year snapshot, NOT stored point-in-time historical consensus.
    if "+1y" in trend.index:
        current = number(trend.loc["+1y"].get("current"))
        prior = number(trend.loc["+1y"].get("30daysAgo"))
        # Exclude negative/near-zero EPS bases rather than create explosive percentages.
        if finite(current) and finite(prior) and current > 0 and prior >= .10:
            out["eps_revision_30d"] = (current - prior) / abs(prior)
    if "+1y" in revisions.index:
        rr = revisions.loc["+1y"]
        up, down = number(rr.get("upLast30days")), number(rr.get("downLast30days"))
        if finite(up) and finite(down) and up >= 0 and down >= 0:
            out["revision_breadth_30d"] = (up - down) / (up + down) if up + down > 0 else 0.0
    return out
