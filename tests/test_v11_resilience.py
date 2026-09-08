import pandas as pd

from growth_alert.demo import demo_records
from growth_alert.provider import _merge_payload
from growth_alert.scoring import exclusions, score_records


def test_missing_market_cap_is_warning_not_hard_block(cfg, now):
    record = demo_records(now, cfg)[0]
    record.pop('market_cap', None)
    assert 'MARKET_CAP_FILTER' not in exclusions(record, cfg)


def test_partial_fundamentals_can_rank_with_coverage(cfg, now):
    records = demo_records(now, cfg)
    for r in records:
        # Simulate missing analyst estimates and valuation while retaining growth/quality/momentum.
        r.pop('eps_revision_30d', None)
        r.pop('revision_breadth_30d', None)
        r.pop('sales_to_ev', None)
    ranked = score_records(records, cfg)
    eligible = [r for r in ranked if r['eligible']]
    assert eligible
    assert all(r['coverage'] >= cfg['filters']['min_score_coverage'] for r in eligible)
    assert all(r['confidence'] in {'LOW', 'MEDIUM', 'HIGH'} for r in eligible)


def test_sec_rows_fill_missing_yahoo_rows():
    primary = {
        'info': {'sector': 'Technology'},
        'income': pd.DataFrame([[1.0]], index=['Operating Income'], columns=[pd.Timestamp('2026-06-30')]),
        'cashflow': pd.DataFrame(), 'balance': pd.DataFrame(),
        'eps_trend': pd.DataFrame(), 'eps_revisions': pd.DataFrame(),
        'warnings': [], 'source': 'Yahoo', 'fetched_at': '2026-09-08T00:00:00+00:00',
    }
    fallback = {
        'info': {'shortName': 'Test'},
        'income': pd.DataFrame([[10.0]], index=['Total Revenue'], columns=[pd.Timestamp('2026-06-30')]),
        'cashflow': pd.DataFrame([[3.0]], index=['Operating Cash Flow'], columns=[pd.Timestamp('2026-06-30')]),
        'balance': pd.DataFrame([[20.0]], index=['Total Assets'], columns=[pd.Timestamp('2026-06-30')]),
        'warnings': ['SEC_FUNDAMENTALS_FALLBACK'], 'source': 'SEC', 'fetched_at': '2026-09-08T00:00:01+00:00',
    }
    merged = _merge_payload(primary, fallback)
    assert 'Total Revenue' in merged['income'].index
    assert 'Operating Income' in merged['income'].index
    assert merged['source'] == 'Yahoo+SEC'
