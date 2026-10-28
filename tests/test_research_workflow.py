"""Required declarations, strict holdout isolation, and a durable access budget."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date,timedelta
import hashlib
import json
from threading import Event
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest

from alphaquest.app import create_app
from alphaquest.research import ResearchStore,ResearchConflict,SplitDeclaration

STRATEGY='consecutive_green_hold'


def history(days=2):
    lines=['Date,Time,Open,High,Low,Close,Volume,UpVol,DownVol'];stamp=date(2026,1,5);count=0
    while count<days:
        if stamp.weekday()<5:
            for minute,prices in [(0,'99,100,99,100'),(1,'100,103,100,103'),(2,'103,103,103,103')]:
                lines.append(stamp.strftime('%m/%d/%Y')+f',18:0{minute},{prices},100,60,40')
            count+=1
        stamp+=timedelta(days=1)
    return ('\n'.join(lines)+'\n').encode()


def save(client,days=2,point='10',zone='UTC'):
    response=client.post('/api/datasets',params=dict(filename='SYNTHETIC-IS-OOS.csv',name='SYNTHETIC holdout isolation',symbol='SYNTHETIC',source_timezone=zone,tick_size='.25',point_value=point),content=history(days))
    assert response.status_code==201,response.text
    return response.json()


def body(dataset,split=None):
    return dict(dataset_id=dataset['id'],strategy_id=STRATEGY,strategy_parameters=dict(green_bar_count=1,hold_minutes=1,contracts=1),
                execution_settings=dict(initial_capital='10000',slippage_ticks=0,commission_per_contract_per_side='0'),
                sample_split=split or dict(mode='percentage',is_percent=50),reuse_results=False)


def sweep(dataset):
    request=body(dataset);values=request.pop('strategy_parameters')
    request.update(method='exhaustive',workers=1,parameter_ranges={k:dict(start=v,end=v,step=0) for k,v in values.items()})
    request['parameter_ranges']['contracts'].update(end=2,step=1)
    return request


def start_is(client,dataset):
    response=client.post('/api/backtests',json=body(dataset));assert response.status_code==201,response.text
    return response.json()


def oos(client,record,id=None,**kwargs):
    return client.post('/api/backtests/'+record['id']+'/oos',json=dict(request_id=id or str(uuid4()),**kwargs))


def status(client,dataset,strategy=STRATEGY):
    return client.get('/api/backtests/research-plan',params=dict(dataset_id=dataset['id'],strategy_id=strategy)).json()


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path/'datasets.sqlite3')) as client:yield client


def test_required_for_single_sweep_and_compatibility_alias_before_any_execution(client):
    dataset=save(client)
    for endpoint,request in [('/api/backtests',body(dataset)),('/api/backtests',sweep(dataset)),('/api/optimizations',sweep(dataset))]:
        del request['sample_split']
        assert client.post(endpoint,json=request).status_code==422
    assert client.get('/api/backtests').json()['total']==0
    assert client.get('/api/backtests/batches').json()['total']==0
    assert status(client,dataset)['plan'] is None
    request=body(dataset);request['from_date']='2026-01-06'
    assert client.post('/api/backtests',json=request).status_code==422


def test_percentage_trading_dates_and_explicit_equivalence_source_timezone(client):
    dataset=save(client,days=10,zone='Asia/Singapore')
    request=dict(dataset_id=dataset['id'],strategy_id=STRATEGY,sample_split=dict(mode='percentage',is_percent=70))
    response=client.post('/api/backtests/research-plan/preview',json=request)
    assert response.status_code==200,response.text
    plan=response.json()['proposed_plan']
    assert (plan['is_start'],plan['is_end'],plan['oos_start'],plan['oos_end'])==('2026-01-05','2026-01-13','2026-01-14','2026-01-16')
    assert (plan['is_bars'],plan['oos_bars'])==(21,9)
    request['sample_split']=dict(mode='dates',**{k:plan[k] for k in ('is_start','is_end','oos_start','oos_end')})
    assert client.post('/api/backtests/research-plan/preview',json=request).json()['proposed_plan']==plan
    assert status(client,dataset)['plan'] is None,'Preview must not lock a plan or consume OOS budget'


@pytest.mark.parametrize('split',[
    {},dict(mode='dates',is_start='2026-01-05',is_end='2026-01-05'),
    dict(mode='percentage',is_percent=0),dict(mode='percentage',is_percent=100),dict(mode='percentage',is_percent=True),
    dict(mode='percentage',is_percent=50,oos_end='2026-01-06'),
    dict(mode='dates',is_start='2026-01-05',is_end='2026-01-06',oos_start='2026-01-06',oos_end='2026-01-06'),
    dict(mode='dates',is_start='2026-01-06',is_end='2026-01-06',oos_start='2026-01-05',oos_end='2026-01-05'),
    dict(mode='dates',is_start='2026-01-04',is_end='2026-01-05',oos_start='2026-01-06',oos_end='2026-01-06'),
    dict(mode='dates',is_start='2026-99-05',is_end='2026-01-05',oos_start='2026-01-06',oos_end='2026-01-06'),
    dict(mode='dates',is_start='2026-01-05',is_end='2026-01-05',oos_start='2026-01-06',oos_end='2026-01-07'),
])
def test_invalid_declarations_rejected_before_lock_or_backtest(client,split):
    dataset=save(client);request=body(dataset);request['sample_split']=split
    assert client.post('/api/backtests',json=request).status_code==422
    assert status(client,dataset)['plan'] is None
    assert client.get('/api/backtests').json()['total']==0


def test_single_day_dataset_and_empty_windows_rejected(client):
    dataset=save(client,days=1)
    response=client.post('/api/backtests',json=body(dataset));assert response.status_code==422
    assert 'two distinct trading dates' in response.text
    client.delete('/api/datasets/'+dataset['id']);dataset=save(client,days=6)
    request=body(dataset,dict(mode='dates',is_start='2026-01-10',is_end='2026-01-11',oos_start='2026-01-12',oos_end='2026-01-12'))
    assert client.post('/api/backtests',json=request).status_code==422


def test_is_isolation_then_selected_oos_exact_values_and_idempotency(client,tmp_path):
    dataset=save(client);record=start_is(client,dataset)
    assert record['run_metadata']['research']['phase']=='is'
    assert record['run_metadata']['selection']['row_count']==3
    assert record['summary']['total_net_pnl']=='30.00' and record['summary']['trades_taken']==1
    trades=client.get('/api/backtests/'+record['id']+'/trades').json()['items']
    assert all(t['entry_time_utc'].startswith('2026-01-05') and t['exit_time_utc'].startswith('2026-01-05') for t in trades)
    default=client.get('/api/prop-analyses/'+record['run_metadata']['automatic_prop_analysis']['id']).json()
    assert default['status']=='incompatible','One IS weekday must not be combined with OOS to satisfy prop source checks'
    assert status(client,dataset)['used']==0
    original=client.get('/api/backtests/'+record['id']+'/exports/report').content
    request_id=str(uuid4());response=oos(client,record,request_id);assert response.status_code==201,response.text
    holdout=response.json();r=holdout['run_metadata']['research']
    assert r['phase']=='oos' and r['parent_run_id']==record['id'] and r['attempt_number']==1
    assert holdout['run_metadata']['strategy']['parameters']==record['run_metadata']['strategy']['parameters']
    assert holdout['execution_settings']==record['execution_settings']
    assert holdout['run_metadata']['selection']['row_count']==3 and holdout['summary']['total_net_pnl']=='30.00'
    trades=client.get('/api/backtests/'+holdout['id']+'/trades').json()['items']
    assert all(t['entry_time_utc'].startswith('2026-01-06') for t in trades)
    assert oos(client,record,request_id).json()['id']==holdout['id']
    assert status(client,dataset)['used']==1
    assert oos(client,record,strategy_parameters=dict(contracts=9)).status_code==422
    assert oos(client,holdout).status_code==409
    assert client.post('/api/backtests/'+holdout['id']+'/detailed').status_code==409
    assert client.get('/api/backtests/'+record['id']+'/exports/report').content==original
    (tmp_path/'is-oos-independent-values.json').write_text(json.dumps(dict(synthetic=True,is_report=record,oos_report=holdout,expected_net_per_period=30,expected_trades_per_period=1,expected_prop='incompatible: one source weekday per period',budget=status(client,dataset)),indent=2))


def test_unlimited_manual_oos_history_concurrency_deletion_and_restart(client,tmp_path):
    dataset=save(client);record=start_is(client,dataset)
    with ThreadPoolExecutor(max_workers=6) as workers:
        responses=list(workers.map(lambda _:oos(client,record),range(6)))
    assert [r.status_code for r in responses]==[201]*6
    assert not status(client,dataset)['exhausted'] and status(client,dataset)['used']==6
    assert status(client,dataset)['budget'] is None and status(client,dataset)['remaining'] is None
    original_ids=[r.json()['id'] for r in responses if r.status_code==201]
    for id in original_ids:assert client.delete('/api/backtests/'+id).status_code==204
    request=body(dataset);request['strategy_parameters']['contracts']=2
    another=client.post('/api/backtests',json=request);assert another.status_code==201
    assert oos(client,another.json()).status_code==201
    assert status(client,dataset,'vwap_pullback_risk_sizing')['used']==0
    assert client.delete('/api/datasets/'+dataset['id']).status_code==204
    restored=save(client);assert restored['sha256']==dataset['sha256']
    assert status(client,restored)['used']==7
    # Reopen the same on-disk catalogue without creating another server/analysis worker.
    reopened=ResearchStore(client.app.state.runs)
    assert reopened.status(restored,STRATEGY)['used']==7
    assert oos(client,start_is(client,restored)).status_code==201


def test_failed_and_interrupted_attempts_count_and_reused_request_is_not_recomputed(client,monkeypatch):
    dataset=save(client);record=start_is(client,dataset);research=client.app.state.research
    from alphaquest import backtest_api
    original=backtest_api.run_backtest
    def fails(*args,**kwargs):raise RuntimeError('Injected worker failure')
    monkeypatch.setattr(backtest_api,'run_backtest',fails)
    response=oos(client,record);assert response.status_code==500
    assert status(client,dataset)['used']==1 and status(client,dataset)['attempts'][0]['status']=='failed'
    monkeypatch.setattr(backtest_api,'run_backtest',original)
    plan=record['run_metadata']['research']['plan'];id=str(uuid4())
    attempt,fresh=research.reserve(plan,record['id'],id);assert fresh
    assert oos(client,record,id).status_code==202
    recovered=ResearchStore(client.app.state.runs)
    assert recovered.status(dataset,STRATEGY)['used']==2
    assert next(a for a in status(client,dataset)['attempts'] if a['id']==id)['status']=='interrupted'
    assert oos(client,record,id).status_code==409
    assert oos(client,record).status_code==201
    assert oos(client,record).status_code==201


def test_editing_split_preserves_old_is_plan_and_manual_oos_selection(client):
    dataset=save(client,days=10)
    original=client.post('/api/backtests',json=body(dataset,dict(mode='percentage',is_percent=70))).json()
    original_bytes=client.get('/api/backtests/'+original['id']+'/exports/report').content
    request=body(dataset,dict(mode='percentage',is_percent=80))
    changed=client.post('/api/backtests',json=request)
    assert changed.status_code==201,changed.text
    assert changed.json()['run_metadata']['selection']['row_count']==24
    assert status(client,dataset)['plan']['is_end']=='2026-01-14'
    assert status(client,dataset)['used']==0
    assert client.get('/api/backtests/'+original['id']+'/oos').json()['plan']==original['run_metadata']['research']['plan']
    heldout=oos(client,original);assert heldout.status_code==201,heldout.text
    assert heldout.json()['run_metadata']['selection']['row_count']==9
    assert heldout.json()['run_metadata']['research']['plan']==original['run_metadata']['research']['plan']
    assert client.get('/api/backtests/'+original['id']+'/exports/report').content==original_bytes
    assert client.post('/api/optimizations',json={**sweep(dataset),'sample_split':request['sample_split']}).status_code==202


@pytest.mark.parametrize('workers',[1,2])
def test_optimisation_runs_is_only_and_selects_one_normal_trial_for_oos(client,workers):
    import time
    from alphaquest.worker_limits import MAX_WORKERS
    if workers>MAX_WORKERS:pytest.skip('Host permits one worker')
    dataset=save(client);response=client.post('/api/backtests',json={**sweep(dataset),'workers':workers});assert response.status_code==202,response.text
    id=response.json()['id'];deadline=time.monotonic()+30
    while True:
        job=client.get('/api/backtests/batches/'+id).json()
        if job['status'] not in ('queued','running'):break
        assert time.monotonic()<deadline;time.sleep(.02)
    assert job['status']=='complete',job
    assert job['research']['phase']=='is' and status(client,dataset)['used']==0
    results=client.get('/api/backtests/batches/'+id+'/results').json()['items']
    assert [r['metrics']['total_net_pnl'] for r in results]==['30.00','60.00']
    for row in results:
        record=client.get('/api/backtests/'+row['run_id']).json()
        assert record['run_metadata']['research']['phase']=='is'
        assert record['run_metadata']['selection']['row_count']==3
    record=client.get('/api/backtests/'+results[1]['run_id']).json()
    response=oos(client,record);assert response.status_code==201,response.text
    assert response.json()['summary']['total_net_pnl']=='60.00'
    assert status(client,dataset)['used']==1


def test_same_request_id_is_reserved_once_under_concurrent_submission(client):
    dataset=save(client);record=start_is(client,dataset);id=str(uuid4())
    with ThreadPoolExecutor(max_workers=4) as workers:
        responses=list(workers.map(lambda _:oos(client,record,id),range(4)))
    assert all(r.status_code in (200,201,202) for r in responses)
    assert sum(r.status_code==201 for r in responses)==1
    assert status(client,dataset)['used']==1
    assert client.get('/api/backtests').json()['total']==2


def test_legacy_reports_readable_disclosed_and_cannot_launch_holdout(client):
    dataset=save(client);record=start_is(client,dataset)
    original=client.get('/api/backtests/'+record['id']+'/exports/report').content
    record['run_metadata'].pop('research')
    with client.app.state.runs.connect() as db:
        db.execute('UPDATE runs SET manifest=? WHERE id=?',(json.dumps(record),record['id']))
    assert client.get('/api/backtests/'+record['id']).status_code==200
    assert client.get('/api/backtests/'+record['id']+'/exports/report').content==original
    assert oos(client,record).status_code==409
    assert client.post('/api/backtests/'+record['id']+'/detailed').status_code==409
    assert status(client,dataset)['legacy_reports']==1 and status(client,dataset)['used']==0


def test_new_registered_strategy_uses_the_same_policy_without_strategy_specific_code(client,monkeypatch):
    from types import SimpleNamespace
    from alphaquest.strategies import registry
    original=registry.get_strategy(STRATEGY)
    module=SimpleNamespace(**vars(original.module));module.STRATEGY_ID='synthetic_future_strategy'
    monkeypatch.setitem(registry.STRATEGIES,module.STRATEGY_ID,registry.StrategyDefinition(module,original.factory))
    dataset=save(client);request=body(dataset);request['strategy_id']=module.STRATEGY_ID
    response=client.post('/api/backtests',json=request);assert response.status_code==201,response.text
    record=response.json()
    assert record['run_metadata']['research']['plan']['strategy_id']==module.STRATEGY_ID
    assert oos(client,record).status_code==201
    assert status(client,dataset,module.STRATEGY_ID)['used']==1
    assert status(client,dataset,STRATEGY)['used']==0


def test_prepolicy_full_history_cannot_bypass_holdout_budget_through_prop_api(client):
    from alphaquest.backtest_api import run_backtest
    from alphaquest.backtest_data import DateRange
    from alphaquest.backtest_requests import ExecutionSettings
    from alphaquest.strategies.registry import get_strategy
    dataset=save(client);start_is(client,dataset)
    request=body(dataset);definition=get_strategy(STRATEGY)
    # An actual native report represents saved pre-policy full-history data.
    # Its original files stay readable and are never rewritten by the guard.
    record=run_backtest(client.app.state.store,client.app.state.runs,uuid4().hex,dataset,definition,
        definition.parameters(request['strategy_parameters']),ExecutionSettings.model_validate(request['execution_settings']).execution_config(dataset),
        DateRange(),lambda *args:None,prop_analyses=None,reuse_results=False)
    original=client.get('/api/backtests/'+record['id']+'/exports/report').content
    analysis=dict(source_backtest_id=record['id'],trade_file='',settings={})
    assert client.post('/api/prop-analyses/check',json=analysis).status_code==409
    assert client.post('/api/prop-analyses',json=analysis).status_code==409
    assert client.get('/api/backtests/'+record['id']+'/exports/report').content==original
    assert status(client,dataset)['used']==0
