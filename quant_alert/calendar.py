from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
from zoneinfo import ZoneInfo

import exchange_calendars as xcals
import pandas as pd

NY = ZoneInfo("America/New_York")
UTC = timezone.utc


@dataclass(frozen=True)
class Session:
    day: date
    open: datetime
    close: datetime


@lru_cache(maxsize=8)
def _calendar(name: str, year: int):
    # Explicit bounds also cover year-end and long price histories.
    return xcals.get_calendar(name, start=f"{year - 3}-01-01", end=f"{year + 2}-12-31")


def session_for(day: date, name: str = "XNYS") -> Session | None:
    cal = _calendar(name, day.year)
    label = pd.Timestamp(day)
    if not cal.is_session(label):
        return None
    return Session(day, cal.session_open(label).to_pydatetime(),
                   cal.session_close(label).to_pydatetime())


def previous_session_day(day: date, name: str = "XNYS") -> date:
    cal = _calendar(name, day.year)
    # Previous means strictly before this date, even on a holiday/weekend.
    return cal.date_to_session(pd.Timestamp(day - timedelta(days=1)), direction="previous").date()


def last_completed_session(now: datetime, name: str = "XNYS") -> date:
    day = now.astimezone(NY).date()
    session = session_for(day, name)
    if session and now >= session.close:
        return day
    return previous_session_day(day, name)


def due_mode(now: datetime, cfg: dict) -> tuple[str | None, Session | None]:
    if now.tzinfo is None:
        raise ValueError("A timezone-aware timestamp is required")
    session = session_for(now.astimezone(NY).date(), cfg["calendar"])
    if session is None:
        return None, None
    lo = cfg["schedule"]["latest_minutes_before"]
    hi = cfg["schedule"]["earliest_minutes_before"]
    for mode, event in (("preopen", session.open), ("preclose", session.close)):
        minutes = (event - now).total_seconds() / 60
        if lo <= minutes <= hi:
            return mode, session
    return None, session


def expected_daily_session(now: datetime, cfg: dict) -> date:
    """Allow the provider to finalize the daily bar after regular-session close."""
    day = now.astimezone(NY).date()
    session = session_for(day, cfg["calendar"])
    grace = timedelta(minutes=cfg["schedule"]["daily_close_grace_minutes"])
    if session and now >= session.close + grace:
        return day
    return previous_session_day(day, cfg["calendar"])


def session_dates(start: date, end: date, name: str = "XNYS") -> pd.DatetimeIndex:
    cal = _calendar(name, end.year)
    idx = cal.sessions_in_range(pd.Timestamp(start), pd.Timestamp(end))
    if idx.tz is not None:
        idx = idx.tz_localize(None)
    return idx.normalize()


def next_session_day(day: date, name: str = "XNYS") -> date:
    cal = _calendar(name, day.year)
    return cal.date_to_session(pd.Timestamp(day + timedelta(days=1)), direction="next").date()
