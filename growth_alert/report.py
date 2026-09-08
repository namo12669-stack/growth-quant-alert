from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from .factors import finite
from .storage import clean, write_json


def pct(x, signed=True) -> str:
    if not finite(x):
        return "N/A"
    return f"{x:+.1%}" if signed else f"{x:.1%}"


def money(x) -> str:
    return f"${x:,.2f}" if finite(x) else "N/A"


def build_message(selected: list[dict], speculative: list[dict], meta: dict, cfg: dict) -> str:
    local = datetime.fromisoformat(meta["as_of"]).astimezone(ZoneInfo(cfg["display_timezone"]))
    title = "DEMO - SYNTHETIC DATA - NOT LIVE" if meta.get("demo") else "GROWTH RESEARCH ALERT"
    lines = [title, f"{meta['mode'].upper()} | {local:%Y-%m-%d %H:%M %Z}",
             f"Model {cfg['model_version']} | seed universe, not all US stocks",
             f"Price usable: {meta.get('usable', 0)}/{meta.get('requested', 0)} | Fundamental usable: {meta.get('fundamental_usable', 0)}/{meta.get('requested', 0)} | Eligible: {meta.get('eligible', 0)}",
             f"Benchmark context (last completed session): {meta.get('market_context', 'UNAVAILABLE')}"]
    if meta.get("data_degraded"):
        lines += ["DATA QUALITY ALERT: too few current price observations. Candidate alerts withheld."]
    if meta.get("state_restored") is False:
        lines.append("Fresh state: no previous alert history was available.")
    if not selected:
        lines.append("\nNo new/changed core candidates passed all alert conditions.")
    for i, r in enumerate(selected, 1):
        lines += ["", f"{i}. {r['symbol']} | Research score {r['score']:.1f}/100 | Coverage {r['coverage']:.0%} | Confidence {r.get('confidence', 'N/A')}",
                  f"{r.get('sector', 'Unknown')} | {', '.join(r.get('triggers', []))}",
                  "Growth / Quality / Expectations / Momentum / Valuation",
                  " / ".join(f"{r.get(f + '_score', 50):.0f}" for f in ("growth", "quality", "expectations", "momentum", "valuation")),
                  f"Revenue YoY {pct(r.get('revenue_yoy'))} | FCF margin {pct(r.get('fcf_margin'))}",
                  f"12-1 momentum {pct(r.get('momentum_12_1'))} | EPS revision 30d {pct(r.get('eps_revision_30d'))}"]
        if r.get("intraday_available"):
            lines.append(f"5m bar price {money(r.get('intraday_price'))} | Move {pct(r.get('session_return'))}")
            rvol = r.get("rvol_same_time")
            lines.append(f"Same-time RVOL {f'{rvol:.2f}x' if finite(rvol) else 'N/A'} | Bar end {r.get('quote_time', 'N/A')}")
        else:
            lines.append(f"PRIOR CLOSE ONLY: {money(r.get('previous_close'))} on {r.get('price_date', 'N/A')}; no fresh intraday confirmation")
        lines.append(f"Drivers: {', '.join(r.get('drivers', [])) or 'N/A'}")
        lines.append(f"Fundamentals: {r.get('fundamental_source', 'Unknown')} | Statement: {r.get('statement_period') or 'N/A'}")
        important = [f for f in r.get("flags", []) if f != "EPS_PERIOD_ROLLOVER_NOT_INDEPENDENTLY_VERIFIED"]
        lines.append("Risks/data: " + (", ".join(important[:5]) or "No configured flag; other risks may exist"))
    if speculative:
        lines += ["", "SPECULATIVE PRICE WATCH - NO RESEARCH SCORE"]
        for r in speculative:
            lines.append(f"{r['symbol']}: {money(r.get('intraday_price'))}, {pct(r.get('session_return'))}; bar end {r.get('quote_time')}")
        lines.append("Price movement only; catalyst and funding risk not independently verified.")
    lines += ["", "Score is a research rank, NOT a win probability or a buy/sell instruction.",
              "Price data may be delayed/incomplete. Fundamentals can use SEC filing fallback; analyst revisions remain Yahoo snapshots when available.",
              "No broker connection. Verify official filings and a reliable quote before acting."]
    return "\n".join(lines)


def write_outputs(ranked: list[dict], selected: list[dict], speculative: list[dict],
                  meta: dict, message: str, cfg: dict) -> None:
    root = Path(cfg["data"]["output_dir"])
    root.mkdir(parents=True, exist_ok=True)
    write_json(root / "snapshot.json", {"metadata": meta, "ranked": ranked,
                                         "alerts": selected, "speculative": speculative})
    flat = []
    for record in ranked:
        r = {k: v for k, v in record.items() if k not in ("factor_scores", "ranking_scopes")}
        for k, v in list(r.items()):
            if isinstance(v, list):
                r[k] = " | ".join(str(x) for x in v)
        for k, v in list(r.items()):
            if isinstance(v, str) and v[:1] in ("=", "+", "-", "@"):
                r[k] = "'" + v
        r["demo"] = bool(meta.get("demo"))
        flat.append(clean(r))
    pd.DataFrame(flat).to_csv(root / "ranking.csv", index=False, encoding="utf-8-sig")
    (root / "telegram_preview.txt").write_text(message + "\n", encoding="utf-8")
    safe_message = message.replace("```", "'''")
    (root / "summary.md").write_text("# Growth Research Alert\n\n```text\n" + safe_message + "\n```\n", encoding="utf-8")
