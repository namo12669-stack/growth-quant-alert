from datetime import date, datetime, timezone

import pytest

from growth_alert.calendar import due_mode, last_completed_session, session_for


@pytest.mark.parametrize('day', [date(2026, 9, 7), date(2026, 12, 25), date(2026, 9, 12)])
def test_holidays_and_weekends(day):
    assert session_for(day) is None


@pytest.mark.parametrize('stamp,expected', [
    ('2026-09-08T12:37:00+00:00', 'preopen'),
    ('2026-09-08T19:07:00+00:00', 'preclose'),
    ('2026-09-08T16:07:00+00:00', None),
    ('2026-11-27T17:07:00+00:00', 'preclose'),
    ('2026-11-27T20:07:00+00:00', None),
    ('2026-09-08T13:25:00+00:00', None),
    ('2026-09-07T12:37:00+00:00', None),
    ('2026-12-01T13:37:00+00:00', 'preopen'),
    ('2026-12-01T20:07:00+00:00', 'preclose'),
])
def test_windows(cfg, stamp, expected):
    assert due_mode(datetime.fromisoformat(stamp), cfg)[0] == expected


def test_early_close_and_dst():
    assert session_for(date(2026, 11, 27)).close.hour == 18
    assert session_for(date(2026, 9, 8)).open.hour == 13
    assert session_for(date(2026, 12, 1)).open.hour == 14


def test_previous_complete_session_skips_long_weekend(now):
    assert last_completed_session(now) == date(2026, 9, 4)
    assert last_completed_session(datetime(2026, 9, 8, 21, tzinfo=timezone.utc)) == date(2026, 9, 8)


def test_reject_naive_timestamp(cfg):
    with pytest.raises(ValueError):
        due_mode(datetime(2026, 9, 8, 9), cfg)
