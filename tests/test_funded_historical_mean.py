"""Independent cash/history/noise oracles for conservative estimated-mean selection."""
from copy import deepcopy
from dataclasses import asdict, replace
from datetime import date, timedelta
from hashlib import sha256
from types import SimpleNamespace

import numpy as np
import pytest

from alphaquest.prop import funded_profiles
from alphaquest.prop.adapter import canonical
from alphaquest.prop.funded_optimization import (
    CONSERVATIVE_OBJECTIVE, OBJECTIVE, FundedHistoricalMean, FundedSearch,
    FundedCandidate, FundedConstraints, parse_request, rank_candidates,
)
from alphaquest.prop.phase_profiles import (
    FundedProfile, SamplingConfig, SavedTradeSource, SimulationConfig, SourceCosts, rule_version,
)
from alphaquest.prop.phase_search import PhaseCalendar


def labels(count):
    start=date(2025,1,6);result=[]
    while len(result)<count:
        if start.weekday()<5:result.append(start.isoformat())
        start+=timedelta(days=1)
    return result


def winning_day():
    # Source-dollar convention: $3000 per NQ becomes $900 with three MNQ.
    return [(3000.,0.,((0.,False),),True)]


def losing_day():
    # Observed adverse gap at three MNQ loses $3000 and blows the account.
    return [(-10000.,10000.,((10000.,True),),True)]


@pytest.fixture
def source_book(monkeypatch):
    content=[winning_day() for _ in range(20)]
    snapshot={'source_kind':'native_backtest','profile_research_period':{
        'first_session':labels(20)[0],'last_session':labels(20)[-1]}}
    def prepare(*args,**kwargs):
        return deepcopy(snapshot),deepcopy(content),{}
    monkeypatch.setattr(funded_profiles,'prepare_phase_source',prepare)
    monkeypatch.setattr(funded_profiles,'verify_phase_source',lambda *a,**k:None)
    return content,snapshot


def cfg(**changes):
    return replace(FundedHistoricalMean(),replicates=100,block_sessions=2,
        minimum_history_sessions=20,minimum_history_blocks=10,simulations_per_replicate=8,
        maximum_mc_standard_error=0,**changes)


def estimate(configuration=None, *, observed=True,family=1,calendar=None):
    return funded_profiles.historical_funded_mean(None,SavedTradeSource('a'*32),
        FundedProfile('apex-50k-eod',rule_version('apex-50k-eod')),3,5,
        calendar or PhaseCalendar(('2026-01-05',),'2026-01-10'),0,
        SimulationConfig(simulations=8),None,SamplingConfig(1),SourceCosts(mode='source'),
        configuration=configuration or cfg(),family_size=family,
        observed_sessions=labels(20) if observed else None)


def test_constant_history_exact_cash_mean_has_zero_history_and_mc_spread(source_book):
    result=estimate(family=2)
    assert result['status']=='estimated' and result['lower_mean_cash']==1500
    assert result['tail_rank']==5 and float(result['expected_tail_replicates'])==5
    assert result['history_session_count']==20 and result['history_block_count']==10
    assert {r['mean_cash'] for r in result['replicates']}=={1500}
    assert {r['mean_monte_carlo_se'] for r in result['replicates']}=={0}
    assert result['mc_noise']['maximum_observed_standard_error']==0


def test_original_dated_owner_retains_exact_cash_with_optional_estimator_disabled(source_book):
    result=funded_profiles.simulate_dated_funded_profile(None,SavedTradeSource('a'*32),
        FundedProfile('apex-50k-eod',rule_version('apex-50k-eod')),3,5,
        PhaseCalendar(('2026-01-05',),'2026-01-10'),0,SimulationConfig(simulations=8),
        sampling=SamplingConfig(1),costs=SourceCosts(mode='source'),observed_sessions=labels(20))
    assert len(result['paths'])==8 and {path['cash_received'] for path in result['paths']}=={1500}
    assert all(path['equity']==3000 and path['trading_profit']==4500 for path in result['paths'])
    assert 'historical_mean' not in result and result['provenance']['kernel']['source']=='native_engine.py'


def test_historical_mean_is_distinct_from_single_account_p10_and_inner_mc_error(source_book):
    content,_=source_book
    content[-2:]=[losing_day(),losing_day()]
    configuration=replace(cfg(),block_sessions=1,replicates=50,
        simulations_per_replicate=256,maximum_mc_standard_error=100)
    result=estimate(configuration)
    assert result['status']=='estimated' and result['lower_mean_cash']>0
    # Five successive winning sessions are necessary for the sole possible
    # $1500 receipt. Conditional on a bootstrap history, exact mean is 1500*p^5.
    for row in result['replicates']:
        p=sum(index<18 for index in row['source_indices'])/20
        analytic=1500*p**5
        assert abs(row['mean_cash']-analytic) <= 5*row['mean_monte_carlo_se']+15
    means=sorted(row['mean_cash'] for row in result['replicates'])
    assert result['lower_mean_cash']==means[4] and len(set(means))>1
    paths,_,_=funded_profiles._dated_funded_paths(content,
        FundedProfile('apex-50k-eod',rule_version('apex-50k-eod')),3,5,
        PhaseCalendar(('2026-01-05',),'2026-01-10'),0,SimulationConfig(simulations=256),SamplingConfig(1))
    assert np.quantile([p['cash_received'] for p in paths],.1,method='inverted_cdf')==0
    assert result['lower_mean_cash'] != result['mc_noise']['maximum_observed_standard_error']


def test_source_indices_are_reproducible_whole_blocks_and_family_adjustment_is_explicit(source_book):
    configuration=replace(cfg(),replicates=200)
    one=estimate(configuration,family=1);four=estimate(configuration,family=4)
    assert one['replicates']==four['replicates']
    assert (one['tail_rank'],four['tail_rank'])==(20,5)
    assert estimate(configuration,family=4)==four
    for row in four['replicates']:
        indices=row['source_indices']
        assert len(indices)==20 and all(0<=index<20 for index in indices)
        assert all(indices[i+1]==(indices[i]+1)%20 for i in range(0,20,2))
        assert row['indices_sha256']==sha256(canonical(indices).encode()).hexdigest()
    changed=estimate(replace(configuration,history_seed=8420),family=4)
    assert changed['replicates'][0]['source_indices']!=four['replicates'][0]['source_indices']


def test_recurring_family_tail_boundary_is_exact_and_independent_of_decimal_context(source_book):
    from decimal import localcontext
    configuration=replace(cfg(),replicates=350)
    expected=estimate(configuration,family=7)
    assert expected['status']=='estimated' and expected['tail_rank']==5
    assert expected['tail_probability_fraction']=={'numerator':1,'denominator':70}
    with localcontext() as context:
        context.prec=6
        assert estimate(configuration,family=7)==expected


@pytest.mark.parametrize('change,reason',[
    ({'minimum_history_sessions':21},'minimum_history_sessions'),
    ({'minimum_history_blocks':11},'minimum_history_blocks'),
    ({'replicates':49},'insufficient_family_tail_replicates'),
])
def test_insufficient_history_or_tail_never_becomes_more_evidence_from_mc(source_book,change,reason):
    result=estimate(replace(cfg(),**change))
    assert result['status']=='insufficient_evidence' and result['lower_mean_cash'] is None
    assert reason in result['reasons'] and result['replicates']==[]


def test_missing_observed_inventory_is_not_replaced_with_weekday_fillers(source_book):
    result=estimate(observed=False)
    assert result['lower_mean_cash'] is None and result['history_session_count']==0
    assert result['history_evidence']=='unavailable'
    assert 'verified_observed_session_inventory_required' in result['reasons']


def test_exporter_observed_inventory_keeps_its_declared_status(source_book):
    _,snapshot=source_book
    snapshot.update(source_kind='external_trade_export',canonical_manifest={'coverage':{'sessions':labels(20)}})
    result=estimate(observed=False)
    assert result['lower_mean_cash']==1500
    assert result['history_evidence']=='exporter_declared_observed_sessions_not_independently_certified'


def test_residual_mc_noise_gate_retains_replicates_but_withholds_score(source_book):
    source_book[0][-2:]=[losing_day(),losing_day()]
    result=estimate(replace(cfg(),block_sessions=1,maximum_mc_standard_error=0))
    assert result['status']=='insufficient_evidence' and result['lower_mean_cash'] is None
    assert result['mc_noise']['maximum_observed_standard_error']>0 and len(result['replicates'])==100
    assert result['reasons']==['inner_monte_carlo_standard_error_exceeds_declared_limit']


def test_inner_start_cohorts_require_two_paths_and_equal_allocation(source_book):
    cal=PhaseCalendar(('2026-01-05','2026-01-06','2026-01-07'),'2026-01-12')
    result=estimate(calendar=cal)
    assert result['replicates']==[] and 'minimum_two_inner_paths_per_start_cohort' in result['reasons']


def search(conservative=None):
    candidate=FundedCandidate(SavedTradeSource('a'*32),
        FundedProfile('apex-50k-eod',rule_version('apex-50k-eod')),3,SimulationConfig(simulations=8))
    return FundedSearch('a'*32,(candidate,),PhaseCalendar(('2026-01-05',),'2026-01-10'),5,0,
        bootstrap_replicates=100,conservative_objective=conservative)


def ranking_row(id,mean,lower,p10):
    return dict(candidate_id=id,status='estimated',manifest={'configuration':{'micros':3}},
        metrics={OBJECTIVE:mean,CONSERVATIVE_OBJECTIVE:lower,'account_breach_probability':0,
            'probability_first_payout':.8,'p10_payouts':p10},uncertainty={'mean_family_interval':[mean-1,mean+1]})


def test_conservative_ranking_uses_mean_history_score_not_point_mean_or_account_p10():
    rows=[ranking_row('high_mean',1000,300,500),ranking_row('stable_mean',800,600,0)]
    assert rank_candidates(deepcopy(rows),search())['winner']=='high_mean'
    ranked=rank_candidates(deepcopy(rows),search(cfg()))
    assert ranked['winner']=='stable_mean' and ranked['objective']==CONSERVATIVE_OBJECTIVE
    rows[0].update(status='unresolved');rows[0]['metrics'][CONSERVATIVE_OBJECTIVE]=None
    unresolved=rank_candidates(rows,search(cfg()))
    assert unresolved['winner'] is None and len(unresolved['candidates'])==2


def test_conservative_contract_roundtrip_cache_inputs_and_strict_bounds():
    declared=search(cfg())
    assert parse_request(asdict(declared))==declared
    assert parse_request(asdict(search())).conservative_objective is None
    for change in ({'confidence_level':True},{'confidence_level':1},{'confidence_level':.49},
        {'replicates':True},{'block_sessions':0},{'minimum_history_blocks':1},
        {'simulations_per_replicate':1},{'maximum_mc_standard_error':float('inf')},
        {'maximum_mc_standard_error':-1},{'history_seed':-1}):
        with pytest.raises(ValueError):replace(cfg(),**change)
    raw=asdict(declared);raw['conservative_objective']['account_p10']=.1
    with pytest.raises(ValueError,match='Invalid funded-only'):parse_request(raw)
