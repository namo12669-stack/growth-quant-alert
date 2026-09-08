from __future__ import annotations

import re
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml


def load_config(path: str | Path = "config.yaml") -> dict:
    with Path(path).open(encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)
    required = {"model_version", "calendar", "display_timezone", "benchmark",
                "schedule", "filters", "scoring", "alerts", "data"}
    if not isinstance(cfg, dict) or not required.issubset(cfg):
        raise ValueError("Configuration is missing a required section")
    weights = cfg["scoring"]["family_weights"]
    expected = {"growth", "quality", "expectations", "momentum", "valuation"}
    if set(weights) != expected or abs(sum(weights.values()) - 1) > 1e-9:
        raise ValueError("The five family weights must total 1.0")
    if any(not isinstance(w, (int, float)) or w < 0 for w in weights.values()):
        raise ValueError("Family weights must be nonnegative numbers")
    ZoneInfo(cfg["display_timezone"])
    if cfg["schedule"]["earliest_minutes_before"] <= cfg["schedule"]["latest_minutes_before"]:
        raise ValueError("The schedule window is reversed")
    if not 0 <= cfg["filters"]["min_score_coverage"] <= 1:
        raise ValueError("min_score_coverage must be in [0, 1]")
    if not 0 <= cfg["alerts"]["min_score"] <= 100:
        raise ValueError("min_score must be in [0, 100]")
    if not 1 <= cfg["alerts"]["top_n"] <= 20:
        raise ValueError("top_n must be between 1 and 20")
    return cfg


def load_universe(path: str | Path = "universe.yaml") -> dict[str, list[str]]:
    with Path(path).open(encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    out: dict[str, list[str]] = {}
    seen: set[str] = set()
    for group in ("core", "speculative"):
        out[group] = []
        for symbol in raw.get(group, []):
            symbol = str(symbol).strip().upper()
            if not re.fullmatch(r"[A-Z][A-Z0-9.-]{0,11}", symbol):
                raise ValueError(f"Invalid ticker: {symbol!r}")
            if symbol not in seen:
                out[group].append(symbol)
                seen.add(symbol)
    if not out["core"]:
        raise ValueError("At least one core ticker is required")
    return out
