"""Independent Monte Carlo arithmetic and the real frozen-family journey."""
import time
from uuid import uuid4

from alphaquest.campaign_monte_carlo import POLICY
from test_research_workflow import client
from test_campaign_oos import frozen_workflow, run_oos


def wait_analysis(client,id):
    deadline=time.monotonic()+30
    while True:
        job=client.app.state.prop_analyses.get(id)
        if job['status'] not in ('queued','running'):break
        assert time.monotonic()<deadline,job
        time.sleep(.02)
    assert job['status']=='complete',job
    return job


def test_full_period_native_sources_reconcile_and_saved_check_never_replays(client,monkeypatch):
    dataset,workflow=frozen_workflow(client)
    base='/api/campaign-workflows/'+workflow['id']+'/oos/monte-carlo'
    assert client.post(base+'/run',json={'job_id':uuid4().hex}).status_code==404
    job,_=run_oos(client,workflow)
    parameters=[i['parameters'] for i in client.get(base.rsplit('/monte-carlo',1)[0]+'/results').json()['items']]
    from alphaquest import optimization_worker
    monkeypatch.setattr(optimization_worker,'compute_trial',lambda *a,**k:(_ for _ in ()).throw(AssertionError('Monte Carlo must not replay native backtests')))
    before=client.app.state.research.status(dataset,'consecutive_green_hold')['used']
    record=client.post(base+'/run',json={'job_id':job['id']})
    assert record.status_code==202,record.text
    id=record.json()['id'];wait_analysis(client,id)
    data=client.get(base,params={'job':job['id']}).json()
    report=data['report']
    assert report['policy']==POLICY and report['total']==4
    assert report['unobserved_split_gap_calendar_days']==0
    assert [c['parameters'] for c in report['candidates']]==parameters
    for candidate in report['candidates']:
        assert candidate['observed']['net_profit']==14040*candidate['parameters']['contracts']
        assert candidate['observed']['closed_trades']==1080
        assert candidate['observed']['days']>=180
        assert candidate['evidence_passed']
        assert len(candidate['scenarios'])==2
        assert all(len(s['checks'])==1 for s in candidate['scenarios'])
        assert all(set(s['artifacts']) for s in candidate['sources'])
    assert client.app.state.research.status(dataset,'consecutive_green_hold')['used']==before
    assert client.app.state.campaign_workflows.get(workflow['id'])['narrow']==workflow['narrow']
    assert client.get('/api/jobs/monte_carlo/'+id).json()['links'][0]['href'].endswith('/oos?job='+job['id'])
    assert client.get('/api/jobs?kind=monte_carlo').json()['total']==1
    assert client.post(base+'/run',json={'job_id':job['id']}).json()['id']==id
    assert client.post(base+'/run',json={'job_id':job['id'],'seed':123}).status_code==422
    for format in ('json','zip','daily','paths'):
        assert client.get(base+'/jobs/'+id+'/download?format='+format).status_code==200
    assert client.delete('/api/prop-analyses/'+id).status_code==409
    # Reopening the actual app preserves the exact report, without Monte Carlo.
    from fastapi.testclient import TestClient
    from alphaquest.app import create_app
    with TestClient(create_app(client.app.state.store.path)) as reopened:
        assert reopened.get(base,params={'job':job['id']}).json()['report']==report
    # Native evidence corruption cannot silently create a new passing assessment.
    native=client.app.state.runs.root/report['candidates'][0]['sources'][1]['run_id']/'strategy_equity_day.csv'
    native.write_bytes(native.read_bytes()+b'\n')
    assert client.post(base+'/run',json={'job_id':job['id']}).status_code==409
    assert client.get(base,params={'job':job['id']}).json()['report']==report # saved snapshot remains inspectable
    path=client.app.state.prop_analyses.root/id/'daily.csv';path.write_text('tampered')
    assert client.get(base,params={'job':job['id']}).status_code==409
    assert client.get(base+'/jobs/'+id+'/download').status_code==409


def test_no_monte_carlo_for_oos_rejected_candidates(client):
    _,workflow=frozen_workflow(client,degraded=True)
    job,_=run_oos(client,workflow)
    base='/api/campaign-workflows/'+workflow['id']+'/oos/monte-carlo'
    response=client.post(base+'/run',json={'job_id':job['id']})
    assert response.status_code==409 and 'No verified OOS-passing' in response.json()['detail']
    assert client.get('/api/jobs?kind=monte_carlo').json()['total']==0
