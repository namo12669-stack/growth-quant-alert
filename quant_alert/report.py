from __future__ import annotations
from collections import Counter
from pathlib import Path
from zoneinfo import ZoneInfo
import pandas as pd
from .models import Signal
from .storage import write_json


def header(result: dict) -> str:
    mode = result["mode"].upper()
    lines = ["QUANT SIGNAL ALERT V2", f"{mode} | {result['display_time']}",
             f"Model {result['model']} | seed watchlist, not all US stocks"]
    if result.get("demo"):
        lines.insert(0, "DEMO - SYNTHETIC DATA - NOT LIVE")
    lines.extend([f"Completed daily session required: {result['expected_session']}",
                  f"Price usable: {result['usable_stocks']}/{result['total_stocks']} | signals detected: {result['detected_count']}",
                  f"Selected new alerts: {result['selected_count']} | suppressed: {len(result['suppressed'])}",
                  "Fundamentals/news: NOT CHECKED (not a scoring gate)",
                  "Daily patterns use completed sessions; only 15m alerts describe today's incomplete session."])
    if not result["quality_gate"]:
        lines.append("DATA QUALITY GATE: candidate alerts withheld. See diagnostics.json in Actions artifacts.")
    if result.get("send_window_expired"):
        lines.append("SEND WINDOW EXPIRED: no candidate messages sent after the scheduled window.")
    if result["selected_count"] == 0:
        lines.append("No NEW signals passed all enabled rules and deduplication. No forced Top 5 list.")
    if result.get("benchmark_context"):
        lines.append(result["benchmark_context"])
    reasons = Counter(r for x in result["quality"].values() for r in x.get("reasons", []))
    if reasons:
        lines.append("Price exclusions: " + "; ".join(f"{k}={v}" for k, v in reasons.most_common(4)))
    rel = result.get("relationship_audit", [])
    for name in ("pair_spread", "lead_lag"):
        rows = [x for x in rel if x["engine"] == name]
        if rows:
            lines.append(f"{name}: model screens passed {sum(bool(x.get('validated_screen_pass')) for x in rows)}/{len(rows)} hypotheses")
    lines.extend(["", "Priority is a display rule, NOT a win probability. Signals are unvalidated research hypotheses.",
                  "Prices may be delayed. No broker connection. Verify an independent quote and company news."])
    return "\n".join(lines)


def signal_message(signal: Signal, demo: bool = False) -> str:
    title = f"{signal.kind} | {' / '.join(signal.symbols)}"
    lines = ["DEMO - SYNTHETIC DATA - NOT LIVE"] if demo else []
    lines += [title, f"Direction: {signal.direction} | Priority: {signal.priority}",
              f"Data: {signal.asof} | {signal.timeframe}", "WHY ALERTED:"]
    lines.extend(f"- {r}" for r in signal.reasons)
    lines.extend([f"Horizon: {signal.horizon}", f"CAUTION: {signal.caution}", f"Event ID: {signal.signal_id}"])
    return "\n".join(lines)


def write_reports(root: Path, result: dict, selected: list[Signal], all_signals: list[Signal],
                  daily: dict[str, pd.DataFrame], intraday: dict[str, pd.DataFrame], cfg: dict) -> None:
    root.mkdir(parents=True, exist_ok=True)
    preview = "\n\n".join([header(result)] + [signal_message(s, result.get("demo", False)) for s in selected])
    (root/"telegram_preview.txt").write_text(preview+"\n", encoding="utf-8")
    write_json(root/"diagnostics.json", result)
    write_json(root/"signals.json", [s.to_dict() for s in all_signals])
    selected_ids = {s.signal_id for s in selected}
    rows = [{"id": s.signal_id, "kind": s.kind, "symbols": "/".join(s.symbols), "direction": s.direction,
             "timeframe": s.timeframe, "asof": s.asof, "priority": s.priority,
             "selected": s.signal_id in selected_ids, "why": " | ".join(s.reasons)} for s in all_signals]
    pd.DataFrame(rows, columns=["id", "kind", "symbols", "direction", "timeframe", "asof", "priority", "selected", "why"]).to_csv(root/"signals.csv", index=False)
    pd.DataFrame(result.get("relationship_audit", [])).to_csv(root/"relationships.csv", index=False)
    pd.DataFrame([{"symbol": s, **v} for s, v in result["quality"].items()]).to_csv(root/"price_diagnostics.csv", index=False)
    summary = "# Quant Signals V2\n\n```text\n"+preview+"\n```\n\n"
    summary += "Full rules, skipped checks, p-values, and rejection reasons: download this run's reports artifact.\n"
    summary += "\n`HIGH` is not calibrated confidence. No historical profit claim is made by this software.\n"
    (root/"summary.md").write_text(summary, encoding="utf-8")
    if cfg["provider"]["save_input_snapshots"]:
        target = root/"inputs"
        target.mkdir(exist_ok=True)
        for collection, suffix in ((daily, "daily"), (intraday, "15m")):
            for s, df in collection.items():
                if not df.empty:
                    df.to_csv(target/f"{s}_{suffix}.csv", index_label="Date")
