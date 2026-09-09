from __future__ import annotations
from datetime import date, timedelta
import numpy as np
import pandas as pd
from .calendar import NY, session_dates
from .provider import REQUIRED


def valid_ohlcv(df: pd.DataFrame) -> pd.Series:
    nums = df[REQUIRED]
    return (np.isfinite(nums).all(axis=1) & (nums[["Open", "High", "Low", "Close"]] > 0).all(axis=1)
            & (df.Volume >= 0) & (df.High >= df[["Open", "Close", "Low"]].max(axis=1))
            & (df.Low <= df[["Open", "Close", "High"]].min(axis=1)))


def prepare_daily(raw: pd.DataFrame, expected: date, cfg: dict, stock: bool = True) -> tuple[pd.DataFrame, dict]:
    q = cfg["quality"]
    diag = {"usable": False, "expected_session": expected.isoformat(), "reasons": []}
    if raw is None or raw.empty:
        diag["reasons"] = ["EMPTY_DAILY_PRICE"]
        return pd.DataFrame(), diag
    f = raw.copy()
    if not set(REQUIRED) <= set(f.columns):
        diag["reasons"] = ["MISSING_OHLCV_COLUMNS"]
        return pd.DataFrame(), diag
    try:
        idx = pd.DatetimeIndex(pd.to_datetime(f.index))
        if idx.tz is not None:
            idx = idx.tz_convert(NY).tz_localize(None)
        f.index = idx.normalize()
    except (TypeError, ValueError):
        diag["reasons"] = ["INVALID_DAILY_INDEX"]
        return pd.DataFrame(), diag
    diag["future_or_partial_bars_removed"] = int((f.index.date > expected).sum())
    f = f.loc[f.index.date <= expected].sort_index()
    diag["duplicate_dates"] = int(f.index.duplicated().sum())
    f = f.loc[~f.index.duplicated(keep="last")]
    for c in REQUIRED:
        f[c] = pd.to_numeric(f[c], errors="coerce")
    good = valid_ohlcv(f)
    diag["invalid_ohlcv_rows"] = int((~good).sum())
    f = f.loc[good]
    if f.empty:
        diag["reasons"] = ["NO_VALID_DAILY_BARS"]
        return f, diag
    valid_dates = session_dates(max(f.index[0].date(), expected - timedelta(days=1090)), expected, cfg["calendar"])
    f = f.loc[f.index.isin(valid_dates)]
    if f.empty:
        diag["reasons"] = ["NO_EXCHANGE_SESSIONS"]
        return f, diag
    diag.update(rows=len(f), last_session=f.index[-1].date().isoformat(), last_close=float(f.Close.iloc[-1]))
    if f.index[-1].date() != expected:
        diag["reasons"].append("STALE_DAILY_PRICE")
    if len(f) < q["min_daily_bars"]:
        diag["reasons"].append("INSUFFICIENT_DAILY_HISTORY")
    required_dates = valid_dates[-min(q["completeness_window"], len(valid_dates)):]
    coverage = len(f.index.intersection(required_dates)) / max(1, len(required_dates))
    diag["session_completeness"] = coverage
    if coverage < q["min_completeness"]:
        diag["reasons"].append("GAPS_IN_DAILY_HISTORY")
    dv = float((f.Close * f.Volume).tail(20).mean())
    diag["average_dollar_volume_20"] = dv
    if stock:
        if f.Close.iloc[-1] < q["min_price"]:
            diag["reasons"].append("BELOW_MIN_PRICE")
        if dv < q["min_average_dollar_volume"]:
            diag["reasons"].append("LOW_DOLLAR_VOLUME")
        if "Stock Splits" in f and (pd.to_numeric(f["Stock Splits"], errors="coerce").tail(q["split_cooldown_sessions"]).fillna(0) != 0).any():
            diag["reasons"].append("RECENT_SPLIT_REVIEW_REQUIRED")
    diag["usable"] = not diag["reasons"]
    return f, diag
