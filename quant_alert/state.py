from __future__ import annotations
from datetime import datetime, timedelta
from pathlib import Path
from .models import Signal
from .storage import read_json, write_json, append_journal


def load(root: str | Path) -> dict:
    state = read_json(Path(root)/"state.json", None)
    if state is None:
        return {"schema": 2, "seen": {}, "last_by_key": {}, "summaries": {}}
    if state.get("schema") != 2:
        raise ValueError("State is not V2. Use the separate state_v2 directory.")
    return state


def save(root: str | Path, state: dict) -> None:
    state["seen"] = dict(sorted(state["seen"].items(), key=lambda x: x[1])[-5000:])
    state["summaries"] = dict(sorted(state["summaries"].items(), key=lambda x: x[1])[-180:])
    write_json(Path(root)/"state.json", state)


def select(signals: list[Signal], state: dict, now: datetime, cfg: dict) -> tuple[list[Signal], list[dict]]:
    chosen, suppressed, counts = [], [], {}
    seen_in_run = set()
    order = {"HIGH": 0, "WATCH": 1}
    for s in sorted(signals, key=lambda x: (order.get(x.priority, 2), x.kind, x.symbols)):
        reason = None
        if s.signal_id in state["seen"] or s.signal_id in seen_in_run:
            reason = "ALREADY_SENT_EVENT"
        last = state["last_by_key"].get(s.cooldown_key)
        if not reason and last:
            age = now-datetime.fromisoformat(last)
            if age < timedelta(hours=cfg["alerts"]["cooldown_hours"]):
                reason = "COOLDOWN"
        if not reason and len(chosen) >= cfg["alerts"]["max_signals"]:
            reason = "MAX_SIGNALS"
        if not reason and any(counts.get(t, 0) >= cfg["alerts"]["max_per_ticker"] for t in s.symbols):
            reason = "MAX_PER_TICKER"
        if reason:
            suppressed.append({"signal_id": s.signal_id, "reason": reason})
        else:
            chosen.append(s)
            seen_in_run.add(s.signal_id)
            for t in s.symbols:
                counts[t] = counts.get(t, 0)+1
    return chosen, suppressed


def mark_delivered(root: str | Path, state: dict, signal: Signal, now: datetime, mode: str, ids: list[int]) -> None:
    stamp = now.isoformat()
    record = {**signal.to_dict(), "observed_at": stamp, "mode": mode,
              "telegram_message_ids": ids, "model": "quant-signals-v2.0.0"}
    # Journal first, then atomically save state. A failure is surfaced; delivery
    # cannot be exactly-once across a remote API and a local artifact transaction.
    append_journal(root, record)
    state["seen"][signal.signal_id] = stamp
    state["last_by_key"][signal.cooldown_key] = stamp
    save(root, state)
