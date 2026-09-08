from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path
from typing import Callable

import pandas as pd

from .sec_provider import SecEdgarProvider
from .storage import read_json, write_json

LOG = logging.getLogger(__name__)
TABLE_NAMES = ("income", "cashflow", "balance", "eps_trend", "eps_revisions")
INFO_FIELDS = ("shortName", "longName", "sector", "industry", "currency", "financialCurrency",
               "marketCap", "enterpriseValue", "quoteType")
PROVIDER_CACHE_VERSION = 2


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


def _merge_payload(primary: dict, fallback: dict) -> dict:
    """Prefer Yahoo fields, fill missing tables/info from SEC without pretending they are one source."""
    out = dict(primary)
    out_info = dict(fallback.get("info", {}))
    out_info.update({k: v for k, v in primary.get("info", {}).items() if v not in (None, "")})
    out["info"] = out_info
    used_sec = False
    for key in ("income", "cashflow", "balance"):
        current = primary.get(key, pd.DataFrame())
        other = fallback.get(key, pd.DataFrame())
        if other is None or other.empty:
            continue
        if current is None or current.empty:
            out[key] = other
            used_sec = True
        else:
            before_rows = set(current.index)
            merged = current.combine_first(other)
            if set(merged.index) != before_rows or merged.notna().sum().sum() > current.notna().sum().sum():
                used_sec = True
            out[key] = merged
    warnings = list(dict.fromkeys(primary.get("warnings", []) + fallback.get("warnings", [])))
    out["warnings"] = warnings
    if used_sec:
        out["source"] = "Yahoo+SEC"
        # Statement observations came from SEC; use its retrieval time for disclosure in report.
        out["fetched_at"] = fallback.get("fetched_at") or primary.get("fetched_at")
    else:
        out["source"] = primary.get("source", "Yahoo")
    return out


class YahooProvider:
    """Yahoo price adapter with SEC Company Facts fallback for core fundamentals."""

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
        self.sec = SecEdgarProvider(cfg, self.clock) if cfg["data"].get("enable_sec_fallback", True) else None
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
        raise RuntimeError(f"Provider request failed ({type(error).__name__})") from None

    def daily(self, symbol: str) -> pd.DataFrame:
        return self._call(lambda: self.ticker(symbol).history(
            period="2y", interval="1d", auto_adjust=False, actions=False,
            timeout=20, raise_errors=True))

    def intraday(self, symbol: str) -> pd.DataFrame:
        return self._call(lambda: self.ticker(symbol).history(
            period="1mo", interval="5m", prepost=True, auto_adjust=False,
            actions=False, timeout=20, raise_errors=True))

    def _fast_info(self, ticker) -> dict:
        result = {}
        try:
            fast = self._call(lambda: ticker.fast_info)
            # yfinance FastInfo behaves like a mapping but versions vary.
            for src, dst in (("market_cap", "marketCap"), ("currency", "currency")):
                try:
                    value = fast.get(src) if hasattr(fast, "get") else getattr(fast, src, None)
                    if value not in (None, ""):
                        result[dst] = value
                except Exception:
                    pass
        except RuntimeError:
            pass
        return result

    def fundamentals(self, symbol: str) -> dict:
        now = self.clock()
        path = self.cache / f"{symbol}.json"
        stored = read_json(path, None)
        age = float("inf")
        cache_compatible = bool(stored and stored.get("provider_cache_version") == PROVIDER_CACHE_VERSION)
        if cache_compatible and stored.get("fetched_at"):
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
        fast_info = self._fast_info(ticker)
        selected_info = {key: info.get(key) for key in INFO_FIELDS}
        for key, value in fast_info.items():
            if selected_info.get(key) in (None, ""):
                selected_info[key] = value
        payload = {"info": selected_info, "warnings": warnings,
                   "fetched_at": now.isoformat(), "source": "Yahoo",
                   "provider_cache_version": PROVIDER_CACHE_VERSION}
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

        # SEC is an official filings fallback for statement tables. It does not provide
        # analyst revision snapshots, sector classifications, or real-time prices.
        if self.sec is not None and (payload["income"].empty or payload["cashflow"].empty or payload["balance"].empty):
            try:
                payload = _merge_payload(payload, self.sec.fundamentals(symbol))
            except RuntimeError:
                payload["warnings"].append("SEC_FALLBACK_UNAVAILABLE")

        has_statement = any(not payload.get(k, pd.DataFrame()).empty for k in ("income", "cashflow", "balance"))
        if not has_statement and cache_compatible and stored and 0 <= age <= self.cfg["data"]["fallback_cache_hours"]:
            fallback = unpack_payload(stored)
            fallback["warnings"] = list(set(fallback.get("warnings", []) + ["STALE_CACHE_FALLBACK"]))
            return fallback
        if has_statement or bool(payload["info"].get("marketCap")):
            write_json(path, pack_payload(payload))
        return payload
