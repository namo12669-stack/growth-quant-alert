from __future__ import annotations
from pathlib import Path
import re
import yaml


def load_config(path: str = "config.yaml") -> dict:
    cfg = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(cfg, dict) or not str(cfg.get("model", "")).startswith("quant-signals-v2"):
        raise ValueError("V2 config.yaml is required. Replace V1 files, including main.py and config.yaml.")
    for key in ("quality", "signals", "relationships", "provider", "alerts", "schedule", "calendar"):
        if key not in cfg:
            raise ValueError(f"Missing config key: {key}")
    q, sig = cfg["quality"], cfg["signals"]
    if not 0 < q["min_universe_fraction"] <= 1 or not 0 < q["min_completeness"] <= 1:
        raise ValueError("Quality fractions must be in (0,1]")
    if q["min_daily_bars"] < 65 or cfg["alerts"]["max_signals"] < 1:
        raise ValueError("min_daily_bars must be >=65 and max_signals >=1")
    d = sig["divergence"]
    if min(d["pivot_left"], d["pivot_right"]) < 1 or d["min_pivot_gap"] > d["max_pivot_gap"]:
        raise ValueError("Invalid confirmed-pivot parameters")
    if sig["intraday_breakout"]["interval_minutes"] != 15:
        raise ValueError("V2 supports 15-minute intraday bars only")
    if cfg["relationships"]["correction"] not in {"fdr_by", "fdr_bh", "bonferroni"}:
        raise ValueError("Unknown multiple-testing correction")
    if cfg["provider"]["batch_size"] < 1 or cfg["provider"]["threads"] < 1:
        raise ValueError("Provider batch size and threads must be positive")
    if not 0 <= cfg["schedule"]["latest_minutes_before"] < cfg["schedule"]["earliest_minutes_before"]:
        raise ValueError("Invalid schedule window")
    pair = cfg["relationships"]["pairs"]
    lag = cfg["relationships"]["lead_lag"]
    if pair["formation_sessions"] < 126 or pair["validation_sessions"] < 40:
        raise ValueError("Pair models require >=126 formation and >=40 validation sessions")
    if lag["initial_train"] < 126 or lag["validation_sessions"] < 40:
        raise ValueError("Lead-lag models require >=126 training and >=40 validation sessions")
    if not 0 < pair["entry_z"] < pair["max_z"]:
        raise ValueError("Invalid pair Z thresholds")
    return cfg


def load_universe(path: str = "universe.yaml") -> dict:
    u = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    members, meta = [], {}
    for name, g in u["groups"].items():
        for s in g["symbols"]:
            s = str(s).upper()
            if s in meta:
                raise ValueError(f"Duplicate stock: {s}")
            meta[s] = {"group": name, "benchmark": str(g["benchmark"]).upper()}
            members.append(s)
    if not members:
        raise ValueError("Universe must contain at least one stock")
    pairs, seen = [], set()
    for pair in u.get("relationship_candidates", []):
        if len(pair) != 2 or pair[0] == pair[1] or not set(pair) <= set(members):
            raise ValueError(f"Invalid relationship candidate: {pair}")
        key = tuple(sorted(pair))
        if key in seen:
            raise ValueError(f"Duplicate relationship candidate: {pair}")
        seen.add(key)
        pairs.append(pair)
    all_symbols = sorted(set(members) | {m["benchmark"] for m in meta.values()} | {u["market_benchmark"]})
    if any(not re.fullmatch(r"[A-Z0-9.^=-]{1,20}", s) for s in all_symbols):
        raise ValueError("Invalid symbol syntax")
    return {"stocks": members, "meta": meta, "symbols": all_symbols,
            "pairs": pairs, "market": u["market_benchmark"]}
