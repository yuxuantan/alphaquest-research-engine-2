from dataclasses import replace
from decimal import Decimal
import pytest
from test_native_forecast_profiles import catalogue,request,targets,factory,CONFIG
from alphaquest.prop.native_preparation import NativeEventPreparation
from alphaquest.prop.phase_profiles import EvaluationProfile,FundedProfile,SizingConfiguration,rule_version
from alphaquest.prop.evaluation_profiles import forecast_native_evaluation,native_acquisition_metrics
from alphaquest.prop.funded_profiles import forecast_native_funded
from alphaquest.prop.evaluation_optimization import SequentialRetry

@pytest.mark.parametrize('profile',['apex-50k-eod','lucidflex-50k'])
@pytest.mark.parametrize('phase',['evaluation','funded'])
def test_prepared_percentage_native_forecast_captures_and_exact_sample_counts(profile,phase):
 c=catalogue.__wrapped__();f=request(simulations=8,capture=1).model_copy(update={'model':'native_percentage_observed_blocks_v2'})
 p=NativeEventPreparation(c,factory,CONFIG)
 sizing=SizingConfiguration(dict(kind='percentage_risk',risk_percent='.2',reference='initial_configured_capital'),'50000',dict(tick_size='.25',point_value='2',commission_per_contract_per_side='0'))
 common=dict(forecast=f,preparation=p,parallel=False)
 if phase=='funded':
  r=forecast_native_funded(c,targets(f),factory,CONFIG,FundedProfile(profile,rule_version(profile)),sizing,40,
   receipt_delay_calendar_days=2,receipt_amount_convention='kernel_entitlement_unrounded',**common)
  assert r['metrics']['paths']==8
 else:
  r=forecast_native_evaluation(c,targets(f),factory,CONFIG,EvaluationProfile(profile,rule_version(profile),'49','129' if profile=='apex-50k-eod' else '0'),sizing,40,
   retry=SequentialRetry(activation_delay_sessions=0),**common)
  if profile=='apex-50k-eod':
   a=native_acquisition_metrics(r);assert a['status']=='estimated'
   assert a['metrics']['cost_per_funded']==178
 assert len(r['paths'])==8 and len(r['captures'])==1 and len(r['schedules'])==8
 assert [x['path_index'] for x in r['paths']]==list(range(8))


def test_twenty_thousand_requested_paths_are_not_clipped():
 c=catalogue.__wrapped__();f=request(horizon=1,simulations=8,capture=1).model_copy(update={'model':'native_percentage_observed_blocks_v2','simulations':20000})
 p=NativeEventPreparation(c,factory,CONFIG)
 sizing=SizingConfiguration(dict(kind='percentage_risk',risk_percent='.2',reference='initial_configured_capital'),'50000',dict(tick_size='.25',point_value='2',commission_per_contract_per_side='0'))
 from alphaquest.prop.parallel import Runtime
 runtime=Runtime(4)
 try:
  with runtime.activate():r=forecast_native_funded(c,targets(f),factory,CONFIG,FundedProfile('apex-50k-eod',rule_version('apex-50k-eod')),sizing,40,forecast=f,preparation=p,receipt_delay_calendar_days=2,receipt_amount_convention='kernel_entitlement_unrounded')
 finally:runtime.close()
 assert len(r['paths'])==len(r['schedules'])==20000 and r['metrics']['paths']==20000
 assert r['paths'][-1]['path_index']==19999 and len(r['captures'])==1

@pytest.mark.parametrize('profile',['apex-50k-eod','lucidflex-50k'])
def test_full_3650_calendar_day_guard_keeps_declared_horizon(profile):
 from alphaquest.prop.native_replay import NativeForecastRequest
 c=catalogue.__wrapped__();f=NativeForecastRequest(**{**request(simulations=8,capture=1).model_dump(mode='json'),'model':'native_percentage_observed_blocks_v2','horizon_calendar_days':3650,'calendar':dict(start_dates=['2026-01-19'],coverage_end='2036-01-19',closures=[],timezone='America/Chicago',version='synthetic-declared-3650-day-calendar')})
 p=NativeEventPreparation(c,factory,CONFIG)
 sizing=SizingConfiguration(dict(kind='percentage_risk',risk_percent='.2',reference='initial_configured_capital'),'50000',dict(tick_size='.25',point_value='2',commission_per_contract_per_side='0'))
 r=forecast_native_evaluation(c,targets(f),factory,CONFIG,EvaluationProfile(profile,rule_version(profile),'49','129' if profile=='apex-50k-eod' else '0'),sizing,40,forecast=f,preparation=p,retry=SequentialRetry(activation_delay_sessions=0),parallel=False)
 assert all(row['cutoff_date_exclusive']=='2036-01-17' for row in r['paths'])
 assert r['settings']['horizon_calendar_days']==3650 and len(r['paths'])==8
 assert native_acquisition_metrics(r)['status']=='estimated'


def test_diagnostic_capture_ends_after_five_sessions_without_cutting_cash_or_paths():
 c=catalogue.__wrapped__();f=request(simulations=8,capture=1).model_copy(update={'model':'native_percentage_observed_blocks_v2'})
 p=NativeEventPreparation(c,factory,CONFIG)
 sizing=SizingConfiguration(dict(kind='percentage_risk',risk_percent='.2',reference='initial_configured_capital'),'50000',dict(tick_size='.25',point_value='2',commission_per_contract_per_side='0'))
 args=(c,targets(f),factory,CONFIG,FundedProfile('apex-50k-eod',rule_version('apex-50k-eod')),sizing,40)
 a=forecast_native_funded(*args,forecast=f,preparation=p,parallel=False,receipt_delay_calendar_days=2,receipt_amount_convention='kernel_entitlement_unrounded')
 quiet=f.model_copy(update={'capture_paths':0}) # private refit path, never an API override
 b=forecast_native_funded(*args,forecast=quiet,preparation=p,parallel=False,receipt_delay_calendar_days=2,receipt_amount_convention='kernel_entitlement_unrounded')
 assert len(a['paths'])==len(b['paths'])==8 and a['metrics']==b['metrics']
 for x,y in zip(a['paths'],b['paths'],strict=True):
  for key in ('cash_received','pending_cash','trading_profit','gross_account_deductions','equity','payout_events','sizing_summary'):
   assert x[key]==y[key]
 capture,=a['captures']
 assert len(capture['captures'])<=5
