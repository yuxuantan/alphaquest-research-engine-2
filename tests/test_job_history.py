"""Focused job metadata, retry history, paging and legacy backfill contracts."""
import json
import time
from uuid import uuid4
from hashlib import sha256

from alphaquest.campaign_workflow import CampaignWorkflowStore
from alphaquest.job_history import public_job
from test_research_workflow import client
from test_campaign_mechanics import create_workflow, run_validation


def test_batch_history_exposes_existing_worker_progress_without_recalculation():
    job_id=uuid4().hex
    payload=dict(stage='running_trials',completed_trials=0,total_trials=16,worker_count=4,
                 active_trials=[dict(trial=1,stage='cost_stress: replaying',bars_processed=1200,total_bars=2400)])
    row=('backtest_batch',job_id,'2026-11-11T00:00:00+00:00','running','synthetic_strategy','synthetic_dataset',json.dumps(payload))
    item=public_job(row,None)
    assert item['progress']==dict(stage='running_trials',completed=0,total=16,unit='trials',worker_count=4,
                                  active_trials=payload['active_trials'])
    assert item['stop_url']==f'/api/backtests/batches/{job_id}/cancel'


def test_failed_attempt_is_retained_after_success_and_filters_are_bounded(client,monkeypatch):
    _,_,workflow=create_workflow(client)
    assert client.get('/api/jobs').json()['total']==0 # setup is not an executed job
    from alphaquest import backtest_api
    original=backtest_api.execute_backtest
    async def fail(*args,**kwargs):
        from fastapi import HTTPException
        raise HTTPException(422,'SYNTHETIC recorded failure')
    monkeypatch.setattr(backtest_api,'execute_backtest',fail)
    prefix='/api/campaign-workflows/'+workflow['id']
    assert client.post(prefix+'/run').status_code==422
    first=client.get('/api/jobs').json()['items'][0]
    assert first['status']=='failed' and first['error']=='SYNTHETIC recorded failure'
    monkeypatch.setattr(backtest_api,'execute_backtest',original)
    result=run_validation(client,workflow)
    rows=client.get('/api/jobs').json()
    assert rows['total']==2
    completed=next(j for j in rows['items'] if j['status']=='complete')
    assert completed['id']==result['run_id'] and completed['review_status']=='review_required'
    assert completed['progress']==dict(stage='complete',completed=24,total=24,unit='bars')
    assert completed['started_at_utc'] and completed['finished_at_utc']
    assert len(completed['links'])==2
    assert client.get('/api/jobs?status=active').json()['total']==0
    assert client.get('/api/jobs?status=completed').json()['total']==1
    assert client.get('/api/jobs?status=attention').json()['items'][0]['id']==first['id']
    for offset in (0,1):
        assert client.get('/api/jobs',params={'limit':1,'offset':offset}).json()['items'][0]['id']==rows['items'][offset]['id']
    assert client.get('/api/jobs',params={'q':result['run_id']}).json()['total']==1
    assert client.get('/api/jobs',params={'q':"' OR 1=1 --"}).json()['total']==0
    for query in ['status=unknown','kind=unknown','limit=0','offset=-1']:
        assert client.get('/api/jobs?'+query).status_code==422
    assert client.get('/api/jobs/mechanic_validation/'+uuid4().hex).status_code==404
    assert client.get('/api/jobs/mechanic_validation/'+first['id']).json()['error']==first['error']


def test_catalogues_are_combined_without_duplicate_trials_or_report_mutation(client):
    dataset,body,workflow=create_workflow(client)
    validation=run_validation(client,workflow)
    request=dict(body,method='exhaustive',workers=1,automatic_prop=False,parameter_ranges={
        'green_bar_count':dict(start=3,end=3,step=0),'hold_minutes':dict(start=20,end=20,step=0),'contracts':dict(start=1,end=2,step=1)})
    response=client.post('/api/backtests',json=request)
    assert response.status_code==202,response.text
    batch=response.json()['id'];deadline=time.monotonic()+15
    while True:
        job=client.get('/api/backtests/batches/'+batch).json()
        if job['status'] not in ('queued','running'):break
        assert time.monotonic()<deadline;time.sleep(.01)
    assert job['status']=='complete',job
    standalone=client.post('/api/backtests',json=dict(body,strategy_parameters=dict(green_bar_count=3,hold_minutes=20,contracts=3)))
    assert standalone.status_code==201,standalone.text
    prop_id=uuid4().hex
    with client.app.state.prop_analyses.connect() as db:
        db.execute('INSERT INTO analyses VALUES (?,?,?,?,?,?,?)',(prop_id,'SYNTHETIC metadata-only failure',validation['run_id'],'2026-11-10T00:00:00+00:00','error','Interrupted','SYNTHETIC interrupted analysis'))
    files={p:sha256(p.read_bytes()).hexdigest() for p in client.app.state.runs.root.glob('*/*') if p.is_file()}
    result=client.get('/api/jobs').json()
    assert result['total']==6 # includes the standalone report's two automatic prop checks
    assert {j['kind'] for j in result['items']}=={'mechanic_validation','backtest_batch','backtest','prop_analysis'}
    batch_row=client.get('/api/jobs/backtest_batch/'+batch).json()
    assert batch_row['progress']['completed']==batch_row['progress']['total']==2
    assert batch_row['links'][0]['href']=='#backtests/batches/'+batch
    assert client.get('/api/jobs/prop_analysis/'+prop_id).json()['status']=='failed'
    assert client.get('/api/jobs?kind=backtest').json()['items'][0]['id']==standalone.json()['id']
    assert files=={p:sha256(p.read_bytes()).hexdigest() for p in files}


def test_old_validation_backfill_and_interruption_do_not_invent_start_times(client):
    _,_,workflow=create_workflow(client)
    result=run_validation(client,workflow)
    original_review=result['review']
    with client.app.state.runs.connect() as db:
        db.execute('DELETE FROM mechanic_job_attempts WHERE id=?',(result['run_id'],))
    CampaignWorkflowStore(client.app.state.runs)
    item=client.get('/api/jobs/mechanic_validation/'+result['run_id']).json()
    assert item['status']=='complete' and item['started_at_utc'] is None and item['finished_at_utc'] is None
    assert item['progress']['completed']==24
    assert client.app.state.campaign_workflows.get(workflow['id'])['review']==original_review
    body=dict(result['declaration'])
    # Separate declaration to exercise interrupted-attempt recovery.
    saved=client.app.state.campaign_workflows.create(dict(body,version='SYNTHETIC interrupted metadata'))
    running,fresh=client.app.state.campaign_workflows.reserve(saved['id']);assert fresh
    CampaignWorkflowStore(client.app.state.runs)
    item=client.get('/api/jobs/mechanic_validation/'+running['run_id']).json()
    assert item['status']=='interrupted' and 'restarted' in item['error']
