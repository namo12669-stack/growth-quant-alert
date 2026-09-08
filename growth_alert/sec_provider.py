from __future__ import annotations

import logging
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

from .storage import read_json, write_json

LOG = logging.getLogger(__name__)

TICKER_URL = "https://www.sec.gov/files/company_tickers.json"
FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"

# Preferred concepts first. The adapter intentionally exposes only concepts used by factors.py.
CONCEPTS = {
    "Total Revenue": [
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "Revenues",
        "SalesRevenueNet",
    ],
    "Gross Profit": ["GrossProfit"],
    "Operating Income": ["OperatingIncomeLoss"],
    "Basic Average Shares": ["WeightedAverageNumberOfSharesOutstanding"],
    "Diluted Average Shares": ["WeightedAverageNumberOfDilutedSharesOutstanding"],
    "Operating Cash Flow": ["NetCashProvidedByUsedInOperatingActivities"],
    "Capital Expenditure": [
        "PaymentsToAcquirePropertyPlantAndEquipment",
        "PaymentsForAdditionsToPropertyPlantAndEquipment",
    ],
    "Total Assets": ["Assets"],
    "Cash Cash Equivalents And Short Term Investments": [
        "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
        "CashAndCashEquivalentsAtCarryingValue",
        "CashCashEquivalentsAndShortTermInvestments",
    ],
}


class SecEdgarProvider:
    """Small SEC Company Facts adapter used as a fundamentals fallback.

    It is deliberately conservative: only filed 10-Q/10-K facts are used and each
    observation keeps the latest filing for a period. It is a live-snapshot data
    source, not a point-in-time historical backtest database.
    """

    def __init__(self, cfg: dict, clock=None, session: requests.Session | None = None):
        self.cfg = cfg
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.session = session or requests.Session()
        default_ua = cfg.get("data", {}).get(
            "sec_user_agent_default",
            "growth-quant-alert/1.1 github.com/namo12669-stack/growth-quant-alert",
        )
        self.session.headers.update({
            "User-Agent": os.getenv("SEC_USER_AGENT", default_ua),
            "Accept-Encoding": "gzip, deflate",
        })
        self.cache = Path(cfg["data"]["state_dir"]) / "sec"
        self.cache.mkdir(parents=True, exist_ok=True)
        self._ticker_map: dict[str, str] | None = None

    def _get_json(self, url: str) -> dict:
        error = None
        for attempt in range(self.cfg["data"].get("request_attempts", 2)):
            try:
                response = self.session.get(url, timeout=20)
                response.raise_for_status()
                time.sleep(max(.11, self.cfg["data"].get("request_pause_seconds", .15)))
                return response.json()
            except Exception as exc:
                error = exc
                time.sleep(min(2 ** attempt, 4))
        raise RuntimeError(f"SEC request failed ({type(error).__name__})") from None

    def _ticker_lookup(self) -> dict[str, str]:
        if self._ticker_map is not None:
            return self._ticker_map
        path = self.cache / "company_tickers.json"
        stored = read_json(path, None)
        now = self.clock()
        fresh = False
        if stored and stored.get("fetched_at"):
            try:
                age = (now - datetime.fromisoformat(stored["fetched_at"])).total_seconds() / 86400
                fresh = 0 <= age < 7
            except Exception:
                fresh = False
        payload = stored.get("payload") if stored and fresh else None
        if payload is None:
            try:
                payload = self._get_json(TICKER_URL)
                write_json(path, {"fetched_at": now.isoformat(), "payload": payload})
            except RuntimeError:
                if stored:
                    payload = stored.get("payload", {})
                else:
                    raise
        mapping = {}
        for item in payload.values():
            ticker = str(item.get("ticker", "")).upper()
            cik = item.get("cik_str")
            if ticker and cik is not None:
                mapping[ticker] = f"{int(cik):010d}"
        self._ticker_map = mapping
        return mapping

    def _facts(self, symbol: str) -> dict:
        cik = self._ticker_lookup().get(symbol.upper())
        if not cik:
            raise RuntimeError("SEC ticker mapping unavailable")
        path = self.cache / f"{symbol.upper()}_companyfacts.json"
        stored = read_json(path, None)
        now = self.clock()
        if stored and stored.get("fetched_at"):
            try:
                age = (now - datetime.fromisoformat(stored["fetched_at"])).total_seconds() / 3600
                if 0 <= age < self.cfg["data"].get("fundamental_cache_hours", 4):
                    return stored["payload"]
            except Exception:
                pass
        try:
            payload = self._get_json(FACTS_URL.format(cik=cik))
            write_json(path, {"fetched_at": now.isoformat(), "payload": payload})
            return payload
        except RuntimeError:
            if stored:
                return stored.get("payload", {})
            raise

    @staticmethod
    def _unit_rows(fact: dict, share_metric: bool) -> list[dict]:
        units = fact.get("units", {})
        preferred = ("shares",) if share_metric else ("USD", "USD/shares")
        for unit in preferred:
            if unit in units:
                return units[unit]
        return []

    @staticmethod
    def _quarterly_series(rows: list[dict], instant: bool = False) -> pd.Series:
        observations: dict[pd.Timestamp, tuple[str, float]] = {}
        for item in rows:
            if item.get("form") not in ("10-Q", "10-K"):
                continue
            val = item.get("val")
            end = item.get("end")
            filed = item.get("filed", "")
            if val is None or not end:
                continue
            frame = str(item.get("frame") or "")
            # Prefer SEC calendar-quarter frames. For instant facts allow QxI.
            if instant:
                frame_ok = bool(re.fullmatch(r"CY\d{4}Q[1-4]I", frame))
            else:
                frame_ok = bool(re.fullmatch(r"CY\d{4}Q[1-4]", frame))
            if not frame_ok:
                continue
            date = pd.Timestamp(end)
            previous = observations.get(date)
            if previous is None or filed > previous[0]:
                observations[date] = (filed, float(val))
        if not observations:
            return pd.Series(dtype=float)
        return pd.Series({d: v for d, (_, v) in observations.items()}).sort_index(ascending=False)

    def _concept_series(self, facts: dict, concepts: list[str], instant: bool = False,
                        share_metric: bool = False) -> pd.Series:
        usgaap = facts.get("facts", {}).get("us-gaap", {})
        for concept in concepts:
            fact = usgaap.get(concept)
            if not fact:
                continue
            series = self._quarterly_series(self._unit_rows(fact, share_metric), instant=instant)
            if not series.empty:
                return series
        return pd.Series(dtype=float)

    def fundamentals(self, symbol: str) -> dict:
        facts = self._facts(symbol)
        income, cashflow, balance = {}, {}, {}
        for row_name, concepts in CONCEPTS.items():
            share = "Shares" in row_name
            instant = row_name in ("Total Assets", "Cash Cash Equivalents And Short Term Investments")
            series = self._concept_series(facts, concepts, instant=instant, share_metric=share)
            if series.empty:
                continue
            target = balance if instant else cashflow if row_name in ("Operating Cash Flow", "Capital Expenditure") else income
            target[row_name] = series
        def frame(rows: dict[str, pd.Series]) -> pd.DataFrame:
            if not rows:
                return pd.DataFrame()
            return pd.DataFrame(rows).T
        entity = facts.get("entityName", "")
        return {
            "info": {"shortName": entity, "longName": entity},
            "income": frame(income),
            "cashflow": frame(cashflow),
            "balance": frame(balance),
            "eps_trend": pd.DataFrame(),
            "eps_revisions": pd.DataFrame(),
            "fetched_at": self.clock().isoformat(),
            "warnings": ["SEC_FUNDAMENTALS_FALLBACK", "SEC_LIVE_SNAPSHOT_NOT_POINT_IN_TIME"],
            "source": "SEC",
        }
