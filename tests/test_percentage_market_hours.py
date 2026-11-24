from datetime import date,datetime,time,timezone
from dataclasses import asdict,replace
from decimal import Decimal
import pytest
from test_native_forecast_profiles import catalogue,CONFIG,targets,request
from native_replay_fixtures import parameters
from alphaquest.prop.native_market_hours import required_holding_minutes
from alphaquest.prop.native_draws import _encoded_bar,_json
from alphaquest.session_calendar import CT,load_calendar


def sparse_source(missing, *, adverse_open=False):
 from native_replay_fixtures import bars
 from test_native_draws import contexts
 from alphaquest.prop.native_draws import build_catalogue
 values=tuple(replace(b,bar_number=i+1) for i,b in enumerate(b for b in bars(days=1) if b.timestamp_utc.astimezone(CT).strftime('%H:%M') not in missing))
 if adverse_open:
  values=tuple(replace(b,open=Decimal(110),high=Decimal(111),low=Decimal(109),close=Decimal(110)) if b.timestamp_utc.astimezone(CT).strftime('%H:%M')=='09:04' else b for b in values)
 day=date(2026,1,5);context=replace(contexts([day])[day],observed_bar_count=len(values))
 return build_catalogue(values,{day:context},parameters(),block_sessions=1,
  source_identity=dict(complete_holding_intervals=True,strategy=dict(id='vwap_pullback_risk_sizing')))


def execute_sparse(source,phase,accelerated,percentage='.2'):
 from test_native_draws import contexts,owner,schedule,CONFIG
 from alphaquest.prop.native_draws import run_path
 from alphaquest.prop.native_preparation import NativeEventPreparation,run_prepared_path
 from alphaquest.strategies.vwap_pullback_risk_sizing import VwapPullbackRiskSizing
 target=contexts([date(2026,1,12)],modeled=True)
 factory=lambda:VwapPullbackRiskSizing(parameters(),execution_config=CONFIG,instrument_symbol='MNQ')
 plan=schedule(source,target,phase=phase);control=owner(target,phase=phase,percentage=percentage)
 if accelerated:
  prepared=NativeEventPreparation(source,factory,CONFIG)
  return run_prepared_path(source,plan,control,factory,CONFIG,target,preparation=prepared)
 return run_path(source,plan,control,factory,CONFIG,target,capture=True)


@pytest.mark.parametrize('phase',['evaluation','funded'])
@pytest.mark.parametrize('accelerated',[False,True])
def test_real_flat_gaps_before_entry_and_after_exit_preserve_actual_fills(phase,accelerated):
 # Both holes are inside/beside the former possible holding window. Neither
 # overlaps the actual 09:02 entry through 09:03 stop at 113.
 output=execute_sparse(sparse_source({'08:59','09:04'}),phase,accelerated)
 assert Decimal(output['result']['trading_profit'])==-100
 assert output['result']['execution_counts']['completed_trades']==1


@pytest.mark.parametrize('phase',['evaluation','funded'])
@pytest.mark.parametrize('accelerated',[False,True])
def test_held_gap_continues_at_observed_open_with_actual_pnl_diagnostic(phase,accelerated):
 source=sparse_source({'09:03'},adverse_open=True)
 skipped=execute_sparse(source,phase,accelerated,percentage='.000001')
 assert Decimal(skipped['result']['trading_profit'])==0
 assert skipped['result']['observed_bar_diagnostics']['gap_exposed_completed_trades']==0
 output=execute_sparse(source,phase,accelerated)
 # Known entry 118, stop 113, quantity 10; next observed Open 110 gaps past
 # the stop. Existing execution must fill at 110, not invent a 113 exit.
 assert Decimal(output['result']['trading_profit'])==-160
 d=output['result']['observed_bar_diagnostics']
 assert d['position_gap_encounters']==1 and d['missing_minutes_crossed']==1
 assert d['gap_exposed_completed_trades']==1 and Decimal(d['gap_exposed_trade_net_pnl'])==-160
 assert d['longest_gap_minutes']==1


def test_working_twin_stop_entry_gap_is_diagnosed_and_continues():
 from test_twin_continuation import breakout_rows
 from test_native_draws import contexts,owner,CONFIG
 from alphaquest.prop.native_market_hours import ObservedExposureCoverage,missing_minute_ranges
 from alphaquest.strategies.twin_continuation import TwinContinuation,Parameters
 from alphaquest.execution import execute
 from datetime import timedelta
 values=breakout_rows();missing=values[105].timestamp_utc
 close=datetime(2024,1,16,16,tzinfo=CT).astimezone(timezone.utc)
 while values[-1].timestamp_utc<close:
  values.append(replace(values[-1],bar_number=len(values)+1,timestamp_utc=values[-1].timestamp_utc+timedelta(minutes=1)))
 values=[replace(b,bar_number=i+1) for i,b in enumerate(b for b in values if b.timestamp_utc!=missing)]
 day=date(2024,1,16);context=replace(contexts([day])[day],observed_bar_count=len(values))
 control=owner({day:context},fixed=2)
 control.observed_coverage=ObservedExposureCoverage(missing_minute_ranges(day,[b.timestamp_utc for b in values],context.scheduled_close_utc))
 p=Parameters(max_bars_back=0,use_momentum=False,bo_pivot_tf=15,bo_atr_period=1)
 list(execute(values,TwinContinuation(p,execution_config=CONFIG),CONFIG,account_control=control,completion='require_flat'))
 d=control.finish_replay()['observed_bar_diagnostics']
 assert d['working_entry_gap_encounters']==1
 assert d['gap_exposed_completed_trades']==1
 assert any(e['event']=='source_gap' and e['exposure']=='a stop-entry order is working' for e in control.events)


@pytest.mark.parametrize('accelerated',[False,True])
def test_missing_liquidation_tail_cannot_create_an_eof_exit(accelerated):
 from datetime import timedelta
 missing=set();stamp=datetime(2026,1,5,9,3)
 while stamp<=datetime(2026,1,5,16):
  missing.add(stamp.strftime('%H:%M'));stamp+=timedelta(minutes=1)
 with pytest.raises(ValueError,match='source truncation cannot fabricate an EOF liquidation'):
  execute_sparse(sparse_source(missing),'funded',accelerated)


def test_exposure_coverage_exempts_only_the_reviewed_historical_pause():
 from datetime import timedelta
 from alphaquest.prop.native_market_hours import missing_minute_ranges,ObservedExposureCoverage
 for day,paused in [(date(2021,6,25),True),(date(2021,6,28),False)]:
  begin=datetime.combine(day-timedelta(days=1),time(17,1),CT).astimezone(timezone.utc)
  close=datetime.combine(day,time(16),CT).astimezone(timezone.utc)
  stamps=[];stamp=begin
  while stamp<=close:
   if not time(15,15)<stamp.astimezone(CT).time()<=time(15,30):stamps.append(stamp)
   stamp+=timedelta(minutes=1)
  gaps=missing_minute_ranges(day,stamps,close)
  guard=ObservedExposureCoverage(gaps)
  guard.check(datetime.combine(day,time(15,15),CT).astimezone(timezone.utc),None)
  resumed=datetime.combine(day,time(15,31),CT).astimezone(timezone.utc)
  if paused:
   assert not gaps
   guard.check(resumed,'a position is open')
  else:
   rows=guard.check(resumed,'a position is open')
   assert len(rows)==1 and rows[0]['missing_minutes']==15


def test_observed_bar_encoding_is_byte_identical_to_legacy():
 for b in catalogue.__wrapped__().bars[::37]:assert _encoded_bar(b)==(_json(asdict(b))+'\n').encode()


def test_reviewed_halt_ends_on_20210628_and_only_flat_tail_is_exempt():
 p=replace(parameters(),entry_start_time=900,eod_flat_time=1540)
 for day,paused in [(date(2021,6,25),True),(date(2021,6,28),False)]:
  close=datetime.combine(day,time(16),CT).astimezone(timezone.utc);required=required_holding_minutes(day,p,close)
  stamp=lambda h,m:datetime.combine(day,time(h,m),CT).astimezone(timezone.utc)
  assert (stamp(15,16) not in required)==paused
  assert stamp(15,15) in required and stamp(15,31) in required
  assert stamp(15,41) in required and stamp(15,42) not in required


def test_acceleration_counts_only_real_holes_once_even_across_multiple_ranges():
 from datetime import timedelta
 from alphaquest.prop.native_market_hours import ObservedExposureCoverage
 start=datetime(2026,1,5,15,tzinfo=timezone.utc)
 guard=ObservedExposureCoverage([(start+timedelta(minutes=n),start+timedelta(minutes=n)) for n in (1,3)])
 assert not guard.check(start,None)
 rows=guard.check(start+timedelta(minutes=5),'a position is open')
 assert len(rows)==2 and sum(row['missing_minutes'] for row in rows)==2
 assert not guard.check(start+timedelta(minutes=6),'a position is open')
