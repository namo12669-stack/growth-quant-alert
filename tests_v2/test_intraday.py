from datetime import datetime, date, timedelta
import numpy as np
import pandas as pd
import pytest
from quant_alert.calendar import session_dates, session_for
from quant_alert.intraday import session_snapshot, intraday_breakout

@pytest.fixture
def tape():
    days=session_dates(date(2026,8,10),date(2026,9,9))[-15:]
    frames=[]
    for day in days:
        s=session_for(day.date())
        ix=pd.date_range(s.open,s.close-timedelta(minutes=15),freq='15min')
        vol=3000 if day.date()==date(2026,9,9) else 1000
        n=len(ix)
        cl=np.linspace(99,105,n)
        frames.append(pd.DataFrame({'Open':cl-.1,'High':cl+.2,'Low':cl-.2,'Close':cl,'Volume':vol},index=ix))
    return pd.concat(frames)

def test_same_clock_volume_not_full_day(cfg,tape):
    snap,a=session_snapshot(tape,datetime.fromisoformat('2026-09-09T19:07:00+00:00'),cfg)
    assert snap['rvol_same_clock']==3
    assert snap['elapsed_minutes']==330
    assert snap['age_minutes']==7
    assert snap['bar_end']=='2026-09-09T15:00:00-04:00'

def test_incomplete_bar_excluded(cfg,tape):
    now=datetime.fromisoformat('2026-09-09T19:07:00+00:00')
    s1,_=session_snapshot(tape,now,cfg)
    tape.loc[pd.Timestamp('2026-09-09T19:00:00Z'),'Volume']=99999999
    s2,_=session_snapshot(tape,now,cfg)
    assert s1['cumulative_volume']==s2['cumulative_volume']

def test_missing_current_slot_fails(cfg,tape):
    tape=tape.drop(pd.Timestamp('2026-09-09T15:00:00Z'))
    snap,a=session_snapshot(tape,datetime.fromisoformat('2026-09-09T19:07:00+00:00'),cfg)
    assert snap is None and a['status']=='MISSING_CURRENT_INTRADAY_SLOTS'

def test_naive_intraday_timezone_rejected(cfg,tape):
    tape.index=tape.index.tz_localize(None)
    assert session_snapshot(tape,datetime.fromisoformat('2026-09-09T19:07:00Z'),cfg)[1]['status']=='INTRADAY_TIMEZONE_REQUIRED'

def test_stale_intraday_rejected(cfg,tape):
    tape=tape.loc[tape.index<pd.Timestamp('2026-09-09T18:00:00Z')]
    assert session_snapshot(tape,datetime.fromisoformat('2026-09-09T19:07:00Z'),cfg)[1]['status']=='STALE_INTRADAY'

def test_premarket_is_not_regular_session_volume(cfg,tape):
    assert session_snapshot(tape,datetime.fromisoformat('2026-09-09T12:45:00Z'),cfg)[0] is None

def test_too_few_comparable_days(cfg,tape):
    tape=tape.loc[tape.index>pd.Timestamp('2026-09-08T00:00Z')]
    assert session_snapshot(tape,datetime.fromisoformat('2026-09-09T19:07:00Z'),cfg)[1]['status']=='INSUFFICIENT_SAME_CLOCK_HISTORY'

def test_intraday_breakout_requires_price_volume_and_structure(cfg,tape,demo):
    _,data=demo
    f=data['DEMO_BREAK'].copy()
    f[['Open','High','Low','Close']]=f[['Open','High','Low','Close']]*.90
    signals,a=intraday_breakout('X',f,tape,datetime.fromisoformat('2026-09-09T19:07:00Z'),cfg)
    assert len(signals)==1 and 'PROVISIONAL' in signals[0].caution
    assert a['rvol_same_clock']==3
