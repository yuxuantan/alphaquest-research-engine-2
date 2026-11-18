"""Original Twin replay is the oracle; cached features never supply a trade tape."""
from dataclasses import replace
from datetime import date,datetime,time,timedelta,timezone
from decimal import Decimal as D
import pickle
import pytest
from test_native_draws import CONFIG,contexts,open_days,owner
from test_twin_continuation import breakout_rows,momentum_rows
from alphaquest.prop.native_draws import build_catalogue,build_schedule,run_path
from alphaquest.prop.native_preparation import NativeEventPreparation,run_prepared_path,worker_programme
from alphaquest.strategies.twin_continuation import TwinContinuation,Parameters
from alphaquest.strategy import Bar
from alphaquest.session_calendar import CT


def twin_catalogue(*,momentum=False,short=False,gaps=False,days=3):
 p=Parameters(max_bars_back=5,use_breakout=not momentum,use_momentum=momentum,bo_pivot_tf=15,bo_atr_period=1,
  mo_basis_len=3,mo_range_len=1,mo_signal_len=1,mo_trigger=D(10),mo_warmup=2)
 pattern=momentum_rows() if momentum else breakout_rows()
 if momentum:
  prices={b.timestamp_utc.astimezone(CT).strftime('%H:%M'):(b.open,b.high,b.low,b.close) for b in pattern}
 else:prices={}
 values=[];source_days=open_days(date(2026,1,5),days)
 for day in source_days:
  start=datetime.combine(day-timedelta(days=1),time(17,1),CT)
  for j in range(1380):
   stamp=start+timedelta(minutes=j)
   if gaps and j in (10,105,330,331,800):continue
   v=prices.get(stamp.strftime('%H:%M'),(100,101,99,100)) if momentum else ((pattern[j].open,pattern[j].high,pattern[j].low,pattern[j].close) if j<len(pattern) else (126,127,125,126))
   v=tuple(D(x) for x in v)
   if short:v=(200-v[0],200-v[2],200-v[1],200-v[3])
   utc=stamp.astimezone(timezone.utc);cells=(utc.strftime('%m/%d/%Y'),utc.strftime('%H:%M'),*map(str,v),'100','50','50')
   values.append(Bar(len(values)+1,utc,cells[0],cells[1],*v,D(100),D(50),D(50),cells))
 ctx=contexts(source_days)
 for day in source_days:ctx[day]=replace(ctx[day],observed_bar_count=sum(b.timestamp_utc.astimezone(CT).date()==day and b.timestamp_utc.astimezone(CT).time()<=time(16) or b.timestamp_utc.astimezone(CT).date()==day-timedelta(days=1) and b.timestamp_utc.astimezone(CT).time()>time(17) for b in values))
 c=build_catalogue(values,ctx,p,block_sessions=1,source_identity=dict(complete_holding_intervals=True,strategy=dict(id='twin_continuation')))
 return c,p


def compare(c,p,*,phase,percentage='.2',fixed=None,seed=4,prepared=None,target_days=3):
 target=contexts(open_days(date(2026,2,2),target_days),modeled=True)
 factory=lambda:TwinContinuation(p,execution_config=CONFIG,instrument_symbol='MNQ')
 plan=build_schedule(c,target,p,phase=phase,seed=seed,path_index=0,start_date=min(target))
 if prepared is None:prepared=NativeEventPreparation(c,factory,CONFIG)
 a=run_path(c,plan,owner(target,phase=phase,percentage=percentage,fixed=fixed),factory,CONFIG,target,capture=False)
 b=run_prepared_path(c,plan,owner(target,phase=phase,percentage=percentage,fixed=fixed),factory,CONFIG,target,preparation=prepared,capture=False)
 for key in ('equity','trading_profit','execution_counts','cash_ledger','outcome','observed_bar_diagnostics','attempts','payout_events','conservation'):
  assert a['result'].get(key)==b['result'].get(key),(key,a['result'].get(key),b['result'].get(key))
 assert a['result']['sizing']['summary']==b['result']['sizing']['summary']
 def fills(o):
  return [{k:v for k,v in e.items() if k not in ('sequence','source_session','target_session','draw_slot','path_index')}
   for e in o['result']['control_events'] if e['event'] in ('entry_fill','trade_close')]
 assert fills(a)==fills(b)
 assert b['preparation']['market_features_reused'] and not b['preparation']['account_state_shared']
 return a,b,prepared


@pytest.mark.parametrize('phase',['evaluation','funded'])
@pytest.mark.parametrize('momentum,short,gaps',[(False,False,False),(False,True,True),(True,False,True),(True,True,False)])
def test_cached_prices_eligibility_fills_and_cash_match_original(phase,momentum,short,gaps):
 c,p=twin_catalogue(momentum=momentum,short=short,gaps=gaps)
 a,b,prepared=compare(c,p,phase=phase,percentage='1' if momentum else '.2')
 assert a['result']['execution_counts']['completed_trades']>0
 assert sum(r['processed_execution_bars'] for r in b['source_model_clock_mapping'])<len(c.bars)/2
 # Reuse the exact immutable programme at a different risk; skips, provider
 # floors and subsequent eligibility still belong to that account, not the cache.
 compare(c,p,phase=phase,percentage='.000001',prepared=prepared)
 compare(c,p,phase=phase,percentage='5',prepared=prepared)


def test_worker_spool_preserves_cached_exact_features_and_no_mutable_account_state(tmp_path):
 c,p=twin_catalogue(gaps=True)
 factory=lambda:TwinContinuation(p,execution_config=CONFIG,instrument_symbol='MNQ')
 prepared=NativeEventPreparation(c,factory,CONFIG)
 worker=pickle.loads(pickle.dumps(worker_programme(prepared,tmp_path)))
 compare(worker.catalogue,p,phase='funded',prepared=worker)
 compare(worker.catalogue,p,phase='evaluation',prepared=worker)
 first=next(iter(prepared.twin.snapshots));a=prepared.twin.strategy(first,lambda:None);b=prepared.twin.strategy(first,lambda:None)
 a.total_trades+=100;a.session_flattening['examples'].append('separate')
 assert b.total_trades!=a.total_trades and 'separate' not in b.session_flattening['examples']


def test_captured_path_continues_into_cached_sessions_and_preserves_original_fills():
 c,p=twin_catalogue(days=10)
 target=contexts(open_days(date(2026,2,2),10),modeled=True)
 factory=lambda:TwinContinuation(p,execution_config=CONFIG,instrument_symbol='MNQ')
 prepared=NativeEventPreparation(c,factory,CONFIG)
 # One ten-session source block exercises the transition after five retained
 # full sessions, while carrying actual filled-trade eligibility into session six.
 c=build_catalogue(c.bars,{s.context.session:s.context for s in c.sessions},p,block_sessions=10,source_identity=dict(complete_holding_intervals=True,strategy=dict(id='twin_continuation')))
 prepared=NativeEventPreparation(c,factory,CONFIG)
 plan=build_schedule(c,target,p,phase='funded',seed=1,path_index=0,start_date=min(target))
 a_owner=owner(target);b_owner=owner(target)
 a_owner.prepared_execution=b_owner.prepared_execution=True
 a=run_path(c,plan,a_owner,factory,CONFIG,target,capture=True)
 b=run_prepared_path(c,plan,b_owner,factory,CONFIG,target,preparation=prepared,capture=True)
 assert a['result']['trading_profit']==b['result']['trading_profit']
 assert a['result']['execution_counts']==b['result']['execution_counts']
 assert a['result']['cash_ledger']==b['result']['cash_ledger']
 assert len(b['captures'])==5


def test_cached_mixed_setups_fixed_quantity_and_temporal_prefix_are_independent():
 c,p=twin_catalogue(momentum=True,days=3)
 p=replace(p,use_breakout=True)
 c=build_catalogue(c.bars,{s.context.session:s.context for s in c.sessions},p,block_sessions=1,source_identity=dict(complete_holding_intervals=True,strategy=dict(id='twin_continuation')))
 compare(c,p,phase='funded',fixed=2)
 factory=lambda:TwinContinuation(p,execution_config=CONFIG,instrument_symbol='MNQ')
 prepared=NativeEventPreparation(c,factory,CONFIG)
 # Later price changes must not change the already-completed market frames.
 cutoff=c.sessions[1].first_bar
 altered=tuple(replace(b,open=b.open+10,high=b.high+10,low=b.low+10,close=b.close+10) if i>=cutoff else b for i,b in enumerate(c.bars))
 changed=build_catalogue(altered,{s.context.session:s.context for s in c.sessions},p,block_sessions=1,source_identity=dict(complete_holding_intervals=True,strategy=dict(id='twin_continuation')))
 other=NativeEventPreparation(changed,factory,CONFIG)
 for i in range(cutoff):
  a=prepared.twin.arm_at[i];b=other.twin.arm_at[i]
  assert (a<0)==(b<0)
  if a>=0:
   assert [prepared.twin.values[j] for j in prepared.twin.arms[a:a+5]]==[other.twin.values[j] for j in other.twin.arms[b:b+5]]
  assert prepared.twin.momentum.get(i)==other.twin.momentum.get(i)


def test_quantity_cache_revalidates_causality_and_preserves_every_quote(monkeypatch):
 import alphaquest.prop.sizing as sizing_module
 from alphaquest.prop.native_control import KnownEntryProposal,ExecutionSnapshot
 from test_native_account_execution import bar,owner as unit_owner
 calls=[];original=sizing_module.choose_quantity
 def measured(*args,**kwargs):calls.append(1);return original(*args,**kwargs)
 monkeypatch.setattr(sizing_module,'choose_quantity',measured)
 rows=[bar(1),bar(2)];control=unit_owner(rows,dict(kind='fixed_dollar_risk',risk_dollars='100'))
 first=ExecutionSnapshot(rows[0].timestamp_utc,1,D(10000),D(10000),None)
 control.begin_session(next(iter(control.contexts.values())),first)
 proposal=KnownEntryProposal(first.timestamp_utc,1,'long','next_open',D(100),D(95),first.timestamp_utc,'test',None)
 q=control.admit_entry(proposal,first,provisional=True);control.cancel_quoted_entry(q,first,'refresh')
 q=control.admit_entry(proposal,first,provisional=True);control.cancel_quoted_entry(q,first,'refresh')
 assert len(calls)==1 and control._decision_count==2
 # Even a cached geometry must reject a newly supplied future-known stop.
 bad=replace(proposal,initial_stop_known_at_utc=first.timestamp_utc+timedelta(minutes=1))
 with pytest.raises(ValueError,match='known at the sizing decision'):control.admit_entry(bad,first,provisional=True)
 control.provider_cap=1
 q=control.admit_entry(proposal,first,provisional=True)
 assert len(calls)==2 and q.accepted_intent.contracts==1


def test_serial_and_multicore_forecasts_have_identical_schedules_fills_and_cash():
 from alphaquest.prop.parallel import Runtime
 from alphaquest.prop.native_replay import NativeForecastRequest
 from alphaquest.prop.phase_profiles import FundedProfile,SizingConfiguration,rule_version
 from alphaquest.prop.funded_profiles import forecast_native_funded
 c,p=twin_catalogue(days=1)
 factory=lambda:TwinContinuation(p,execution_config=CONFIG,instrument_symbol='MNQ')
 prepared=NativeEventPreparation(c,factory,CONFIG)
 target=contexts([date(2026,2,2)],modeled=True)
 request=NativeForecastRequest(model='native_percentage_observed_blocks_v2',simulations=65,seed=42,block_sessions=1,horizon_calendar_days=1,capture_paths=1,
  calendar=dict(start_dates=['2026-02-02'],coverage_end='2026-02-03',closures=[],timezone='America/Chicago',version='test-declared-calendar'))
 target={day:replace(context,calendar_sha256=request.target_calendar().sha256,calendar_version=request.calendar['version']) for day,context in target.items()}
 sizing=SizingConfiguration(dict(kind='percentage_risk',risk_percent='.2',reference='initial_configured_capital'),'50000',dict(tick_size='.25',point_value='2',commission_per_contract_per_side='0'))
 def run(parallel):
  return forecast_native_funded(c,{'2026-02-02':target},factory,CONFIG,FundedProfile('apex-50k-eod',rule_version('apex-50k-eod')),sizing,40,forecast=request,
   receipt_delay_calendar_days=2,receipt_amount_convention='kernel_entitlement_unrounded',preparation=prepared,parallel=parallel)
 a=run(False);runtime=Runtime(workers=2)
 try:
  with runtime.activate():b=run(True)
 finally:runtime.close()
 assert a==b


@pytest.mark.parametrize('short',[False,True])
def test_fill_relative_capped_stops_and_rounded_targets_match_original(short):
 c,p=twin_catalogue(short=short,gaps=True)
 p=replace(p,bo_max_stop_mult=D('.5'),bo_target_mult=D('1.33'))
 c=build_catalogue(c.bars,{s.context.session:s.context for s in c.sessions},p,block_sessions=1,source_identity=dict(complete_holding_intervals=True,strategy=dict(id='twin_continuation')))
 compare(c,p,phase='funded',percentage='2.75')


@pytest.mark.parametrize('budget',[0,32*1024*1024])
def test_prefix_warm_state_and_calendar_hash_match_original_with_cache_overflow(monkeypatch,budget):
 from alphaquest.prop.twin_preparation import TwinMarketPreparation,STATE_FIELDS
 from alphaquest.prop.native_draws import NativePathPreparation
 monkeypatch.setattr(TwinMarketPreparation,'MAX_PREFIX_BYTES',budget)
 c,p=twin_catalogue(momentum=True)
 factory=lambda:TwinContinuation(p,execution_config=CONFIG,instrument_symbol='MNQ')
 original=NativePathPreparation(c,factory,CONFIG)
 cached=NativeEventPreparation(c,factory,CONFIG)
 for session in c.sessions:
  a=original.strategy(session.first_bar,lambda:None);b=cached.twin.strategy(session.first_bar,lambda:None)
  for name in STATE_FIELDS:assert getattr(a,name)==getattr(b,name),name
  assert a.session_digest.hexdigest()==b.session_digest.hexdigest()
  assert a.session_flattening==b.session_flattening
 assert cached.twin.snapshot_bytes<=budget


@pytest.mark.parametrize('exit_time',[1800,0,900,1545,1600])
def test_source_session_relative_exit_boundaries_match_original(exit_time):
 c,p=twin_catalogue(gaps=True)
 p=replace(p,bo_exit_time=exit_time,bo_target_mult=D(0),bo_max_stop_mult=D('12'))
 c=build_catalogue(c.bars,{s.context.session:s.context for s in c.sessions},p,block_sessions=1,source_identity=dict(complete_holding_intervals=True,strategy=dict(id='twin_continuation')))
 compare(c,p,phase='funded',percentage='2.75')


def test_changed_strategy_revision_uses_original_replay_until_cache_is_requalified(monkeypatch):
 import alphaquest.prop.twin_preparation as module
 c,p=twin_catalogue()
 monkeypatch.setattr(module,'QUALIFIED_STRATEGY_SHA256','unreviewed')
 factory=lambda:TwinContinuation(p,execution_config=CONFIG,instrument_symbol='MNQ')
 prepared=NativeEventPreparation(c,factory,CONFIG)
 assert prepared.twin is None and prepared.legacy is not None
 compare_result=run_prepared_path(c,build_schedule(c,contexts([date(2026,2,2)],modeled=True),p,phase='funded',seed=42,path_index=0,start_date=date(2026,2,2)),
  owner(contexts([date(2026,2,2)],modeled=True)),factory,CONFIG,contexts([date(2026,2,2)],modeled=True),preparation=prepared)
 assert compare_result['preparation']['version']=='generic-controlled-bars-v1'
