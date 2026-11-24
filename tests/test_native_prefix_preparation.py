from dataclasses import replace
import pytest
from test_native_draws import catalog,contexts,open_days,owner,schedule,CONFIG,D
from alphaquest.prop.native_draws import NativePathPreparation,run_path
from alphaquest.strategies.vwap_pullback_risk_sizing import VwapPullbackRiskSizing
from native_replay_fixtures import parameters
from datetime import date

@pytest.mark.parametrize('phase',['evaluation','funded'])
@pytest.mark.parametrize('budget',[0,32*1024*1024])
def test_prefix_snapshots_preserve_all_account_trades_state_and_clock(phase,budget):
 c=catalog();target=contexts(open_days(date(2026,1,12),5),modeled=True)
 factory=lambda:VwapPullbackRiskSizing(parameters(),execution_config=CONFIG,instrument_symbol='MNQ')
 preparation=NativePathPreparation(c,factory,CONFIG,max_bytes=budget)
 for seed in (1,3,9):
  plan=schedule(c,target,phase=phase,seed=seed)
  expected=run_path(c,plan,owner(target,phase=phase),factory,CONFIG,target,capture=True)
  actual=run_path(c,plan,owner(target,phase=phase),factory,CONFIG,target,capture=True,preparation=preparation)
  assert actual==expected
 assert preparation.bytes_used<=budget
 with pytest.raises(ValueError,match='differs'):
  run_path(replace(c,catalogue_sha256='0'*64),plan,owner(target,phase=phase),factory,CONFIG,target,preparation=preparation)


def test_preparation_obeys_stop_before_source_replay():
 c=catalog()
 factory=lambda:VwapPullbackRiskSizing(parameters(),execution_config=CONFIG,instrument_symbol='MNQ')
 class Stopped(Exception):pass
 def checkpoint():raise Stopped('cooperative stop')
 with pytest.raises(Stopped,match='cooperative stop'):
  NativePathPreparation(c,factory,CONFIG,checkpoint=checkpoint)
