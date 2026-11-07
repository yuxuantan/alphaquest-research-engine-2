"""Native history refits retain original blocks/prefixes and real cash means."""
from dataclasses import replace
from datetime import date
from decimal import Decimal
from copy import deepcopy

import pytest

from native_replay_fixtures import bars,parameters
from test_native_forecast_profiles import (CONFIG,SIZING,PROFILE_VERSION,request,targets,context,factory)
from alphaquest.session_calendar import load_calendar,session_date
from alphaquest.prop.native_draws import (build_catalogue,build_schedule,history_origin_weights,
    NativeHistoryPoolUnavailable,run_path)
from alphaquest.prop.funded_profiles import (NativeFundedController,historical_native_funded_mean)
from alphaquest.prop.funded_optimization import FundedHistoricalMean
from alphaquest.prop.phase_profiles import FundedProfile


def source(days=2,block=1):
    values=bars(days=days,payout=True);calendar=load_calendar(symbol='MNQ')
    contexts={day:context(day,calendar,modeled=False) for day in sorted({session_date(bar.timestamp_utc) for bar in values})}
    return build_catalogue(values,contexts,parameters(),block_sessions=block,source_identity={'fixture':'synthetic-constant-payout'})


def inputs(catalogue,horizon=7):
    forecast=request(horizon,simulations=2,capture=1);cohorts=targets(forecast)
    value=dict(catalogue=catalogue,target_contexts_by_cohort=cohorts,strategy_factory=factory,config=CONFIG,
        profile=FundedProfile('apex-50k-eod',PROFILE_VERSION),sizing=SIZING,micros=40,forecast=forecast,max_micros=40)
    plans=[build_schedule(catalogue,cohorts['2026-01-19'],parameters(),phase='funded',seed=forecast.seed,
        path_index=index,start_date='2026-01-19',cutoff_date_exclusive='2026-01-26') for index in range(2)]
    return value,dict(cohorts=[{}],schedules=plans)


def settings(**changes):
    return FundedHistoricalMean(**dict(method='native_origin_block_bootstrap_lower_mean_v1',replicates=50,
        confidence_level=.9,block_sessions=1,minimum_history_sessions=2,minimum_history_blocks=2,
        simulations_per_replicate=2,maximum_mc_standard_error=0,**changes))


def test_origin_frequency_resampling_preserves_original_history_and_is_reproducible():
    catalogue=source();before=catalogue.metadata()
    weights=history_origin_weights(catalogue,block_sessions=1,history_seed=8419,replicate=0)
    assert weights==history_origin_weights(catalogue,block_sessions=1,history_seed=8419,replicate=0)
    assert len(weights['sampled_origins'])==sum(weights['origin_counts'])==2
    assert catalogue.metadata()==before
    inputs_,_=inputs(catalogue);contexts=inputs_['target_contexts_by_cohort']['2026-01-19']
    normal=build_schedule(catalogue,contexts,parameters(),phase='funded',seed=1729,path_index=0,start_date='2026-01-19')
    weighted=build_schedule(catalogue,contexts,parameters(),phase='funded',seed=1729,path_index=0,start_date='2026-01-19',origin_weights=weights)
    assert 'origin_weights' not in normal
    assert weighted['origin_weights']['weights_sha256']==weights['weights_sha256']
    for draw in weighted['draws']:
        block=catalogue.blocks[draw['source_block_index']]
        assert draw['prefix_sha256']==block.prefix_sha256 and draw['source_block_sha256']==block.content_sha256
    altered=deepcopy(weights);altered['origin_counts'].reverse();altered['sampled_origins']=[99,99]
    with pytest.raises(ValueError,match='origin counts'):
        build_schedule(catalogue,contexts,parameters(),phase='funded',seed=1729,path_index=0,start_date='2026-01-19',origin_weights=altered)


def test_empty_weighted_shape_pool_is_unresolved_without_uniform_fallback():
    catalogue=source(days=6,block=5)
    forecast=request(5);contexts=targets(forecast)['2026-01-19']
    weights=next(value for index in range(100) if (value:=history_origin_weights(catalogue,
        block_sessions=1,history_seed=8419,replicate=index))['origin_counts'][0]==0)
    # Only the Monday-origin block matches the full Mon-Fri civil gap shape.
    with pytest.raises(NativeHistoryPoolUnavailable,match='no positive-weight'):
        build_schedule(catalogue,contexts,parameters(),phase='funded',seed=1,path_index=0,
            start_date='2026-01-19',origin_weights=weights)


def test_actual_native_refits_reestimate_mean_cash_not_account_percentile():
    catalogue=source();kwargs,plan=inputs(catalogue)
    result=historical_native_funded_mean(kwargs,plan,settings(),1,receipt_delay_calendar_days=0)
    assert result['status']=='estimated' and result['lower_mean_cash']==1500
    assert result['tail_rank']==5 and result['source_history_sessions']==2
    assert len(result['replicates'])==50
    assert all(row['mean_cash']==1500 and row['mean_monte_carlo_se']==0 for row in result['replicates'])
    assert all(len(row['paths'])==2 for row in result['replicates'])
    assert result['mc_noise']['maximum_observed_standard_error']==0
    assert all(Decimal(path['gross_account_deductions'])==1500 for row in result['replicates'] for path in row['paths'])


def test_history_and_complete_family_tail_sufficiency_precede_any_refit(monkeypatch):
    import alphaquest.prop.funded_profiles as owner
    catalogue=source();kwargs,plan=inputs(catalogue)
    monkeypatch.setattr(owner,'forecast_native_funded',lambda **kwargs:pytest.fail('Insufficient evidence cannot simulate refits.'))
    result=historical_native_funded_mean(kwargs,plan,settings(),2,receipt_delay_calendar_days=0)
    assert result['lower_mean_cash'] is None and result['replicates']==[]
    assert 'insufficient_family_tail_replicates' in result['reasons']
    cfg=replace(settings(),minimum_history_sessions=60)
    result=historical_native_funded_mean(kwargs,plan,cfg,1,receipt_delay_calendar_days=0)
    assert result['source_history_sessions']==2 and 'minimum_history_sessions' in result['reasons']
