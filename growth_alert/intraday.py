from __future__ import annotations

from datetime import datetime, time

import numpy as np
import pandas as pd

from .calendar import NY, session_for
from .factors import divide, finite


def intraday_features(frame: pd.DataFrame, now: datetime, mode: str, previous_close: float, cfg: dict) -> dict:
    missing = {"intraday_available": False, "quote_status": "UNAVAILABLE", "rvol_same_time": None}
    if frame is None or frame.empty:
        return missing
    bars = frame.copy().sort_index()
    index = pd.DatetimeIndex(bars.index)
    # An unlabelled intraday timezone cannot safely be assumed.
    if index.tz is None:
        return {**missing, "quote_status": "UNKNOWN_TIMEZONE"}
    bars.index = index.tz_convert(NY)
    local = now.astimezone(NY)
    day = local.date()
    session = session_for(day, cfg["calendar"])
    if not session:
        return {**missing, "quote_status": "NONTRADING_DAY"}
    bars = bars.loc[~bars.index.duplicated(keep="last")]
    # Yahoo 5-minute bars are start-labelled. Never use an unfinished bar.
    bars = bars.loc[bars.index + pd.Timedelta(minutes=5) <= local]
    bars = bars.loc[bars["Close"].notna() & (bars["Close"] > 0)]
    opening = session.open.astimezone(NY)
    closing = session.close.astimezone(NY)
    if mode != "preopen" and not opening <= local < closing:
        return {**missing, "quote_status": "REGULAR_SESSION_CLOSED"}
    start = datetime.combine(day, time(4, 0), NY) if mode == "preopen" else opening
    stop = opening if mode == "preopen" else closing
    today = bars.loc[(bars.index >= start) & (bars.index < stop)]
    if today.empty:
        return missing
    latest = today.index[-1]
    quote_end = latest + pd.Timedelta(minutes=5)
    age = (local - quote_end.to_pydatetime()).total_seconds() / 60
    last = float(today["Close"].iloc[-1])
    result = {"intraday_available": age <= cfg["alerts"]["max_quote_age_minutes"],
              "quote_status": "BAR_RECENT_NOT_GUARANTEED_REALTIME" if age <= cfg["alerts"]["max_quote_age_minutes"] else "STALE",
              "quote_time": quote_end.isoformat(), "quote_age_minutes": round(age, 1),
              "intraday_price": last, "session_return": divide(last, previous_close) - 1,
              "rvol_same_time": None, "rvol_history_days": 0,
              "range_position": None}
    if not result["intraday_available"]:
        return result
    if mode != "preopen":
        high, low = today["High"].max(), today["Low"].min()
        result["range_position"] = divide(last - low, high - low)
    # Compare completed bars at the same local NY clock time, not to full-day volume.
    cut = latest.hour * 60 + latest.minute
    begin = 240 if mode == "preopen" else opening.hour * 60 + opening.minute
    expected = max(1, (cut - begin) // 5 + 1)
    if len(today) < expected * .90:
        return result
    histories = []
    old = bars.loc[bars.index.date < day]
    for old_day, group in old.groupby(old.index.date):
        old_session = session_for(old_day, cfg["calendar"])
        if not old_session:
            continue
        old_close = old_session.close.astimezone(NY)
        # Half days lacking this clock-time interval must not enter the baseline.
        if mode != "preopen" and old_close.hour * 60 + old_close.minute <= cut:
            continue
        minute = group.index.hour * 60 + group.index.minute
        use = group.loc[(minute >= begin) & (minute <= cut)]
        if len(use) >= expected * .90:
            volume = float(use["Volume"].sum())
            if volume > 0:
                histories.append(volume)
    histories = histories[-20:]
    result["rvol_history_days"] = len(histories)
    if len(histories) >= cfg["data"]["min_rvol_history_days"]:
        result["rvol_same_time"] = divide(today["Volume"].sum(), np.median(histories))
    return result
