from __future__ import annotations
from datetime import datetime, date, timezone, timedelta
import numpy as np
import pandas as pd
from .calendar import session_dates

DEMO_NOW = datetime(2026, 9, 9, 12, 45, tzinfo=timezone.utc)


def frame_from_close(close: np.ndarray, index: pd.DatetimeIndex, volume: float = 1_500_000) -> pd.DataFrame:
    x = np.asarray(close)
    op = np.r_[x[0], x[:-1]]
    return pd.DataFrame({"Open": op, "High": np.maximum(op, x)*1.005,
                         "Low": np.minimum(op, x)*0.995, "Close": x,
                         "Volume": np.full(len(x), volume), "Stock Splits": 0.0}, index=index)


def make_demo(cfg: dict) -> tuple[dict, dict[str, pd.DataFrame]]:
    """Deliberately constructed toy processes. Never evidence of a live edge."""
    idx = session_dates(date(2024, 1, 1), date(2026, 9, 8))[-480:]
    n = len(idx)
    rng = np.random.default_rng(410)
    m = rng.normal(0.0004, 0.008, n)
    leader = rng.normal(0.0003, 0.017, n) + 0.25*m
    follower = np.zeros(n)
    noise = rng.normal(0, 0.006, n)
    for t in range(1, n):
        follower[t] = 0.80*leader[t-1]+0.10*follower[t-1]+0.20*m[t-1]+noise[t]
    leader[-1] = 0.048
    data = {"DEMO_MKT": frame_from_close(100*np.exp(np.cumsum(m)), idx),
            "DEMO_LEAD": frame_from_close(75*np.exp(np.cumsum(leader)), idx),
            "DEMO_FOLLOW": frame_from_close(80*np.exp(np.cumsum(follower)), idx)}
    # Pair formation/validation + current dislocation are separate observations.
    prng = np.random.default_rng(5)
    x = np.log(60) + np.cumsum(prng.normal(0.0003, 0.012, n))
    e = np.zeros(n)
    for t in range(1, n):
        e[t] = 0.83*e[t-1]+prng.normal(0, 0.0025)
    y = 0.2+1.05*x+e
    data["DEMO_B"] = frame_from_close(np.exp(x), idx)
    data["DEMO_A"] = frame_from_close(np.exp(y), idx)
    # Set last two residuals relative to the exact frozen-formation parameters.
    c = cfg["relationships"]["pairs"]
    nt, nv = c["formation_sessions"], c["validation_sessions"]
    start = n-(nt+nv+1)
    xt, yt = x[start:start+nt], y[start:start+nt]
    alpha, beta = np.linalg.lstsq(np.c_[np.ones(nt), xt], yt, rcond=None)[0]
    sd = np.std(yt-alpha-beta*xt, ddof=1)
    y[-2] = alpha+beta*x[-2]+0.4*sd
    y[-1] = alpha+beta*x[-1]-2.5*sd
    data["DEMO_A"] = frame_from_close(np.exp(y), idx)
    # A sharp first sell-off then a slower second sell-off produces higher RSI
    # at a lower confirmed low. The final three closes confirm the second pivot.
    close = np.linspace(70, 75, n)
    knots_x = [n-46, n-26, n-19, n-4, n-3, n-2, n-1]
    knots_y = [75, 40, 53, 38, 41, 43, 45]
    close[n-46:] = np.interp(np.arange(n-46, n), knots_x, knots_y)
    bull = frame_from_close(close, idx)
    # Distinct lows on the close-pivot date (no tied lows from adjacent opens).
    bull["Low"] = np.minimum(bull.Open, bull.Close)-0.2
    bull.loc[idx[n-26], "Low"] -= 0.2
    bull.loc[idx[n-4], "Low"] -= 0.3
    data["DEMO_BULL"] = bull
    close = np.linspace(65, 90, n)+np.sin(np.arange(n)*0.5)*0.15
    close[-1] = 94
    br = frame_from_close(close, idx)
    br.loc[idx[-1], "Volume"] = 4_800_000
    data["DEMO_BREAK"] = br
    stocks = [s for s in data if s != "DEMO_MKT"]
    u = {"stocks": stocks, "symbols": list(data), "market": "DEMO_MKT",
         "meta": {s: {"group": "SYNTHETIC", "benchmark": "DEMO_MKT"} for s in stocks},
         "pairs": [["DEMO_A", "DEMO_B"], ["DEMO_LEAD", "DEMO_FOLLOW"]]}
    return u, data


class DemoProvider:
    def __init__(self, cfg: dict):
        self.universe, self.data = make_demo(cfg)
        self.diagnostics = [{"source": "SYNTHETIC_FIXTURES", "not_live": True}]

    def fetch(self, symbols: list[str], intraday: bool = False) -> dict[str, pd.DataFrame]:
        return {s: pd.DataFrame() if intraday else self.data.get(s, pd.DataFrame()).copy() for s in symbols}
