from copy import deepcopy
import json
from threading import Event
from uuid import uuid4
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from alphaquest.prop.store import AnalysisStore
from alphaquest.forward_contracts import Assessment,Control
from alphaquest.forward_reconcile import digest
from alphaquest.forward_monitoring import ForwardStore,Conflict,parse_batch
from alphaquest.forward_api import router
from tests.test_forward_reconcile import declaration,fixture,time


def raw(events=None,*,batch_id=None):
    return json.dumps(dict(schema_version='aq-forward-events-v1',batch_id=batch_id or uuid4().hex,
        source_id='fixture',events=events if events is not None else fixture())).encode()


@pytest.fixture
def workspace(tmp_path):
    analyses=AnalysisStore(tmp_path);exposures=[]
    def expose(*args):
        exposures.append(args)
        return dict(status='RECORDED',protected_conflicts=[])
    value=ForwardStore(analyses,record_exposure=expose,clock=lambda:time(20))
    yield value,exposures
    analyses.close()


def wait(store,id):
    # Queue a sentinel on the ordinary single worker; no nested task waits.
    store.analyses.worker.submit(lambda:None).result(timeout=10)
    result=store.analyses.get(id)
    assert result['status']=='complete',result
    return store.report(id)


def test_exact_retry_correction_immutable_receive_clock_and_bytes(workspace):
    store,exposures=workspace;d=declaration();store.create(d);data=raw()
    first=store.append(d.monitor_id,data);store.clock=lambda:time(22)
    retry=store.append(d.monitor_id,data)
    assert first['new_event_count']==17 and retry['new_event_count']==0 and retry['existing_batch']
    alternate=store.append(d.monitor_id,raw())
    assert alternate['idempotent_event_count']==17
    assert {row['received_at_utc'] for row in store.events(d.monitor_id)['records']}=={time(20)}
    with store.analyses.connect() as db:
        assert db.execute('SELECT raw FROM forward_event_batches WHERE batch_id=?',(first['batch_id'],)).fetchone()[0]==data
    changed=json.loads(data);changed['events'][5]['price']='101'
    with pytest.raises(Conflict,match='original bytes'):store.append(d.monitor_id,json.dumps(changed).encode())
    with pytest.raises(Conflict,match='immutable payload'):store.append(d.monitor_id,raw(changed['events']))
    assert len(exposures)==5 # conflict does not erase already supplied observation access
    correction=deepcopy(fixture()[11]);correction.update(event_id='corrected',supersedes_event_id='event-11',correction_reason='Source execution correction',price='100.5')
    store.append(d.monitor_id,raw([correction]))
    assert store.events(d.monitor_id)['total']==18


def test_real_analysis_report_reopen_without_reconcile_and_correction_snapshot(workspace,monkeypatch):
    store,_=workspace;d=declaration();store.create(d);store.append(d.monitor_id,raw())
    request=Assessment(request_id=uuid4().hex,as_of_utc=time(25));job=store.submit(d.monitor_id,request);before=wait(store,job['id'])
    assert before['calculations']['metrics']['net_realized_pnl']=='2'
    assert before['model_version']=='forward-monitor-v1'
    assert {'events.jsonl','reconciliation.json','policy_snapshot.json'}<=set(before['files'])
    report_bytes=(store.analyses.root/job['id']/'report.json').read_bytes()
    correction=deepcopy(fixture()[11]);correction.update(event_id='corrected',supersedes_event_id='event-11',correction_reason='Correct execution',price='100.5')
    store.append(d.monitor_id,raw([correction]));job2=store.submit(d.monitor_id,Assessment(request_id=uuid4().hex,as_of_utc=time(25)))
    second=wait(store,job2['id'])
    assert second['calculations']['metrics']['net_realized_pnl']=='0.0'
    assert (store.analyses.root/job['id']/'report.json').read_bytes()==report_bytes
    def forbidden(*args,**kwargs):raise AssertionError('Saved read recalculated')
    monkeypatch.setattr('alphaquest.forward_monitoring.reconcile',forbidden)
    reopened=ForwardStore(store.analyses,record_exposure=store.record_exposure)
    assert reopened.report(job['id'])==before
    assert reopened.submit(d.monitor_id,request)['id']==job['id']
    assert reopened.get(d.monitor_id)['event_count']==18


def test_control_pause_during_publication_is_retained_and_resume_requires_exact_current_report(workspace,monkeypatch):
    store,_=workspace;d=declaration();store.create(d);store.append(d.monitor_id,raw())
    import alphaquest.forward_monitoring as module
    original=module.seal_report;entered=Event();release=Event()
    def paused(*args,**kwargs):
        original(*args,**kwargs);entered.set();assert release.wait(5)
    monkeypatch.setattr(module,'seal_report',paused)
    job=store.submit(d.monitor_id,Assessment(request_id=uuid4().hex,as_of_utc=time(25)))
    assert entered.wait(5)
    store.control(d.monitor_id,Control(request_id=uuid4().hex,action='pause',reason='Operator review'))
    release.set();report=wait(store,job['id'])
    assert store.get(d.monitor_id)['advisory_state']=='PAUSED'
    with pytest.raises(Conflict,match='exact latest'):
        store.control(d.monitor_id,Control(request_id=uuid4().hex,action='resume',reason='Reviewed',acknowledged_snapshot_sha256='0'*64))
    store.control(d.monitor_id,Control(request_id=uuid4().hex,action='resume',reason='No observed blocker remains',acknowledged_snapshot_sha256=digest(report)))
    assert store.get(d.monitor_id)['advisory_state']=='ACTIVE'
    store.control(d.monitor_id,Control(request_id=uuid4().hex,action='retire',reason='Retired observed policy'))
    with pytest.raises(Conflict,match='retired'):store.control(d.monitor_id,Control(request_id=uuid4().hex,action='pause',reason='No reactivation'))


def test_duplicate_keys_and_unknown_money_reject_before_event_write(workspace):
    store,_=workspace;d=declaration();store.create(d)
    with pytest.raises(ValueError,match='Duplicate JSON'):parse_batch(b'{"source_id":"a","source_id":"b"}')
    value=fixture();value[5]['price']='1e3'
    with pytest.raises(ValueError):store.append(d.monitor_id,raw(value))
    assert store.events(d.monitor_id)['total']==0


def test_normal_router_status_codes_and_preserved_event_provenance(workspace):
    store,_=workspace;app=FastAPI();app.state.forward_monitors=store;app.include_router(router);d=declaration()
    with TestClient(app) as client:
        assert client.get('/api/forward-monitors/defaults').status_code==200
        assert client.post('/api/forward-monitors/check',json=d.model_dump(mode='json')).status_code==200
        assert client.post('/api/forward-monitors',json=d.model_dump(mode='json')).status_code==201
        assert client.post('/api/forward-monitors',json=d.model_dump(mode='json')).status_code==200
        base='/api/forward-monitors/'+d.monitor_id;data=raw()
        checked=client.post(base+'/events/check',content=data);assert checked.status_code==200
        assert client.get(base+'/events').json()['total']==0
        assert client.post(base+'/events',content=data).status_code==201
        assert client.post(base+'/events',content=data).status_code==200
        wrong=json.loads(data);wrong['events'][5]['quantity']=3
        assert client.post(base+'/events',json=wrong).status_code==409
        job=client.post(base+'/assess',json=dict(request_id=uuid4().hex,as_of_utc=time(25)))
        assert job.status_code==200;wait(store,job.json()['id'])
        assert client.get(base).json()['latest_assessment']['status']=='complete'
        assert client.get(base+'/exports/events.jsonl').content.count(b'\n')==17
        assert client.get(base+'/snapshots').json()[0]['id']==job.json()['id']


def test_preserved_historical_incident_needs_acknowledgement_and_does_not_repause(workspace):
    from tests.test_forward_reconcile import records as event_records
    store,_=workspace;d=declaration();store.create(d)
    events=fixture()
    for event in events[6:]:
        n=int(event['event_id'].split('-')[-1]);event['event_time_utc']=time(n+6)
    store.clock=lambda:time(30);store.append(d.monitor_id,raw(events))
    first=wait(store,store.submit(d.monitor_id,Assessment(request_id=uuid4().hex,as_of_utc=time(30)))['id'])
    assert first['calculations']['advisory']['state']=='PAUSED'
    assert 'protective_order_gap' in first['calculations']['advisory']['reasons']
    assert first['calculations']['recovery']['eligible_for_acknowledgement']
    store.control(d.monitor_id,Control(request_id=uuid4().hex,action='resume',reason='Closed protection incident investigated; flat reconciled state and feeds recovered',acknowledged_snapshot_sha256=digest(first)))
    assert store.get(d.monitor_id)['advisory_state']=='WATCH'
    later=wait(store,store.submit(d.monitor_id,Assessment(request_id=uuid4().hex,as_of_utc=time(30)))['id'])
    assert later['calculations']['advisory']['state']=='WATCH'
    assert any(row['code']=='protective_order_gap' and row['acknowledged'] for row in later['calculations']['reconciliation']['issues'])
    assert first['calculations']['metrics']['max_observed_drawdown']==later['calculations']['metrics']['max_observed_drawdown']
    assert store.report(first['id'])==first


@pytest.mark.parametrize('target',['event','raw_batch','monitor'])
def test_tampered_inputs_reject_new_assessment_but_prior_saved_bytes_reopen(workspace,target):
    store,_=workspace;d=declaration();store.create(d);store.append(d.monitor_id,raw())
    original=wait(store,store.submit(d.monitor_id,Assessment(request_id=uuid4().hex,as_of_utc=time(25)))['id'])
    with store.analyses.connect() as db:
        if target=='event':
            db.execute("UPDATE forward_events SET payload=json_set(payload,'$.price','999') WHERE monitor_id=? AND event_id='event-5'",(d.monitor_id,))
        elif target=='raw_batch':db.execute("UPDATE forward_event_batches SET raw=? WHERE monitor_id=?",(b'{}',d.monitor_id))
        else:db.execute("UPDATE forward_monitors SET declaration=json_set(declaration,'$.initial_balance','90000') WHERE id=?",(d.monitor_id,))
    with pytest.raises(Conflict):store.submit(d.monitor_id,Assessment(request_id=uuid4().hex,as_of_utc=time(25)))
    assert store.report(original['id'])==original


def test_report_pins_and_recovery_after_new_events_require_new_snapshot(workspace):
    store,_=workspace;d=declaration();store.create(d);store.append(d.monitor_id,raw())
    report=wait(store,store.submit(d.monitor_id,Assessment(request_id=uuid4().hex,as_of_utc=time(25)))['id'])
    with pytest.raises(ValueError,match='forward'):store.analyses.delete(report['id'])
    store.control(d.monitor_id,Control(request_id=uuid4().hex,action='pause',reason='Review new observation'))
    heartbeat=deepcopy(fixture()[-2]);heartbeat.update(event_id='fresh-heartbeat',event_time_utc=time(26),source_sequence=30)
    store.append(d.monitor_id,raw([heartbeat]))
    with pytest.raises(Conflict,match='New observations'):
        store.control(d.monitor_id,Control(request_id=uuid4().hex,action='resume',reason='Old acknowledgement',acknowledged_snapshot_sha256=digest(report)))


def test_recovery_cannot_use_old_assessment_clock(workspace):
    store,_=workspace;d=declaration();store.create(d);store.append(d.monitor_id,raw())
    report=wait(store,store.submit(d.monitor_id,Assessment(request_id=uuid4().hex,as_of_utc=time(25)))['id'])
    store.clock=lambda:time(300)
    with pytest.raises(Conflict,match='recent assessment'):
        store.control(d.monitor_id,Control(request_id=uuid4().hex,action='resume',reason='Too old to establish current feed health',acknowledged_snapshot_sha256=digest(report)))


def test_catalogue_is_bounded_projection_without_saved_report_reads(workspace,monkeypatch):
    store,_=workspace;d=declaration();store.create(d);store.append(d.monitor_id,raw())
    report=wait(store,store.submit(d.monitor_id,Assessment(request_id=uuid4().hex,as_of_utc=time(25)))['id'])
    def forbidden(*args,**kwargs):pytest.fail('Catalogue opened/validated a full saved report')
    monkeypatch.setattr(store,'report',forbidden)
    monkeypatch.setattr(store.analyses,'fingerprint',forbidden)
    listed=store.list(limit=1,q='independent')
    assert listed['total']==1 and listed['projection_only']
    assert listed['items'][0]['advisory_state']=='ACTIVE'
    assert listed['items'][0]['last_completed_analysis_id']==report['id']
    assert 'policy_snapshot' not in listed['items'][0]
    assert store.list(offset=1)['items']==[]
    with pytest.raises(ValueError):store.list(limit=101)
