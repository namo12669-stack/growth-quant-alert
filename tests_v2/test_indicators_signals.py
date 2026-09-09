import numpy as np
import pandas as pd
import pytest
from quant_alert.indicators import rsi, confirmed_pivots, range_position
from quant_alert.single import divergence, breakout, relative_strength

@pytest.mark.parametrize("values,expected", [(range(40),100), (range(40,0,-1),0), ([5]*40,50)])
def test_rsi_edges(values, expected):
    assert rsi(pd.Series(values, dtype=float)).iloc[-1] == expected

def test_rsi_wilder_seed():
    values=[44.34,44.09,44.15,43.61,44.33,44.83,45.10,45.42,45.84,46.08,45.89,46.03,45.61,46.28,46.28]
    assert rsi(pd.Series(values)).iloc[-1] == pytest.approx(70.464135, abs=.00001)

def test_rsi_short_history():
    assert rsi(pd.Series([1.,2.,3.])).isna().all()

def test_pivot_requires_right_hand_confirmation():
    series=pd.Series([8,7,5,7,8,9],dtype=float)
    assert confirmed_pivots(series.iloc[:4],2,2)==[]
    assert confirmed_pivots(series.iloc[:5],2,2)==[2]
    assert confirmed_pivots(series,2,2)==[2]

def test_pivot_ties_are_not_confirmed():
    assert confirmed_pivots(pd.Series([8,7,5,5,7,8]),2,2)==[]

def test_high_pivot():
    assert confirmed_pivots(pd.Series([1,2,5,2,1]),2,2,"high")==[2]

def test_range_flat_is_neutral():
    assert range_position(10,10,10)==.5

def test_bull_divergence_detected(cfg,demo):
    _,data=demo
    signals,audit=divergence('DEMO_BULL',data['DEMO_BULL'],cfg)
    assert len(signals)==1 and signals[0].direction=='bullish'
    assert signals[0].metrics['rsi_2'] > signals[0].metrics['rsi_1']
    assert signals[0].metrics['confirmation_date']==signals[0].asof

def test_divergence_cannot_alert_at_pivot_low(cfg,demo):
    _,data=demo
    signals,_=divergence('DEMO_BULL',data['DEMO_BULL'].iloc[:-3],cfg)
    assert signals==[]

def test_divergence_expires(cfg,demo):
    _,data=demo
    f=data['DEMO_BULL'].copy()
    extra=f.tail(1).copy()
    for i in range(4):
        row=extra.copy(); row.index=[f.index[-1]+pd.Timedelta(days=1)]
        row[['Open','High','Low','Close']]+=3+i
        f=pd.concat([f,row])
    signals,_=divergence('DEMO_BULL',f,cfg)
    assert signals==[]

def test_breakout_uses_previous_window_not_itself(cfg,demo):
    _,data=demo
    signals,audit=breakout('DEMO_BREAK',data['DEMO_BREAK'],cfg)
    assert len(signals)==1
    assert audit['prior_high'] < audit['bar_close']
    assert audit['rvol_daily']==pytest.approx(3.2)

def test_breakout_requires_volume(cfg,demo):
    _,data=demo
    f=data['DEMO_BREAK'].copy(); f.loc[f.index[-1],'Volume']=1
    assert breakout('X',f,cfg)[0]==[]

def test_breakout_requires_high_close_position(cfg,demo):
    _,data=demo
    f=data['DEMO_BREAK'].copy(); f.loc[f.index[-1],'High']=140
    assert breakout('X',f,cfg)[0]==[]

def test_relative_strength_is_price_ratio_not_duplicate_return_rank(cfg,demo):
    _,data=demo
    s,a=relative_strength('DEMO_BREAK',data['DEMO_BREAK'],'DEMO_MKT',data['DEMO_MKT'],cfg)
    assert len(s)==1 and a['excess_return'] > .03

def test_relative_strength_missing_benchmark(cfg,demo):
    _,data=demo
    assert relative_strength('X',data['DEMO_BREAK'],'M',None,cfg)[1]['status']=='BENCHMARK_UNAVAILABLE_OR_STALE'

def test_relative_strength_stale_benchmark(cfg,demo):
    _,data=demo
    assert relative_strength('X',data['DEMO_BREAK'],'M',data['DEMO_MKT'].iloc[:-1],cfg)[0]==[]

def test_bearish_divergence_is_detected_not_short_execution(cfg,demo):
    _,data=demo
    x=data['DEMO_BULL']; f=x.copy()
    f['Open']=300-x.Open; f['Close']=300-x.Close
    f['High']=300-x.Low; f['Low']=300-x.High
    signals,_=divergence('BEAR',f,cfg)
    assert any(s.direction=='bearish' for s in signals)
    cfg['alerts']['allow_bearish']=False
    assert divergence('BEAR',f,cfg)[0]==[]
