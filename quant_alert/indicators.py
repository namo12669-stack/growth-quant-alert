from __future__ import annotations
import numpy as np
import pandas as pd


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """Wilder RSI: seed with an arithmetic mean, then recursive smoothing."""
    x = close.to_numpy(dtype=float)
    out = np.full(len(x), np.nan)
    if len(x) <= period:
        return pd.Series(out, index=close.index)
    diff = np.diff(x)
    gain, loss = np.maximum(diff, 0), np.maximum(-diff, 0)
    ag, al = gain[:period].mean(), loss[:period].mean()
    for i in range(period, len(x)):
        if i > period:
            ag = (ag * (period - 1) + gain[i - 1]) / period
            al = (al * (period - 1) + loss[i - 1]) / period
        out[i] = 50.0 if ag == al == 0 else 100.0 if al == 0 else 100 - 100 / (1 + ag / al)
    return pd.Series(out, index=close.index)


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    prev = df.Close.shift(1)
    tr = pd.concat([df.High - df.Low, (df.High - prev).abs(), (df.Low - prev).abs()], axis=1).max(axis=1)
    return tr.rolling(period, min_periods=period).mean()


def confirmed_pivots(series: pd.Series, left: int, right: int, kind: str = "low") -> list[int]:
    """A pivot at i exists only after i+right. Ties are not pivots."""
    a = series.to_numpy(dtype=float)
    pivots = []
    for i in range(left, len(a) - right):
        neighbors = np.r_[a[i-left:i], a[i+1:i+right+1]]
        if not np.isfinite(a[i]) or not np.isfinite(neighbors).all():
            continue
        if (kind == "low" and np.all(a[i] < neighbors)) or (kind == "high" and np.all(a[i] > neighbors)):
            pivots.append(i)
    return pivots


def range_position(close: float, low: float, high: float) -> float:
    return float((close - low) / (high - low)) if high > low else 0.5
