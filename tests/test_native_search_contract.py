"""Native phase contracts and metric adapters preserve selector meanings."""
from dataclasses import asdict,replace
from types import SimpleNamespace

import pytest

from alphaquest.prop.phase_profiles import (NativeExecution,EvaluationProfile,FundedProfile,rule_version,
    SavedTradeSource,SimulationConfig,SamplingConfig,EvaluationSamplingConfig,SourceCosts)
from alphaquest.prop.phase_search import PhaseCalendar
from alphaquest.prop.evaluation_optimization import (EvaluationCandidate,EvaluationSearch,EvaluationConstraints,
    parse_request as parse_evaluation,pareto_sort)
from alphaquest.prop.funded_optimization import (FundedCandidate,FundedSearch,FundedHistoricalMean,
    parse_request as parse_funded,funded_metrics,rank_candidates,FundedConstraints)
from alphaquest.prop.evaluation_profiles import native_acquisition_metrics
from alphaquest.prop.native_search import candidate_request

SOURCE='a'*32
CALENDAR=PhaseCalendar(('2026-01-26',),'2026-02-09')
NATIVE=NativeExecution(9)
COSTS=SourceCosts(mode='source',instrument='MNQ')


def search(phase):
    if phase=='evaluation':
        c=EvaluationCandidate(SavedTradeSource(SOURCE),EvaluationProfile('apex-50k-eod',rule_version('apex-50k-eod'),'30','40'),3,
            SimulationConfig(4,1729),EvaluationSamplingConfig(1,4,1729),COSTS)
        return EvaluationSearch(SOURCE,(c,),CALENDAR,native_execution=NATIVE)
    c=FundedCandidate(SavedTradeSource(SOURCE),FundedProfile('apex-50k-eod',rule_version('apex-50k-eod')),3,
        SimulationConfig(4,1729),SamplingConfig(1),COSTS)
    return FundedSearch(SOURCE,(c,),CALENDAR,9,2,native_execution=NATIVE)


@pytest.mark.parametrize('phase',['evaluation','funded'])
def test_native_search_roundtrip_uses_one_explicit_actual_path_budget(phase):
    original=search(phase)
    parsed=(parse_evaluation if phase=='evaluation' else parse_funded)(asdict(original))
    assert parsed==original
    request=candidate_request(parsed,parsed.candidates[0])
    assert request.native_forecast.simulations==4 and request.native_forecast.seed==1729
    assert request.native_forecast.block_sessions==1 and request.native_forecast.horizon_calendar_days==9
    assert type(request.native_forecast.calendar['start_dates']) is list
    if phase=='evaluation':assert request.receipt_delay_calendar_days is None
    else:assert request.retry is None


def test_native_search_rejects_conflicting_horizons_seeds_and_resampling_models():
    with pytest.raises(ValueError,match='horizon must equal'):replace(search('funded'),horizon_calendar_days=8)
    evaluation=search('evaluation')
    with pytest.raises(ValueError,match='counts/seeds must agree'):
        replace(evaluation,candidates=(replace(evaluation.candidates[0],sampling=EvaluationSamplingConfig(1,4,999)),))
    with pytest.raises(ValueError,match='resampling law'):
        replace(search('funded'),conservative_objective=FundedHistoricalMean())
    native_cfg=FundedHistoricalMean(method='native_origin_block_bootstrap_lower_mean_v1')
    assert replace(search('funded'),conservative_objective=native_cfg).conservative_objective==native_cfg
    with pytest.raises(ValueError,match='resampling law'):
        replace(search('funded'),native_execution=None,conservative_objective=native_cfg)
    with pytest.raises(ValueError):NativeExecution(True)
    with pytest.raises(TypeError):NativeExecution(9,unknown=True)


def test_native_first_attempt_probability_never_substitutes_for_acquisition_probability():
    forecast=dict(paths=[dict(attempts=[{'outcome':'blown'},{'outcome':'passed'}],acquisition_completed=True),
                         dict(attempts=[{'outcome':'passed'}],acquisition_completed=True)],
        metrics=dict(mean_acquisition_cost=85,mean_calendar_days_to_funded=5,probability_acquisition_by_cutoff=1,
            mean_attempts_started=1.5,restricted_mean_paid_fees=85,restricted_mean_observed_calendar_days=5,censored_paths=0),
        uncertainty=dict(metrics=dict(mean_acquisition_cost={'mc_standard_error':15},
            mean_calendar_days_to_funded={'mc_standard_error':1}),scope='conditional MC'),
        model=NATIVE.model,phase_configuration={},assumptions=[])
    result=native_acquisition_metrics(forecast)
    assert result['metrics']['pass_probability']==.5
    assert result['metrics']['probability_acquisition_by_cutoff']==1
    assert result['metrics']['cost_per_funded']==85 # actual(100+70)/2, never30/.5+40=100
    forecast['paths'][0]['attempts'][0]['outcome']='open'
    forecast['paths'][0]['acquisition_completed']=False
    forecast['metrics'].update(mean_acquisition_cost=None,mean_calendar_days_to_funded=None,censored_paths=1)
    result=native_acquisition_metrics(forecast)
    assert result['metrics']['pass_probability'] is None and result['metrics']['pass_probability_bounds']==[.5,1]
    assert result['status']=='unresolved' and result['metrics']['cost_per_funded'] is None


def test_existing_pareto_keeps_resolved_frontier_and_complete_unresolved_membership():
    rows=[dict(candidate_id='resolved',status='estimated',metrics=dict(cost_per_funded=70,expected_calendar_days_to_funded=7,pass_probability=1)),
          dict(candidate_id='censored',status='unresolved',metrics=dict(cost_per_funded=None,expected_calendar_days_to_funded=None,pass_probability=None))]
    result=pareto_sort(rows,EvaluationConstraints())
    assert result['frontier']==['resolved'] and result['unresolved_candidates']==['censored']
    assert len(result['candidates'])==2 and result['winner'] is None


def test_native_cash_projection_preserves_exact_evidence_and_reuses_numeric_funded_metrics():
    from copy import deepcopy
    from alphaquest.prop.funded_profiles import native_funded_metric_paths
    base=dict(start_date='2026-01-26',cutoff_date_exclusive='2026-02-04',terminal_date=None,
        outcome='open',lifetime_censored=True,cash_received='0',pending_cash='1500.00',
        gross_account_deductions='1500.00',equity='4800.00',trading_profit='6300.00',
        payout_events=[dict(received_within_horizon=False,receipt_date='2026-02-04')])
    paths=[dict(base,path_index=0),dict(base,path_index=1,cash_received='1500.00',pending_cash='0',
        outcome='blown',lifetime_censored=False,terminal_date='2026-02-02',
        payout_events=[dict(received_within_horizon=True,receipt_date='2026-02-01')])]
    forecast=dict(paths=deepcopy(paths))
    projected=native_funded_metric_paths(forecast)
    result=funded_metrics(projected,search('funded'))
    assert result['metrics']['expected_funded_cash_payouts_within_horizon']==750
    assert result['metrics']['expected_pending_cash']==750
    assert result['metrics']['expected_gross_account_deductions']==1500
    assert result['metrics']['account_breach_probability']==.5
    assert result['metrics']['probability_first_payout']==.5
    assert forecast['paths']==paths # strings are authoritative captured actual cash.


def test_trace_provenance_discriminates_terminal_application_from_outer_fold():
    from alphaquest.prop.phase_profiles import frozen_replay_tags
    terminal=dict(schema_version='procedure-phase-freeze-v1',application_id='a'*32,
        procedure_sha256='b'*64,application_role='final_fit',candidate_id='c'*64)
    tags=frozen_replay_tags(terminal)
    assert tags['stage']=='procedure_chronological' and tags['application_id']=='a'*32
    assert 'outer_fold_index' not in tags
    outer=frozen_replay_tags(dict(outer_fold_index=2,candidate_id='c'*64))
    assert outer==dict(stage='outer_chronological',outer_fold_index=2,candidate_id='c'*64)
