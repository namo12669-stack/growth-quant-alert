import copy

import pandas as pd

from growth_alert.demo import demo_records
from growth_alert.scoring import percentile, score_records


def test_ties_are_neutral():
    assert percentile(3, pd.Series([3, 3, 3, 3])) == 50
    assert percentile(3, pd.Series([1, 2, 3])) == 100
    assert percentile(1, pd.Series([1, 2, 3])) == 0


def test_good_synthetic_records_rank_above_bad(cfg, now):
    ranked = score_records(demo_records(now, cfg), cfg)
    assert ranked[0]['score'] > ranked[-1]['score']
    assert all(0 <= r['score'] <= 100 for r in ranked)
    assert all(r['coverage'] == 1 for r in ranked)


def test_missing_factors_neutral_and_not_reweighted(cfg, now):
    records = demo_records(now, cfg)
    records[-1].pop('eps_revision_30d')
    records[-1].pop('revision_breadth_30d')
    result = next(r for r in score_records(records, cfg) if r['symbol'] == 'DEMO16')
    assert result['expectations_score'] == 50
    assert result['coverage'] == .8
    assert result['score'] == round(result['raw_score'] - 2.4, 2)


def test_insufficient_pool_not_ranked(cfg, now):
    ranked = score_records(demo_records(now, cfg)[:3], cfg)
    assert all(not r['eligible'] and r['score'] is None for r in ranked)


def test_cash_runway_cannot_be_offset_by_high_score(cfg, now):
    records = demo_records(now, cfg)
    records[-1]['cash_runway_quarters'] = 2
    r = next(r for r in score_records(records, cfg) if r['symbol'] == 'DEMO16')
    assert 'CASH_RUNWAY_BLOCK' in r['exclusions']
    assert r['score'] is None


def test_sector_fallback_disclosed_and_valuation_not_cross_sector(cfg, now):
    records = demo_records(now, cfg)
    records[-1]['sector'] = 'Unique sector'
    result = next(r for r in score_records(records, cfg) if r['symbol'] == 'DEMO16')
    assert result['ranking_scopes']['revenue_yoy'] == 'growth_universe_fallback'
    assert result['ranking_scopes']['sales_to_ev'] == 'unavailable_neutral'


def test_config_input_records_not_mutated(cfg, now):
    records = demo_records(now, cfg)
    original = copy.deepcopy(records)
    score_records(records, cfg)
    assert records == original
