"""Deterministic IS-only family rules and page-independent automatic execution."""
from copy import deepcopy
import json
import time
from uuid import uuid4
import pytest
from alphaquest.prop_sim_selection import choose


def report(phase,points):
    rows=[]
    for size,a,b in points:
        metrics=dict(cost_per_funded=a,expected_calendar_days_to_funded=b) if phase=='evaluation' else dict(expected_funded_cash_payouts_within_horizon=a)
        rows.append(dict(candidate_id=str(size),status='estimated',feasible=True,metrics=metrics,manifest=dict(configuration=dict(micros=size))))
    return dict(phase=phase,calculations=dict(candidates=rows,frontier=[r['candidate_id'] for r in rows],ranking=[r['candidate_id'] for r in rows]))


def test_evaluation_three_objectives_and_exact_time_boundary():
    result=choose(report('evaluation',[(10,100,50),(20,120,25),(30,160,20),(25,110,25.01)]),'evaluation')
    assert [(r['micros'],r['roles']) for r in result['candidates']]==[(10,['Lowest acquisition cost']),(30,['Fastest funding']),(20,['Lowest cost within 25% of fastest'])]


def test_funded_peak_and_smallest_ninety_five_percent_boundary():
    result=choose(report('funded',[(5,949,0),(10,950,0),(15,970,0),(20,1000,0)]),'funded')
    assert [r['micros'] for r in result['candidates']]==[20,10]


@pytest.mark.parametrize('phase',['evaluation','funded'])
def test_duplicates_and_exact_ties_choose_smaller_size(phase):
    result=choose(report(phase,[(30,100,20),(10,100,20),(20,100,20)]),phase)
    assert len(result['candidates'])==1 and result['candidates'][0]['micros']==10
    assert len(result['candidates'][0]['roles'])==(3 if phase=='evaluation' else 2)


def test_unresolved_and_constraints_excluded_without_blocking_resolved():
    value=report('funded',[(5,10000,0),(10,1000,0),(20,990,0)])
    value['calculations']['candidates'][0]['status']='unresolved'
    value['calculations']['candidates'][2]['feasible']=False
    assert [r['micros'] for r in choose(value,'funded')['candidates']]==[10]
    value['calculations']['ranking']=[]
    assert choose(value,'funded')['status']=='no_eligible_candidates'
    assert choose(report('funded',[(5,0,0)]),'funded')['status']=='no_eligible_candidates'
    assert choose(report('evaluation',[(5,0,10)]),'evaluation')['status']=='selected'


def test_phase_and_is_role_reject_and_rules_do_not_consult_other_phase():
    value=report('evaluation',[(10,100,50),(20,150,20)])
    before=choose(value,'evaluation')
    value['unrelated_funded_and_oos_outcomes']={'winner':10,'cash':99999999}
    assert choose(value,'evaluation')==before
    with pytest.raises(ValueError):choose(value,'funded')
    with pytest.raises(ValueError):choose(value,'unknown')
    value['assessment']={'kind':'oos'}
    with pytest.raises(ValueError):choose(value,'evaluation')


from test_prop_sim_assessment_reuse import qualified_library
from test_prop_sim import body


def wait_automatic(client,id,timeout=180):
    deadline=time.monotonic()+timeout
    while True:
        data=client.get('/api/prop-sim/'+id).json()
        states=data['automation']['phases']
        if all(s['stage'] in ('complete','no_eligible_candidates','error','cancelled') for s in states.values()):return data
        assert time.monotonic()<deadline,data
        time.sleep(.1)


def test_full_pipeline_needs_only_run_preserves_frozen_family_and_reopens(qualified_library,monkeypatch):
    client,source=qualified_library
    config=dict(body(source),automatic=True,evaluation_minimum_micros=9,evaluation_maximum_micros=10,
        funded_minimum_micros=9,funded_maximum_micros=10,simulations=8,maximum_funded_breach_probability=None)
    response=client.post('/api/prop-sim',json=config);assert response.status_code==202,response.text
    saved=wait_automatic(client,response.json()['id'])
    assert all(s['stage']=='complete' for s in saved['automation']['phases'].values()),saved
    store=client.app.state.campaigns;references={}
    for phase in ('evaluation','funded'):
        state=saved['automation']['phases'][phase];campaign=store.get(saved['campaign_ids'][phase])
        assert set(campaign['frozen']['candidate_ids'])=={c['candidate_id'] for c in state['selection']['candidates']}
        attempts=store.assessments(campaign['campaign_id']);assert len(attempts)==1
        r=client.get(f"/api/prop-sim/{saved['id']}/validation/{phase}/"+attempts[0]['request_id']).json()
        assert r['assessment']['prop_sim_review']['automatic_selection']==state['selection']
        assert {x['frozen_candidate_id'] for x in r['calculations']['candidates']}==set(campaign['frozen']['candidate_ids'])
        assert r['calculations']['winner'] is None
        references[phase]=(attempts[0]['analysis_id'],campaign['frozen']['package_sha256'])
    with monkeypatch.context() as guard:
        guard.setattr(client.app.state.prop_analyses,'submit_phase',lambda *a,**k:pytest.fail('Completed automatic run resubmitted'))
        assert client.post('/api/prop-sim',json=config).status_code==202
        client.app.state.prop_sim_automation._advance(saved['id'])
    for phase,(aid,sha) in references.items():
        c=store.get(saved['campaign_ids'][phase]);assert c['frozen']['package_sha256']==sha
        assert store.assessments(c['campaign_id'])[0]['analysis_id']==aid


def test_restart_recovers_after_freeze_and_interrupted_launch_reservation(qualified_library,monkeypatch):
    from fastapi.testclient import TestClient
    from alphaquest.app import create_app
    client,source=qualified_library;owner=client.app.state.prop_sim_automation
    owner.close()
    config=dict(body(source),automatic=True,evaluation_minimum_micros=10,evaluation_maximum_micros=10,
        funded_minimum_micros=10,funded_maximum_micros=10,simulations=8,maximum_funded_breach_probability=None)
    response=client.post('/api/prop-sim',json=config);assert response.status_code==202,response.text
    id=response.json()['id'];client.app.state.prop_analyses.worker.submit(lambda:None).result(timeout=60)
    class SimulatedCrash(BaseException):pass
    def lost_queue(*args,**kwargs):raise SimulatedCrash()
    owner.closed=False
    with monkeypatch.context() as guard:
        guard.setattr('alphaquest.prop_sim.submit_assessment',lost_queue)
        with pytest.raises(SimulatedCrash):owner._advance(id)
    owner.close();saved=owner._read(id)
    phase=saved['automation']['phases']['evaluation'];cid=saved['campaign_ids']['evaluation']
    frozen=client.app.state.campaigns.get(cid)['frozen'];assert frozen
    # Simulate process loss after reservation but before a numerical job existed.
    client.app.state.campaigns.begin_assessment(cid,phase['oos_request_id'])
    database=client.app.state.store.path
    with TestClient(create_app(database)) as reopened:
        final=wait_automatic(reopened,id)
        assert all(s['stage']=='complete' for s in final['automation']['phases'].values()),final
        assert reopened.app.state.campaigns.get(cid)['frozen']==frozen
        for p,c in final['campaign_ids'].items():
            successes=[a for a in reopened.app.state.campaigns.assessments(c) if a['status']=='complete']
            assert len(successes)==1


def test_stop_cancels_oos_and_never_starts_follow_on_jobs(qualified_library,monkeypatch):
    from threading import Event
    from alphaquest.prop.oos_qualification import qualify
    client,source=qualified_library;entered,release=Event(),Event()
    def paused(*args,**kwargs):
        entered.set();assert release.wait(45)
        return qualify(*args,**kwargs)
    config=dict(body(source),automatic=True,evaluation_minimum_micros=10,evaluation_maximum_micros=10,
        funded_minimum_micros=10,funded_maximum_micros=10,simulations=8,maximum_funded_breach_probability=None)
    with monkeypatch.context() as guard:
        guard.setattr('alphaquest.prop.oos_qualification.qualify',paused)
        try:
            response=client.post('/api/prop-sim',json=config);assert response.status_code==202,response.text
            id=response.json()['id'];assert entered.wait(45)
            assert client.post('/api/prop-sim/'+id+'/cancel').status_code==200
        finally:release.set()
        client.app.state.prop_analyses.worker.submit(lambda:None).result(timeout=60)
    saved=client.get('/api/prop-sim/'+id).json();assert saved['automation']['stop_requested']
    before=[]
    for cid in saved['campaign_ids'].values():
        attempts=client.app.state.campaigns.assessments(cid);before.extend(a['request_id'] for a in attempts)
        assert all(a['status'] not in ('running','queued','complete') for a in attempts)
    client.app.state.prop_sim_automation._advance(id)
    assert before==[a['request_id'] for cid in saved['campaign_ids'].values() for a in client.app.state.campaigns.assessments(cid)]


def test_no_positive_funded_estimate_does_not_block_evaluation(qualified_library):
    client,source=qualified_library
    config=dict(body(source),automatic=True,evaluation_minimum_micros=10,evaluation_maximum_micros=10,
        funded_minimum_micros=10,funded_maximum_micros=10,simulations=8,
        maximum_funded_breach_probability=None,funded_horizon_calendar_days=1)
    response=client.post('/api/prop-sim',json=config);assert response.status_code==202,response.text
    saved=wait_automatic(client,response.json()['id'])
    assert saved['automation']['phases']['evaluation']['stage']=='complete',saved
    assert saved['automation']['phases']['funded']['stage']=='no_eligible_candidates',saved
    cid=saved['campaign_ids']['funded']
    assert client.app.state.campaigns.get(cid)['frozen'] is None
    assert client.app.state.campaigns.assessments(cid)==[]
    assert client.post(f"/api/prop-sim/{saved['id']}/validation/funded/freeze",json=dict(candidate_ids=['fake'],rationale='Manual override')).status_code==409


def test_stopping_one_run_preserves_shared_is_job_and_other_run(qualified_library,monkeypatch):
    from threading import Event
    from alphaquest.prop.evaluation_optimization import optimize_evaluation
    client,source=qualified_library;entered,release=Event(),Event()
    def paused(*args,**kwargs):
        entered.set();assert release.wait(45);return optimize_evaluation(*args,**kwargs)
    config=dict(body(source),automatic=True,evaluation_minimum_micros=10,evaluation_maximum_micros=10,
        funded_minimum_micros=10,funded_maximum_micros=10,simulations=8,
        maximum_funded_breach_probability=None,start_date='2026-11-18')
    with monkeypatch.context() as guard:
        guard.setattr('alphaquest.prop.evaluation_optimization.optimize_evaluation',paused)
        try:
            one=client.post('/api/prop-sim',json=config);assert one.status_code==202,one.text
            assert entered.wait(20)
            two=client.post('/api/prop-sim',json=dict(config,request_id=uuid4().hex));assert two.status_code==202,two.text
            assert one.json()['phases']['evaluation']['analysis_id']==two.json()['phases']['evaluation']['analysis_id']
            stopped=client.post('/api/prop-sim/'+one.json()['id']+'/cancel');assert stopped.status_code==200,stopped.text
            assert stopped.json()['automation']['retained_shared_analysis_ids']
        finally:release.set()
        final=wait_automatic(client,two.json()['id'])
    assert all(s['stage']=='complete' for s in final['automation']['phases'].values()),final
    original=client.get('/api/prop-sim/'+one.json()['id']).json()
    assert original['automation']['stop_requested']
    for cid in original['campaign_ids'].values():assert client.app.state.campaigns.assessments(cid)==[]
