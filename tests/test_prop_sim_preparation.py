"""Real process isolation, visible preparation, and unchanged-source cache guards."""
import json
import os
from pathlib import Path
from threading import Event
import time
from types import SimpleNamespace
from uuid import uuid4
import pytest

from test_prop_sim_assessment_reuse import qualified_library
from test_prop_sim import body
from test_prop_sim_automatic import wait_automatic


def wait_preparation(client,id,timeout=180):
    deadline=time.monotonic()+timeout
    while True:
        saved=client.get('/api/prop-sim/'+id).json()
        if saved['preparation']['status'] not in ('queued','running'):return saved
        assert time.monotonic()<deadline,saved
        time.sleep(.05)


def test_real_process_background_preparation_and_complete_automatic_pipeline(qualified_library):
    client,source=qualified_library
    config=dict(body(source),automatic=True,background_prepare=True,simulations=8,
        evaluation_minimum_micros=10,evaluation_maximum_micros=10,
        funded_minimum_micros=10,funded_maximum_micros=10,maximum_funded_breach_probability=None)
    start=time.monotonic();response=client.post('/api/prop-sim',json=config)
    assert response.status_code==202,response.text
    assert time.monotonic()-start<2
    id=response.json()['id']
    prepared=wait_preparation(client,id)
    assert prepared['preparation']['status']=='complete',prepared
    saved=wait_automatic(client,id)
    assert all(s['stage']=='complete' for s in saved['automation']['phases'].values()),saved
    job=client.get('/api/jobs/prop_preparation/'+id)
    assert job.status_code==200 and job.json()['status']=='complete'
    assert job.json()['links'][0]['href']=='#prop-sim?analysis='+id
    assert client.get('/api/prop-sim/candidates').json()['items']
    # Same completed request reopens its canonical reports without preparing again.
    before=client.get('/api/prop-sim/'+id).json()
    repeat=client.post('/api/prop-sim',json=config)
    assert repeat.status_code==202 and repeat.json()['preparation']['status']=='complete'
    assert repeat.json()['campaign_ids']==before['campaign_ids']
    assert repeat.json()['automation']==before['automation']
    with client.app.state.prop_analyses.connect() as db:
        workers=db.execute('SELECT workers FROM analysis_compute WHERE analysis_id IN (?,?)',
            tuple(p['analysis_id'] for p in before['phases'].values())).fetchall()
    assert workers==[(4,),(4,)]



def test_blocked_preparation_is_visible_navigable_idempotent_and_stoppable(qualified_library,monkeypatch):
    client,source=qualified_library
    service=client.app.state.prop_sim_preparation;original=service.execute
    entered,release=Event(),Event();calls=[]
    def blocked(operation,payload,checkpoint=lambda:None):
        if operation=='check':
            calls.append(operation);entered.set();assert release.wait(30);checkpoint()
        return original(operation,payload,checkpoint)
    monkeypatch.setattr(service,'execute',blocked)
    config=dict(body(source),background_prepare=True)
    try:
        response=client.post('/api/prop-sim',json=config);assert response.status_code==202,response.text
        id=response.json()['id'];assert entered.wait(3)
        for url in ('/api/jobs?limit=25','/api/jobs/prop_preparation/'+id,'/api/prop-sim/'+id,'/api/prop-sim/defaults'):
            started=time.monotonic();r=client.get(url);assert r.status_code==200,r.text
            assert time.monotonic()-started<2,url
        assert client.post('/api/prop-sim',json=config).json()['id']==id
        assert calls==['check']
        assert client.get('/api/prop-sim/'+id+'/deletion').json()['deletable'] is False
        start=time.monotonic();stop=client.post('/api/prop-sim/'+id+'/cancel');assert stop.status_code==200
        assert time.monotonic()-start<2
        assert stop.json()['preparation']['stop_requested']
    finally:release.set()
    saved=wait_preparation(client,id)
    assert saved['preparation']['status']=='cancelled'
    assert not saved['campaign_ids']


def test_cache_reuses_only_unchanged_verified_evidence(qualified_library,monkeypatch):
    from alphaquest.prop_sim_preparation import cached,evidence_identity
    client,source=qualified_library;request=SimpleNamespace(app=client.app)
    calls=[]
    selection=dict(source['selection'],_test_cache_scope=uuid4().hex)
    def verified():calls.append(1);return {'selection':source['selection'],'proof':'SYNTHETIC cache arithmetic oracle'}
    first,token=cached(request,'qualified',selection,verified)
    assert cached(request,'qualified',selection,verified)==(first,token)
    assert calls==[1]
    # Mutable numerical progress is unrelated to campaign qualification.
    mc=source['selection']['monte_carlo_id']
    with client.app.state.prop_analyses.connect() as db:db.execute("UPDATE analyses SET progress='metadata only' WHERE id=?",(mc,))
    assert evidence_identity(request,source['selection'])==token
    path=client.app.state.runs.root/source['source_backtest_id']/'trades.csv'
    old=path.read_bytes();stamp=path.stat()
    path.write_bytes(old.replace(b'\n',b'\r',1));os.utime(path,ns=(stamp.st_atime_ns,stamp.st_mtime_ns))
    assert evidence_identity(request,source['selection'])!=token
    cached(request,'qualified',selection,verified)
    assert calls==[1,1]


def test_source_changes_after_process_check_reject_before_publication(qualified_library,monkeypatch):
    client,source=qualified_library;service=client.app.state.prop_sim_preparation;original=service.execute
    path=client.app.state.runs.root/source['source_backtest_id']/'trades.csv'
    def changed(operation,payload,checkpoint=lambda:None):
        result=original(operation,payload,checkpoint)
        if operation=='check':path.write_bytes(path.read_bytes()+b'\n')
        return result
    monkeypatch.setattr(service,'execute',changed)
    response=client.post('/api/prop-sim',json=dict(body(source),background_prepare=True))
    assert response.status_code==202,response.text
    saved=wait_preparation(client,response.json()['id'])
    assert saved['preparation']['status']=='error' and 'changed before queueing' in saved['preparation']['error']
    assert not saved['campaign_ids']
    assert client.get('/api/prop-sim/'+saved['id']+'/deletion').json()['deletable']


def test_queued_preparation_recovers_but_cancelled_preparation_does_not(qualified_library):
    from alphaquest.prop_sim_preparation import PropSimPreparation
    client,source=qualified_library;app=client.app;owner=app.state.prop_sim_preparation
    owner.close()
    first=client.post('/api/prop-sim',json=dict(body(source),background_prepare=True))
    assert first.status_code==202 and first.json()['preparation']['status']=='queued'
    second=client.post('/api/prop-sim',json=dict(body(source),background_prepare=True))
    assert second.status_code==202
    stopped=client.post('/api/prop-sim/'+second.json()['id']+'/cancel')
    assert stopped.json()['preparation']['status']=='cancelled'
    app.state.prop_sim_preparation=PropSimPreparation(app)
    app.state.prop_sim_preparation.recover()
    saved=wait_preparation(client,first.json()['id'])
    assert saved['preparation']['status']=='complete',saved
    assert client.get('/api/prop-sim/'+second.json()['id']).json()['campaign_ids']=={}


def test_configuration_waiters_share_one_thread_and_leave_metadata_requests_free(tmp_path,monkeypatch):
    from alphaquest.app import create_app
    from fastapi.testclient import TestClient
    from concurrent.futures import ThreadPoolExecutor
    entered,release,all_seen=Event(),Event(),Event();seen=[];calls=[]
    app=create_app(tmp_path/'datasets.sqlite3')
    @app.middleware('http')
    async def track(request,call_next):
        if request.url.path=='/api/prop-sim/candidates':
            seen.append(1)
            if len(seen)==10:all_seen.set()
        return await call_next(request)
    with TestClient(app) as client:
        def blocked():
            calls.append(1);entered.set();assert release.wait(20)
            return dict(items=[],unavailable=[])
        monkeypatch.setattr(app.state.prop_sim_preparation,'candidates',blocked)
        with ThreadPoolExecutor(max_workers=10) as pool:
            futures=[pool.submit(client.get,'/api/prop-sim/candidates') for _ in range(10)]
            try:
                assert entered.wait(3) and all_seen.wait(3)
                start=time.monotonic();assert client.get('/api/prop-sim/defaults').status_code==200
                assert client.get('/api/jobs').status_code==200
                assert time.monotonic()-start<2
                assert calls==[1]
            finally:release.set()
            assert all(f.result(timeout=10).status_code==200 for f in futures)


def test_status_poll_does_not_load_large_phase_manifests(qualified_library,monkeypatch):
    client,source=qualified_library
    config=dict(body(source),background_prepare=True,simulations=8,
        evaluation_minimum_micros=10,evaluation_maximum_micros=10,funded_minimum_micros=10,funded_maximum_micros=10)
    response=client.post('/api/prop-sim',json=config);assert response.status_code==202
    id=response.json()['id'];saved=wait_preparation(client,id)
    assert saved['preparation']['status']=='complete',saved
    with monkeypatch.context() as patch:
        patch.setattr(client.app.state.campaigns,'_row',lambda *a:pytest.fail('Status polling loaded a complete phase manifest'))
        result=client.get('/api/prop-sim/'+id)
        assert result.status_code==200 and result.json()['phases']['evaluation']['candidate_count']==1
    with client.app.state.runs.connect() as db:
        plan=db.execute("EXPLAIN QUERY PLAN SELECT id FROM runs r WHERE NOT EXISTS (SELECT 1 FROM optimization_trials t WHERE json_extract(t.payload,'$.run_id')=+r.id)").fetchall()
        assert any('SEARCH t USING INDEX optimization_trial_run_id' in str(tuple(row)) for row in plan)


def test_reader_does_not_recover_active_jobs_and_warms_only_immutable_source_plans(tmp_path,monkeypatch):
    from alphaquest.app import create_app
    from research_fixtures import ResearchClient
    from test_saved_trade_simulation import saved_source_pair
    from alphaquest.prop_sim_preparation import read_context,warm_saved_source_plans
    from alphaquest.prop.saved_trade_simulation import ACCOUNT_MODEL
    from hashlib import sha256
    import alphaquest.prop.source as source_module
    with ResearchClient(create_app(tmp_path/'datasets.sqlite3')) as client:
        source=saved_source_pair(client)
        fake=uuid4().hex;optimization=uuid4().hex
        with client.app.state.prop_analyses.connect() as db:
            db.execute('INSERT INTO analyses VALUES (?,?,?,?,?,?,?)',(fake,'synthetic-read-only-oracle',source['source_backtest_id'],'2026-01-01','running','Synthetic metadata only',None))
        with client.app.state.runs.connect() as db:
            db.execute('INSERT INTO optimizations VALUES (?,?,?)',(optimization,'2026-01-01',json.dumps(dict(id=optimization,status='running'))))
        originals={p:sha256(p.read_bytes()).hexdigest() for id in (source['source_backtest_id'],source['oos_report_id'])
            for p in (client.app.state.runs.root/id).iterdir() if p.is_file()}
        request=read_context(tmp_path)
        assert not hasattr(request.app.state.prop_analyses,'worker')
        assert not hasattr(request.app.state.optimizations,'executor')
        prepare=source_module.prepare_source
        def historical(*a,**kw):
            snapshot,rows=prepare(*a,**kw)
            # Exercise older saved sources via one exact reconstruction. The
            # original catalogue/report is never modified by this test fixture.
            snapshot['backtest'].pop('execution_decisions',None)
            return snapshot,rows
        monkeypatch.setattr(source_module,'prepare_source',historical)
        warm_saved_source_plans(request,dict(source=source,phases=dict(evaluation=dict(request=dict(candidates=[dict(sizing=dict(execution_model=ACCOUNT_MODEL))])))))
        assert all(sha256(p.read_bytes()).hexdigest()==digest for p,digest in originals.items())
        assert request.app.state.prop_analyses.get(fake)['status']=='running'
        assert request.app.state.optimizations.get(optimization)['status']=='running'


def test_unrelated_grid_writes_during_verification_do_not_invalidate_qualified_sources(qualified_library,monkeypatch,tmp_path):
    """Reproduce concurrent catalogue progress with the actual qualification owner."""
    from alphaquest import prop_sim
    from alphaquest.prop_sim_preparation import cached,read_context,evidence_identity
    from alphaquest.replay_cache import ReplayCache
    client,source=qualified_library
    request=read_context(client.app.state.runs.path.parent)
    request.app.state.runs.replay_cache=ReplayCache(tmp_path/'fresh-qualification-cache')
    runs=request.app.state.runs;job=uuid4().hex
    with runs.connect() as db:db.execute('INSERT INTO optimizations VALUES (?,?,?)',(job,'SYNTHETIC',json.dumps(dict(id=job,status='running',progress='0 / 2'))))
    # A different workflow may already be in OOS but have no completed MC.
    # Its bar-progress writes must not spoil the qualified configuration list.
    other_workflow=uuid4().hex
    with runs.connect() as db:
        parent=source['selection']['workflow_id'].replace('-','')
        db.execute('INSERT INTO campaign_workflows SELECT ?,?,strategy_id,dataset_id,payload FROM campaign_workflows WHERE id=?',
            (other_workflow,uuid4().hex,parent))
        db.execute('INSERT INTO campaign_oos_jobs VALUES (?,?,?)',(job,other_workflow,uuid4().hex))
        db.execute('INSERT INTO campaign_oos_state VALUES (?,?)',(other_workflow,job))
    before=evidence_identity(request);calls=[];original=prop_sim._qualified_verified
    def checking(*args):
        value=original(*args);calls.append(1)
        with runs.connect() as db:db.execute("UPDATE optimizations SET payload=? WHERE id=?",(json.dumps(dict(id=job,status='running',progress=f'{len(calls)} / 2')),job))
        return value
    monkeypatch.setattr(prop_sim,'_qualified_verified',checking)
    first,token=cached(request,'candidates',{},lambda:prop_sim.candidates(request))
    assert first['items'] and not first['unavailable'],first
    assert any(i['selection']==source['selection'] for i in first['items'])
    assert calls and token==before==evidence_identity(request)
    count=len(calls)
    assert cached(request,'candidates',{},lambda:pytest.fail('Unchanged evidence should reuse the verified cache'))==(first,token)
    assert len(calls)==count


def test_selected_catalogue_changes_invalidate_qualification_cache(qualified_library):
    from alphaquest.prop_sim_preparation import evidence_identity
    client,source=qualified_library;request=SimpleNamespace(app=client.app);runs=client.app.state.runs
    selection=source['selection'];workflow=selection['workflow_id'].replace('-','')
    checks=[('campaign_workflows','id',workflow,'payload'),('campaign_broad_state','workflow_id',workflow,'payload'),
        ('runs','id',source['source_backtest_id'],'manifest')]
    with runs.connect() as db:
        oos=db.execute('SELECT job_id FROM campaign_oos_state WHERE workflow_id=?',(workflow,)).fetchone()[0]
    checks.append(('optimizations','id',oos,'payload'))
    for table,key,id,field in checks:
        before=evidence_identity(request,selection)
        with runs.connect() as db:
            raw=db.execute(f'SELECT {field} FROM {table} WHERE {key}=?',(id,)).fetchone()[0]
            value=json.loads(raw);value['_SYNTHETIC_source_mutation']=True
            db.execute(f'UPDATE {table} SET {field}=? WHERE {key}=?',(json.dumps(value),id))
        try:assert evidence_identity(request,selection)!=before,table
        finally:
            with runs.connect() as db:db.execute(f'UPDATE {table} SET {field}=? WHERE {key}=?',(raw,id))
        assert evidence_identity(request,selection)==before
    # A changed verification result must never be published into the cache.
    from alphaquest.prop_sim_preparation import cached
    with runs.connect() as db:raw=db.execute('SELECT payload FROM campaign_workflows WHERE id=?',(workflow,)).fetchone()[0]
    def changed():
        value=json.loads(raw);value['_SYNTHETIC_source_mutation']=True
        with runs.connect() as db:db.execute('UPDATE campaign_workflows SET payload=? WHERE id=?',(json.dumps(value),workflow))
        return {'not_publishable':True}
    try:
        with pytest.raises(ValueError,match='evidence changed during verification'):
            cached(request,'qualified',dict(selection,_test_cache_scope=uuid4().hex),changed)
    finally:
        with runs.connect() as db:db.execute('UPDATE campaign_workflows SET payload=? WHERE id=?',(raw,workflow))
