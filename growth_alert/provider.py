from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path
from typing import Callable

import pandas as pd

from .storage import read_json, write_json

LOG = logging.getLogger(__name__)
TABLE_NAMES = ("income", "cashflow", "balance", "eps_trend", "eps_revisions")
INFO_FIELDS = ("shortName", "longName", "sector", "industry", "currency", "financialCurrency",
               "marketCap", "enterpriseValue", "quoteType")


def pack_payload(payload: dict) -> dict:
    packed = dict(payload)
    for key in TABLE_NAMES:
        packed[key] = payload.get(key, pd.DataFrame()).to_json(orient="split", date_format="iso")
    return packed


def unpack_payload(packed: dict) -> dict:
    result = dict(packed)
    for key in TABLE_NAMES:
        result[key] = pd.read_json(StringIO(packed.get(key, '{"columns":[],"index":[],"data":[]}')),
                                   orient="split")
    return result


class YahooProvider:
    """Replaceable provider adapter. Yahoo availability/delay is not guaranteed."""

    def __init__(self, cfg: dict, clock: Callable[[], datetime] | None = None):
        try:
            import yfinance as yf
        except ImportError as exc:
            raise RuntimeError("Install requirements.txt before running the live provider") from exc
        self.yf = yf
        self.cfg = cfg
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.cache = Path(cfg["data"]["state_dir"]) / "fundamentals"
        self.cache.mkdir(parents=True, exist_ok=True)
        self.tickers: dict = {}
        logging.getLogger("yfinance").setLevel(logging.CRITICAL)

    def ticker(self, symbol: str):
        if symbol not in self.tickers:
            self.tickers[symbol] = self.yf.Ticker(symbol)
        return self.tickers[symbol]

    def _call(self, fn: Callable):
        error = None
        for attempt in range(self.cfg["data"]["request_attempts"]):
            try:
                result = fn()
                time.sleep(self.cfg["data"]["request_pause_seconds"])
                return result
            except Exception as exc:
                error = exc
                time.sleep(min(2 ** attempt, 4))
        # Do not propagate arbitrary third-party URLs or request representations.
        raise RuntimeError(f"Provider request failed ({type(error).__name__})") from None

    def daily(self, symbol: str) -> pd.DataFrame:
        return self._call(lambda: self.ticker(symbol).history(
            period="2y", interval="1d", auto_adjust=False, actions=False,
            timeout=20, raise_errors=True))

    def intraday(self, symbol: str) -> pd.DataFrame:
        return self._call(lambda: self.ticker(symbol).history(
            period="1mo", interval="5m", prepost=True, auto_adjust=False,
            actions=False, timeout=20, raise_errors=True))

    def fundamentals(self, symbol: str) -> dict:
        now = self.clock()
        path = self.cache / f"{symbol}.json"
        stored = read_json(path, None)
        age = float("inf")
        if stored and stored.get("fetched_at"):
            age = (now - datetime.fromisoformat(stored["fetched_at"])).total_seconds() / 3600
            if 0 <= age < self.cfg["data"]["fundamental_cache_hours"]:
                return unpack_payload(stored)
        ticker = self.ticker(symbol)
        warnings: list[str] = []
        try:
            info = self._call(ticker.get_info)
        except RuntimeError:
            info = {}
            warnings.append("INFO_UNAVAILABLE")
        payload = {"info": {key: info.get(key) for key in INFO_FIELDS}, "warnings": warnings,
                   "fetched_at": now.isoformat()}
        methods = {
            "income": lambda: ticker.get_income_stmt(freq="quarterly"),
            "cashflow": lambda: ticker.get_cash_flow(freq="quarterly"),
            "balance": lambda: ticker.get_balance_sheet(freq="quarterly"),
            "eps_trend": ticker.get_eps_trend,
            "eps_revisions": ticker.get_eps_revisions,
        }
        for name, method in methods.items():
            try:
                value = self._call(method)
                payload[name] = value if isinstance(value, pd.DataFrame) else pd.DataFrame()
                if payload[name].empty:
                    warnings.append(name.upper() + "_UNAVAILABLE")
            except RuntimeError:
                payload[name] = pd.DataFrame()
                warnings.append(name.upper() + "_UNAVAILABLE")
        critical_ok = bool(payload["info"].get("marketCap")) and not payload["income"].empty
        if not critical_ok and stored and 0 <= age <= self.cfg["data"]["fallback_cache_hours"]:
            fallback = unpack_payload(stored)
            fallback["warnings"] = list(set(fallback.get("warnings", []) + ["STALE_CACHE_FALLBACK"]))
            # Preserve original fetched_at and do not refresh the cache TTL.
            return fallback
        if critical_ok:
            write_json(path, pack_payload(payload))
        return payload
