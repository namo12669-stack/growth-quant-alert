import numpy as np
import pytest
from quant_alert.relationships import inspect_pair, inspect_lead_lag, correct_family, relationship_signals


def test_synthetic_cointegrated_pair_passes(cfg,demo):
    _,d=demo
    r=inspect_pair('DEMO_A','DEMO_B',d,cfg)
    assert r['model_gates_pass'] and r['trigger_gates_pass']
    assert r['raw_p']<.01
    assert r['zscore']==pytest.approx(-2.5)
    assert r['formation_end'] < r['validation_end'] < r['asof']

def test_pair_current_observation_is_not_in_formation(cfg,demo):
    _,d=demo
    r1=inspect_pair('DEMO_A','DEMO_B',d,cfg)
    d2={s:f.copy() for s,f in d.items()}
    d2['DEMO_A'].iloc[-1,d2['DEMO_A'].columns.get_loc('Close')]*=1.10
    r2=inspect_pair('DEMO_A','DEMO_B',d2,cfg)
    for key in ['beta','alpha','raw_p','sigma']:
        assert r1[key]==pytest.approx(r2[key])
    assert not r2['trigger_gates_pass']

def test_pair_missing_observations_rejected(cfg,demo):
    _,d=demo
    d['DEMO_A']=d['DEMO_A'].drop(d['DEMO_A'].index[-30])
    assert not inspect_pair('DEMO_A','DEMO_B',d,cfg)['model_gates_pass']

def test_pair_missing_symbol(cfg,demo):
    _,d=demo
    r=inspect_pair('MISSING','DEMO_B',d,cfg)
    assert r['raw_p']==1 and r['reject_reasons']==['MISSING_OR_REJECTED_PRICE_DATA']

def test_pair_identical_series_rejected(cfg,demo):
    _,d=demo
    d['COPY']=d['DEMO_A'].copy()
    r=inspect_pair('DEMO_A','COPY',d,cfg)
    assert not r['model_gates_pass']

def test_multiple_testing_includes_failed_hypotheses(cfg):
    rows=[{'raw_p':.01,'model_gates_pass':True,'trigger_gates_pass':True,'reject_reasons':[]},
          {'raw_p':1.,'model_gates_pass':False,'trigger_gates_pass':False,'reject_reasons':['MISSING']}]
    out=correct_family(rows,cfg,'pairs')
    assert out[0]['adjusted_p']==pytest.approx(.03)
    assert out[0]['family_tests']==2

def test_true_lagged_synthetic_process_passes(cfg,demo):
    _,d=demo
    r=inspect_lead_lag('DEMO_LEAD','DEMO_FOLLOW','DEMO_MKT',d,cfg)
    assert r['model_gates_pass'] and r['trigger_gates_pass']
    assert r['oos_mse_improvement']>.5 and r['validation_sessions']==63
    assert r['target_session'] > r['asof']

def test_leader_today_changes_forecast_not_estimated_training_coefficient(cfg,demo):
    _,d=demo
    r1=inspect_lead_lag('DEMO_LEAD','DEMO_FOLLOW','DEMO_MKT',d,cfg)
    d['DEMO_LEAD'].iloc[-1,d['DEMO_LEAD'].columns.get_loc('Close')]*=1.01
    r2=inspect_lead_lag('DEMO_LEAD','DEMO_FOLLOW','DEMO_MKT',d,cfg)
    assert r1['beta']==pytest.approx(r2['beta'])
    assert r1['oos_mse_improvement']==pytest.approx(r2['oos_mse_improvement'])
    assert r2['predicted_return']>r1['predicted_return']

def test_reverse_direction_is_not_assumed_predictive(cfg,demo):
    _,d=demo
    assert not inspect_lead_lag('DEMO_FOLLOW','DEMO_LEAD','DEMO_MKT',d,cfg)['model_gates_pass']

def test_lagged_model_needs_market_history(cfg,demo):
    _,d=demo
    del d['DEMO_MKT']
    assert not inspect_lead_lag('DEMO_LEAD','DEMO_FOLLOW','DEMO_MKT',d,cfg)['model_gates_pass']

def test_all_fixed_candidate_directions_audited(cfg,demo):
    u,d=demo
    signals,audit=relationship_signals(d,u,cfg)
    assert len(audit)==len(u['pairs'])*3
    assert {'PAIR_SPREAD','LEAD_LAG'} <= {s.kind for s in signals}
    assert all('adjusted_p' in r for r in audit)
