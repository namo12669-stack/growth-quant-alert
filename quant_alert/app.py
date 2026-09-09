from __future__ import annotations
from datetime import datetime, date, timezone
from pathlib import Path
from typing import Callable
from zoneinfo import ZoneInfo
import logging
import pandas as pd
from .calendar import NY, expected_daily_session, session_for, due_mode
from .quality import prepare_daily
from .single import divergence, breakout, relative_strength
from .intraday import intraday_breakout
from .relationships import relationship_signals
from .report import header, signal_message, write_reports
from .telegram import TelegramClient, TelegramError
from . import state as history

LOG = logging.getLogger(__name__)


def run_scan(cfg: dict, universe: dict, provider, now: datetime, mode: str = "manual",
             dry_run: bool = False, output_dir: str = "output", state_dir: str = "state_v2",
             scheduled: bool = False, client=None, clock: Callable | None = None) -> dict:
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    clock = clock or (lambda: datetime.now(timezone.utc))
    demo = mode == "demo"
    expected = expected_daily_session(now, cfg)
    raw_daily = provider.fetch(universe["symbols"])
    prepared, usable, quality, checks, all_signals = {}, {}, {}, [], []
    for s in universe["symbols"]:
        frame, diag = prepare_daily(raw_daily.get(s, pd.DataFrame()), expected, cfg, stock=s in universe["stocks"])
        prepared[s] = frame
        quality[s] = diag
        if diag["usable"]:
            usable[s] = frame
    usable_stocks = [s for s in universe["stocks"] if s in usable]
    needed = min(len(universe["stocks"]), cfg["quality"]["min_universe_count"])
    quality_gate = (len(usable_stocks) >= needed and
                    len(usable_stocks)/max(1, len(universe["stocks"])) >= cfg["quality"]["min_universe_fraction"])
    for s in usable_stocks:
        for fn in (divergence, breakout):
            try:
                signals, audit = fn(s, usable[s], cfg)
                all_signals.extend(signals)
                checks.append(audit)
            except Exception as exc:
                checks.append({"symbol": s, "engine": fn.__name__, "status": "ENGINE_ERROR", "error": type(exc).__name__})
                LOG.exception("Detector failed: %s / %s", s, fn.__name__)
        benchmark = universe["meta"][s]["benchmark"]
        signals, audit = relative_strength(s, usable[s], benchmark, usable.get(benchmark), cfg)
        all_signals.extend(signals)
        checks.append(audit)
    session = session_for(now.astimezone(NY).date(), cfg["calendar"])
    in_session = bool(session and session.open <= now < session.close)
    raw_intra = {}
    if in_session and cfg["signals"]["intraday_breakout"]["enabled"]:
        raw_intra = provider.fetch(usable_stocks, intraday=True)
        for s in usable_stocks:
            signals, audit = intraday_breakout(s, usable[s], raw_intra.get(s, pd.DataFrame()), now, cfg)
            all_signals.extend(signals)
            checks.append(audit)
    relations, relationship_audit = relationship_signals(usable, universe, cfg)
    all_signals.extend(relations)
    active, time_suppressed = [], []
    for signal in all_signals:
        # A next-session close-to-close model must not masquerade as a fresh
        # forecast once that target session has already opened.
        if signal.kind == "LEAD_LAG":
            target = session_for(date.fromisoformat(signal.metrics["target_session"]), cfg["calendar"])
            if target is None or now >= target.open:
                time_suppressed.append({"signal_id": signal.signal_id, "reason": "LEAD_LAG_TARGET_ALREADY_STARTED"})
                continue
        if any(universe["meta"].get(t, {}).get("group") == "speculative" for t in signal.symbols):
            signal.caution = "SPECULATIVE SEED WATCHLIST. " + signal.caution
        active.append(signal)
    hist = {"schema": 2, "seen": {}, "last_by_key": {}, "summaries": {}} if demo else history.load(state_dir)
    chosen, suppressed = history.select(active if quality_gate else [], hist, now, cfg)
    suppressed += time_suppressed
    if not quality_gate:
        suppressed += [{"signal_id": s.signal_id, "reason": "UNIVERSE_PRICE_QUALITY_GATE"} for s in active]
    market = universe["market"]
    benchmark_context = f"{market}: unavailable/stale; no market regime inference."
    if market in usable and len(usable[market]) >= 200:
        m = usable[market]
        position = "ABOVE" if m.Close.iloc[-1] > m.Close.tail(200).mean() else "BELOW"
        benchmark_context = f"Context only: {market} {position} 200-session SMA on {m.index[-1].date()}."
    result = {"model": cfg["model"], "mode": mode, "demo": demo, "observed_at": now.isoformat(),
              "display_time": now.astimezone(ZoneInfo("Asia/Bangkok")).strftime("%Y-%m-%d %H:%M %z"),
              "expected_session": str(expected), "total_stocks": len(universe["stocks"]),
              "usable_stocks": len(usable_stocks), "quality_gate": quality_gate,
              "detected_count": len(all_signals), "selected_count": len(chosen), "suppressed": suppressed,
              "quality": quality, "detector_checks": checks, "relationship_audit": relationship_audit,
              "provider_diagnostics": getattr(provider, "diagnostics", []),
              "benchmark_context": benchmark_context, "fundamentals": "NOT_REQUESTED_NOT_CHECKED",
              "delivery": "DRY_RUN" if dry_run else "NOT_STARTED"}
    root = Path(output_dir)
    if not dry_run and not demo:
        publication_time = clock()
        result["publication_checked_at"] = publication_time.isoformat()
        result["display_time"] = publication_time.astimezone(ZoneInfo("Asia/Bangkok")).strftime("%Y-%m-%d %H:%M %z")
        fresh = []
        for signal in chosen:
            reason = None
            if signal.kind == "LEAD_LAG":
                target = session_for(date.fromisoformat(signal.metrics["target_session"]), cfg["calendar"])
                if target is None or publication_time >= target.open:
                    reason = "LEAD_LAG_TARGET_STARTED_BEFORE_SEND"
            if signal.kind == "INTRADAY_BREAKOUT":
                end = datetime.fromisoformat(signal.asof)
                if (publication_time-end).total_seconds()/60 > cfg["quality"]["max_intraday_age_minutes"]:
                    reason = "INTRADAY_STALE_BEFORE_SEND"
            if expected_daily_session(publication_time, cfg) != expected:
                reason = "DAILY_SESSION_CHANGED_DURING_SCAN"
            if reason:
                result["suppressed"].append({"signal_id": signal.signal_id, "reason": reason})
            else:
                fresh.append(signal)
        chosen = fresh
        result["selected_count"] = len(chosen)
    if scheduled and not dry_run:
        current_mode, current_session = due_mode(clock(), cfg)
        if current_mode != mode or current_session is None or current_session.day != now.astimezone(NY).date():
            result["send_window_expired"] = True
            result["delivery"] = "SKIPPED_LATE"
            result["suppressed"] += [{"signal_id": s.signal_id, "reason": "SEND_WINDOW_EXPIRED"} for s in chosen]
            chosen = []
            result["selected_count"] = 0
    write_reports(root, result, chosen, all_signals, prepared, raw_intra, cfg)
    if dry_run or result.get("send_window_expired"):
        return result
    client = client or TelegramClient.from_env()
    summary_key = f"{now.astimezone(NY).date()}:{mode}"
    send_summary = (demo or not scheduled or summary_key not in hist["summaries"])
    try:
        if send_summary and (chosen or cfg["alerts"]["send_empty_summary"] or not quality_gate):
            client.send(header(result))
            if not demo:
                hist["summaries"][summary_key] = now.isoformat()
                history.save(state_dir, hist)
        for signal in chosen:
            ids = client.send(signal_message(signal, demo))
            if not demo:
                history.mark_delivered(state_dir, hist, signal, clock(), mode, ids)
        result["delivery"] = "SENT" if chosen or send_summary else "DEDUPLICATED"
    except TelegramError:
        result["delivery"] = "FAILED_OR_PARTIAL_CHECK_TELEGRAM"
        write_reports(root, result, chosen, all_signals, prepared, raw_intra, cfg)
        raise
    write_reports(root, result, chosen, all_signals, prepared, raw_intra, cfg)
    return result
