"""Independent fold arithmetic, censored denominators and family boundaries."""
from copy import deepcopy
from datetime import date, timedelta
from math import sqrt

import pytest

from alphaquest.research_reliability import (
    ReliabilitySettings, consolidate_reliability, logical_policy_identity, _empirical_bounds)


def fixture(phase='funded', predictions=(100, 200, 300), actual=(80, 260, 210),
            baseline=(60, 220, 200), probabilities=(.2, .7, .9)):
    plan = dict(input_identity='procedure', economic_studies=[dict(phase=phase)], folds=[],
                baselines=[dict(id='fixed', phase=phase, required=True)])
    folds = []
    for index, (predicted, realized, reference, probability) in enumerate(zip(predictions, actual, baseline, probabilities), 1):
        stamp = (date(2026, 1, 1)+timedelta(days=10*index)).isoformat()
        window = dict(first_session=stamp, last_session=stamp, sessions=[stamp])
        outer = dict(index=index, train={}, test=window)
        plan['folds'].append(outer)
        target = dict(window, cutoff_date_exclusive=(date.fromisoformat(stamp)+timedelta(days=1)).isoformat())
        package = dict(candidate_id=f'choice{index}', package_sha256=f'package{index}', phase=phase,
            strategy=dict(id='signal', parameters={'period': 20}, code_sha256='stable'),
            configuration=dict(micros=3, sizing=None, simulation=dict(max_micros=40, seed=index),
                profile={'id': 'same'}, costs={'mode': 'source'}, period=window,
                source={'source_backtest_id':f'run{index}'}), outer_window=target,
            receipt_delay_calendar_days=0, receipt_amount_convention='kernel_entitlement_unrounded')
        forecast = dict(candidate_id=package['candidate_id'], metrics=dict(
            expected_funded_cash_payouts_within_horizon=predicted, probability_first_payout=probability,
            cost_per_funded=70, expected_calendar_days_to_funded=2), uncertainty={'mean_monte_carlo_se':1})
        output = dict(frozen_binding=package, cash_received=realized, pending_cash=0, gross_account_deductions=realized,
            horizon_observations_complete=True, lifetime_censored=True, outcome='open',
            receipt_amount_convention='kernel_entitlement_unrounded', paid_fees=realized,
            acquisition_completed=True, censored=False, calendar_days_to_funded=2)
        ref_package = deepcopy(package); ref_package['package_sha256'] = f'reference{index}'
        ref_output = dict(output, frozen_binding=ref_package, cash_received=reference, paid_fees=reference)
        selection = dict(status='SELECTION_FROZEN', phases=[dict(phase=phase, decision={'status':'SELECTED'},
            frozen_packages=[package], training_forecasts=[forecast])])
        folds.append(dict(index=index, economic_selection=selection,
            chronological_replay=dict(items=[dict(phase=phase, candidate_id=package['candidate_id'], result=output)]),
            baseline_results=[dict(baseline_id='fixed',phase=phase,required=True,training_forecast=forecast,
                frozen_package=ref_package,chronological_replay=ref_output,edge_qualification={'status':'FAIL'})]))
    return plan, folds


def run(plan, folds, **settings):
    return consolidate_reliability(plan, folds, ReliabilitySettings(**settings))['phases'][plan['economic_studies'][0]['phase']]


def test_forecast_error_arithmetic_and_reference_threshold():
    plan, folds = fixture()
    result = run(plan, folds, minimum_baseline_mean_improvement='30')
    errors = result['forecast_errors']
    assert errors['mean_error'] == pytest.approx(-50/3)
    assert errors['mean_absolute_error'] == pytest.approx(170/3)
    assert errors['root_mean_squared_error'] == pytest.approx(sqrt(12100/3))
    assert result['scalar_metrics']['mean_cash_received'] == pytest.approx(550/3)
    comparison = result['baseline_comparisons'][0]
    assert [p['improvement'] for p in comparison['pairs']] == [20,40,10]
    assert comparison['paired_mean_improvement'] == pytest.approx(70/3)
    assert not comparison['point_estimate_exceeds_threshold']
    assert comparison['decision'] == 'INSUFFICIENT_EVIDENCE'
    assert result['status'] == 'INSUFFICIENT_EVIDENCE'
    assert result['coverage']['independent_block_count'] is None
    assert all(not m['recommendation_eligible'] for r in result['folds'] for m in r['baseline_members'])


def test_probability_calibration_uses_historical_blocks_not_mc_paths():
    plan, folds = fixture(actual=(0,260,210))
    result = run(plan, folds)
    calibration = result['calibration']
    assert calibration['brier_score'] == pytest.approx(.14/3)
    assert calibration['historical_block_count'] == 3
    assert calibration['status'] == 'INSUFFICIENT_EVIDENCE'
    for fold in folds:
        fold['economic_selection']['phases'][0]['training_forecasts'][0]['uncertainty']['monte_carlo_paths'] = 100000
    assert run(plan, folds)['calibration'] == calibration


def test_missing_fold_stays_in_denominator_without_zero_filling():
    plan, folds = fixture()
    result = run(plan, folds[:2])
    assert result['coverage']['declared_outer_folds'] == 3
    assert result['coverage']['complete_fold_fraction'] == 2/3
    assert result['scalar_metrics']['mean_cash_received'] is None
    assert result['scalar_metrics']['total_observed_cash_received'] == 340
    assert result['forecast_errors']['paired_fold_count'] == 2
    assert result['forecast_errors']['historical_interval'] is None
    assert result['baseline_comparisons'][0]['paired_outer_folds'] == 2
    assert result['folds'][-1]['action'] == 'missing'


def test_missing_forecast_preserves_observed_cash_and_baseline_pair():
    plan, folds = fixture()
    folds[0]['economic_selection']['phases'][0]['training_forecasts'][0]['metrics']['expected_funded_cash_payouts_within_horizon']=None
    folds[0]['baseline_results'][0]['training_forecast']['metrics']['expected_funded_cash_payouts_within_horizon']=None
    result=run(plan,folds)
    assert result['scalar_metrics']['total_observed_cash_received']==550
    assert result['scalar_metrics']['mean_cash_received']==pytest.approx(550/3)
    assert result['forecast_errors']['paired_fold_count']==2
    assert result['baseline_comparisons'][0]['paired_outer_folds']==3
    assert result['folds'][0]['members'][0]['observation_valid']
    assert not result['folds'][0]['members'][0]['comparable']


def test_high_confidence_without_tail_resolution_has_no_interval():
    plan,folds=fixture(predictions=(100,)*5,actual=(120,)*5,baseline=(80,)*5,probabilities=(1,)*5)
    result=run(plan,folds,confidence_level=.999,historical_bootstrap_replicates=100)
    assert result['scalar_metrics']['historical_interval']['interval'] is None
    assert 'five expected replicates' in result['scalar_metrics']['historical_interval']['reason']
    assert result['baseline_comparisons'][0]['decision']=='INSUFFICIENT_EVIDENCE'


@pytest.mark.parametrize('count,confidence,bounds,ranks', [
    (1000,.95,[24.,974.],[25,975]),
    (200,.95,[4.,194.],[5,195]),
    (1000,.90,[49.,949.],[50,950]),
    (10000,.999,[4.,9994.],[5,9995])])
def test_exact_inverse_cdf_tail_ranks_do_not_move_on_float_rounding(count,confidence,bounds,ranks):
    # Values are their zero-based ranks: the 25th observation is exactly 24.
    assert _empirical_bounds(list(range(count)),confidence)==(bounds,ranks)


def test_family_is_one_block_and_never_implicit_portfolio():
    plan, folds = fixture()
    selection = folds[0]['economic_selection']['phases'][0]
    package = deepcopy(selection['frozen_packages'][0]); package['candidate_id']='alternative';package['package_sha256']='alternativehash'
    package['configuration']['micros']=5
    selection['frozen_packages'].append(package)
    selection['training_forecasts'].append(dict(selection['training_forecasts'][0],candidate_id='alternative'))
    output = deepcopy(folds[0]['chronological_replay']['items'][0]['result'])
    output['frozen_binding']=package;output['cash_received']=999999
    folds[0]['chronological_replay']['items'].append(dict(phase='funded',candidate_id='alternative',result=output))
    result = run(plan, folds)
    assert result['coverage']['historical_outer_blocks'] == 3
    assert result['coverage']['selected_family_folds'] == 1
    assert result['folds'][0]['family_size'] == 2
    assert result['scalar_metrics']['mean_cash_received'] is None
    assert result['scalar_metrics']['total_observed_cash_received'] is None
    assert result['forecast_errors']['mean_error'] is None
    assert result['calibration']['brier_score'] is None
    assert result['baseline_comparisons'][0]['decision'] == 'INSUFFICIENT_EVIDENCE'


def test_censored_acquisition_retains_all_fees_not_completed_only_mean():
    plan, folds = fixture('evaluation', predictions=(70,70), actual=(70,90), baseline=(80,100), probabilities=(1,1))
    output = folds[1]['chronological_replay']['items'][0]['result']
    output.update(acquisition_completed=False,censored=True,calendar_days_to_funded=None,outcome='still_evaluating')
    result = run(plan, folds)
    metrics = result['scalar_metrics']
    assert metrics['total_observed_paid_fees'] == 160
    assert metrics['completed_acquisitions'] == metrics['censored_acquisitions'] == 1
    assert metrics['mean_acquisition_cost'] is metrics['mean_calendar_days_to_funded'] is None
    assert result['forecast_errors']['mean_error'] is None
    comparison = result['baseline_comparisons'][0]
    assert comparison['paired_outer_folds'] == 1 and comparison['historical_interval']['interval'] is None
    assert comparison['exclusions'][0]['reason'] == 'acquisition_incomplete_or_no_account_action'


def test_abstention_zero_only_with_explicit_predeclared_no_account_action():
    plan, folds = fixture()
    folds[1]['economic_selection'] = dict(status='NO_QUALIFIED_CONFIGURATION',phases=[])
    folds[1]['chronological_replay'] = dict(items=[])
    ordinary = run(plan, folds)
    assert ordinary['folds'][1]['action'] == 'unmeasured_abstention'
    assert ordinary['scalar_metrics']['mean_cash_received'] is None
    explicit = run(plan, folds, abstention_action='no_account_no_fee')
    assert explicit['folds'][1]['action'] == 'no_account_no_fee'
    assert explicit['scalar_metrics']['mean_cash_received'] == pytest.approx(290/3)
    assert explicit['baseline_comparisons'][0]['pairs'][1]['improvement'] == -220


@pytest.mark.parametrize('change,reason', [
    ('missing','baseline_missing'), ('profile','profile_or_cost_assumptions_differ'),
    ('receipt','receipt_estimands_differ')])
def test_reference_pairing_rejects_incompatible_or_absent_evidence(change, reason):
    plan, folds = fixture()
    reference = folds[0]['baseline_results'][0]
    if change == 'missing':
        folds[0]['baseline_results']=[]
    elif change == 'profile':
        reference['frozen_package']['configuration']['profile']={'id':'other'}
    else:
        reference['frozen_package']['receipt_delay_calendar_days']=2
    result = run(plan, folds)
    comparison = result['baseline_comparisons'][0]
    assert comparison['exclusions'][0]['reason'] == reason
    assert comparison['decision'] == 'INSUFFICIENT_EVIDENCE'


def test_logical_stability_excludes_generated_sources_dates_and_random_draws():
    plan, folds = fixture()
    first, second = [f['economic_selection']['phases'][0]['frozen_packages'][0] for f in folds[:2]]
    assert first != second
    assert logical_policy_identity(first) == logical_policy_identity(second)
    second['configuration']['micros']=4
    result = run(plan, folds)
    transition = result['stability']['transitions'][0]
    assert transition['sizing_changed'] and not transition['signal_changed'] and not transition['profile_changed']
    assert transition['family_jaccard'] == 0


def test_descriptive_threshold_and_interval_reproducible_without_certification():
    plan, folds = fixture(predictions=(100,)*5,actual=(120,)*5,baseline=(80,)*5,probabilities=(1,)*5)
    settings = ReliabilitySettings(minimum_calibration_blocks=5)
    a = consolidate_reliability(plan, folds, settings)
    assert a == consolidate_reliability(plan, folds, settings)
    assert a['phases']['funded']['baseline_comparisons'][0]['historical_interval']['interval']==[40,40]
    assert a['status']=='ASSESSABLE_WITH_LIMITATIONS'
    assert not a['production_qualified']
    assert a['phases']['funded']['coverage']['independent_block_count'] is None


@pytest.mark.parametrize('field,value', [('minimum_outer_blocks',True), ('minimum_outer_blocks',1),
    ('minimum_complete_fold_fraction',0),('confidence_level',1),('confidence_level',float('nan')),
    ('bootstrap_block_folds',0),('historical_bootstrap_replicates',99),
    ('minimum_baseline_mean_improvement',True),('minimum_baseline_mean_improvement','NaN'),
    ('minimum_baseline_mean_improvement',-1),('minimum_baseline_mean_improvement','abc'),
    ('minimum_baseline_mean_improvement',{}),('minimum_baseline_mean_improvement',[]),
    ('minimum_baseline_mean_improvement','1e1000'),('require_baseline_for_recommendation',1)])
def test_settings_reject_ambiguous_or_invalid_declarations(field,value):
    with pytest.raises(ValueError):ReliabilitySettings(**{field:value})


def test_duplicate_or_unknown_folds_reject():
    plan, folds = fixture()
    with pytest.raises(ValueError, match='Duplicate'):run(plan, folds+[folds[0]])
    folds[0]['index']=99
    with pytest.raises(ValueError, match='Unexpected'):run(plan, folds)
