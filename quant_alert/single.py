from __future__ import annotations
import numpy as np
import pandas as pd
from .indicators import rsi, atr, confirmed_pivots, range_position
from .models import Signal


def divergence(symbol: str, df: pd.DataFrame, cfg: dict) -> tuple[list[Signal], dict]:
    d = cfg["signals"]["divergence"]
    audit = {"symbol": symbol, "engine": "divergence", "checks": {}}
    if not d["enabled"]:
        return [], {**audit, "status": "DISABLED"}
    osc = rsi(df.Close, d["rsi_period"])
    result = []
    for side, series, direction in (("low", df.Low, "bullish"), ("high", df.High, "bearish")):
        if direction == "bearish" and not cfg["alerts"]["allow_bearish"]:
            continue
        pivots = confirmed_pivots(series, d["pivot_left"], d["pivot_right"], side)
        checks = {}
        audit["checks"][direction] = checks
        if len(pivots) < 2:
            checks["status"] = "FEWER_THAN_TWO_CONFIRMED_PIVOTS"
            continue
        p2 = pivots[-1]
        previous = [p for p in pivots[:-1] if d["min_pivot_gap"] <= p2 - p <= d["max_pivot_gap"]]
        if not previous:
            checks["status"] = "NO_PRIOR_PIVOT_WITHIN_GAP"
            continue
        p1 = previous[-1]
        a, b = float(series.iloc[p1]), float(series.iloc[p2])
        r1, r2 = float(osc.iloc[p1]), float(osc.iloc[p2])
        age = len(df) - 1 - (p2 + d["pivot_right"])
        finite = np.isfinite([r1, r2]).all()
        if direction == "bullish":
            price_test = b <= a * (1 - d["min_price_change"])
            osc_test = r2 >= r1 + d["min_rsi_difference"] and min(r1, r2) <= d["bullish_rsi_max"]
            confirmation = df.Close.iloc[-1] > df.Close.iloc[p2] and df.Close.iloc[-1] > df.Close.iloc[-2]
            not_invalidated = df.Low.iloc[p2+1:].min() > b
        else:
            price_test = b >= a * (1 + d["min_price_change"])
            osc_test = r2 <= r1 - d["min_rsi_difference"] and max(r1, r2) >= d["bearish_rsi_min"]
            confirmation = df.Close.iloc[-1] < df.Close.iloc[p2] and df.Close.iloc[-1] < df.Close.iloc[-2]
            not_invalidated = df.High.iloc[p2+1:].max() < b
        checks.update(price_pivot_1=a, price_pivot_2=b, rsi_1=r1, rsi_2=r2,
                      pivot_1_date=str(df.index[p1].date()), pivot_2_date=str(df.index[p2].date()),
                      confirmation_date=str(df.index[p2+d["pivot_right"]].date()),
                      confirmation_age_sessions=age,
                      price_condition=bool(price_test), oscillator_condition=bool(osc_test),
                      latest_close_confirmation=bool(confirmation), not_invalidated=bool(not_invalidated))
        passed = bool(finite and price_test and osc_test and confirmation and not_invalidated
                      and age <= d["max_confirmation_age"])
        checks["status"] = "DETECTED" if passed else "CONDITIONS_NOT_MET"
        if passed:
            change = "lower low / higher RSI" if direction == "bullish" else "higher high / lower RSI"
            result.append(Signal(
                "RSI_DIVERGENCE", [symbol], direction, "1D confirmed pivots", str(df.index[-1].date()),
                f"{df.index[p1].date()}:{df.index[p2].date()}",
                [f"Price pivots {a:.2f} -> {b:.2f}; RSI({d['rsi_period']}) {r1:.1f} -> {r2:.1f}",
                 f"{change}; waited {d['pivot_right']} completed bars to confirm second pivot",
                 f"Latest close confirms direction; review level {b:.2f} (not an automatic stop)"],
                metrics=checks, priority="WATCH"))
    return result, audit


def breakout(symbol: str, df: pd.DataFrame, cfg: dict) -> tuple[list[Signal], dict]:
    c = cfg["signals"]["breakout"]
    audit = {"symbol": symbol, "engine": "daily_breakout"}
    if not c["enabled"]:
        return [], {**audit, "status": "DISABLED"}
    n = c["lookback"]
    if len(df) < n + 2:
        return [], {**audit, "status": "SHORT_HISTORY"}
    prev = df.iloc[-n-1:-1]
    level = float(prev.High.max())
    baseline_vol = float(prev.Volume.mean())
    v = float(df.Volume.iloc[-1] / baseline_vol) if baseline_vol > 0 else 0.0
    close, high, low = map(float, [df.Close.iloc[-1], df.High.iloc[-1], df.Low.iloc[-1]])
    pos = range_position(close, low, high)
    norm_atr = atr(df) / df.Close
    ref = norm_atr.iloc[-c["squeeze_lookback"]-1:-1].dropna()
    squeeze_rank = float((ref <= ref.iloc[-1]).mean()) if len(ref) >= 60 else None
    squeeze = squeeze_rank is not None and squeeze_rank <= c["squeeze_percentile"]
    # All baselines exclude the current bar.
    passed = close > level * (1 + c["buffer"]) and v >= c["min_rvol"] and pos >= c["min_range_position"]
    metrics = {"bar_close": close, "prior_high": level, "rvol_daily": v,
               "day_range_position": pos, "prior_natr_percentile": squeeze_rank,
               "squeeze_context": bool(squeeze)}
    audit.update(metrics, status="DETECTED" if passed else "CONDITIONS_NOT_MET")
    if not passed:
        return [], audit
    reasons = [f"Completed close {close:.2f} exceeds prior {n}-session high {level:.2f}",
               f"Full-session volume {v:.2f}x prior {n}-session mean; range position {pos:.0%}"]
    if squeeze:
        reasons.append(f"Prior-day normalized ATR in bottom {c['squeeze_percentile']:.0%} of reference history")
    signal = Signal("BREAKOUT_VOLUME", [symbol], "bullish", "1D closed", str(df.index[-1].date()),
                    str(df.index[-1].date()), reasons, metrics, priority="HIGH")
    return [signal], audit


def relative_strength(symbol: str, df: pd.DataFrame, benchmark: str,
                      b: pd.DataFrame | None, cfg: dict) -> tuple[list[Signal], dict]:
    c = cfg["signals"]["relative_strength"]
    audit = {"symbol": symbol, "engine": "relative_strength", "benchmark": benchmark}
    if not c["enabled"]:
        return [], {**audit, "status": "DISABLED"}
    if b is None or b.empty or df.index[-1] != b.index[-1]:
        return [], {**audit, "status": "BENCHMARK_UNAVAILABLE_OR_STALE"}
    n = c["lookback"]
    tail = df.tail(max(n+2, c["trend_window"], c["return_window"]+1))
    if len(tail) < n+2 or not tail.index.isin(b.index).all():
        return [], {**audit, "status": "UNALIGNED_OR_SHORT_HISTORY"}
    bclose = b.Close.reindex(tail.index)
    ratio = tail.Close / bclose
    threshold = float(ratio.iloc[-n-1:-1].max())
    w = c["return_window"]
    rs = float(tail.Close.iloc[-1] / tail.Close.iloc[-w-1] - 1)
    rb = float(bclose.iloc[-1] / bclose.iloc[-w-1] - 1)
    trend = float(tail.Close.tail(c["trend_window"]).mean())
    passed = ratio.iloc[-1] > threshold and rs-rb >= c["min_excess_return"] and rs > 0 and df.Close.iloc[-1] > trend
    metrics = {"ratio": float(ratio.iloc[-1]), "prior_ratio_high": threshold,
               "stock_return": rs, "benchmark_return": rb, "excess_return": rs-rb, "sma": trend}
    audit.update(metrics, status="DETECTED" if passed else "CONDITIONS_NOT_MET")
    if not passed:
        return [], audit
    return [Signal("RELATIVE_STRENGTH_BREAKOUT", [symbol], "bullish", "1D closed",
                   str(df.index[-1].date()), str(df.index[-1].date()),
                   [f"Stock/{benchmark} price ratio exceeds prior {n}-session high",
                    f"{w}-session return {rs:+.1%} vs {benchmark} {rb:+.1%}; excess {rs-rb:+.1%}",
                    f"Absolute return is positive; close above {c['trend_window']}-session SMA"],
                   metrics, priority="WATCH")], audit
