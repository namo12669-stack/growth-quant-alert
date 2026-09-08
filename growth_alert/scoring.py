from __future__ import annotations

import numpy as np
import pandas as pd

from .factors import FEATURES, finite


def risk_flags(record: dict, cfg: dict) -> list[str]:
    flags = list(record.get("source_warnings", []))
    if not record.get("daily_price_valid"):
        flags.append("STALE_OR_MISSING_DAILY_PRICE")
    age = record.get("statement_age_days")
    if not finite(age):
        flags.append("STATEMENT_UNAVAILABLE")
    elif age < 0 or age > cfg["filters"]["max_statement_age_days"]:
        flags.append("STALE_STATEMENT")
    if not finite(record.get("market_cap")):
        flags.append("MARKET_CAP_UNAVAILABLE")
    if record.get("quote_currency") in (None, ""):
        flags.append("QUOTE_CURRENCY_UNAVAILABLE")
    if finite(record.get("dilution_yoy")) and record["dilution_yoy"] > .10:
        flags.append("DILUTION_OVER_10PCT")
    if finite(record.get("cash_runway_quarters")) and record["cash_runway_quarters"] < 4:
        flags.append("CASH_RUNWAY_UNDER_4Q_PROXY")
    if finite(record.get("volatility_60d")) and record["volatility_60d"] > .65:
        flags.append("HIGH_VOLATILITY")
    if finite(record.get("drawdown_252d")) and record["drawdown_252d"] < -.40:
        flags.append("DEEP_DRAWDOWN")
    if finite(record.get("fcf_margin")) and record["fcf_margin"] < 0:
        flags.append("NEGATIVE_FCF")
    if record.get("sector") == "Unknown":
        flags.append("UNKNOWN_SECTOR")
    if not finite(record.get("eps_revision_30d")):
        flags.append("EPS_REVISION_UNAVAILABLE_OR_NONPOSITIVE_BASE")
    else:
        flags.append("EPS_PERIOD_ROLLOVER_NOT_INDEPENDENTLY_VERIFIED")
    return sorted(set(flags))


def exclusions(record: dict, cfg: dict) -> list[str]:
    """Hard blocks only. Missing fundamentals are handled by coverage, not fabricated."""
    f = cfg["filters"]
    reasons = []
    if not finite(record.get("previous_close")) or record["previous_close"] < f["min_price_usd"]:
        reasons.append("PREVIOUS_CLOSE_FILTER")
    if not finite(record.get("dollar_volume_20d")) or record["dollar_volume_20d"] < f["min_dollar_volume_20d"]:
        reasons.append("DOLLAR_VOLUME_20D_FILTER")
    # Unknown market cap/currency is a data warning, not an automatic exclusion.
    if finite(record.get("market_cap")) and record["market_cap"] < f["min_market_cap_usd"]:
        reasons.append("MARKET_CAP_FILTER")
    if record.get("quote_currency") not in (None, "", "USD"):
        reasons.append("QUOTE_CURRENCY_NOT_USD")
    if not record.get("daily_price_valid"):
        reasons.append("DAILY_PRICE_NOT_CURRENT")
    age = record.get("statement_age_days")
    if finite(age) and not 0 <= age <= f["max_statement_age_days"]:
        reasons.append("STATEMENT_NOT_CURRENT")
    if record.get("sector") in f["excluded_sectors"]:
        reasons.append("EXCLUDED_SECTOR")
    # If growth is known and below the configured threshold, it fails the growth-universe definition.
    if finite(record.get("revenue_yoy")) and record["revenue_yoy"] < f["min_revenue_yoy"]:
        reasons.append("REVENUE_YOY_FILTER")
    if finite(record.get("cash_runway_quarters")) and record["cash_runway_quarters"] < 4:
        reasons.append("CASH_RUNWAY_BLOCK")
    return reasons


def percentile(value: float, pool: pd.Series) -> float:
    values = pd.to_numeric(pool, errors="coerce").dropna()
    if len(values) < 2 or not finite(value):
        return 50.0
    less = int((values < value).sum())
    equal = int((values == value).sum())
    return float(100 * (less + (equal - 1) / 2) / (len(values) - 1))


def _confidence(coverage: float, cfg: dict) -> str:
    if coverage >= cfg["scoring"].get("high_confidence_coverage", .80):
        return "HIGH"
    if coverage >= cfg["scoring"].get("medium_confidence_coverage", .60):
        return "MEDIUM"
    if coverage >= cfg["filters"]["min_score_coverage"]:
        return "LOW"
    return "INSUFFICIENT"


def score_records(records: list[dict], cfg: dict) -> list[dict]:
    if not records:
        return []
    all_records = []
    for original in records:
        item = dict(original)
        item["flags"] = risk_flags(item, cfg)
        item["exclusions"] = exclusions(item, cfg)
        all_records.append(item)

    # Ranking peers pass only hard market/risk blocks. Low factor coverage is evaluated after scoring.
    peers = pd.DataFrame([r for r in all_records if not r["exclusions"]])
    min_peers = cfg["scoring"]["min_peers"]
    for item in all_records:
        coverage = 0.0
        raw_score = 0.0
        contributions = []
        item["factor_scores"] = {}
        item["ranking_scopes"] = {}
        for family, features in FEATURES.items():
            family_score = 0.0
            for feature, internal_weight in features.items():
                valid = pd.DataFrame()
                scope = "unavailable"
                if not peers.empty and feature in peers and finite(item.get(feature)) and not item["exclusions"]:
                    valid = peers.loc[pd.to_numeric(peers[feature], errors="coerce").notna()]
                    same_sector = valid.loc[(valid["sector"] == item.get("sector")) & (valid["sector"] != "Unknown")]
                    if len(same_sector) >= min_peers:
                        valid, scope = same_sector, "sector"
                    elif family == "valuation":
                        valid = pd.DataFrame()
                    elif len(valid) >= min_peers:
                        scope = "growth_universe_fallback"
                    else:
                        valid = pd.DataFrame()
                usable = not valid.empty
                subscore = percentile(item.get(feature), valid[feature]) if usable else 50.0
                w = internal_weight * cfg["scoring"]["family_weights"][family]
                if usable:
                    coverage += w
                family_score += internal_weight * subscore
                item["factor_scores"][feature] = round(subscore, 2)
                item["ranking_scopes"][feature] = scope if usable else "unavailable_neutral"
                if usable:
                    contributions.append((w * (subscore - 50), feature))
            item[family + "_score"] = round(family_score, 2)
            raw_score += cfg["scoring"]["family_weights"][family] * family_score
        item["coverage"] = round(coverage, 4)
        item["confidence"] = _confidence(coverage, cfg)
        item["raw_score"] = round(raw_score, 2)
        item["score"] = round(max(0.0, raw_score - cfg["scoring"]["missing_penalty"] * (1 - coverage)), 2)
        item["drivers"] = [f for contribution, f in sorted(contributions, reverse=True)[:3] if contribution > 0]
        if coverage < cfg["filters"]["min_score_coverage"]:
            item["exclusions"].append("LOW_FACTOR_COVERAGE")
        if len(peers) < cfg["filters"]["min_rank_pool"]:
            item["exclusions"].append("INSUFFICIENT_RANK_POOL")
        item["eligible"] = not item["exclusions"]
        if not item["eligible"]:
            item["score"] = None
    return sorted(all_records, key=lambda r: (not r["eligible"], -(r["score"] or 0), r["symbol"]))
