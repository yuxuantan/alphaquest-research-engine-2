"""Removing navigation links never deletes campaigns or execution evidence."""
from copy import deepcopy
from hashlib import sha256
import json
from uuid import uuid4

from fastapi.testclient import TestClient
from alphaquest.app import create_app
from alphaquest.campaign_dataset_links import identity
from test_research_workflow import client
from test_campaign_mechanics import create_workflow,run_validation,mechanics_csv


def preview(client,workflow):
    body=dict(strategy_id=workflow['declaration']['strategy_id'],source=identity(workflow['declaration']['dataset']))
    response=client.post('/api/campaign-dataset-links/preview',json=body)
    assert response.status_code==200,response.text
    return body,response.json()


def remove(client,body,p):
    return client.request('DELETE','/api/campaign-dataset-links',json=dict(body,confirmation_sha256=p['confirmation_sha256']))


def test_remove_retains_results_phase_progress_and_dataset_and_restores_after_reopen(client):
    dataset,config,workflow=create_workflow(client);result=run_validation(client,workflow)
    runs=client.app.state.runs
    path=runs.root/result['run_id'];before={p.name:sha256(p.read_bytes()).hexdigest() for p in path.iterdir() if p.is_file()}
    campaigns=client.get('/api/strategies/library').json()
    jobs=client.get('/api/jobs').json();body,p=preview(client,workflow)
    assert p['retained_workflows']==1 and p['retained_reports']==1
    assert 'Running jobs continue' in p['interpretation']
    response=remove(client,body,p);assert response.status_code==200,response.text
    receipt=response.json();assert receipt['removed']
    assert remove(client,body,p).json()==receipt # idempotent
    assert client.get('/api/datasets/'+dataset['id']).status_code==200
    assert client.get('/api/backtests/'+result['run_id']).json()['id']==result['run_id']
    assert client.get('/api/campaign-workflows/'+workflow['id']).json()==result
    assert client.get('/api/strategies/library').json()==campaigns
    assert client.get('/api/jobs').json()==jobs
    assert before=={p.name:sha256(p.read_bytes()).hexdigest() for p in path.iterdir() if p.is_file()}
    with TestClient(create_app(client.app.state.store.path)) as reopened:
        deleted=reopened.get('/api/campaign-dataset-links',params=dict(strategy_id=body['strategy_id'])).json()['items']
        assert deleted==[receipt]
        assert reopened.post(f"/api/campaign-dataset-links/{body['strategy_id']}/{receipt['source_key']}/restore").json()['restored']
        assert reopened.get('/api/campaign-dataset-links',params=dict(strategy_id=body['strategy_id'])).json()['items']==[]
    assert client.get('/api/campaign-workflows/'+workflow['id']).json()==result


def test_scope_is_one_campaign_source_and_stale_preview_rejects(client):
    uploaded=client.post('/api/datasets',params=dict(filename='SYNTHETIC-link-scope.csv',name='SYNTHETIC shared source',symbol='NQ',source_timezone='UTC',tick_size='.25',point_value='20'),content=mechanics_csv())
    assert uploaded.status_code==201,uploaded.text
    dataset=uploaded.json()
    config=dict(dataset_id=dataset['id'],strategy_id='consecutive_green_hold',sample_split=dict(mode='dates',is_start='2026-01-05',is_end='2026-01-05',oos_start='2026-01-06',oos_end='2026-01-06'),execution_settings=dict(initial_capital='10000',slippage_ticks=1,commission_per_contract_per_side='1'))
    created=client.post('/api/campaign-workflows',json=config);assert created.status_code==201,created.text
    workflow=created.json()
    other=client.post('/api/campaign-workflows',json=dict(config,strategy_id='vwap_pullback_risk_sizing'))
    assert other.status_code==201,other.text
    body,p=preview(client,workflow)
    another=client.post('/api/campaign-workflows',json=dict(config,execution_settings=dict(config['execution_settings'],slippage_ticks=2)))
    assert another.status_code==201 and another.json()['id']!=workflow['id']
    assert remove(client,body,p).status_code==409
    body,p=preview(client,workflow);assert p['retained_workflows']==2
    assert remove(client,body,p).status_code==200
    assert client.get('/api/campaign-dataset-links',params=dict(strategy_id='vwap_pullback_risk_sizing')).json()['items']==[]
    assert len(client.get('/api/strategies/library').json()['items'])>=2
    # Explicitly starting a workflow relinks its source, without erasing progress.
    restored=client.post('/api/campaign-workflows',json=config)
    assert restored.status_code==201 and restored.json()['id']==workflow['id']
    assert client.get('/api/campaign-dataset-links',params=dict(strategy_id=body['strategy_id'])).json()['items']==[]


def test_legacy_saved_run_link_and_missing_or_unconfirmed_targets(client):
    from test_research_workflow import save,start_is
    dataset=save(client);record=start_is(client,dataset)
    body=dict(strategy_id='consecutive_green_hold',source=identity(record['run_metadata']['dataset']))
    p=client.post('/api/campaign-dataset-links/preview',json=body)
    assert p.status_code==200,p.text
    assert p.json()['retained_workflows']==0 and p.json()['retained_reports']==1
    assert remove(client,body,dict(confirmation_sha256='0'*64)).status_code==409
    assert remove(client,body,p.json()).status_code==200
    assert client.get('/api/backtests/'+record['id']).status_code==200
    unknown=deepcopy(body);unknown['source']['sha256']='f'*64
    assert client.post('/api/campaign-dataset-links/preview',json=unknown).status_code==404
    assert remove(client,unknown,p.json()).status_code==404
    # No whole-campaign deletion route is introduced.
    assert client.request('DELETE','/api/campaign-dataset-links',json=dict(strategy_id=body['strategy_id'])).status_code==422


def test_removal_does_not_cancel_active_job_metadata(client):
    _,_,workflow=create_workflow(client)
    job=uuid4().hex
    with client.app.state.runs.connect() as db:
        db.execute("INSERT INTO mechanic_job_attempts VALUES (?,?,?,NULL,NULL,'running',NULL,NULL)",(job,workflow['id'],'2026-11-15T00:00:00Z'))
    body,p=preview(client,workflow);assert remove(client,body,p).status_code==200
    with client.app.state.runs.connect() as db:assert db.execute('SELECT status FROM mechanic_job_attempts WHERE id=?',(job,)).fetchone()[0]=='running'
