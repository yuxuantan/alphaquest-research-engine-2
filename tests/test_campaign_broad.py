"""IS-only grid arithmetic, profitable selection, immutable carry-forward and boundaries."""
import json
import time
from uuid import uuid4
from hashlib import sha256
from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient
from alphaquest.app import create_app
from test_research_workflow import client
from test_campaign_mechanics import create_workflow,run_validation,checks


def passed_mechanics(client):
    dataset,body,workflow=create_workflow(client)
    result=run_validation(client,workflow);prefix='/api/campaign-workflows/'+workflow['id']
    reviewed=client.patch(prefix+'/review',json=checks(result)).json()
    response=client.post(prefix+'/confirm',json={'revision':reviewed['review']['revision']})
    assert response.status_code==200,response.text
    return dataset,body,response.json()


def broad_grid(green_end=4,hold_end=60,contracts_end=3):
    return dict(workers=1,parameter_ranges={
        'green_bar_count':dict(start=3,end=green_end,step=1 if green_end!=3 else 0),
        'hold_minutes':dict(start=20,end=hold_end,step=20 if hold_end!=20 else 0),
        'contracts':dict(start=1,end=contracts_end,step=1 if contracts_end!=1 else 0)})


def preview_body(client,prefix,grid):
    response=client.post(prefix+'/broad/preview',json=grid);assert response.status_code==200,response.text
    return dict(grid,revision=response.json()['revision'],preview_token=response.json()['preview_token'])


def start_grid(client,prefix,grid):
    body=preview_body(client,prefix,grid)
    response=client.post(prefix+'/broad/run',json=body);assert response.status_code==202,response.text
    return wait_job(client,response.json()['id']),body


def wait_job(client,id):
    deadline=time.monotonic()+20
    while True:
        job=client.get('/api/backtests/batches/'+id).json()
        if job['status'] not in ('queued','running'):break
        assert time.monotonic()<deadline;time.sleep(.01)
    assert job['status']=='complete',job
    return job


def selection(client,prefix,trials,revision=None,job_id=None):
    state=client.get(prefix+'/broad').json()['state']
    return client.patch(prefix+'/broad/selection',json=dict(job_id=job_id or state['job_id'],revision=state['revision'] if revision is None else revision,trials=trials))


def test_grid_uses_fixed_is_costs_rejects_nonprofit_and_freezes_at_most_two(client):
    dataset,body,workflow=create_workflow(client)
    prefix='/api/campaign-workflows/'+workflow['id']
    assert client.post(prefix+'/broad/preview',json=broad_grid()).status_code==409
    assert client.get('/api/backtests/batches').json()['total']==0
    result=run_validation(client,workflow)
    reviewed=client.patch(prefix+'/review',json=checks(result)).json()
    assert client.post(prefix+'/confirm',json={'revision':reviewed['review']['revision']}).status_code==200
    job,request=start_grid(client,prefix,broad_grid())
    assert job['total_trials']==18 and job['request']['automatic_prop'] is False
    response=client.get(prefix+'/broad/results');assert response.status_code==200,response.text
    rows=response.json()['items'];assert len(rows)==18
    assert [float(row['metrics']['total_net_pnl']) for row in rows]==[78,156,234,-81,-162,-243,-21,-42,-63]+[0]*9
    assert [r['trial'] for r in rows if r['qualifies']]==[1,2,3]
    for row in rows:
        record=client.get('/api/backtests/'+row['run_id']).json()
        assert record['run_metadata']['selection']['from_date']=='2026-01-05'
        assert record['run_metadata']['selection']['to_date']=='2026-01-05'
        assert record['execution_settings']==result['declaration']['execution_settings']
        assert record['run_metadata']['research']['workflow_phase']=='is_broad'
        assert 'automatic_prop_analysis' not in record['run_metadata']
    for bad in [[4],[10],[999],[1,1]]:
        assert selection(client,prefix,bad).status_code==409
    assert selection(client,prefix,[1,2,3]).status_code==422
    assert selection(client,prefix,[1],job_id=uuid4().hex).status_code==409
    state=selection(client,prefix,[1]).json()
    assert selection(client,prefix,[2],revision=state['revision']-1).status_code==409
    state=selection(client,prefix,[1,2]).json()
    frozen=client.post(prefix+'/broad/confirm',json={'job_id':job['id'],'revision':state['revision']})
    assert frozen.status_code==200,frozen.text
    frozen=frozen.json();assert [x['total_net_pnl'] for x in frozen['selection']]==['78.00','156.00']
    assert frozen['confirmed_at_utc']
    assert client.get(prefix+'/phases/is_narrow').status_code==200
    assert client.get(prefix+'/phases/oos').status_code==409
    assert selection(client,prefix,[]).status_code==409
    assert client.post(prefix+'/broad/preview',json=broad_grid()).status_code==409
    assert client.post(prefix+'/broad/run',json=request).status_code==409
    assert client.delete('/api/backtests/batches/'+job['id']).status_code==409
    assert client.delete('/api/backtests/'+rows[-1]['run_id']).status_code==409
    assert client.post('/api/backtests/'+rows[0]['run_id']+'/oos',json={'request_id':str(uuid4())}).status_code==409
    downloaded=client.get(prefix+'/broad/download').json()
    before={p:sha256(p.read_bytes()).hexdigest() for p in client.app.state.runs.root.glob('*/*') if p.is_file()}
    with TestClient(create_app(client.app.state.store.path)) as reopened:
        assert reopened.get(prefix+'/broad/download').json()==downloaded
        assert reopened.get('/api/jobs?kind=mechanic_validation').json()['total']==1
        assert reopened.get('/api/jobs?kind=backtest_batch').json()['total']==1
        assert reopened.get(prefix+'/phases/is_narrow').status_code==200
    assert before=={p:sha256(p.read_bytes()).hexdigest() for p in before}


def test_no_profitable_rows_do_not_advance_retries_are_idempotent_and_one_choice_is_enough(client):
    _,_,workflow=passed_mechanics(client);prefix='/api/campaign-workflows/'+workflow['id']
    grid=broad_grid();grid['parameter_ranges']['green_bar_count']=dict(start=4,end=4,step=0)
    body=preview_body(client,prefix,grid)
    with ThreadPoolExecutor(2) as pool:
        responses=list(pool.map(lambda _:client.post(prefix+'/broad/run',json=body),range(2)))
    assert all(r.status_code==202 for r in responses)
    assert len({r.json()['id'] for r in responses})==1
    job=wait_job(client,responses[0].json()['id'])
    assert not any(r['qualifies'] for r in client.get(prefix+'/broad/results').json()['items'])
    state=client.get(prefix+'/broad').json()['state']
    assert client.post(prefix+'/broad/confirm',json=dict(job_id=job['id'],revision=state['revision'])).status_code==409
    assert selection(client,prefix,[1]).status_code==409
    assert client.get(prefix+'/phases/is_narrow').status_code==409
    assert client.post(prefix+'/broad/run',json=body).json()['id']==job['id']
    replacement,_=start_grid(client,prefix,broad_grid(3,20))
    assert replacement['id']!=job['id']
    assert client.get('/api/jobs?kind=backtest_batch').json()['total']==2
    assert client.delete('/api/backtests/batches/'+job['id']).status_code==409
    state=selection(client,prefix,[2]).json()
    confirmed=client.post(prefix+'/broad/confirm',json=dict(job_id=replacement['id'],revision=state['revision'])).json()
    assert len(confirmed['selection'])==1 and confirmed['selection'][0]['parameters']['contracts']==2
    path=client.app.state.runs.root/confirmed['selection'][0]['run_id']/'trades.csv'
    path.write_bytes(path.read_bytes()+b'\n')
    assert client.get(prefix+'/phases/is_narrow').status_code==409
    assert client.get(prefix+'/broad/download').status_code==409


def test_preview_boundaries_and_code_drift_do_not_change_saved_jobs(client,monkeypatch):
    _,_,workflow=passed_mechanics(client);prefix='/api/campaign-workflows/'+workflow['id']
    bad=broad_grid();bad['parameter_ranges']['contracts']['end']=10001
    assert client.post(prefix+'/broad/preview',json=bad).status_code==409
    bad=broad_grid();bad['parameter_ranges']['contracts']['step']='0.5'
    assert client.post(prefix+'/broad/preview',json=bad).status_code==409
    assert client.post(prefix+'/broad/preview',json=dict(broad_grid(),sample_split={})).status_code==422
    body=preview_body(client,prefix,broad_grid(3,20))
    from alphaquest import campaign_broad
    original=campaign_broad.engine_identity
    monkeypatch.setattr(campaign_broad,'engine_identity',lambda:'changed')
    assert client.post(prefix+'/broad/run',json=body).status_code==409
    assert client.get('/api/backtests/batches').json()['total']==0
    monkeypatch.setattr(campaign_broad,'engine_identity',original)
    job=client.post(prefix+'/broad/run',json=body).json();wait_job(client,job['id'])
    state=selection(client,prefix,[1]).json()
    monkeypatch.setattr(campaign_broad,'engine_identity',lambda:'changed')
    assert client.post(prefix+'/broad/confirm',json=dict(job_id=job['id'],revision=state['revision'])).status_code==409
