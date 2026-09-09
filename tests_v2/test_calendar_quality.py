from datetime import datetime, date, timezone
import pandas as pd
import pytest
from quant_alert.calendar import expected_daily_session, due_mode, session_for
from quant_alert.quality import prepare_daily

@pytest.mark.parametrize('timestamp,expected',[
 ('2026-09-08T12:45:00+00:00','2026-09-04'),
 ('2026-09-08T19:30:00+00:00','2026-09-04'),
 ('2026-09-08T20:05:00+00:00','2026-09-04'),
 ('2026-09-08T20:25:00+00:00','2026-09-08'),
 ('2026-09-09T12:45:00+00:00','2026-09-08'),
])
def test_expected_completed_session(timestamp,expected,cfg):
    assert str(expected_daily_session(datetime.fromisoformat(timestamp),cfg))==expected

@pytest.mark.parametrize('stamp,mode',[
 ('2026-09-09T12:37:00+00:00','preopen'),
 ('2026-09-09T19:07:00+00:00','preclose'),
 ('2026-09-09T16:07:00+00:00',None),
 ('2026-09-07T12:37:00+00:00',None),
 ('2026-11-27T17:07:00+00:00','preclose'),
 ('2026-11-30T13:37:00+00:00','preopen'),
 ('2026-09-09T19:55:00+00:00',None),
])
def test_schedule_dst_holiday_half_day(stamp,mode,cfg):
    assert due_mode(datetime.fromisoformat(stamp),cfg)[0]==mode

def test_quality_valid(cfg,demo):
    _,data=demo
    f,q=prepare_daily(data['DEMO_BREAK'],date(2026,9,8),cfg)
    assert q['usable'] and q['session_completeness']==1

def test_quality_incomplete_future_bar_removed(cfg,demo):
    _,data=demo
    f=data['DEMO_BREAK'].copy(); row=f.tail(1).copy(); row.index=[pd.Timestamp('2026-09-09')]
    f=pd.concat([f,row])
    out,q=prepare_daily(f,date(2026,9,8),cfg)
    assert q['usable'] and q['future_or_partial_bars_removed']==1
    assert out.index[-1]==pd.Timestamp('2026-09-08')

def test_quality_stale_fails_closed(cfg,demo):
    _,data=demo
    _,q=prepare_daily(data['DEMO_BREAK'].iloc[:-1],date(2026,9,8),cfg)
    assert not q['usable'] and 'STALE_DAILY_PRICE' in q['reasons']

def test_quality_rejects_invalid_latest_bar(cfg,demo):
    _,data=demo
    f=data['DEMO_BREAK'].copy(); f.loc[f.index[-1],'High']=1
    _,q=prepare_daily(f,date(2026,9,8),cfg)
    assert not q['usable'] and q['invalid_ohlcv_rows']==1

def test_quality_does_not_fill_gaps(cfg,demo):
    _,data=demo
    f=data['DEMO_BREAK'].drop(data['DEMO_BREAK'].index[-20:-10])
    out,q=prepare_daily(f,date(2026,9,8),cfg)
    assert not q['usable'] and len(out)==len(f)

def test_split_guard(cfg,demo):
    _,data=demo
    f=data['DEMO_BREAK'].copy(); f.loc[f.index[-2],'Stock Splits']=4
    _,q=prepare_daily(f,date(2026,9,8),cfg)
    assert not q['usable'] and 'RECENT_SPLIT_REVIEW_REQUIRED' in q['reasons']

def test_quality_empty(cfg):
    assert not prepare_daily(pd.DataFrame(),date(2026,9,8),cfg)[1]['usable']

def test_benchmark_still_needs_freshness(cfg,demo):
    _,data=demo
    _,q=prepare_daily(data['DEMO_MKT'].iloc[:-1],date(2026,9,8),cfg,stock=False)
    assert not q['usable']
