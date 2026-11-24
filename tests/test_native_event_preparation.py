from datetime import date
import pytest
from test_native_draws import catalog,contexts,open_days,owner,schedule,CONFIG
from native_replay_fixtures import parameters,bars
from alphaquest.prop.native_draws import run_path
from alphaquest.prop.native_preparation import NativeEventPreparation,run_prepared_path
from alphaquest.strategies.vwap_pullback_risk_sizing import VwapPullbackRiskSizing

@pytest.mark.parametrize('phase',['funded','evaluation'])
@pytest.mark.parametrize('gap,skip_retry',[(False,False),(True,False),(False,True)])
def test_all_actual_quantities_fills_cash_dates_and_controller_events_match_full_engine(phase,gap,skip_retry):
 c=catalog(bars(gap=gap,skip_retry=skip_retry));t=contexts(open_days(date(2026,1,12),3),modeled=True)
 factory=lambda:VwapPullbackRiskSizing(parameters(),execution_config=CONFIG,instrument_symbol='MNQ')
 prepared=NativeEventPreparation(c,factory,CONFIG)
 for seed in (1,9):
  s=schedule(c,t,phase=phase,seed=seed)
  a=run_path(c,s,owner(t,phase=phase,percentage='.002' if skip_retry else '.2'),factory,CONFIG,t)
  b=run_prepared_path(c,s,owner(t,phase=phase,percentage='.002' if skip_retry else '.2'),factory,CONFIG,t,preparation=prepared)
  assert a['result']==b['result']
  assert sum(x['processed_execution_bars'] for x in b['source_model_clock_mapping'])<40


@pytest.mark.parametrize('phase',['evaluation','funded'])
def test_gap_through_provider_floor_uses_actual_engine_fill_and_caps(phase):
 from dataclasses import replace
 from decimal import Decimal
 from alphaquest.session_calendar import CT
 from test_native_draws import chosen
 values=bars(gap=True)
 for i,bar in enumerate(values):
  local=bar.timestamp_utc.astimezone(CT)
  if local.date()==date(2026,1,5) and (local.hour,local.minute)==(9,2):
   fields=list(bar.source_fields);fields[2:6]=['180','181','179','180']
   values[i]=replace(bar,open=Decimal('180'),high=Decimal('181'),low=Decimal('179'),close=Decimal('180'),source_fields=tuple(fields))
 c=catalog(values);t=contexts(open_days(date(2026,1,12),1),modeled=True)
 factory=lambda:VwapPullbackRiskSizing(parameters(),execution_config=CONFIG,instrument_symbol='MNQ')
 prepared=NativeEventPreparation(c,factory,CONFIG);s=chosen(c,t,[0],phase=phase)
 expected=run_path(c,s,owner(t,phase=phase,percentage='5'),factory,CONFIG,t)['result']
 actual=run_prepared_path(c,s,owner(t,phase=phase,percentage='5'),factory,CONFIG,t,preparation=prepared)['result']
 assert actual==expected
 close,=[e for e in actual['control_events'] if e['event']=='trade_close']
 assert close['quantity']==(20 if phase=='funded' else 40) and close['account_hit']>0 and close['triggering_floor'] is not None
 assert Decimal(close['entry_fill_price'])==180 and Decimal(close['exit_fill_price'])==120
 assert Decimal(close['net_pnl'])==Decimal('-120')*close['quantity']
