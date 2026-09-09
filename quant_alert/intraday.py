from __future__ import annotations
from datetime import datetime, timedelta
import pandas as pd
from .calendar import NY, session_for
from .indicators import range_position
from .models import Signal
from .provider import REQUIRED
from .quality import valid_ohlcv


def session_snapshot(raw: pd.DataFrame, now: datetime, cfg: dict) -> tuple[dict | None, dict]:
    """Only completed 15m bars. Compare volume at identical elapsed-session times.

    A comparable day must have every regular-session slot from open through the
    current cutoff; short sessions and gaps are not filled with zero volume.
    """
    c = cfg["signals"]["intraday_breakout"]
    audit = {"engine": "intraday", "status": "UNAVAILABLE"}
    session = session_for(now.astimezone(NY).date(), cfg["calendar"])
    if not session or not session.open <= now < session.close:
        return None, {**audit, "status": "OUTSIDE_REGULAR_SESSION"}
    if (now-session.open).total_seconds()/60 < c["min_elapsed_minutes"]:
        return None, {**audit, "status": "TOO_EARLY_IN_SESSION"}
    if raw is None or raw.empty or not set(REQUIRED) <= set(raw.columns):
        return None, {**audit, "status": "NO_INTRADAY_OHLCV"}
    f = raw.copy()
    idx = pd.DatetimeIndex(f.index)
    if idx.tz is None:
        return None, {**audit, "status": "INTRADAY_TIMEZONE_REQUIRED"}
    f.index = idx.tz_convert(NY)
    f = f.sort_index().loc[lambda x: ~x.index.duplicated(keep="last")]
    for col in REQUIRED:
        f[col] = pd.to_numeric(f[col], errors="coerce")
    f = f.loc[valid_ohlcv(f)]
    step = timedelta(minutes=c["interval_minutes"])
    f = f.loc[f.index + step <= now]
    current = f.loc[f.index.date == session.day]
    current = current.loc[(current.index >= session.open) & (current.index + step <= session.close)]
    if current.empty:
        return None, {**audit, "status": "NO_COMPLETED_CURRENT_BARS"}
    end = current.index[-1].to_pydatetime() + step
    age = (now-end).total_seconds()/60
    if age < 0 or age > cfg["quality"]["max_intraday_age_minutes"]:
        return None, {**audit, "status": "STALE_INTRADAY", "age_minutes": age}
    elapsed = end - session.open
    if elapsed.total_seconds()/60 < c["min_elapsed_minutes"]:
        return None, {**audit, "status": "TOO_FEW_COMPLETED_BARS"}
    expected = pd.date_range(session.open.astimezone(NY), end-step, freq=f"{c['interval_minutes']}min").tz_convert(NY)
    if not current.index.equals(expected):
        return None, {**audit, "status": "MISSING_CURRENT_INTRADAY_SLOTS"}
    volumes = []
    eligible_days = sorted({t for t in f.index.date if t < session.day}, reverse=True)
    for day in eligible_days:
        s = session_for(day, cfg["calendar"])
        if not s or s.open + elapsed > s.close:
            continue
        needed = pd.date_range(s.open, s.open + elapsed-step, freq=f"{c['interval_minutes']}min").tz_convert(NY)
        bars = f.reindex(needed)
        if bars[REQUIRED].isna().any().any():
            continue
        volume = float(bars.Volume.sum())
        if volume > 0:
            volumes.append(volume)
        if len(volumes) >= c["prior_sessions"]:
            break
    if len(volumes) < c["min_comparable_sessions"]:
        return None, {**audit, "status": "INSUFFICIENT_SAME_CLOCK_HISTORY", "comparable_sessions": len(volumes)}
    volume = float(current.Volume.sum())
    if volume <= 0:
        return None, {**audit, "status": "ZERO_SESSION_VOLUME"}
    median = float(pd.Series(volumes).median())
    typical = (current.High + current.Low + current.Close) / 3
    snapshot = {
        "bar_close": float(current.Close.iloc[-1]), "session_low": float(current.Low.min()),
        "session_high": float(current.High.max()), "vwap_proxy": float((typical*current.Volume).sum()/volume),
        "rvol_same_clock": volume/median, "cumulative_volume": volume,
        "median_same_clock_volume": median, "comparable_sessions": len(volumes),
        "bar_end": end.isoformat(), "age_minutes": age,
        "session": str(session.day), "elapsed_minutes": elapsed.total_seconds()/60,
    }
    return snapshot, {**audit, **snapshot, "status": "USABLE"}


def intraday_breakout(symbol: str, daily: pd.DataFrame, raw: pd.DataFrame,
                      now: datetime, cfg: dict) -> tuple[list[Signal], dict]:
    c = cfg["signals"]["intraday_breakout"]
    if not c["enabled"]:
        return [], {"symbol": symbol, "engine": "intraday_breakout", "status": "DISABLED"}
    snap, audit = session_snapshot(raw, now, cfg)
    audit.update(symbol=symbol, engine="intraday_breakout")
    if snap is None:
        return [], audit
    n = cfg["signals"]["breakout"]["lookback"]
    level = float(daily.High.tail(n).max())
    px = snap["bar_close"]
    pos = range_position(px, snap["session_low"], snap["session_high"])
    above_vwap = px > snap["vwap_proxy"]
    passed = (px > level*(1+cfg["signals"]["breakout"]["buffer"])
              and snap["rvol_same_clock"] >= c["min_rvol"]
              and pos >= c["min_range_position"]
              and (above_vwap or not c["require_above_vwap"]))
    metrics = {**snap, "prior_high": level, "range_position": pos, "above_vwap_proxy": above_vwap}
    audit.update(metrics, status="DETECTED" if passed else "CONDITIONS_NOT_MET")
    if not passed:
        return [], audit
    return [Signal("INTRADAY_BREAKOUT", [symbol], "bullish", "15m / provisional session",
                   snap["bar_end"], snap["session"],
                   [f"Completed 15m bar {px:.2f} exceeds prior {n}-session high {level:.2f}",
                    f"Same-clock RVOL {snap['rvol_same_clock']:.2f}x across {snap['comparable_sessions']} comparable sessions",
                    f"Session range position {pos:.0%}; above 15m typical-price VWAP proxy: {above_vwap}"],
                   metrics, priority="HIGH",
                   caution="PROVISIONAL: session has not closed. VWAP is a 15m-bar approximation, not tick VWAP. News/fundamentals NOT checked.",
                   horizon="1-5 sessions; unvalidated research hypothesis")], audit
