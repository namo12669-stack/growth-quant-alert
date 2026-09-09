"""Descriptive forward event study of delivered V2 alerts, NOT a trading backtest."""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
from datetime import datetime, date
import numpy as np
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from quant_alert.calendar import NY, session_for, next_session_day, session_dates
from quant_alert.provider import CSVProvider
from quant_alert.config import load_universe
from quant_alert.storage import write_json


def entry_session(observed: datetime) -> date:
    day = observed.astimezone(NY).date()
    session = session_for(day)
    # A pre-open alert can be studied at that day's open. During/after session
    # alerts use the NEXT session's open; no fill at a price known before alert.
    return day if session and observed < session.open else next_session_day(day)


def normalize_prices(f: pd.DataFrame) -> pd.DataFrame:
    f = f.copy()
    idx = pd.DatetimeIndex(f.index)
    if idx.tz is not None:
        idx = idx.tz_convert(NY).tz_localize(None)
    f.index = idx.normalize()
    return f.sort_index().loc[lambda x: ~x.index.duplicated(keep="last")]


def evaluate(records: list[dict], prices: dict, benchmark: str = "QQQ", horizons=(1, 5, 20)) -> pd.DataFrame:
    prices = {s: normalize_prices(f) for s, f in prices.items() if not f.empty}
    rows = []
    used = set()
    for r in records:
        if r.get("signal_id") in used:
            continue
        used.add(r["signal_id"])
        observed = datetime.fromisoformat(r["observed_at"])
        start = pd.Timestamp(entry_session(observed))
        for h in horizons:
            row = {"id": r["signal_id"], "kind": r["kind"], "symbols": "/".join(r["symbols"]),
                   "observed_at": r["observed_at"], "horizon_sessions": h, "entry_session": str(start.date()),
                   "status": "PENDING_OR_MISSING_DATA"}
            symbols = r["symbols"]
            selected = symbols[-1] if r["kind"] == "LEAD_LAG" else symbols[0]
            f = prices.get(selected)
            if f is None or start not in f.index:
                rows.append(row)
                continue
            sessions = session_dates(start.date(), f.index[-1].date())
            if len(sessions) < h:
                rows.append(row)
                continue
            end = sessions[h-1]
            needed = sessions[:h]
            if not needed.isin(f.index).all():
                rows.append(row)
                continue
            if r["kind"] == "PAIR_SPREAD":
                a, b = (prices.get(s) for s in symbols)
                beta = float(r["metrics"]["beta"])
                if a is None or b is None or not needed.isin(a.index).all() or not needed.isin(b.index).all():
                    rows.append(row)
                    continue
                delta = float(np.log(a.loc[end, "Close"]/a.loc[start, "Open"])
                              - beta*np.log(b.loc[end, "Close"]/b.loc[start, "Open"]))
                sign = -1 if r["metrics"]["zscore"] > 0 else 1
                row.update(metric="directional_frozen_log_spread_change_NOT_PORTFOLIO_RETURN", value=sign*delta)
            else:
                change = float(f.loc[end, "Close"]/f.loc[start, "Open"]-1)
                sign = -1 if r["direction"] == "bearish" else 1
                row.update(metric="directional_open_to_close_return_proxy", value=sign*change, raw_return=change)
                b = prices.get(benchmark)
                if b is not None and start in b.index and end in b.index:
                    br = float(b.loc[end, "Close"]/b.loc[start, "Open"]-1)
                    row.update(benchmark_return=br, directional_excess_return=sign*(change-br))
            row.update(status="OBSERVED", exit_session=str(end.date()))
            rows.append(row)
    columns = ["id", "kind", "symbols", "observed_at", "horizon_sessions",
               "entry_session", "status", "metric", "value", "raw_return",
               "benchmark_return", "directional_excess_return", "exit_session"]
    return pd.DataFrame(rows, columns=columns)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--journal", default="state_v2/journal.jsonl")
    p.add_argument("--prices", required=True, help="Directory containing SYMBOL_daily.csv snapshots")
    p.add_argument("--benchmark", help="Defaults to market_benchmark in universe.yaml")
    p.add_argument("--out", default="output/evaluation")
    args = p.parse_args()
    args.benchmark = args.benchmark or load_universe()["market"]
    records = [json.loads(line) for line in Path(args.journal).read_text().splitlines() if line.strip()]
    symbols = sorted({s for r in records for s in r["symbols"]} | {args.benchmark})
    prices = CSVProvider(args.prices).fetch(symbols)
    results = evaluate(records, prices, args.benchmark)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    results.to_csv(out/"forward_outcomes.csv", index=False)
    stats = []
    if not results.empty:
        available = results.loc[results.status == "OBSERVED"]
        for (kind, horizon, metric), g in available.groupby(["kind", "horizon_sessions", "metric"]):
            stats.append({"kind": kind, "horizon": int(horizon), "metric": metric, "n": len(g),
                          "mean": float(g.value.mean()), "median": float(g.value.median()),
                          "fraction_positive": float((g.value > 0).mean()),
                          "sample_label": "SMALL_SAMPLE" if len(g) < 30 else "DESCRIPTIVE_ONLY"})
    write_json(out/"summary.json", {"note": "Not a trading backtest: no spreads, slippage, fees, borrow costs, delistings, or execution model. Overlapping alerts are not independent. Hypothesis forecasts and entry-return proxies are different targets.",
                                    "stats": stats, "records": len(records)})
    print(f"Wrote {out}/forward_outcomes.csv; unavailable future observations stay pending.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
