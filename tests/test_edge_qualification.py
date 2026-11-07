"""Analytical inner-evidence examples, never runtime qualification fixtures."""
from copy import deepcopy
from datetime import date, timedelta
from decimal import Decimal

import pytest

from alphaquest.edge_qualification import QualificationSettings, qualify_candidates


def candidates(count=3, strategy='signal'):
    return [dict(id=str(i), strategy_id=strategy, parameters=dict(length=i+1)) for i in range(count)]


def evidence(values=(10, 10, 10), sessions=10):
    start = date(2020, 1, 1)
    return [dict(fold_index=i, sessions=[dict(session=(start+timedelta(days=i*sessions+j)).isoformat(),
        net_pnl=str(value[j] if isinstance(value, list) else value), trade_count=1)
        for j in range(sessions)]) for i, value in enumerate(values)]


def settings(**changes):
    return QualificationSettings(**dict(dict(minimum_sessions=30, minimum_trades=30), **changes))


def result(cs=None, es=None, **changes):
    cs = candidates() if cs is None else cs
    es = {c['id']: evidence() for c in cs} if es is None else es
    return qualify_candidates(cs, es, settings(**changes))


def test_complete_stable_region_admitted_without_winner_and_exact_cost_units():
    r = result(additional_round_trip_cost='2')
    assert r['approved_ids'] == ['0', '1', '2']
    assert 'winner' not in r
    assert len(r['candidates']) == 3
    for row in r['candidates']:
        assert row['status'] == 'PASS'
        assert row['metrics']['validation_sessions'] == row['metrics']['validation_trades'] == 30
        assert row['uncertainty']['lower'] == row['uncertainty']['upper'] == 10
        assert row['execution_stress']['stressed_mean_session_net'] == '8'
        assert row['execution_stress']['break_even_additional_round_trip_cost'] == '10'
    assert r['historical_observation_count'] == 30
    assert r['settings']['additional_round_trip_cost'] == '2'


def test_isolated_lucky_peak_is_not_a_robust_region():
    r = result(es={'0': evidence((-10, -10, -10)), '1': evidence(), '2': evidence((-10, -10, -10))})
    assert r['approved_ids'] == []
    peak = r['candidates'][1]
    assert peak['status'] == 'FAIL'
    assert 'unstable_parameter_region' in peak['reasons']
    assert peak['parameter_stability']['neighbor_ids'] == ['0', '2']


def test_disappearing_signal_and_profit_concentration_fail_predeclared_tests():
    r = result(es={str(i): evidence((100, 1, -5)) for i in range(3)}, minimum_positive_fold_fraction=1.0)
    assert all(r['status'] == 'FAIL' for r in r['candidates'])
    assert 'too_few_profitable_inner_folds' in r['candidates'][0]['reasons']
    assert 'profits_concentrated_in_one_fold' in r['candidates'][0]['reasons']


def test_controlled_zero_expectancy_noise_does_not_pass():
    # Specified deterministic zero expectancy, not a claim about all random draws.
    noise = [-10, 10]*5
    r = result(es={str(i): evidence((noise, noise, noise)) for i in range(3)})
    assert not r['approved_ids']
    assert all('mean_session_net_below_threshold' in row['reasons'] for row in r['candidates'])


def test_sparse_evidence_is_insufficient_and_does_not_become_sample_size_from_bootstrap():
    r = result(es={str(i): evidence((100, 100), sessions=3) for i in range(3)}, bootstrap_replicates=10000)
    assert all(row['status'] == 'INSUFFICIENT_EVIDENCE' for row in r['candidates'])
    assert r['candidates'][0]['metrics']['validation_trades'] == 6
    assert 'too_few_sessions_for_blocks' in r['candidates'][0]['reasons']


def test_missing_candidate_fold_is_insufficient_without_dropping_the_candidate():
    es = {str(i): evidence() for i in range(3)}
    es['0'].pop()
    es['1'] = []
    r = result(es=es)
    assert len(r['candidates']) == 3
    assert r['historical_observation_count'] == 30
    assert r['candidates'][0]['status'] == 'INSUFFICIENT_EVIDENCE'
    assert 'missing_declared_inner_folds' in r['candidates'][0]['reasons']
    assert 'missing_declared_inner_folds' in r['candidates'][1]['reasons']


def test_multiplicity_uses_entire_declared_family_including_missing_candidates():
    cs = candidates(12)
    r = result(cs=cs, es={c['id']: evidence() for c in cs[:-1]})
    assert r['multiplicity_family_size'] == 12
    assert not r['approved_ids']
    assert 'bootstrap_tail_resolution' in r['candidates'][0]['reasons']
    assert r['candidates'][0]['uncertainty'] is None
    assert all(row['status'] == 'INSUFFICIENT_EVIDENCE' for row in r['candidates'])
    # Increasing computation resolves tail discretization, not future uncertainty.
    r = result(cs=cs, es={c['id']: evidence() for c in cs}, bootstrap_replicates=5000)
    assert len(r['approved_ids']) == 12
    assert r['candidates'][0]['uncertainty']['nominal_candidate_confidence_level'] == pytest.approx(1-.05/12)
    assert r['candidates'][0]['metrics']['validation_sessions'] == 30


def test_reproducible_and_candidate_order_cannot_change_admission():
    cs = candidates()
    es = {c['id']: evidence(([1, 20]*5, [2, 30]*5, [3, 40]*5)) for c in cs}
    a = result(cs=cs, es=es)
    assert a == result(cs=list(reversed(cs)), es=dict(reversed(list(es.items()))))
    assert a['input_sha256'] != result(cs=cs, es=es, bootstrap_seed=43)['input_sha256']
    assert a['settings']['bootstrap_seed'] == 42


def test_neighbors_do_not_cross_strategy_or_categorical_strata():
    cs = candidates(2) + candidates(2, strategy='other')
    for i, c in enumerate(cs):
        c['id'] = str(i)
    cs += [dict(id='4', strategy_id='signal', parameters=dict(length=1, mode='a')),
           dict(id='5', strategy_id='signal', parameters=dict(length=2, mode='b'))]
    r = result(cs=cs)
    assert r['candidates'][0]['parameter_stability']['neighbor_ids'] == ['1']
    assert r['candidates'][2]['parameter_stability']['neighbor_ids'] == ['3']
    assert all(row['status'] == 'INSUFFICIENT_EVIDENCE' for row in r['candidates'][4:])


def test_missing_required_execution_or_regime_assessment_blocks_admission():
    r = result(required_scenarios=('adverse_limit_fills',), required_regimes=('high_vol',))
    for row in r['candidates']:
        assert row['status'] == 'INSUFFICIENT_EVIDENCE'
        assert 'missing_scenario:adverse_limit_fills' in row['reasons']
        assert 'missing_regime:high_vol' in row['reasons']


def test_specialized_regime_strategy_need_only_pass_its_predeclared_regime():
    es = {str(i): evidence() for i in range(3)}
    for fs in es.values():
        for f in fs:
            f['regimes'] = [dict(name='trend', observable_at_decision=True, sessions=deepcopy(f['sessions'])),
                dict(name='range', observable_at_decision=True,
                     sessions=[dict(s, net_pnl='-1') for s in f['sessions']])]
    r = result(es=es, required_regimes=('trend',))
    assert r['approved_ids'] == ['0', '1', '2']
    assert all(row['market_conditions'][0]['name'] == 'trend' for row in r['candidates'])
    # A hindsight-defined regime cannot become required causal evidence.
    es['0'][0]['regimes'][0]['observable_at_decision'] = False
    r = result(es=es, required_regimes=('trend',))
    assert r['candidates'][0]['status'] == 'INSUFFICIENT_EVIDENCE'
    assert 'regime_not_observable_at_decision:trend' in r['candidates'][0]['reasons']


def test_cost_stress_has_break_even_boundary_and_scenario_rerun_is_distinct():
    r = result(additional_round_trip_cost='10')
    assert not r['approved_ids']
    assert all('additional_cost_stress_failed' in row['reasons'] for row in r['candidates'])
    es = {str(i): evidence() for i in range(3)}
    for fs in es.values():
        for f in fs:
            f['scenarios'] = {'slower_stop': [dict(s, net_pnl='-1') for s in f['sessions']]}
    r = result(es=es, required_scenarios=('slower_stop',))
    assert all('scenario_failed:slower_stop' in row['reasons'] for row in r['candidates'])


def test_zero_trade_sessions_are_retained_in_denominator():
    es = {str(i): evidence() for i in range(3)}
    for fs in es.values():
        for f in fs:
            f['sessions'][0].update(net_pnl='0', trade_count=0)
    r = result(es=es, minimum_trades=20)
    assert r['candidates'][0]['metrics']['validation_sessions'] == 30
    assert r['candidates'][0]['metrics']['validation_trades'] == 27
    assert Decimal(r['candidates'][0]['metrics']['mean_session_net']) == 9


@pytest.mark.parametrize('change', [dict(minimum_folds=True), dict(minimum_sessions=2.5),
    dict(additional_round_trip_cost='NaN'), dict(additional_round_trip_cost='-1'),
    dict(confidence_level=1.0), dict(required_regimes=('trend', 'trend')),
    dict(outer_test_threshold=1), dict(bootstrap_seed=-1)])
def test_settings_reject_invalid_or_undeclared_fields(change):
    with pytest.raises(ValueError):
        settings(**change)


@pytest.mark.parametrize('damage', ['scope', 'future_field', 'session_order', 'fold_overlap',
    'calendar', 'count', 'nan', 'scenario_dates', 'regime_future', 'unknown_id', 'duplicate_id', 'duplicate_configuration'])
def test_strict_evidence_boundaries(damage):
    cs = candidates()
    es = {c['id']: evidence() for c in cs}
    f = es['0'][0]
    if damage == 'scope': f['scope'] = 'outer_test'
    elif damage == 'future_field': f['outer_test_net'] = '100000'
    elif damage == 'session_order': f['sessions'].reverse()
    elif damage == 'fold_overlap': es['0'][1]['sessions'] = deepcopy(f['sessions'])
    elif damage == 'calendar': es['0'][2]['sessions'].pop()
    elif damage == 'count': f['sessions'][0]['trade_count'] = True
    elif damage == 'nan': f['sessions'][0]['net_pnl'] = 'Infinity'
    elif damage == 'scenario_dates': f['scenarios'] = {'stops': f['sessions'][:-1]}
    elif damage == 'regime_future': f['regimes'] = [dict(name='future', observable_at_decision=True,
        sessions=[dict(session='2030-01-01', net_pnl='100', trade_count=1)])]
    elif damage == 'unknown_id': es['outer_test_winner'] = evidence()
    elif damage == 'duplicate_id': cs[1]['id'] = cs[0]['id']
    elif damage == 'duplicate_configuration': cs[1]['parameters'] = dict(cs[0]['parameters'])
    with pytest.raises(ValueError):
        result(cs=cs, es=es)
