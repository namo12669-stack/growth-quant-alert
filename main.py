#!/usr/bin/env python3
from __future__ import annotations
import argparse
from datetime import datetime, timezone
from pathlib import Path
import logging
import sys
from quant_alert.app import run_scan
from quant_alert.calendar import due_mode
from quant_alert.config import load_config, load_universe
from quant_alert.demo import DemoProvider, DEMO_NOW
from quant_alert.provider import YahooProvider, CSVProvider
from quant_alert.telegram import TelegramError


def main() -> int:
    p = argparse.ArgumentParser(description="Quant Signals V2: research-only Telegram notifications")
    p.add_argument("--mode", choices=["demo", "manual", "auto"], default="manual")
    p.add_argument("--dry-run", action="store_true", help="No Telegram and no state changes")
    p.add_argument("--config", default="config.yaml")
    p.add_argument("--universe", default="universe.yaml")
    p.add_argument("--data-dir", help="Use local, consistently adjusted OHLCV CSV files instead of Yahoo")
    p.add_argument("--asof", help="Timezone-aware historical timestamp; CSV + dry-run only")
    p.add_argument("--output", default="output")
    p.add_argument("--state", default="state_v2")
    args = p.parse_args()
    if args.asof and not (args.data_dir and args.dry_run):
        p.error("--asof requires --data-dir and --dry-run; historical data cannot send live alerts")
    cfg = load_config(args.config)
    now = datetime.fromisoformat(args.asof) if args.asof else datetime.now(timezone.utc)
    if now.tzinfo is None:
        p.error("--asof must include a timezone offset")
    mode = args.mode
    if mode == "auto":
        mode, _ = due_mode(now, cfg)
        if mode is None:
            root = Path(args.output)
            root.mkdir(parents=True, exist_ok=True)
            text = "# Quant Signals V2\n\nSKIPPED: outside configured exchange-session alert windows. No Telegram sent.\n"
            (root/"summary.md").write_text(text)
            print(text)
            return 0
    if mode == "demo":
        provider = DemoProvider(cfg)
        universe, now = provider.universe, DEMO_NOW
    else:
        universe = load_universe(args.universe)
        provider = CSVProvider(args.data_dir) if args.data_dir else YahooProvider(cfg)
    result = run_scan(cfg, universe, provider, now, mode=mode, dry_run=args.dry_run,
                      output_dir=args.output, state_dir=args.state, scheduled=args.mode == "auto")
    print(f"Model {cfg['model']} | {mode} | price {result['usable_stocks']}/{result['total_stocks']} | "
          f"signals {result['detected_count']} | selected {result['selected_count']} | {result['delivery']}")
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        raise SystemExit(main())
    except (TelegramError, ValueError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
