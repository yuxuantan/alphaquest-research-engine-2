"""Independent native-run arithmetic, review gates, persistence and source integrity."""
from hashlib import sha256
import json
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from alphaquest.app import create_app
from alphaquest.campaign_workflow import CampaignWorkflowStore, sample_trades
from test_research_workflow import client


def mechanics_csv():
    lines = ['Date,Time,Open,High,Low,Close,Volume,UpVol,DownVol']
    for hour, close, duration in zip(range(9, 15), [101,105,97,102,103,104], [21,24,25,20,23,22]):
        for minute, op, end in [(0,97,98),(1,98,99),(2,99,100),(2+duration,close,close)]:
            lines.append(f'01/05/2026,{hour:02}:{minute:02},{op},{max(op,end)},{min(op,end)},{end},100,60,40')
    lines.append('01/06/2026,09:00,900,900,900,900,100,60,40')
    return ('\n'.join(lines)+'\n').encode()


def create_workflow(client, raw=None):
    response = client.post('/api/datasets', params=dict(filename='SYNTHETIC-mechanics.csv',name='SYNTHETIC mechanics',symbol='SYNTHETIC',source_timezone='UTC',tick_size='.25',point_value='10'), content=raw or mechanics_csv())
    assert response.status_code == 201, response.text
    dataset = response.json()
    body = dict(dataset_id=dataset['id'],strategy_id='consecutive_green_hold',sample_split=dict(mode='dates',is_start='2026-01-05',is_end='2026-01-05',oos_start='2026-01-06',oos_end='2026-01-06'),execution_settings=dict(initial_capital='10000',slippage_ticks=1,commission_per_contract_per_side='1'))
    response = client.post('/api/campaign-workflows',json=body)
    assert response.status_code == 201,response.text
    return dataset,body,response.json()


def run_validation(client, workflow):
    response=client.post('/api/campaign-workflows/'+workflow['id']+'/run')
    assert response.status_code == 200,response.text
    return response.json()


def checks(saved, value=True):
    return dict(revision=saved['review']['revision'], **{key:{id:value for id in saved['review'][key]} for key in ('metric_checks','trade_parity','trade_correctness')})


def test_default_run_exact_samples_review_gate_and_durable_reopen(client, tmp_path):
    dataset,body,workflow=create_workflow(client)
    prefix='/api/campaign-workflows/'+workflow['id']
    assert workflow['status']=='not_run' and workflow['run_id'] is None
    assert client.get('/api/backtests').json()['total']==0
    assert client.post('/api/campaign-workflows',json=body).json()['id']==workflow['id']
    for phase in ['is_broad','is_narrow','oos']:
        assert client.get(prefix+'/phases/'+phase).status_code==409
        assert client.post(prefix+'/phases/'+phase+'/run').status_code==409
    result=run_validation(client,workflow)
    report=result['report'];summary=report['summary']
    assert report['run_metadata']['strategy']['parameters']==dict(green_bar_count=3,hold_minutes=20,contracts=1)
    assert report['run_metadata']['selection']['row_count']==24
    assert report['summary']['trades_taken']==6
    for key,expected in [('total_net_pnl',78),('total_gross_pnl',90),('total_commissions',12),('total_slippage_cost',30),('final_equity',10078),('max_drawdown_amount',37)]:
        assert float(summary[key])==expected
    trades=client.get('/api/backtests/'+report['id']+'/trades').json()['items']
    assert [float(t['net_pnl']) for t in trades]==[3,43,-37,13,23,33]
    assert [s['trade']['trade_number'] for s in result['trade_samples']]==[1,6,2,3,4]
    assert [s['reasons'] for s in result['trade_samples']]==[['First trade'],['Last trade'],['Biggest win'],['Biggest loss'],['Shortest duration']]
    assert all(float(t['entry_fill_price'])==100.25 for t in trades)
    assert 'automatic_prop_analysis' not in report['run_metadata']
    assert client.post(prefix+'/confirm',json={'revision':0}).status_code==409
    request=checks(result);request['trade_correctness']['4']=False
    saved=client.patch(prefix+'/review',json=request).json()
    assert client.post(prefix+'/confirm',json={'revision':saved['review']['revision']}).status_code==409
    assert client.patch(prefix+'/review',json=request).status_code==409 # stale tab
    request=checks(saved);request['metric_checks'].pop(next(iter(request['metric_checks'])))
    assert client.patch(prefix+'/review',json=request).status_code==409
    request=checks(saved);request['trade_parity']['4']='true'
    assert client.patch(prefix+'/review',json=request).status_code==422
    saved=client.patch(prefix+'/review',json=checks(saved)).json()
    confirmed=client.post(prefix+'/confirm',json={'revision':saved['review']['revision']}).json()
    assert confirmed['status']=='passed' and confirmed['review']['confirmed_at_utc']
    assert client.get(prefix+'/phases/is_broad').json()['phase']['implemented'] is False
    assert client.post(prefix+'/phases/is_broad/run').status_code==409
    assert client.get(prefix+'/phases/is_narrow').status_code==409
    assert client.get(prefix+'/phases/oos').status_code==409
    assert client.get(prefix+'/phases/unknown').status_code==404
    assert client.patch(prefix+'/review',json=checks(confirmed,False)).status_code==409
    before={p:sha256(p.read_bytes()).hexdigest() for p in client.app.state.runs.root.joinpath(report['id']).iterdir() if p.is_file()}
    assert client.post(prefix+'/run').json()['run_id']==report['id']
    assert client.get('/api/backtests').json()['total']==1
    assert client.delete('/api/backtests/'+report['id']).status_code==409
    with TestClient(create_app(client.app.state.store.path)) as reopened:
        assert reopened.get(prefix).json()['review']==confirmed['review']
        assert reopened.get(prefix+'/download').json()['report']==report
    assert before=={p:sha256(p.read_bytes()).hexdigest() for p in before}
    assert client.get('/api/backtests/research-plan',params={'dataset_id':dataset['id'],'strategy_id':body['strategy_id']}).json()['used']==0


def test_overlapping_samples_ties_missing_signs_and_zero_trade_rejection(client):
    dataset,body,workflow=create_workflow(client)
    result=run_validation(client,workflow)
    trade=result['trade_samples'][0]['trade']
    rows=sample_trades([trade])
    assert len(rows)==1 and rows[0]['reasons']==['First trade','Last trade','Biggest win','Shortest duration']
    assert sample_trades([dict(trade,net_pnl='-1')])[0]['reasons']==['First trade','Last trade','Biggest loss','Shortest duration']
    assert sample_trades([dict(trade,net_pnl='0')])[0]['reasons']==['First trade','Last trade','Shortest duration']
    tied=[dict(trade,trade_number=i) for i in (5,2)]
    assert sample_trades(tied)[0]['trade']['trade_number']==2
    assert sample_trades([])==[]
    flat=mechanics_csv().decode().splitlines();flat=[flat[0]]+[','.join([*line.split(',')[:2], '100','100','100','100',*line.split(',')[6:]]) for line in flat[1:]]
    _,_,empty=create_workflow(client, ('\n'.join(flat)+'\n').encode())
    result=run_validation(client,empty)
    assert result['report']['summary']['trades_taken']==0 and result['trade_samples']==[]
    prefix='/api/campaign-workflows/'+empty['id']
    saved=client.patch(prefix+'/review',json=checks(result)).json()
    response=client.post(prefix+'/confirm',json={'revision':saved['review']['revision']})
    assert response.status_code==409 and 'Zero-trade' in response.text


def test_binding_rejections_code_drift_corruption_and_interrupted_recovery(client, monkeypatch):
    dataset,body,workflow=create_workflow(client)
    prefix='/api/campaign-workflows/'+workflow['id']
    bad=dict(body,strategy_parameters={'contracts':99})
    assert client.post('/api/campaign-workflows',json=bad).status_code==422
    from alphaquest import campaign_workflow
    original=campaign_workflow.engine_identity
    monkeypatch.setattr(campaign_workflow,'engine_identity',lambda:'changed')
    assert client.post(prefix+'/run').status_code==409
    monkeypatch.setattr(campaign_workflow,'engine_identity',original)
    store=client.app.state.campaign_workflows
    with ThreadPoolExecutor(2) as workers:
        reserved=list(workers.map(lambda _:store.reserve(workflow['id']),range(2)))
    assert sum(fresh for _,fresh in reserved)==1
    restarted=CampaignWorkflowStore(client.app.state.runs)
    assert restarted.get(workflow['id'])['status']=='failed'
    result=run_validation(client,workflow)
    with client.app.state.runs.connect() as db:
        raw=db.execute('SELECT payload FROM run_trades WHERE run_id=? AND ordinal=0',(result['run_id'],)).fetchone()[0]
        modified=json.loads(raw);modified['net_pnl']='999'
        db.execute('UPDATE run_trades SET payload=? WHERE run_id=? AND ordinal=0',(json.dumps(modified),result['run_id']))
    assert client.get(prefix).status_code==409
    assert client.post(prefix+'/confirm',json={'revision':0}).status_code==409


def test_changed_instrument_missing_source_and_unsupported_defaults_fail_closed(client):
    dataset,body,workflow=create_workflow(client)
    prefix='/api/campaign-workflows/'+workflow['id']
    for strategy in ['twin_continuation','vwap_pullback_risk_sizing','unknown']:
        assert client.post('/api/campaign-workflows',json=dict(body,strategy_id=strategy)).status_code==422
    assert client.patch('/api/datasets/'+dataset['id']+'/instrument-settings',json={'tick_size':'.5','point_value':'10'}).status_code==200
    assert client.post(prefix+'/run').status_code==409
    assert client.post('/api/campaign-workflows',json=body).json()['id']!=workflow['id']
    assert client.delete('/api/datasets/'+dataset['id']).status_code==204
    assert client.post(prefix+'/run').status_code==409
    assert client.get('/api/backtests').json()['total']==0


def test_saved_result_recovers_after_lost_response_and_artifact_tamper_blocks_review(client):
    _,_,workflow=create_workflow(client)
    result=run_validation(client,workflow)
    prefix='/api/campaign-workflows/'+workflow['id']
    # Simulate a crash after native report publication but before saving review rows.
    with client.app.state.runs.connect() as db:
        db.execute('DELETE FROM campaign_workflow_runs WHERE workflow_id=?',(workflow['id'],))
        result['status']='running';result['review']=None
        saved=client.app.state.campaign_workflows.raw(workflow['id'],db)
        saved.update(status='running',review=None)
        client.app.state.campaign_workflows.write(db,saved)
    recovered=client.get(prefix).json()
    assert recovered['status']=='review_required' and recovered['run_id']==result['run_id']
    assert client.get(prefix).json()['review']==recovered['review']
    assert client.get('/api/backtests').json()['total']==1
    path=client.app.state.runs.root/result['run_id']/'trades.csv'
    path.write_bytes(path.read_bytes()+b'\n')
    assert client.get(prefix).status_code==409
    assert client.post(prefix+'/confirm',json={'revision':0}).status_code==409


def test_run_failure_is_saved_and_retry_uses_same_workflow(client, monkeypatch):
    _,_,workflow=create_workflow(client)
    from alphaquest import backtest_api
    original=backtest_api.execute_backtest
    async def fail(*args,**kwargs):
        from fastapi import HTTPException
        raise HTTPException(422,'Synthetic validation failure')
    monkeypatch.setattr(backtest_api,'execute_backtest',fail)
    prefix='/api/campaign-workflows/'+workflow['id']
    assert client.post(prefix+'/run').status_code==422
    assert client.get(prefix).json()['status']=='failed'
    assert 'Synthetic validation failure' in client.get(prefix).json()['error']
    monkeypatch.setattr(backtest_api,'execute_backtest',original)
    assert run_validation(client,workflow)['status']=='review_required'
