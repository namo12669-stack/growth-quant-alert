from __future__ import annotations
import logging
import time
from pathlib import Path
import pandas as pd

LOG = logging.getLogger(__name__)
REQUIRED = ["Open", "High", "Low", "Close", "Volume"]


def split_download(frame: pd.DataFrame | None, symbols: list[str]) -> dict[str, pd.DataFrame]:
    """Handle both yfinance MultiIndex orientations and flat single-symbol frames."""
    out = {s: pd.DataFrame() for s in symbols}
    if frame is None or frame.empty:
        return out
    if not isinstance(frame.columns, pd.MultiIndex):
        if len(symbols) == 1:
            out[symbols[0]] = frame.copy().dropna(how="all")
        return out
    for symbol in symbols:
        for level in range(frame.columns.nlevels):
            if symbol in frame.columns.get_level_values(level):
                sub = frame.xs(symbol, axis=1, level=level).copy()
                if not isinstance(sub.columns, pd.MultiIndex):
                    out[symbol] = sub.dropna(how="all")
                    break
    return out


class YahooProvider:
    """Price-only adapter. No .info, financial statements, or analyst endpoints.

    Batch download is still multiple HTTP requests internally. Shared-runner
    throttling is possible; a batch API is not a promise to avoid rate limits.
    """
    def __init__(self, cfg: dict):
        try:
            import yfinance as yf
        except ImportError:
            raise RuntimeError("Install requirements.txt before a live scan") from None
        self.yf, self.cfg = yf, cfg["provider"]
        self.diagnostics: list[dict] = []
        self.session = None
        try:
            from curl_cffi import requests as crequests
            self.session = crequests.Session(impersonate="chrome")
        except ImportError:
            pass  # yfinance may supply its own supported session.
        logging.getLogger("yfinance").setLevel(logging.CRITICAL)

    def fetch(self, symbols: list[str], intraday: bool = False) -> dict[str, pd.DataFrame]:
        symbols = list(dict.fromkeys(symbols))
        out = {s: pd.DataFrame() for s in symbols}
        interval = "15m" if intraday else "1d"
        period = self.cfg["intraday_period"] if intraday else self.cfg["daily_period"]
        n = self.cfg["batch_size"]
        for start in range(0, len(symbols), n):
            subset = symbols[start:start+n]
            kwargs = dict(tickers=subset, period=period, interval=interval,
                          group_by="ticker", auto_adjust=True, back_adjust=False,
                          prepost=False, actions=not intraday,
                          threads=self.cfg["threads"], progress=False,
                          timeout=self.cfg["timeout_seconds"], multi_level_index=True,
                          ignore_tz=not intraday)
            if self.session is not None:
                kwargs["session"] = self.session
            try:
                result = self.yf.download(**kwargs)
                out.update(split_download(result, subset))
            except Exception as exc:
                self.diagnostics.append({"scope": "batch", "symbols": subset,
                                         "interval": interval, "error": type(exc).__name__})
            time.sleep(self.cfg["pause_seconds"])
        missing = [s for s in symbols if out[s].empty]
        for symbol in missing[:self.cfg["individual_retry_limit"]]:
            try:
                ticker = self.yf.Ticker(symbol, session=self.session)
                result = ticker.history(period=period, interval=interval, auto_adjust=True,
                                        prepost=False, actions=not intraday,
                                        timeout=self.cfg["timeout_seconds"], raise_errors=True)
                if isinstance(result, pd.DataFrame):
                    out[symbol] = result.dropna(how="all")
            except Exception as exc:
                self.diagnostics.append({"scope": "retry", "symbol": symbol,
                                         "interval": interval, "error": type(exc).__name__})
            time.sleep(self.cfg["pause_seconds"])
        for symbol in symbols:
            if out[symbol].empty:
                self.diagnostics.append({"symbol": symbol, "interval": interval,
                                         "error": "EMPTY_PROVIDER_RESPONSE"})
        return out


class CSVProvider:
    """CSV columns: Date, Open, High, Low, Close, Volume[, Stock Splits].

    Files: SYMBOL_daily.csv and optional SYMBOL_15m.csv. Daily bars must use a
    consistent split/dividend-adjustment basis. Intraday timestamps MUST carry
    an offset or UTC Z. This adapter never forward-fills missing observations.
    """
    def __init__(self, directory: str):
        self.root = Path(directory)
        self.diagnostics: list[dict] = []

    def fetch(self, symbols: list[str], intraday: bool = False) -> dict[str, pd.DataFrame]:
        out = {}
        suffix = "15m" if intraday else "daily"
        for s in symbols:
            path = self.root / f"{s}_{suffix}.csv"
            try:
                f = pd.read_csv(path)
                column = "Date" if "Date" in f else f.columns[0]
                values = f.pop(column)
                if intraday:
                    # Reject ambiguous local times instead of guessing they are UTC.
                    if not values.astype(str).str.contains(r"(?:Z|[+-]\d{2}:?\d{2})$", regex=True).all():
                        raise ValueError("INTRADAY_TIMEZONE_REQUIRED")
                    f.index = pd.to_datetime(values, utc=True)
                else:
                    f.index = pd.to_datetime(values)
                out[s] = f
            except FileNotFoundError:
                out[s] = pd.DataFrame()
                self.diagnostics.append({"symbol": s, "interval": suffix, "error": "CSV_NOT_FOUND"})
            except (ValueError, IndexError):
                out[s] = pd.DataFrame()
                self.diagnostics.append({"symbol": s, "interval": suffix, "error": "CSV_INVALID"})
        return out
