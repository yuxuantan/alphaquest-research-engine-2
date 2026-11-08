"""Hand-calculated regime features and adversarial information boundaries."""
from copy import deepcopy
from datetime import datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from alphaquest.datasets import COLUMNS, DatasetStore, validate_csv
from alphaquest.research_regimes import RegimeSettings, build_regime_evidence


TRAIN = dict(first_session='2026-01-05', last_session='2026-01-05', sessions=['2026-01-05'])
VALIDATION = dict(first_session='2026-01-07', last_session='2026-01-07', sessions=['2026-01-07'])
NAMES = ['trend', 'range', 'high_volatility', 'low_volatility', 'high_liquidity', 'low_liquidity', 'asia_session', 'europe_session', 'us_session']


def settings(**overrides):
    return RegimeSettings(**(dict(enabled_names=NAMES, lookback_bars=2,
        minimum_training_features=2) | overrides))


def rows(day, closes, volumes):
    return [[day, f'14:0{minute}', str(close), str(close+1), str(close-1), str(close), str(volume), '0', '0']
            for minute, (close, volume) in enumerate(zip(closes, volumes))]


def history():
    return rows('01/05/2026', [100, 102, 104, 102, 104, 106], [10, 20, 30, 40, 50, 60]) + rows(
        '01/07/2026', [100, 102, 104, 100, 100, 102], [10, 20, 30, 5, 5, 5])


def save(tmp_path, values=None, symbol='MNQ'):
    raw = (','.join(COLUMNS) + '\n' + '\n'.join(','.join(row) for row in (values or history())) + '\n').encode()
    store = DatasetStore(tmp_path / 'datasets.sqlite3')
    saved = store.save(raw, validate_csv(raw, 'SYNTHETIC-regimes.csv', 'UTC'), 'SYNTHETIC causal regime arithmetic', symbol)
    return store, saved['id']


def trade(id, minute, pnl, exit_minute=5):
    return dict(trade_id=id, entry_time_utc=f'2026-01-07T14:0{minute}:00Z',
        exit_time_utc=f'2026-01-07T14:0{exit_minute}:00Z', net_pnl=str(pnl))


def evidence(tmp_path, *, values=None, trades=None, declaration=None):
    store, id = save(tmp_path, values)
    return build_regime_evidence(store, id, TRAIN, VALIDATION,
        trades if trades is not None else [trade(1, 1, 2), trade(2, 3, 30), trade(3, 4, -10)],
        declaration or settings())


def by_name(result):
    return {regime['name']: regime for regime in result['regimes']}


def test_exact_features_quantiles_labels_exit_cash_and_warmup(tmp_path):
    result = evidence(tmp_path)
    fit = result['fit']
    assert fit['cutoff'] == '2026-01-05T14:05:00Z'
    assert fit['information_cutoff_session'] == '2026-01-05'
    assert fit['training_bars'] == 6 and fit['samples'] == 4
    # Each training true range is 3 points; trailing volume means are 25,35,45,55.
    assert fit['thresholds'] == dict(trend_efficiency='0.6', volatility_points='3.0', liquidity_volume='40.0')
    early, trending, ranging = result['assignments']
    assert early['feature_asof'] == '2026-01-07T14:00:00Z'
    assert early['features'] is None and early['labels'] == ['us_session']
    assert set(early['unclassified_reasons']) == {
        'direction:insufficient_prior_validation_bars', 'volatility:insufficient_prior_validation_bars',
        'liquidity:insufficient_prior_validation_bars'}
    assert trending['feature_asof'] == '2026-01-07T14:02:00Z'
    assert trending['features'] == dict(directional_efficiency='1', mean_true_range_points='3', mean_volume='25')
    assert trending['labels'] == ['high_volatility', 'low_liquidity', 'trend', 'us_session']
    assert ranging['feature_asof'] == '2026-01-07T14:03:00Z'
    assert Decimal(ranging['features']['directional_efficiency']) == Decimal(2)/6
    assert ranging['features']['mean_true_range_points'] == '4'
    assert ranging['labels'] == ['high_volatility', 'low_liquidity', 'range', 'us_session']
    regimes = by_name(result)
    assert regimes['trend']['sessions'] == [dict(session='2026-01-07', net_pnl='30', trade_count=1)]
    assert regimes['range']['sessions'] == [dict(session='2026-01-07', net_pnl='-10', trade_count=1)]
    assert regimes['us_session']['sessions'] == [dict(session='2026-01-07', net_pnl='22', trade_count=3)]
    assert regimes['low_volatility']['sessions'] == [dict(session='2026-01-07', net_pnl='0', trade_count=0)]
    assert all(regime['observable_at_decision'] for regime in regimes.values())
    assert result['availability']['trend']['observable_trades'] == 2
    assert not result['availability']['trend']['complete']
    assert result['availability']['us_session']['complete']
    assert not regimes['trend']['classification_complete']
    assert regimes['trend']['unclassified_trades'] == 1
    assert regimes['us_session']['classification_complete']
    assert regimes['us_session']['unclassified_trades'] == 0
    assert result['unclassified']['trade_count'] == 1
    assert result['validation_bars'] == 6


def test_entry_bar_and_future_mutation_cannot_change_earlier_assignment(tmp_path):
    baseline = evidence(tmp_path / 'baseline', trades=[trade(1, 3, 30)])
    altered = history()
    for row in altered:
        if row[0] == '01/07/2026' and row[1] >= '14:03':
            row[2:7] = ['-10000', '10000', '-10000', '9999', '99999']
    mutated = evidence(tmp_path / 'mutated', values=altered, trades=[trade(1, 3, 30)])
    assert mutated['assignments'] == baseline['assignments']
    assert mutated['fit']['thresholds'] == baseline['fit']['thresholds']
    assert mutated['regimes'] == baseline['regimes']
    assert mutated['fit']['source']['sha256'] != baseline['fit']['source']['sha256']


def test_training_quantiles_are_isolated_and_gap_is_not_feature_warmup(tmp_path):
    baseline = evidence(tmp_path / 'base')
    altered = rows('01/05/2026', [100, 110, 120, 110, 120, 130], [20, 40, 60, 80, 100, 120]) + history()[6:]
    fitted = evidence(tmp_path / 'fit', values=altered)
    assert fitted['fit']['thresholds']['volatility_points'] == '11.0'
    assert fitted['fit']['thresholds']['liquidity_volume'] == '80.0'
    assert fitted['assignments'][1]['features'] == baseline['assignments'][1]['features']
    assert 'low_volatility' in fitted['assignments'][1]['labels']
    with_gap = history()[:6] + rows('01/06/2026', [0, 999, -999, 999, -999, 999], [999]*6) + history()[6:]
    gap = evidence(tmp_path / 'gap', values=with_gap)
    assert gap['assignments'] == baseline['assignments']
    assert gap['fit']['thresholds'] == baseline['fit']['thresholds']
    assert gap['fit']['training_bars'] == baseline['fit']['training_bars']


def test_completed_trade_outcomes_never_fit_or_classify_regimes(tmp_path):
    baseline = evidence(tmp_path / 'base', trades=[trade(1, 3, 30)])
    changed = evidence(tmp_path / 'changed', trades=[trade(1, 3, -99999)])
    assert baseline['assignments'] == changed['assignments']
    assert baseline['fit']['thresholds'] == changed['fit']['thresholds']
    assert by_name(changed)['trend']['sessions'][0]['net_pnl'] == '-99999'


def test_zero_and_negative_prices_have_finite_point_features(tmp_path):
    values = rows('01/05/2026', [-2, 0, 2, 0, -2, 0], [10]*6) + rows(
        '01/07/2026', [-3, -1, 1, 3, 1, -1], [10]*6)
    result = evidence(tmp_path, values=values, trades=[trade(1, 3, 10)])
    assert result['assignments'][0]['features'] == dict(
        directional_efficiency='1', mean_true_range_points='3', mean_volume='10')
    assert result['fit']['feature_units']['mean_true_range_points'] == 'instrument price points'


def test_specialized_labels_do_not_require_profit_or_evidence_in_other_regimes(tmp_path):
    result = evidence(tmp_path, trades=[trade(1, 3, 30), trade(2, 4, -100)],
                      declaration=settings(enabled_names=['trend']))
    assert [regime['name'] for regime in result['regimes']] == ['trend']
    assert result['regimes'][0]['sessions'] == [dict(session='2026-01-07', net_pnl='30', trade_count=1)]
    assert result['assignments'][1]['labels'] == []
    assert result['assignments'][1]['unclassified_reasons'] == []
    assert result['unclassified']['outside_enabled_regimes_trade_count'] == 1
    assert result['unclassified']['trade_count'] == 0
    assert 'status' not in result, 'This module classifies conditions; it does not qualify or select strategies.'


def test_insufficient_fit_and_zero_trades_are_explicit(tmp_path):
    missing = evidence(tmp_path / 'short', declaration=settings(lookback_bars=10, enabled_names=['high_volatility']))
    assert missing['fit']['samples'] == 0
    assert missing['fit']['status'] == 'insufficient_training_features'
    assert missing['fit']['thresholds']['volatility_points'] is None
    assert missing['unclassified']['reasons'] == {'volatility:insufficient_training_features': 3}
    assert not missing['availability']['high_volatility']['complete']
    assert not missing['regimes'][0]['classification_complete']
    assert missing['regimes'][0]['unclassified_trades'] == 3
    assert missing['regimes'][0]['sessions'][0]['trade_count'] == 0
    empty = evidence(tmp_path / 'empty', trades=[])
    assert empty['assignments'] == [] and empty['unclassified']['trade_count'] == 0
    assert all(regime['sessions'] == [dict(session='2026-01-07', net_pnl='0', trade_count=0)] for regime in empty['regimes'])
    assert all(regime['unclassified_trades'] == 0 for regime in empty['regimes'])


@pytest.mark.parametrize('stamp,label', [
    ('2026-01-06T23:00:00Z', 'asia_session'),
    ('2026-01-07T07:59:00Z', 'asia_session'),
    ('2026-01-07T08:00:00Z', 'europe_session'),
    ('2026-01-07T13:59:00Z', 'europe_session'),
    ('2026-01-07T14:00:00Z', 'us_session'),
    ('2026-07-07T22:00:00Z', 'asia_session'),
    ('2026-07-08T07:00:00Z', 'europe_session'),
    ('2026-07-08T13:00:00Z', 'us_session'),
])
def test_declared_chicago_clock_buckets_use_dst(stamp, label, tmp_path):
    instant = datetime.fromisoformat(stamp.replace('Z', '+00:00'))
    from alphaquest.session_calendar import session_date
    day = session_date(instant).isoformat()
    window = dict(first_session=day, last_session=day, sessions=[day])
    values = history()[:6] + [[instant.strftime('%m/%d/%Y'), instant.strftime('%H:%M'), '100', '101', '99', '100', '10', '0', '0']]
    source, id = save(tmp_path, values)
    result = build_regime_evidence(source, id, TRAIN, window,
        [dict(trade_id='clock', entry_time_utc=stamp, exit_time_utc=stamp, net_pnl='7')],
        settings(enabled_names=['asia_session', 'europe_session', 'us_session']))
    assert result['assignments'][0]['labels'] == [label]
    assert result['assignments'][0]['feature_asof'] is None
    assert result['availability'][label]['complete']
    assert result['fit']['session_buckets']['timezone'] == 'America/Chicago'


@pytest.mark.parametrize('patch', [
    dict(enabled_names=['future_winner']), dict(enabled_names=['trend', 'trend']),
    dict(lookback_bars=True), dict(lookback_bars=1), dict(minimum_training_features=0),
    dict(trend_efficiency_threshold=True), dict(trend_efficiency_threshold='NaN'),
    dict(volatility_quantile=0), dict(liquidity_quantile=1),
    dict(timezone='UTC'), dict(timezone='invalid'), dict(asia_start_hour=7),
    dict(us_start_hour='8'), dict(hidden_future_labels=True),
])
def test_settings_reject_unsupported_or_ambiguous_inputs(patch):
    with pytest.raises(ValidationError): settings(**patch)


def test_default_is_disabled_and_json_arrays_are_accepted():
    assert RegimeSettings().enabled_names == ()
    assert RegimeSettings.model_validate({'enabled_names': ['trend']}).enabled_names == ('trend',)


@pytest.mark.parametrize('symbol', ['', 'ES', 'CL', 'SYNTHETIC', 'NQ_unknown'])
def test_unknown_instrument_is_not_silently_given_nq_regime_semantics(tmp_path, symbol):
    source, id = save(tmp_path, symbol=symbol)
    with pytest.raises(ValueError, match='NQ/MNQ'):
        build_regime_evidence(source, id, TRAIN, VALIDATION, [], settings())


@pytest.mark.parametrize('changed', [
    dict(entry_time_utc='2026-01-07T14:03:00'), dict(entry_time_utc='2026-01-08T14:03:00Z'),
    dict(entry_time_utc='2026-01-07T13:59:00Z'), dict(exit_time_utc='2026-01-07T14:06:00Z'),
    dict(exit_time_utc='2026-01-07T14:00:00Z'), dict(trade_id=True), dict(net_pnl='Infinity'),
])
def test_invalid_trade_identity_times_and_money_reject(tmp_path, changed):
    with pytest.raises(ValueError): evidence(tmp_path, trades=[trade(1, 3, 30) | changed])


def test_windows_and_trade_order_are_not_silently_repaired(tmp_path):
    source, id = save(tmp_path)
    with pytest.raises(ValueError, match='overlap'):
        build_regime_evidence(source, id, TRAIN, TRAIN, [], settings())
    malformed = deepcopy(VALIDATION); malformed['first_session'] = '2026-01-06'
    with pytest.raises(ValueError, match='bounds'):
        build_regime_evidence(source, id, TRAIN, malformed, [], settings())
    with pytest.raises(ValueError, match='chronological entry'):
        build_regime_evidence(source, id, TRAIN, VALIDATION, [trade(1, 4, 0), trade(2, 3, 0)], settings())
    with pytest.raises(ValueError, match='unique'):
        build_regime_evidence(source, id, TRAIN, VALIDATION, [trade(1, 3, 0), trade(1, 4, 0)], settings())
