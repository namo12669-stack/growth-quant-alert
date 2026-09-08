from datetime import datetime

import pandas as pd

from growth_alert.intraday import intraday_features


def make_bars():
    dates = ['2026-08-27', '2026-08-28', '2026-08-31', '2026-09-01', '2026-09-02', '2026-09-03', '2026-09-04', '2026-09-08']
    frames = []
    for day in dates:
        idx = pd.date_range(day + ' 09:30', day + ' 15:55', freq='5min', tz='America/New_York')
        frames.append(pd.DataFrame({'Close': 11., 'High': 12., 'Low': 10.,
                                    'Volume': 200 if day == dates[-1] else 100}, index=idx))
    return pd.concat(frames)


def test_rvol_uses_same_time_not_full_day(cfg):
    now = datetime.fromisoformat('2026-09-08T15:07:00-04:00')
    result = intraday_features(make_bars(), now, 'preclose', 10, cfg)
    assert result['intraday_available']
    assert result['rvol_same_time'] == 2
    assert result['rvol_history_days'] == 7
    assert result['quote_time'].startswith('2026-09-08T15:05:00')
    assert abs(result['session_return'] - .1) < 1e-8


def test_unfinished_bar_never_used(cfg):
    bars = make_bars()
    bars.loc[pd.Timestamp('2026-09-08T15:05:00-04:00'), 'Close'] = 999
    result = intraday_features(bars, datetime.fromisoformat('2026-09-08T15:07:00-04:00'), 'preclose', 10, cfg)
    assert result['intraday_price'] == 11


def test_stale_and_no_timezone(cfg):
    bars = make_bars()
    early = bars.loc[bars.index < pd.Timestamp('2026-09-08T14:00:00-04:00')]
    now = datetime.fromisoformat('2026-09-08T15:07:00-04:00')
    assert not intraday_features(early, now, 'preclose', 10, cfg)['intraday_available']
    bars.index = bars.index.tz_localize(None)
    assert intraday_features(bars, now, 'preclose', 10, cfg)['quote_status'] == 'UNKNOWN_TIMEZONE'


def test_premarket_no_data_does_not_reuse_yesterday(cfg):
    now = datetime.fromisoformat('2026-09-08T08:40:00-04:00')
    assert not intraday_features(make_bars(), now, 'preopen', 10, cfg)['intraday_available']


def test_manual_after_close_has_no_intraday_signal(cfg):
    now = datetime.fromisoformat('2026-09-08T16:10:00-04:00')
    result = intraday_features(make_bars(), now, 'manual', 11, cfg)
    assert not result['intraday_available']
    assert result['quote_status'] == 'REGULAR_SESSION_CLOSED'
