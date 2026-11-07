"""Authoritative current policy -> prospective synthetic scope -> normal reports."""
from copy import deepcopy
from datetime import timedelta
from decimal import Decimal
import json
from uuid import uuid4

from fastapi.testclient import TestClient
from alphaquest.app import create_app
from alphaquest.forward_reconcile import stamp, digest
from tests.test_forward_api import current_policy, wait_monitor
from tests.forward_comparison_fixtures import prospective_observation,coverage_events_for_binding
from tests.test_forward_reconcile import fixture
from alphaquest.forward_comparison import iso


def observation_body(client,campaign_id,application,package):
    plan,created=prospective_observation(application,package)
    return dict(monitor_id=uuid4().hex,name='SYNTHETIC complete funded horizon; deterministic receiver clock',observation_kind='synthetic_harness',
        policy_binding=dict(campaign_id=campaign_id,application_id=application['application_id'],phase='funded',package_sha256=package['package_sha256']),
        source=dict(source_id='synthetic-full-horizon',label='SYNTHETIC independent events and deterministic harness receiver clock',receiver_clock_provenance='synthetic_harness_clock'),
        instrument=dict(symbol='MNQ',tick_size='.25',point_value='2'),thresholds=dict(maximum_position_contracts=3),
        forecast_observation=plan),created


def coverage_events(checked,*,complete=False):
    return coverage_events_for_binding(checked['forecast_observation_plan'],complete=complete)


def launch_comparison(client,campaign_id,application,package,*,complete=True):
    body,created=observation_body(client,campaign_id,application,package)
    owner=client.app.state.forward_monitors;owner.clock=lambda:created
    response=client.post('/api/forward-monitors/check',json=body);assert response.status_code==200,response.text
    checked=response.json();assert checked['forecast_observation_plan']['original_window']['first_session']=='2026-01-27'
    response=client.post('/api/forward-monitors',json=body);assert response.status_code==201,response.text
    base='/api/forward-monitors/'+body['monitor_id'];events,asof=coverage_events(checked,complete=complete)
    # Independent real entry/exit records exercise fixed sizing conformance,
    # rather than relying solely on a vacuous no-entry cash observation.
    start=stamp(checked['forecast_observation_plan']['coverage_start_utc']);trades=[]
    for index,event in enumerate(fixture()[1:14],1):
        event=deepcopy(event);event['event_id']='trade-'+event['event_id']
        event['event_time_utc']=iso(start+timedelta(hours=1,seconds=index))
        if event.get('quantity')==2:event['quantity']=3
        if event['kind']=='fill':event['commission']='1.5'
        if event['kind']=='position':event['account_balance']='50003'
        trades.append(event)
    events=events[:4]+trades+events[4:]
    for index,event in enumerate(events,1):
        event['source_sequence']=index
        if event['kind']=='position' and event.get('account_balance')=='49950':event['account_balance']='49953'
    received=(stamp(asof)-timedelta(seconds=1)).isoformat().replace('+00:00','Z');owner.clock=lambda:received
    payload=json.dumps(dict(batch_id=uuid4().hex,source_id=body['source']['source_id'],events=events)).encode()
    response=client.post(base+'/events/check',content=payload);assert response.status_code==200,response.text
    response=client.post(base+'/events',content=payload);assert response.status_code==201,response.text
    assert client.post(base+'/events',content=payload).json()['new_event_count']==0
    job=client.post(base+'/assess',json=dict(request_id=uuid4().hex,as_of_utc=asof));assert job.status_code==200,job.text
    report,raw=wait_monitor(client,job.json()['id'])
    return body,checked,events,asof,report,raw


def test_current_policy_complete_supplied_scope_correction_and_reopen(tmp_path,monkeypatch):
    with TestClient(create_app(tmp_path/'datasets.sqlite3')) as client:
        _,campaign,application,package=current_policy(client)
        body,checked,events,asof,partial,original=launch_comparison(client,campaign,application,package,complete=False)
        assert partial['calculations']['forecast_comparison']['status']=='NOT_COMPARABLE'
        base='/api/forward-monitors/'+body['monitor_id'];correction=deepcopy(events[-1])
        correction.update(event_id='coverage-completed',supersedes_event_id=events[-1]['event_id'],correction_reason='Supplier completed and checked the full synthetic interval',coverage='complete')
        raw=json.dumps(dict(batch_id=uuid4().hex,source_id=body['source']['source_id'],events=[correction])).encode()
        response=client.post(base+'/events',content=raw);assert response.status_code==201,response.text
        response=client.post(base+'/assess',json=dict(request_id=uuid4().hex,as_of_utc=asof));assert response.status_code==200,response.text
        report,report_bytes=wait_monitor(client,response.json()['id']);comparison=report['calculations']['forecast_comparison']
        assert comparison['status']=='SYNTHETIC_SCOPE_COMPARISON',comparison['reasons']
        assert Decimal(comparison['metrics']['expected_trader_receipts'])==1500
        assert Decimal(comparison['metrics']['observed_trader_receipts'])==50
        assert Decimal(comparison['metrics']['observed_minus_expected'])==-1450
        assert Decimal(report['calculations']['metrics']['gross_realized_pnl'])==6
        assert Decimal(report['calculations']['metrics']['commissions'])==3
        assert Decimal(report['calculations']['metrics']['net_realized_pnl'])==3
        assert report['calculations']['policy_conformance']['status']=='MATCH'
        assert report['calculations']['policy_conformance']['decisions'][0]['recalculated']['quantity']==3
        assert not report['calculations']['policy_conformance']['broker_implementation_verified']
        assert comparison['coverage']['receiver_clock_provenance']=='synthetic_harness_clock'
        assert not comparison['coverage']['independently_verified'] and comparison['observation_count']==1
        assert client.get('/api/prop-analyses/'+partial['id']+'/downloads/report.json').content==original
        assert client.delete('/api/prop-analyses/'+report['id']).status_code==409
        wrong=deepcopy(body);wrong['forecast_observation']['open_sessions'].pop()
        assert client.post('/api/forward-monitors/check',json=wrong).status_code==422
        paper=deepcopy(body);paper['observation_kind']='paper'
        assert client.post('/api/forward-monitors/check',json=paper).status_code==422
        monitor_id=body['monitor_id'];report_id=report['id']
    def forbidden(*a,**k):raise AssertionError('Saved comparison read recalculated or reselected')
    monkeypatch.setattr('alphaquest.forward_monitoring.reconcile',forbidden)
    monkeypatch.setattr('alphaquest.forward_monitoring.compare_observation',forbidden)
    with TestClient(create_app(tmp_path/'datasets.sqlite3')) as client:
        assert client.get('/api/prop-analyses/'+report_id+'/downloads/report.json').content==report_bytes
        assert client.get('/api/forward-monitors/'+monitor_id).json()['last_completed_snapshot_sha256']==digest(report)
