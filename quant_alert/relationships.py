from __future__ import annotations
import math
import warnings
from datetime import date
import numpy as np
import pandas as pd
import statsmodels.api as sm
from statsmodels.stats.multitest import multipletests
from statsmodels.tsa.stattools import adfuller, coint
from .calendar import next_session_day, session_dates
from .models import Signal


def _align(data: dict[str, pd.DataFrame], symbols: list[str], rows: int, calendar: str) -> pd.DataFrame:
    if any(s not in data or data[s].empty for s in symbols):
        raise ValueError("MISSING_OR_REJECTED_PRICE_DATA")
    end = data[symbols[0]].index[-1]
    if any(data[s].index[-1] != end for s in symbols):
        raise ValueError("UNALIGNED_LAST_SESSION")
    f = pd.concat({s: data[s].Close for s in symbols}, axis=1).tail(rows)
    if len(f) != rows or f.isna().any().any():
        raise ValueError("INSUFFICIENT_ALIGNED_HISTORY")
    expected = session_dates(f.index[0].date(), f.index[-1].date(), calendar)
    if not f.index.equals(expected):
        raise ValueError("GAPS_IN_RELATIONSHIP_HISTORY")
    if (f <= 0).any().any() or not np.isfinite(f).all().all():
        raise ValueError("INVALID_RELATIONSHIP_PRICES")
    return np.log(f)


def _adf(series: np.ndarray) -> float:
    a = np.asarray(series, dtype=float)
    if len(a) < 30 or np.std(a) < 1e-10:
        return 1.0
    return float(adfuller(a, maxlag=5, autolag="AIC", regression="c")[1])


def _ols(y: np.ndarray, x: np.ndarray, hac: int | None = None):
    if np.linalg.matrix_rank(x) < x.shape[1] or np.linalg.cond(x) > 1e9:
        raise ValueError("DEGENERATE_DESIGN_MATRIX")
    model = sm.OLS(y, x)
    return model.fit(cov_type="HAC", cov_kwds={"maxlags": hac}) if hac is not None else model.fit()


def _base_row(engine: str, a: str, b: str) -> dict:
    return {"engine": engine, "a": a, "b": b, "raw_p": 1.0,
            "model_gates_pass": False, "trigger_gates_pass": False, "reject_reasons": []}


def inspect_pair(a: str, b: str, data: dict, cfg: dict) -> dict:
    c = cfg["relationships"]["pairs"]
    row = _base_row("pair_spread", a, b)
    nt, nv = c["formation_sessions"], c["validation_sessions"]
    try:
        logs = _align(data, [a, b], nt+nv+1, cfg["calendar"])
        train, val = logs.iloc[:nt], logs.iloc[nt:-1]
        y, x = train[a].to_numpy(), train[b].to_numpy()
        fit = _ols(y, sm.add_constant(x))
        alpha, beta = map(float, fit.params)
        residual = y - alpha - beta*x
        sigma = float(np.std(residual, ddof=1))
        if sigma < 1e-5:
            raise ValueError("NEAR_DEGENERATE_PAIR_SPREAD")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            stat, p, _ = coint(y, x, trend="c", maxlag=5, autolag="aic")
        if not np.isfinite(stat) or not np.isfinite(p):
            raise ValueError("UNSTABLE_COINTEGRATION_TEST")
        level_a, level_b = _adf(y), _adf(x)
        diff_a, diff_b = _adf(np.diff(y)), _adf(np.diff(x))
        phi = float(_ols(residual[1:], sm.add_constant(residual[:-1])).params[1])
        half = -math.log(2)/math.log(phi) if 0 < phi < 1 else float("inf")
        hold = val[a].to_numpy() - alpha - beta*val[b].to_numpy()
        hold_p = _adf(hold)
        hold_std_ratio = float(np.std(hold, ddof=1)/sigma)
        val_beta = float(_ols(val[a].to_numpy(), sm.add_constant(val[b].to_numpy())).params[1])
        beta_drift = abs(val_beta-beta)/max(abs(beta), 1e-8)
        mean_shift = abs(float(np.mean(hold)-np.mean(residual)))/sigma
        z = float((logs[a].iloc[-1]-alpha-beta*logs[b].iloc[-1]-np.mean(residual))/sigma)
        prev_z = float((hold[-1]-np.mean(residual))/sigma)
        gates = {
            "POSITIVE_REASONABLE_BETA": 0.1 < beta < 5.0,
            "I1_LEVEL_SCREEN": min(level_a, level_b) >= c["i1_level_min_p"],
            "STATIONARY_DIFFERENCES": max(diff_a, diff_b) <= c["diff_stationarity_max_p"],
            "HALF_LIFE_RANGE": c["half_life_min"] <= half <= c["half_life_max"],
            "HOLDOUT_STATIONARITY": hold_p <= c["validation_adf_max_p"],
            "BETA_STABILITY": beta_drift <= c["max_beta_drift"],
            "HOLDOUT_VARIANCE_STABILITY": c["min_validation_std_ratio"] <= hold_std_ratio <= c["max_validation_std_ratio"],
            "HOLDOUT_MEAN_STABILITY": mean_shift <= 1.0,
        }
        row.update(raw_p=float(p), alpha=alpha, beta=beta, sigma=sigma, zscore=z, previous_zscore=prev_z,
                   half_life_sessions=half, level_adf_a=level_a, level_adf_b=level_b,
                   diff_adf_a=diff_a, diff_adf_b=diff_b, holdout_adf_p=hold_p,
                   holdout_std_ratio=hold_std_ratio, beta_drift=beta_drift, holdout_mean_shift_sigma=mean_shift,
                   formation_end=str(train.index[-1].date()), validation_end=str(val.index[-1].date()),
                   formation_sessions=nt, validation_sessions=nv, asof=str(logs.index[-1].date()),
                   model_gates_pass=all(gates.values()),
                   trigger_gates_pass=bool(c["entry_z"] <= abs(z) <= c["max_z"] and abs(prev_z) < c["entry_z"]),
                   reject_reasons=[k for k, v in gates.items() if not v])
    except (ValueError, np.linalg.LinAlgError, ZeroDivisionError) as exc:
        row["reject_reasons"] = [str(exc) if isinstance(exc, ValueError) else type(exc).__name__]
    return row


def inspect_lead_lag(leader: str, follower: str, market: str, data: dict, cfg: dict) -> dict:
    """One predeclared lag: leader[t] forecasts follower[t+1].

    Baseline = intercept + lagged follower + lagged market. Full adds lagged
    leader. Each validation prediction is made using ONLY earlier observations.
    No contemporaneous close is used to predict itself, no best-lag search.
    """
    c = cfg["relationships"]["lead_lag"]
    row = _base_row("lead_lag", leader, follower)
    n0, nv = c["initial_train"], c["validation_sessions"]
    try:
        logs = _align(data, [leader, follower, market], n0+nv+2, cfg["calendar"])
        returns = logs.diff()
        z = pd.DataFrame({"y": returns[follower], "f": returns[follower].shift(1),
                          "m": returns[market].shift(1), "l": returns[leader].shift(1)}).iloc[2:]
        if z.isna().any().any():
            raise ValueError("MISSING_RETURN_OBSERVATIONS")
        y = z.y.to_numpy()
        xb = np.column_stack([np.ones(len(z)), z.f, z.m])
        xf = np.column_stack([xb, z.l])
        predictions, base_predictions, coefficients = [], [], []
        for i in range(n0, len(z)):
            fb, ff = _ols(y[:i], xb[:i]), _ols(y[:i], xf[:i])
            predictions.append(float(xf[i] @ ff.params))
            base_predictions.append(float(xb[i] @ fb.params))
            coefficients.append(float(ff.params[-1]))
        actual = y[n0:]
        pred, base = np.array(predictions), np.array(base_predictions)
        mse = float(np.mean((actual-pred)**2))
        bmse = float(np.mean((actual-base)**2))
        improvement = 1 - mse/bmse if bmse > 1e-14 else -1.0
        increments, errors_base = pred-base, actual-base
        corr = float(np.corrcoef(increments, errors_base)[0, 1]) if min(np.std(increments), np.std(errors_base)) > 1e-10 else 0.0
        final, baseline = _ols(y, xf, c["hac_lags"]), _ols(y, xb)
        xb_next = np.array([1, returns[follower].iloc[-1], returns[market].iloc[-1]])
        xf_next = np.r_[xb_next, returns[leader].iloc[-1]]
        estimated_log, baseline_log = float(xf_next@final.params), float(xb_next@baseline.params)
        projected = float(np.expm1(estimated_log))
        incremental = projected-float(np.expm1(baseline_log))
        beta, p = float(final.params[-1]), float(final.pvalues[-1])
        if not np.isfinite([beta, p, projected, corr]).all():
            raise ValueError("NONFINITE_LEAD_LAG_ESTIMATE")
        sign_fraction = float(np.mean(np.array(coefficients) > 0))
        feature_z = np.abs((xf_next[1:]-xf[:, 1:].mean(axis=0))/np.maximum(xf[:, 1:].std(axis=0, ddof=1), 1e-8))
        leader_return = float(np.expm1(returns[leader].iloc[-1]))
        gates = {"POSITIVE_LEADER_COEFFICIENT": beta > 0,
                 "OOS_MSE_IMPROVEMENT": improvement >= c["min_oos_mse_improvement"],
                 "OOS_INCREMENTAL_CORRELATION": corr >= c["min_oos_correlation"],
                 "COEFFICIENT_SIGN_STABILITY": sign_fraction >= c["min_positive_coefficient_fraction"],
                 "NO_EXTREME_EXTRAPOLATION": float(max(feature_z)) <= 5.0}
        row.update(raw_p=p, beta=beta, market=market, validation_sessions=nv, train_sessions=n0,
                   oos_mse_improvement=improvement, oos_incremental_correlation=corr,
                   oos_rmse_log_return=math.sqrt(mse), positive_coefficient_fraction=sign_fraction,
                   max_current_feature_z=float(max(feature_z)), leader_return=leader_return,
                   predicted_return=projected, baseline_return=float(np.expm1(baseline_log)),
                   incremental_return=incremental, asof=str(logs.index[-1].date()),
                   target_session=str(next_session_day(logs.index[-1].date(), cfg["calendar"])),
                   model_gates_pass=all(gates.values()),
                   trigger_gates_pass=bool(leader_return >= c["min_leader_return"]
                       and projected >= c["min_predicted_return"] and incremental >= c["min_incremental_return"]),
                   reject_reasons=[k for k, v in gates.items() if not v])
    except (ValueError, np.linalg.LinAlgError, ZeroDivisionError) as exc:
        row["reject_reasons"] = [str(exc) if isinstance(exc, ValueError) else type(exc).__name__]
    return row


def correct_family(rows: list[dict], cfg: dict, family: str) -> list[dict]:
    """Includes every configured hypothesis, assigning missing tests p=1.

    BY handles arbitrary dependence under valid marginal p-values. It does not
    correct repeated scans over time, nonstationarity, or configuration tuning.
    """
    if not rows:
        return rows
    method = cfg["relationships"]["correction"]
    p = [min(1.0, max(0.0, float(r.get("raw_p", 1.0)))) for r in rows]
    corrected = multipletests(p, method=method)[1]
    alpha = cfg["relationships"][family]["max_adjusted_p"]
    for r, q in zip(rows, corrected):
        r.update(adjusted_p=float(q), correction=method, family_tests=len(rows))
        passes = bool(r["model_gates_pass"] and q <= alpha)
        r["validated_screen_pass"] = passes
        r["status"] = "DETECTED" if passes and r["trigger_gates_pass"] else "PASSED_NO_TRIGGER" if passes else "REJECTED"
        if q > alpha:
            r["reject_reasons"].append("MULTIPLE_TESTING_THRESHOLD")
    return rows


def relationship_signals(data: dict, universe: dict, cfg: dict) -> tuple[list[Signal], list[dict]]:
    signals, audit = [], []
    if cfg["relationships"]["pairs"]["enabled"]:
        rows = correct_family([inspect_pair(a, b, data, cfg) for a, b in universe["pairs"]], cfg, "pairs")
        audit.extend(rows)
        for r in rows:
            if r["status"] != "DETECTED":
                continue
            a, b, z = r["a"], r["b"], r["zscore"]
            low = a if z < 0 else b
            signals.append(Signal("PAIR_SPREAD", [a, b], "relative_dislocation", "1D frozen-formation model",
                r["asof"], r["asof"],
                [f"log({a}) - {r['beta']:.3f}*log({b}) - intercept: Z={z:+.2f}; newly crossed threshold",
                 f"Cointegration adjusted p={r['adjusted_p']:.4g}; {r['validation_sessions']} held-out sessions passed stability screens",
                 f"{low} is relatively lower under this model; estimated half-life {r['half_life_sessions']:.1f} sessions"],
                r, priority="WATCH", horizon="Relative spread only; no absolute-return forecast",
                caution="EXPERIMENTAL RELATIVE VALUE. Correlation is not cointegration; statistical screens do not guarantee reversion. Either leg may fall. No short order or hedge is placed."))
    if cfg["relationships"]["lead_lag"]["enabled"]:
        rows = []
        for a, b in universe["pairs"]:
            rows.extend([inspect_lead_lag(a, b, universe["market"], data, cfg),
                         inspect_lead_lag(b, a, universe["market"], data, cfg)])
        rows = correct_family(rows, cfg, "lead_lag")
        audit.extend(rows)
        for r in rows:
            if r["status"] != "DETECTED":
                continue
            signals.append(Signal("LEAD_LAG", [r["a"], r["b"]], "bullish_follower", "1D / 1-session lag",
                r["asof"], r["asof"],
                [f"{r['a']} return {r['leader_return']:+.1%}; model estimates {r['b']} next-session return {r['predicted_return']:+.1%}",
                 f"Increment over own-lag/{r['market']}-lag baseline {r['incremental_return']:+.1%}; target {r['target_session']}",
                 f"Walk-forward MSE improvement {r['oos_mse_improvement']:.1%}; adjusted p={r['adjusted_p']:.4g}",
                 f"Held-out RMSE {r['oos_rmse_log_return']:.1%} (log return), not a probability interval"],
                r, priority="WATCH", horizon="Next session close-to-close, NOT an intraday timing signal",
                caution="EXPERIMENTAL conditional estimate, not causality or a guaranteed catch-up. Only sent before the target session starts. News/fundamentals NOT checked."))
    return signals, audit
