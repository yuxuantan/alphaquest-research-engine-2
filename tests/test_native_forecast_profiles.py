"""Independent real native path/cash oracles and conditional-MC boundaries."""
from dataclasses import replace
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from math import sqrt

import pytest

from native_replay_fixtures import bars, parameters
from alphaquest.prop.native_control import SessionContext
from alphaquest.prop.native_draws import build_catalogue
from alphaquest.prop.native_replay import NativeForecastRequest
from alphaquest.prop.phase_profiles import (EvaluationProfile, FundedProfile, SizingConfiguration,
    equal_stratum_mean, native_forecast_layout, rule_version)
from alphaquest.prop.evaluation_profiles import forecast_native_evaluation, NativeEvaluationController
from alphaquest.prop.funded_profiles import forecast_native_funded, NativeFundedController
from alphaquest.prop.evaluation_optimization import SequentialRetry
from alphaquest.session_calendar import CT, load_calendar
from alphaquest.strategies.vwap_pullback_risk_sizing import VwapPullbackRiskSizing
from alphaquest.strategy import ExecutionConfig

D=Decimal
CONFIG=ExecutionConfig(D(10000),D('.25'),D(2),0,D(0))
PROFILE_VERSION=rule_version('apex-50k-eod')
SIZING=SizingConfiguration(dict(kind='fixed_contracts',contracts=3),'50000',
    dict(tick_size='.25',point_value='2',commission_per_contract_per_side='0'))


def request(horizon=9, starts=('2026-01-19',), simulations=4, capture=2):
    return NativeForecastRequest(model='observed_contiguous_blocks_with_prior_prefix_v1',
        simulations=simulations,seed=1729,block_sessions=1,horizon_calendar_days=horizon,capture_paths=capture,
        calendar=dict(start_dates=list(starts),coverage_end='2026-02-09',closures=[],
            timezone='America/Chicago',version='declared-synthetic-calendar-v1'))


def context(day, calendar, *, modeled):
    close=calendar.plan(day,parameters().eod_flat_time,parameters().close_buffer_minutes).close.astimezone(timezone.utc)
    first=datetime.combine(day-timedelta(days=1),time(17,1),CT).astimezone(timezone.utc)
    count=int((close-first).total_seconds()/60)+1
    return SessionContext(day,close,"synthetic-modeled-v1" if modeled else "reviewed-source-v1",calendar.sha256,0 if modeled else count,not modeled,
        kind='modeled' if modeled else 'observed',expected_bar_count=count if modeled else None)


@pytest.fixture(scope='module')
def catalogue():
    observed=bars(days=1,payout=True)
    day=date(2026,1,5);calendar=load_calendar(symbol='MNQ')
    return build_catalogue(observed,{day:context(day,calendar,modeled=False)},parameters(),
        block_sessions=1,source_identity={'fixture':'synthetic-observed-one-session-payout'})


def targets(forecast):
    calendar=forecast.target_calendar();result={}
    for start in forecast.calendar['start_dates']:
        first=date.fromisoformat(start);contexts={}
        for index in range(forecast.horizon_calendar_days):
            day=first+timedelta(days=index)
            if calendar.plan(day).close is not None:
                contexts[day]=replace(context(day,calendar,modeled=True),calendar_version=forecast.calendar["version"])
        result[start]=contexts
    return result


def factory():return VwapPullbackRiskSizing(parameters(),execution_config=CONFIG,instrument_symbol='MNQ')


def run(catalogue,phase='funded',forecast=None,**extra):
    forecast=forecast or request()
    common=dict(forecast=forecast,**extra)
    if phase=='funded':
        return forecast_native_funded(catalogue,targets(forecast),factory,CONFIG,
            FundedProfile('apex-50k-eod',PROFILE_VERSION),SIZING,40,
            receipt_delay_calendar_days=2,receipt_amount_convention='kernel_entitlement_unrounded',**common)
    return forecast_native_evaluation(catalogue,targets(forecast),factory,CONFIG,
        EvaluationProfile('apex-50k-eod',PROFILE_VERSION,'30','40'),SIZING,40,
        retry=SequentialRetry(activation_delay_sessions=1),**common)


def test_equal_stratum_mcse_excludes_between_start_mean_difference():
    value=equal_stratum_mean([[0,2],[10,14]])
    assert value['mean']==6.5
    assert value['mc_standard_error']==pytest.approx(sqrt(5)/2)
    assert value['cohort_counts']==[2,2]
    assert equal_stratum_mean([[10],[100]])['mc_standard_error'] is None
    assert equal_stratum_mean([[0,0],[100,100]])['mc_standard_error']==0
    for groups in ([],[[]],[[1],[2,3]],[[float('nan'),1]]):
        with pytest.raises(ValueError):equal_stratum_mean(groups)


def test_funded_all_paths_receive_separate_cash_and_exact_conservation(catalogue):
    progress=[]
    result=run(catalogue,progress=progress.append)
    assert result['metrics']['mean_received_cash']==1500
    assert result['metrics']['mean_pending_cash']==0
    assert result['metrics']['mean_gross_account_deductions']==1500
    assert result['metrics']['mean_provider_equity_change']==4800
    assert result['metrics']['p10_received_cash']==1500
    assert result['uncertainty']['metrics']['mean_received_cash']['mc_standard_error']==0
    assert result['readiness']=='MODELED_SCENARIO_ONLY' and not result['observed_future_data']
    assert len(result['paths'])==len(result['schedules'])==4 and len(result['captures'])==2
    assert result['capture_path_indices']==[0,1] and len(progress)==8
    for path in result['paths']:
        assert D(path['trading_profit'])==6300 and D(path['equity'])==4800
        assert path['payout_events'][0]['request_date']=='2026-01-23'
        assert path['payout_events'][0]['receipt_date']=='2026-01-25'
        assert path['execution_counts']['completed_trades']==7
    assert 'paid_fees' not in result['paths'][0]
    assert result['captures'][0]['result']['mode']=='native_modeled_path'
    assert 'historical_paths' not in result['captures'][0]['result']


def test_evaluation_complete_acquisition_all_fees_and_calendar_days(catalogue):
    result=run(catalogue,'evaluation')
    assert result['status']=='identified_model_mean'
    assert result['metrics']['mean_acquisition_cost']==70
    assert result['metrics']['mean_calendar_days_to_funded']==7
    assert result['metrics']['restricted_mean_paid_fees']==70
    assert result['metrics']['censored_paths']==0
    assert all(path['pass_date']=='2026-01-22' and path['ready_date']=='2026-01-26' for path in result['paths'])
    assert all(path['execution_counts']['completed_trades']==4 for path in result['paths'])
    assert 'cash_received' not in result['paths'][0]


def test_censored_acquisition_never_reports_success_only_or_fee_probability_means(catalogue):
    result=run(catalogue,'evaluation',request(3))
    assert result['status']=='unresolved_censoring'
    assert result['metrics']['censored_paths']==4
    assert result['metrics']['mean_acquisition_cost'] is None
    assert result['metrics']['mean_calendar_days_to_funded'] is None
    assert result['metrics']['restricted_mean_paid_fees']==30
    assert result['metrics']['restricted_mean_observed_calendar_days']==3
    assert result['uncertainty']['metrics']['mean_acquisition_cost']['mc_standard_error'] is None
    assert all(D(path['paid_fees'])==30 for path in result['paths'])


def test_mixed_acquired_and_censored_real_paths_keep_all_fees_and_withhold_means():
    from alphaquest.session_calendar import session_date
    # One original losing session (-30 at 3 MNQ), one winning (+900).
    # Every source draw goes through actual VWAP, quantity admission and fills.
    values=bars(days=1)+bars(days=2,payout=True)[1380:]
    calendar=load_calendar(symbol='MNQ')
    contexts={day:context(day,calendar,modeled=False)
              for day in sorted({session_date(bar.timestamp_utc) for bar in values})}
    source=build_catalogue(values,contexts,parameters(),block_sessions=1,
        source_identity={'fixture':'synthetic-observed-mixed-loss-win-sessions'})
    result=run(source,'evaluation',request(12,simulations=8,capture=1))
    assert result['metrics']['completed_paths']==result['metrics']['censored_paths']==4
    assert result['metrics']['mean_acquisition_cost'] is None
    assert result['metrics']['mean_calendar_days_to_funded'] is None
    # Six paths pay 30+40; two pay only 30. No paid activation is discarded
    # merely because readiness is still pending at the cutoff.
    assert result['metrics']['restricted_mean_paid_fees']==60
    assert sum(D(path['paid_fees']) for path in result['paths'])==480
    assert any(path['censored'] and D(path['paid_activation_fees'])==40 for path in result['paths'])


def test_receipt_at_exclusive_cutoff_stays_pending(catalogue):
    result=run(catalogue,forecast=request(6,simulations=2,capture=1))
    assert result['metrics']['mean_received_cash']==0
    assert result['metrics']['mean_pending_cash']==1500
    assert result['metrics']['zero_cash_paths']==2
    assert all(path['cutoff_date_exclusive']=='2026-01-25' for path in result['paths'])
    assert all(schedule['cutoff_date_exclusive']=='2026-01-25' for schedule in result['schedules'])


def test_equal_cohort_replication_and_capture_do_not_create_precision(catalogue):
    forecast=request(1,starts=('2026-01-20','2026-01-19'),simulations=2,capture=1)
    result=run(catalogue,forecast=forecast)
    assert [path['cohort_index'] for path in result['paths']]==[0,1]
    assert [path['start_date'] for path in result['paths']]==['2026-01-19','2026-01-20']
    estimate=result['uncertainty']['metrics']['mean_received_cash']
    assert estimate['mean']==0 and estimate['mc_standard_error'] is None
    assert estimate['precision_status']=='insufficient_within_cohort_replication'
    repeated=run(catalogue,forecast=forecast.model_copy(update={'capture_paths':2}))
    assert repeated['metrics']==result['metrics'] and repeated['paths']==result['paths']
    assert repeated['schedules']==result['schedules']


def test_context_inventory_and_roles_cannot_claim_observed_target_data(catalogue):
    forecast=request(1);supplied=targets(forecast);day=date(2026,1,19)
    modeled=supplied['2026-01-19'][day]
    with pytest.raises(ValueError,match='no observed target bars'):
        replace(modeled,observed_bar_count=1)
    with pytest.raises(ValueError,match='Observed native context'):
        replace(modeled,kind='observed')
    with pytest.raises(ValueError,match='complete ordered modeled'):
        native_forecast_layout(forecast,{'2026-01-19':{}},catalogue)
    altered={'2026-01-19':{day:replace(modeled,calendar_sha256='a'*64)}}
    with pytest.raises(ValueError,match='saved modeled calendar'):
        native_forecast_layout(forecast,altered,catalogue)
    weekend=request(1,starts=('2026-01-24',))
    with pytest.raises(ValueError,match='no modeled open sessions'):
        native_forecast_layout(weekend,targets(weekend),catalogue)
    observed=context(date(2026,1,20),load_calendar(symbol='MNQ'),modeled=False)
    with pytest.raises(ValueError,match='mix'):
        NativeFundedController(FundedProfile('apex-50k-eod',PROFILE_VERSION),SIZING,40,
            session_contexts={day:modeled,observed.session:observed},start_date=day,
            cutoff_date_exclusive=date(2026,1,21),receipt_delay_calendar_days=2)
