import numpy as np
import pandas as pd

from growth_alert.factors import financial_features, price_features, ttm


def make_payload():
    cols = pd.to_datetime(['2026-06-30', '2026-03-31', '2025-12-31', '2025-09-30', '2025-06-30', '2025-03-31'])
    income = pd.DataFrame([
        [140, 125, 120, 115, 100, 100], [13, 12, 12, 11, 10, 10],
        [70, 60, 60, 55, 45, 45], [14, 5, 2, -5, -10, -10],
    ], index=['Total Revenue', 'Basic Average Shares', 'Gross Profit', 'Operating Income'], columns=cols)
    cf = pd.DataFrame([[20]*6, [-5]*6], index=['Operating Cash Flow', 'Capital Expenditure'], columns=cols)
    bs = pd.DataFrame([[500]*6, [100]*6, [50]*6], index=['Total Assets', 'Cash And Cash Equivalents', 'Total Debt'], columns=cols)
    return {'income': income, 'cashflow': cf, 'balance': bs,
            'info': {'currency': 'USD', 'financialCurrency': 'USD', 'enterpriseValue': 2000},
            'eps_trend': pd.DataFrame({'current': [1.2], '30daysAgo': [1.0]}, index=['+1y']),
            'eps_revisions': pd.DataFrame({'upLast30days': [3], 'downLast30days': [1]}, index=['+1y'])}


def test_growth_and_dilution(now):
    f = financial_features(make_payload(), now)
    assert np.isclose(f['revenue_yoy'], .4)
    assert np.isclose(f['revenue_per_share_yoy'], (140/13)/(100/10)-1)
    assert np.isclose(f['revenue_acceleration'], .15)
    assert np.isclose(f['dilution_yoy'], .3)


def test_cash_profitability_and_margin(now):
    f = financial_features(make_payload(), now)
    assert np.isclose(f['cfo_assets'], 80/500)
    assert np.isclose(f['fcf_margin'], 60/500)
    assert np.isclose(f['gross_profit_assets'], 245/500)
    assert np.isclose(f['operating_margin_change'], .2)
    assert np.isclose(f['sales_to_ev'], .25)


def test_negative_eps_and_zero_breadth(now):
    p = make_payload()
    p['eps_trend'].loc['+1y', '30daysAgo'] = -.01
    p['eps_revisions'].loc['+1y'] = [0, 0]
    f = financial_features(p, now)
    assert 'eps_revision_30d' not in f
    assert f['revision_breadth_30d'] == 0


def test_revision_snapshot(now):
    f = financial_features(make_payload(), now)
    assert np.isclose(f['eps_revision_30d'], .2)
    assert np.isclose(f['revision_breadth_30d'], .5)


def test_currency_mismatch_blocks_valuation(now):
    p = make_payload()
    p['info']['financialCurrency'] = 'EUR'
    assert 'sales_to_ev' not in financial_features(p, now)


def test_no_quarterly_history_does_not_fabricate_growth(now):
    p = make_payload()
    p['income'] = p['income'].iloc[:, :4]
    f = financial_features(p, now)
    assert np.isnan(f['revenue_yoy'])
    assert np.isnan(f['revenue_per_share_yoy'])


def test_irregular_periods_do_not_get_summed_as_ttm():
    series = pd.Series([10, 10, 10, 10], index=pd.to_datetime(['2026-06-30', '2026-03-31', '2025-06-30', '2025-03-31']))
    assert np.isnan(ttm(series, pd.Timestamp('2026-06-30')))


def test_empty_financial_statements(now):
    assert financial_features({}, now)['statement_period'] is None


def test_daily_current_partial_bar_is_excluded(now):
    index = pd.bdate_range('2025-01-01', '2026-09-08', tz='America/New_York')
    index = index[index.date != pd.Timestamp('2026-09-07').date()]
    frame = pd.DataFrame({'Close': 10.0, 'Adj Close': 10.0, 'High': 11.0, 'Volume': 1000000}, index=index)
    frame.loc[frame.index[-1], ['Close', 'Adj Close']] = 9999
    f = price_features(frame, now)
    assert f['previous_close'] == 10
    assert f['price_date'] == '2026-09-04'
    assert f['daily_price_valid']
    assert f['momentum_12_1'] == 0


def test_stale_prices_rejected(now):
    frame = pd.DataFrame({'Close': [10.0], 'High': [11], 'Volume': [100]}, index=pd.to_datetime(['2026-09-03']))
    assert not price_features(frame, now)['daily_price_valid']


def test_empty_price_frame(now):
    assert not price_features(pd.DataFrame(), now)['daily_price_valid']


def test_all_missing_adjusted_prices_fail_closed(now):
    frame = pd.DataFrame({'Close': [10.0], 'Adj Close': [float('nan')], 'High': [11.0], 'Volume': [100]},
                         index=pd.to_datetime(['2026-09-04']))
    assert not price_features(frame, now)['daily_price_valid']
