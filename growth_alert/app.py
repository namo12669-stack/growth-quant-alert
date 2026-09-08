from __future__ import annotations

import argparse
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from . import __version__
from .alerts import choose_alerts, choose_speculative
from .calendar import NY, due_mode
from .config import load_config, load_universe
from .demo import demo_records
from .factors import financial_features, price_features, finite
from .intraday import intraday_features
from .provider import YahooProvider
from .report import build_message, write_outputs
from .scoring import score_records
from .storage import append_journal, load_state, save_state, write_json
from .telegram import TelegramClient, TelegramError

LOG = logging.getLogger(__name__)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def run(cfg: dict, universe: dict, mode: str = "auto", dry_run: bool = False,
        provider=None, messenger=None, clock: Callable[[], datetime] = utcnow) -> dict:
    started = clock()
    runtime_start = time.monotonic()
    demo = mode == "demo"
    session = None
    if mode == "auto":
        resolved, session = due_mode(started, cfg)
        if resolved is None:
            LOG.info("SKIP: outside a valid pre-open/pre-close window or a market holiday")
            return {"status": "skipped", "reason": "calendar_or_time"}
        mode = resolved
    elif mode not in ("manual", "demo"):
        raise ValueError("Use auto, manual, or demo")
    state_path = Path(cfg["data"]["state_dir"]) / "state.json"
    restored = state_path.exists()
    state = load_state(cfg["data"]["state_dir"]) if not demo else {"sent_sessions": {}, "last_alerts": {}, "last_scores": {}}
    session_key = f"{started.astimezone(NY).date()}:{mode}"
    if mode in ("preopen", "preclose") and session_key in state["sent_sessions"]:
        LOG.info("SKIP: this session was already sent successfully")
        return {"status": "skipped", "reason": "already_sent"}
    if not dry_run and messenger is None:
        messenger = TelegramClient.from_env()
    meta = {"as_of": started.isoformat(), "started_at": started.isoformat(), "mode": mode,
            "demo": demo, "requested": len(universe["core"]), "usable": 0, "fundamental_usable": 0, "eligible": 0,
            "state_restored": restored, "errors": [], "version": __version__,
            "market_context": "UNAVAILABLE", "data_degraded": False,
            "score_as_of": "last completed regular session; fundamentals fetched during scan"}
    records, speculative = [], []
    if demo:
        records = demo_records(started, cfg)
        meta.update(requested=len(records), usable=len(records), fundamental_usable=len(records), market_context="SYNTHETIC - NO LIVE MARKET OBSERVATION")
        ranked = score_records(records, cfg)
    else:
        provider = provider or YahooProvider(cfg, clock)
        # Price-first architecture: one batch request prevents 40 sequential Yahoo
        # history calls from exhausting/throttling a shared GitHub Actions IP.
        daily_map = {}
        if hasattr(provider, "batch_daily"):
            try:
                daily_map = provider.batch_daily([cfg["benchmark"], *universe["core"]])
            except Exception as exc:
                meta["errors"].append(f"BATCH_PRICE:{type(exc).__name__}")
        try:
            bench_prices = daily_map.get(cfg["benchmark"])
            if bench_prices is None or bench_prices.empty:
                bench_prices = provider.daily(cfg["benchmark"])
            bench = price_features(bench_prices, started, cfg["calendar"])
            if bench.get("daily_price_valid") and bench.get("above_sma200") is not None:
                condition = "ABOVE" if bench["above_sma200"] else "BELOW"
                meta["market_context"] = f"{cfg['benchmark']} {condition} 200-day SMA on {bench['price_date']} (context only)"
        except Exception as exc:
            meta["errors"].append(f"BENCHMARK:{type(exc).__name__}")
        price_failures = {}
        for index, symbol in enumerate(universe["core"], 1):
            if time.monotonic() - runtime_start > cfg["alerts"]["max_run_minutes"] * 60:
                raise RuntimeError("Scan exceeded its freshness budget; candidate alerts withheld")
            try:
                prices = daily_map.get(symbol)
                if prices is None or prices.empty:
                    # Retry only the symbols absent from the batch.
                    prices = provider.daily(symbol)
                pf = price_features(prices, started, cfg["calendar"])
                if not pf.get("daily_price_valid"):
                    price_failures[symbol] = f"LAST_DATE={pf.get('price_date') or 'NONE'}"
                # Fetch fundamentals after price acquisition; missing fundamentals are
                # allowed and reduce factor coverage rather than suppressing price data.
                financial = provider.fundamentals(symbol)
                record = {"symbol": symbol, **financial_features(financial, clock()), **pf}
                if record.get("daily_price_valid"):
                    meta["usable"] += 1
                if record.get("statement_period") and any(finite(record.get(k)) for k in ("revenue_yoy", "operating_margin_change", "gross_profit_assets", "cfo_assets")):
                    meta["fundamental_usable"] += 1
                records.append(record)
                LOG.info("Scanned %s (%d/%d)", symbol, index, len(universe["core"]))
            except Exception as exc:
                records.append({"symbol": symbol, "sector": "Unknown", "source_warnings": ["PROVIDER_FAILURE"]})
                error_name = type(exc).__name__
                price_failures[symbol] = error_name
                meta["errors"].append(f"{symbol}:{error_name}")
                LOG.warning("Provider data unavailable for %s (%s)", symbol, error_name)
        if price_failures:
            # Safe diagnostics only: exception class / observed last date, never URLs or tokens.
            from collections import Counter
            counts = Counter(price_failures.values())
            meta["price_failure_summary"] = ", ".join(f"{k} x{v}" for k, v in counts.most_common(5))
            meta["price_failure_examples"] = ", ".join(f"{k}:{v}" for k, v in list(price_failures.items())[:5])
        ranked = score_records(records, cfg)
        # Data-degraded mode is driven by current price availability. Missing fundamentals
        # reduce coverage/confidence per stock instead of suppressing the entire universe.
        success = meta["usable"] / max(1, meta["requested"])
        meta["data_degraded"] = success < cfg["data"].get("min_price_data_success_ratio", .70)
        if not meta["data_degraded"]:
            shortlist = [r for r in ranked if r["eligible"] and r["score"] >= cfg["alerts"]["min_score"]]
            shortlist = shortlist[:cfg["data"]["intraday_scan_limit"]]
            observation_mode = mode
            if mode == "manual":
                resolved, _ = due_mode(clock(), cfg)
                observation_mode = resolved or "manual"
            for record in shortlist:
                try:
                    fetched = provider.intraday(record["symbol"])
                    record.update(intraday_features(fetched, clock(), observation_mode,
                                                    record["previous_close"], cfg))
                except Exception as exc:
                    record["quote_status"] = "FETCH_FAILED"
                    meta["errors"].append(f"{record['symbol']}:INTRADAY_{type(exc).__name__}")
            if cfg["alerts"]["enable_speculative"]:
                for symbol in universe["speculative"]:
                    try:
                        data = {"symbol": symbol, **price_features(provider.daily(symbol), started, cfg["calendar"])}
                        bars = provider.intraday(symbol)
                        data.update(intraday_features(bars, clock(), observation_mode, data.get("previous_close"), cfg))
                        speculative.append(data)
                    except Exception as exc:
                        meta["errors"].append(f"{symbol}:SPECULATIVE_{type(exc).__name__}")
    finished = clock()
    # Long downloads must never cause a stale pre-event alert after the event.
    if mode in ("preopen", "preclose"):
        still_due, _ = due_mode(finished, cfg)
        if still_due != mode:
            raise RuntimeError("The alert window elapsed while fetching data; no candidate alert sent")
    if not demo and (finished - started).total_seconds() > cfg["alerts"]["max_snapshot_age_minutes"] * 60:
        raise RuntimeError("Snapshot exceeded maximum allowed age; no candidate alert sent")
    # Quote freshness is checked again at send time, not only when fetched.
    for record in ranked + speculative:
        if record.get("quote_time"):
            age = (finished - datetime.fromisoformat(record["quote_time"])).total_seconds() / 60
            if age > cfg["alerts"]["max_quote_age_minutes"]:
                record["intraday_available"] = False
                record["quote_status"] = "STALE_AT_SEND"
    selected = [] if meta["data_degraded"] else choose_alerts(ranked, state, mode, finished, cfg)
    speculative_selected = [] if meta["data_degraded"] else choose_speculative(speculative, cfg)
    meta.update(as_of=finished.isoformat(), eligible=sum(r["eligible"] for r in ranked))
    message = build_message(selected, speculative_selected, meta, cfg)
    write_outputs(ranked, selected, speculative_selected, meta, message, cfg)
    should_send = bool(selected or speculative_selected or cfg["alerts"]["send_empty_summary"] or meta["data_degraded"])
    message_ids = []
    if dry_run:
        LOG.info("DRY RUN: no Telegram message or alert-history mutation")
    elif should_send:
        message_ids = messenger.send(message)
        LOG.info("Telegram accepted %d message(s)", len(message_ids))
    if not demo and not dry_run:
        state["sent_sessions"][session_key] = finished.isoformat()
        for r in selected:
            state["last_alerts"][f"{mode}:{r['symbol']}"] = {
                "score": r["score"], "triggers": r["triggers"], "at": finished.isoformat()}
        state["last_scores"].update({r["symbol"]: {"score": r["score"], "at": finished.isoformat()}
                                     for r in ranked if r["eligible"]})
        # Mark confirmed delivery before appending the journal, reducing retry duplicates.
        save_state(cfg["data"]["state_dir"], state)
        append_journal(cfg["data"]["state_dir"], {
            "metadata": meta, "message_ids": message_ids, "selected": [r["symbol"] for r in selected],
            "ranked": ranked, "speculative": speculative_selected})
    return {"status": "dry_run" if dry_run else "complete", "selected": len(selected), "meta": meta}


def main() -> int:
    parser = argparse.ArgumentParser(description="Research alerts only; no broker or order execution")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--universe", default="universe.yaml")
    parser.add_argument("--mode", choices=["auto", "manual", "demo"], default="auto")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cfg = None
    try:
        cfg = load_config(args.config)
        result = run(cfg, load_universe(args.universe), args.mode, args.dry_run)
        LOG.info("Run status: %s", result["status"])
        return 0
    except Exception as exc:
        # Exception type is safe. Avoid echoing token-bearing third-party request objects.
        reason = str(exc) if isinstance(exc, (TelegramError, ValueError)) else type(exc).__name__
        LOG.error("Run failed: %s", reason)
        if cfg:
            write_json(Path(cfg["data"]["output_dir"]) / "failure.json", {"error_type": type(exc).__name__})
        if not args.dry_run and not isinstance(exc, TelegramError):
            try:
                TelegramClient.from_env().send(
                    f"GROWTH ALERT SYSTEM ERROR ({type(exc).__name__}). No new candidate report was confirmed. "
                    "Check the GitHub Actions run. No trades were placed.")
            except Exception:
                pass
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
