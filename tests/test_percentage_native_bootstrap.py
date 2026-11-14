"""Full addressed native refit count, serial/parallel parity and durable resume."""
from dataclasses import replace
from types import SimpleNamespace
from test_native_forecast_profiles import catalogue,factory,CONFIG,request,targets
from test_native_search_contract import search
from alphaquest.prop.phase_profiles import SizingConfiguration,SimulationConfig,EvaluationSamplingConfig,NativeExecution
from alphaquest.prop.native_preparation import NativeEventPreparation
from alphaquest.prop.native_oos_bootstrap import run
from alphaquest.prop.parallel import Runtime
import pytest


def inputs_and_candidate(phase):
 c=catalogue.__wrapped__();f=request(simulations=8,capture=1).model_copy(update={'model':'native_percentage_observed_blocks_v2'})
 sizing=SizingConfiguration(dict(kind='percentage_risk',risk_percent='.2',reference='initial_configured_capital'),'50000',dict(tick_size='.25',point_value='2',commission_per_contract_per_side='0'))
 s=search(phase);candidate=replace(s.candidates[0],micros=40,sizing=sizing,simulation=SimulationConfig(8,1729),**(dict(sampling=EvaluationSamplingConfig(1,8,1732)) if phase=='evaluation' else {}))
 s=replace(s,candidates=(candidate,),native_execution=NativeExecution(9,model='native_percentage_observed_blocks_v2'))
 inputs=dict(catalogue=c,target_contexts_by_cohort=targets(f),strategy_factory=factory,config=CONFIG,profile=candidate.profile,sizing=sizing,micros=40,forecast=f,max_micros=40,preparation=NativeEventPreparation(c,factory,CONFIG))
 return inputs,candidate,s


class MemoryCheckpoints:
 def __init__(self):self.values={}
 def load_refits(self,key,total):return dict(self.values.get(key,{}))
 def save_refits(self,id,key,rows):self.values.setdefault(key,{}).update((r['replicate']['replicate'],r) for r in rows)

@pytest.mark.parametrize('phase',['evaluation','funded'])
def test_all_10000_native_two_history_refits_and_checkpoint_reopen(phase):
 inputs,candidate,s=inputs_and_candidate(phase);saved=MemoryCheckpoints();progress=[]
 runtime=Runtime(4)
 try:
  with runtime.activate():r=run(inputs,inputs,candidate,candidate,s,lambda:None,progress.append,resume=(saved,'test'))
  assert len(r['replicates'])==10000 and r['inner_precision_ok']
  assert r['unique_histories_evaluated']==[1,1]
  assert all(v==1 for row in r['replicates'] for v in row['ratios'].values())
  assert all(row['is_history']['inner_paths']==8 and row['oos_history']['inner_paths']==8 for row in r['replicates'])
  assert r['replicates'][0]['is_history']['role_seed']!=r['replicates'][0]['oos_history']['role_seed']
  assert progress[-1]['completed']==10000 and progress[-1]['sizing_label'].startswith('0.2%')
  with runtime.activate():again=run(inputs,inputs,candidate,candidate,s,lambda:None,lambda x:None,resume=(saved,'test'))
  assert again['replicates']==r['replicates'] and again['execution']['reused_resamples']==10000
 finally:runtime.close()


def test_stop_preserves_completed_refits_and_serial_resume_matches_parallel():
 inputs,candidate,s=inputs_and_candidate('funded');saved=MemoryCheckpoints();stop=False
 class Stopped(RuntimeError):pass
 def checkpoint():
  if stop:raise Stopped('requested test stop')
 def progress(row):
  nonlocal stop
  if 0<row['completed']<row['total']:stop=True
 runtime=Runtime(4)
 try:
  with runtime.activate(),pytest.raises(Stopped):run(inputs,inputs,candidate,candidate,s,checkpoint,progress,resume=(saved,'stopped'))
 finally:runtime.close()
 retained=sum(len(rows) for rows in saved.values.values())
 assert 0<retained<10000
 runtime=Runtime(1)
 try:
  with runtime.activate():resumed=run(inputs,inputs,candidate,candidate,s,lambda:None,lambda x:None,resume=(saved,'stopped'))
 finally:runtime.close()
 assert resumed['execution']['reused_resamples']==retained
 assert len(resumed['replicates'])==10000 and all(v==1 for r in resumed['replicates'] for v in r['ratios'].values())
 assert [r['replicate'] for r in resumed['replicates']]==list(range(10000))
