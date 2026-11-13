"""Stable frozen assessment identity and real API single-job admission."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
import os
from pathlib import Path
import shutil
from threading import Event
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest
from alphaquest.app import create_app
from alphaquest.prop_sim import assessment_identity,current_assessments
from test_prop_sim import qualified_source,body,wait_prop
from test_prop_oos_qualification import daily_csv
from test_prop_evaluation_validation import wait_assessment


def test_identity_ignores_request_clocks_and_base_but_keeps_meaning():
    options=dict(qualification=True,kind='qualification',implementation={'version':'one'},
        policy=dict(rules={'confidence':.95},declared_at_utc='a',declaration_timing='retrospective',policy_sha256='a'),
        base_report={'analysis_id':'a'})
    updated=deepcopy(options);updated['policy'].update(declared_at_utc='b',policy_sha256='b');updated['base_report']={'analysis_id':'b'}
    assert assessment_identity('qualification',None,options)==assessment_identity('qualification',None,updated)
    updated['policy']['rules']['confidence']=.99
    assert assessment_identity('qualification',None,options)!=assessment_identity('qualification',None,updated)
    assert assessment_identity('precision',32,None)!=assessment_identity('precision',64,None)
    assert assessment_identity('oos',None,{'policy':{'policy_sha256':'one'}})!=assessment_identity('oos',None,{'policy':{'policy_sha256':'two'}})


def test_current_cards_preserve_success_and_hide_old_policy_versions(monkeypatch):
    monkeypatch.setattr('alphaquest.prop.oos_qualification.implementation',lambda:{'version':'current'})
    def a(id,kind,status='complete',**options):return dict(request_id=id,analysis_id=id,kind=kind,status=status,report_options=options)
    old=a('old','qualification',qualification=True,implementation={'version':'old'})
    current=a('q','qualification',qualification=True,implementation={'version':'current'})
    failed=a('failed','qualification','error',qualification=True,implementation={'version':'current'})
    policy={'policy_sha256':'v2'}
    assert current_assessments([old,current,failed,a('v1','oos',policy={'policy_sha256':'v1'}),a('v2','oos',policy=policy)],policy)=={'qualification':'q','oos':'v2'}
    forward=a('f','forward_review',qualification=True,implementation={'version':'current'},base_report={'analysis_id':'q'})
    assert current_assessments([current,forward],None)['forward_review']=='f'
    forward['report_options']['base_report']['analysis_id']='old'
    assert 'forward_review' not in current_assessments([current,forward],None)


@pytest.fixture
def qualified_library(tmp_path,monkeypatch):
    root=tmp_path/'library'
    if seed:=os.environ.get('ALPHAQUEST_QUALIFICATION_SEED_LIBRARY'):shutil.copytree(seed,root)
    else:root.mkdir()
    with TestClient(create_app(root/'datasets.sqlite3')) as client:
        sources=client.get('/api/prop-sim/candidates').json()['items']
        if sources:source=sources[0]
        else:
            import test_campaign_broad,test_campaign_narrow,test_campaign_oos
            wait=test_campaign_broad.wait_job
            for module in (test_campaign_broad,test_campaign_narrow,test_campaign_oos):monkeypatch.setattr(module,'wait_job',lambda client,id,timeout=600:wait(client,id,timeout=600))
            _,source=qualified_source(client,daily_csv())
        yield client,source


def test_reuses_running_complete_and_legacy_reports_but_reviews_changed_limits(qualified_library,monkeypatch,tmp_path):
    client,source=qualified_library
    config=dict(body(source),evaluation_minimum_micros=10,evaluation_maximum_micros=10,
        funded_minimum_micros=10,funded_maximum_micros=10,simulations=8,maximum_funded_breach_probability=None)
    checked=client.post('/api/prop-sim/check',json=config);assert checked.status_code==200,checked.text
    launched=client.post('/api/prop-sim',json=config);assert launched.status_code==202,launched.text
    saved=wait_prop(client,launched.json()['id']);phase='funded';prefix=f"/api/prop-sim/{saved['id']}/validation/{phase}"
    report=client.get(f"/api/prop-sim/{saved['id']}/results/{phase}").json()
    chosen=report['calculations']['ranking'][:1]
    assert client.post(prefix+'/freeze',json=dict(candidate_ids=chosen,rationale='SYNTHETIC one-result identity demonstration')).status_code==200
    request_id=uuid4().hex
    initial=client.post(prefix,json=dict(request_id=request_id,kind='qualification'));assert initial.status_code==202,initial.text
    attempt,result=wait_assessment(client,prefix,request_id)
    original=client.app.state.prop_analyses.fingerprint(result['id'])
    count=len(client.get(prefix).json()['assessments'])
    with monkeypatch.context() as guard:
        guard.setattr(client.app.state.prop_analyses,'submit_phase',lambda *a,**k:pytest.fail('Identical request queued another job'))
        with ThreadPoolExecutor(max_workers=4) as pool:
            responses=list(pool.map(lambda _:client.post(prefix,json=dict(request_id=uuid4().hex,kind='qualification')),range(8)))
    assert all(r.status_code==202 and r.json()['request_id']==request_id and r.json()['reused'] for r in responses)
    assert len(client.get(prefix).json()['assessments'])==count
    assert client.app.state.prop_analyses.fingerprint(result['id'])==original
    with monkeypatch.context() as guard:
        guard.setattr(client.app.state.prop_analyses,'fingerprint',lambda id:None)
        assert client.post(prefix,json=dict(request_id=uuid4().hex,kind='qualification')).status_code==409
    # Optional business limits reuse qualification point paths, not another OOS MC run.
    from alphaquest.prop.assessment_review import enrich
    with monkeypatch.context() as guard:
        guard.setattr('alphaquest.prop.funded_optimization.optimize_funded',lambda *a,**k:pytest.fail('Business review reran MC'))
        assert client.post(prefix+'/policy',json=dict(minimum_funded_receipts='1')).status_code==200
        business_id=uuid4().hex
        assert client.post(prefix,json=dict(request_id=business_id,kind='oos')).status_code==202
        _,business=wait_assessment(client,prefix,business_id)
        assert 'prop_qualification' not in business['calculations']['candidates'][0]
        assert business['calculations']['candidates'][0]['paths']==result['calculations']['candidates'][0]['paths']
        policy=client.get(prefix).json()['assessment_policy']
        revision=client.post(prefix+'/policy/revisions',json=dict(minimum_funded_receipts='999999',previous_policy_sha256=policy['policy_sha256'],reason='SYNTHETIC rejection boundary'))
        assert revision.status_code==200,revision.text
        entered,release=Event(),Event()
        def paused(*args,**kwargs):
            entered.set();assert release.wait(45);return enrich(*args,**kwargs)
        guard.setattr('alphaquest.prop.assessment_review.enrich',paused)
        try:
            rid=uuid4().hex
            queued=client.post(prefix,json=dict(request_id=rid,kind='oos'));assert queued.status_code==202,queued.text
            assert entered.wait(15)
            before=len(client.get(prefix).json()['assessments'])
            with ThreadPoolExecutor(max_workers=4) as pool:responses=list(pool.map(lambda _:client.post(prefix,json=dict(request_id=uuid4().hex,kind='oos')),range(8)))
            assert all(r.status_code==202 and r.json()['request_id']==rid and r.json()['reused'] for r in responses)
            assert len(client.get(prefix).json()['assessments'])==before
        finally:release.set()
        _,revised=wait_assessment(client,prefix,rid)
    assert revised['calculations']['candidates'][0]['economic_assessment']['verdict']=='FAIL'
    assert client.app.state.prop_analyses.fingerprint(result['id'])==original
    assert client.get(prefix).json()['current_assessments']['qualification']==request_id
    # Stopped/failed jobs are not valid cache hits, and may be retried explicitly.
    from alphaquest.prop_sim import reusable_assessment
    request=type('Request',(),{'app':client.app})()
    failed=client.app.state.campaigns.save_assessment(dict(request_id=uuid4().hex,campaign_id=saved['campaign_ids'][phase],kind='precision',paths=128,report_options=None,status='cancelled'))
    with client.app.state.prop_analyses.lock:assert reusable_assessment(request,saved['campaign_ids'][phase],'precision',128,None) is None
