from __future__ import annotations

from datetime import datetime

from .factors import finite


def choose_alerts(ranked: list[dict], state: dict, mode: str, now: datetime, cfg: dict) -> list[dict]:
    selected = []
    sectors: dict[str, int] = {}
    settings = cfg["alerts"]
    for record in ranked:
        if not record.get("eligible") or record["score"] < settings["min_score"]:
            continue
        symbol = record["symbol"]
        previous = state.get("last_alerts", {}).get(f"{mode}:{symbol}")
        triggers = []
        score_change = record["score"] - previous["score"] if previous else None
        if not previous:
            triggers.append("NEW_QUALIFIED_CANDIDATE")
        elif score_change >= settings["min_score_change"]:
            triggers.append("SCORE_IMPROVING")
        fresh = record.get("intraday_available", False)
        change = record.get("session_return")
        if fresh and finite(change):
            if mode == "preopen" and change >= settings["premarket_gap_up"]:
                triggers.append("PREMARKET_GAP_UP")
            if mode == "preopen" and change <= settings["premarket_gap_down"]:
                triggers.append("GAP_DOWN_REVIEW_RISK")
            if mode in ("preclose", "manual"):
                rvol = record.get("rvol_same_time")
                if change >= settings["intraday_return"] and finite(rvol) and rvol >= settings["min_rvol"]:
                    triggers.append("POSITIVE_MOVE_WITH_RVOL")
                high = record.get("prior_52w_high")
                if finite(high) and record.get("intraday_price", 0) >= high:
                    triggers.append("AT_OR_ABOVE_PRIOR_52W_HIGH")
        if previous:
            age = (now - datetime.fromisoformat(previous["at"])).total_seconds() / 86400
            novel = set(triggers) - set(previous.get("triggers", []))
            if age >= settings["repeat_after_days"]:
                triggers.append("PERIODIC_REVIEW")
            elif not novel and (score_change is None or score_change < settings["min_score_change"]):
                continue
        if not triggers:
            continue
        sector = record.get("sector", "Unknown")
        if sectors.get(sector, 0) >= settings["max_alerts_per_sector"]:
            continue
        out = dict(record)
        out["triggers"] = triggers
        out["score_change_since_alert"] = score_change
        selected.append(out)
        sectors[sector] = sectors.get(sector, 0) + 1
        if len(selected) >= settings["top_n"]:
            break
    return selected


def choose_speculative(records: list[dict], cfg: dict) -> list[dict]:
    result = []
    for item in records:
        if not item.get("intraday_available") or not item.get("daily_price_valid"):
            continue
        change = item.get("session_return")
        if not finite(change) or abs(change) < .04:
            continue
        if not finite(item.get("dollar_volume_20d")) or item["dollar_volume_20d"] < cfg["filters"]["min_dollar_volume_20d"]:
            continue
        if not finite(item.get("intraday_price")) or item["intraday_price"] < cfg["filters"]["min_price_usd"]:
            continue
        result.append(item)
    return sorted(result, key=lambda x: -abs(x["session_return"]))[:cfg["alerts"]["speculative_top_n"]]
