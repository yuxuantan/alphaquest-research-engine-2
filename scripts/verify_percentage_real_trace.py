"""Read-only comparison of actual native execution on saved real NQ source.

Uses the ordinary full-bar engine as the independent expected result. No reports
are changed and no recorded baseline trades are resized.
"""
from pathlib import Path
import sys,json,time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from dataclasses import asdict,replace
from types import SimpleNamespace
from datetime import timedelta
from alphaquest.datasets import DatasetStore
from alphaquest.backtest_runs import RunStore
from alphaquest.prop.phase_dispatch import module_for
from alphaquest.prop.phase_search import check_candidates
from alphaquest.prop.native_search import prepare_native_candidate,shared_admission
from alphaquest.prop.native_preparation import _make_native_owner,run_prepared_path
from alphaquest.prop.native_draws import build_schedule,run_path
from alphaquest.prop.phase_profiles import EvaluationProfile,FundedProfile,rule_version

def main(library,evidence):
 datasets=DatasetStore(library/'datasets.sqlite3');runs=RunStore(library);datasets.replay_cache=runs.replay_cache
 saved=json.loads((evidence/'apex-50k-eod-evaluation-report.json').read_text());search=module_for('evaluation').parse_request(saved['request'])
 start=time.monotonic()
 with shared_admission():
  check,=check_candidates(runs,search,datasets=datasets)
  inputs,_=prepare_native_candidate(datasets,runs,search,search.candidates[0],check)
 print('PREPARED',time.monotonic()-start,flush=True)
 c=inputs['catalogue'];prepared=inputs['preparation'];factory=inputs['strategy_factory'];config=inputs['config']
 cohort=next(iter(inputs['target_contexts_by_cohort'].values()));days=sorted(cohort)[:5];target={d:cohort[d] for d in days};cutoff=max(days)+timedelta(days=1);candidate=search.candidates[0];rows=[]
 for profile in ('apex-50k-eod','lucidflex-50k'):
  for phase in ('evaluation','funded'):
   cls=EvaluationProfile if phase=='evaluation' else FundedProfile
   args=dict(profile_id=profile,rule_version=rule_version(profile))
   if phase=='evaluation':args.update(evaluation_price='49',activation_fee='129' if profile.startswith('apex') else '0')
   settings=dict(profile=asdict(cls(**args)),sizing=asdict(candidate.sizing),micros=40,max_micros=40,
    calendar=dict(start_dates=[str(min(days))],coverage_end=str(cutoff),closures=[]),retry=asdict(candidate.retry),receipt_delay_calendar_days=2,receipt_amount_convention='kernel_entitlement_unrounded')
   pattern=SimpleNamespace(contexts=target,phase=phase,start=min(days),cutoff=cutoff)
   for seed in (42,1729):
    schedule=build_schedule(c,target,prepared.parameters,phase=phase,seed=seed,path_index=0,start_date=min(days),cutoff_date_exclusive=cutoff)
    expected_owner=_make_native_owner(pattern,settings);actual_owner=_make_native_owner(pattern,settings)
    expected_owner.first_attempt_only=actual_owner.first_attempt_only=False
    a=run_path(c,schedule,expected_owner,factory,config,target,preparation=prepared.legacy)
    b=run_prepared_path(c,schedule,actual_owner,factory,config,target,preparation=prepared)
    def normalized(value):
     # Ordinary blocks use one execute() call; prepared sessions use one each.
     # Its local trade ordinal is an identifier, not a quantity or cash input.
     if isinstance(value,dict):return {k:normalized(v) for k,v in value.items() if k!='trade_number'}
     if isinstance(value,list):return [normalized(v) for v in value]
     return value
    if normalized(a['result'])!=normalized(b['result']):
     (evidence/'real-native-parity-mismatch.json').write_text(json.dumps(dict(expected=a,actual=b),default=str))
     raise AssertionError((profile,phase,seed,[k for k in a['result'] if normalized(a['result'][k])!=normalized(b['result'].get(k))]))
    row=dict(profile=profile,phase=phase,seed=seed,source_indices=[d['source_block_index'] for d in schedule['draws']],full_bar_financial_event_quantity_equality=True,normalized_identifier='engine-local trade_number only; prepared calls restart per session',
     ordinary_bar_count=sum(m['observed_source_bars'] for m in b['source_model_clock_mapping']),indexed_execution_bars=sum(m['processed_execution_bars'] for m in b['source_model_clock_mapping']),result=b['result'])
    rows.append(row);print('MATCH',profile,phase,seed,row['indexed_execution_bars'],flush=True)
 (evidence/'real-native-full-engine-parity.json').write_text(json.dumps(dict(source=saved['source'],source_catalogue=c.metadata(),checks=rows),indent=2,default=str))
if __name__=='__main__':main(Path(sys.argv[1] if len(sys.argv)>1 else '/private/tmp/aq-percentage-product/data'),Path(sys.argv[2] if len(sys.argv)>2 else '/private/tmp/aq-percentage-product/evidence'))
