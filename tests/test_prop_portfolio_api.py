"""Orchestration boundaries with native analytical fixtures, never portal oracles."""
import json,time
from hashlib import sha256
from uuid import uuid4
import pytest
from alphaquest.prop_portfolio import PortfolioRequest
from alphaquest.prop.adapter import canonical
from test_research_workflow import client
from test_prop_portfolio_core import context


def request_body():
    return dict(request_id=uuid4().hex,selections=[dict(workflow_id=uuid4().hex,oos_job_id=uuid4().hex,monte_carlo_id=uuid4().hex,candidate=1)],
        profile_id='lucidflex-50k',monthly_cap='500',maximum_accounts=1,placements=['separate','shared'],
        evaluation_policy=dict(kind='percentage_risk',risk_percent='.2',reference='initial_configured_capital',maximum_contracts=40),
        funded_policy=dict(kind='percentage_risk',risk_percent='.2',reference='initial_configured_capital',maximum_contracts=40))


def test_declared_risk_and_provider_boundaries():
    body=request_body();assert PortfolioRequest.model_validate(body).evaluation_policy.kind=='percentage_risk'
    for changes in [dict(maximum_accounts=5),dict(placements=['shared','unknown']),dict(monthly_cap='-1'),
                    dict(evaluation_policy=dict(body['evaluation_policy'],maximum_contracts=41)),
                    dict(evaluation_policy=dict(body['evaluation_policy'],risk_percent='0'))]:
        with pytest.raises(ValueError):PortfolioRequest.model_validate(dict(body,**changes))
    with pytest.raises(ValueError):PortfolioRequest.model_validate(dict(body,selections=body['selections']*2))
    # The actual strategy qualification gate still runs before native admission.


def test_native_portfolio_routes_durable_freeze_downloads_pins_and_delete(client,monkeypatch):
    import alphaquest.prop_portfolio as api
    import alphaquest.prop.portfolio_sources as adapter
    from alphaquest.prop.portfolio_search import family
    c=context();source=uuid4().hex;oos=uuid4().hex
    qualified=dict(source_backtest_id=source,oos_report_id=oos,strategy_id='SYNTHETIC-native-analytical-fixture')
    windows={role:dict(start=c['first'],end=c['last']) for role in ['is','oos']}
    def metadata(request,body):return dict(sources=[qualified],windows=windows,allocations=family(1,1,['separate','shared']),allocation_count=3,interpretation='Synthetic analytical fixture, test only')
    monkeypatch.setattr(api,'metadata',metadata)
    monkeypatch.setattr(adapter,'prepare',lambda **kwargs:dict(c,coverage=[]))
    body=request_body();check=client.post('/api/prop-sim/portfolio/check',json=body);assert check.status_code==200,check.text
    response=client.post('/api/prop-sim/portfolio',json=body);assert response.status_code==202,response.text
    parent=response.json();id=parent['id'];aid=parent['portfolio']['analysis_id'];store=client.app.state.prop_analyses
    end=time.monotonic()+100
    while True:
        saved=client.get('/api/prop-sim/'+id).json();job=saved['portfolio']['job']
        if job['status'] not in ['queued','running']:break
        assert time.monotonic()<end,job
        time.sleep(.1)
    assert job['status']=='complete',job.get('error')
    assert client.post('/api/prop-sim/portfolio',json=body).json()['portfolio']['analysis_id']==aid
    report=client.get('/api/prop-sim/portfolio/'+id+'/results');assert report.status_code==200,report.text
    frozen=report.json()['frozen'];expected=frozen.pop('sha256');assert sha256(canonical(frozen).encode()).hexdigest()==expected
    assert frozen['allocation']==dict(placement='separate',counts=[0])
    assert all(r['cash']['net_cash']=='0.00' for r in report.json()['results'].values())
    for filename in ['analysis.zip','report.json','portfolio_frozen.json','combined_cash_ledger.csv','source_checks.json']:
        assert client.get('/api/prop-analyses/'+aid+('/downloads/' if filename in ('analysis.zip','report.json') else '/files/')+filename).status_code==200
    assert client.get('/api/jobs/prop_analysis/'+aid).json()['links'][0]['href']=='#prop-sim?analysis='+id
    assert any(r['kind']=='prop_portfolio' for r in store.source_references(oos))
    with store.connect() as db:
        with pytest.raises(ValueError,match='saved Prop Sim portfolio'):store.deletion_check(db,aid)
    plan=client.get('/api/prop-sim/'+id+'/deletion').json();assert plan['deletable'] and aid in plan['analysis_ids_to_delete']
    response=client.request('DELETE','/api/prop-sim/'+id,json=dict(confirmation_sha256=plan['confirmation_sha256']))
    assert response.status_code==200,response.text
    assert not store.get(aid) and not (store.root/aid).exists()
    assert not store.source_references(oos)
    response=client.post('/api/prop-sim/portfolio',json=body);assert response.status_code==409 and 'deleted' in response.text


def test_queued_stop_explicit_retry_and_attempt_history(client,monkeypatch):
    import alphaquest.prop_portfolio as api
    store=client.app.state.prop_analyses;source=uuid4().hex;oos=uuid4().hex
    checked=dict(sources=[dict(source_backtest_id=source,oos_report_id=oos,strategy_id='SYNTHETIC-queue-fixture')],
        windows=dict(is_=None),allocations=[],allocation_count=0,interpretation='queue-only test')
    monkeypatch.setattr(api,'metadata',lambda *args:checked)
    dispatched=[];monkeypatch.setattr(store.worker,'submit',lambda *args:dispatched.append(args))
    body=request_body();saved=client.post('/api/prop-sim/portfolio',json=body).json();id=saved['id'];first=saved['portfolio']['analysis_id']
    assert len(dispatched)==1 and client.post('/api/prop-sim/portfolio',json=body).json()['portfolio']['analysis_id']==first
    assert not client.get('/api/prop-sim/'+id+'/deletion').json()['deletable']
    response=client.post('/api/prop-sim/'+id+'/cancel');assert response.status_code==200,response.text
    with store.connect() as db:assert db.execute('SELECT stop_requested FROM phase_analysis_control WHERE analysis_id=?',(first,)).fetchone()[0]==1
    store._update(first,'cancelled','Test worker acknowledged stop')
    next=client.post('/api/prop-sim/portfolio',json=body);assert next.status_code==202,next.text
    attempts=next.json()['portfolio']['attempts'];assert attempts[0]==first and len(attempts)==2
    assert next.json()['portfolio']['analysis_id']==attempts[1] and len(dispatched)==2
    assert source in store.active_sources() and oos in store.active_sources()
    store._update(attempts[1],'cancelled','Test worker acknowledged stop')
    plan=client.get('/api/prop-sim/'+id+'/deletion').json();assert set(plan['analysis_ids_to_delete'])==set(attempts)
    assert client.request('DELETE','/api/prop-sim/'+id,json=dict(confirmation_sha256=plan['confirmation_sha256'])).status_code==200
    assert source not in store.active_sources() and oos not in store.active_sources()
