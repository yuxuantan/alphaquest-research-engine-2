"""Independent clocks and fixed-choice assessment contracts for the Prop Sim workflow."""
from copy import deepcopy
from uuid import uuid4
import json
import time
import pytest
from alphaquest.prop.phase_profiles import EvaluationProfile,SimulationConfig,EvaluationSamplingConfig,rule_version
from alphaquest.prop.evaluation_profiles import calendar_evaluation_paths
from alphaquest.prop.evaluation_optimization import SequentialRetry,paired_precision
from alphaquest.prop.phase_search import PhaseCalendar


def paths(percent=40,guard=15,chronological=False):
    return calendar_evaluation_paths([[(1500.,0.)]]*12,
        EvaluationProfile('lucidflex-50k',rule_version('lucidflex-50k'),'99.50','0',True,percent),10,
        SimulationConfig(8,42,40),EvaluationSamplingConfig(5,8,42),
        SequentialRetry(activation_delay_sessions=0,max_calendar_days=guard),
        PhaseCalendar(('2026-11-16',),'2027-01-31'),chronological=chronological)[0]


def test_exact_standard_addon_consistency_clocks_and_diagnostics():
    standard,addon=paths(),paths(50)
    assert all(p['calendar_days_to_funded']==3 and p['paid_fees']==99.5 for p in standard)
    assert all(p['calendar_days_to_funded']==2 and p['paid_fees']==99.5 for p in addon)
    for p in standard:
        d=p['acquisition_diagnostics']
        assert d==dict(failed_attempts_before_target=0,failed_attempts_after_target=0,consistency_blocked_sessions=1,
            days_before_final_attempt=0,final_attempt_days_before_target=1,final_attempt_days_after_target=1,pass_to_ready_days=1)
    assert paths(40,guard=2)[0]['censored']
    assert paths(50,guard=2)[0]['acquisition_completed']
    # An OOS boundary is an exclusive source cutoff, not an extra observed day.
    assert paths(50,guard=2,chronological=True)[0]['censored']
    for value in (52,0,True,'50'):
        with pytest.raises(ValueError):EvaluationProfile('lucidflex-50k',rule_version('lucidflex-50k'),'99.50','0',True,value)


def test_paired_precision_preserves_point_frontier_and_uses_differences():
    rows=[]
    for name,times,costs in [('a',[10,20,30,40],[80,80,160,160]),('b',[10,20,30,40],[80,80,160,160]),('c',[20,30,40,50],[160,160,240,240])]:
        rows.append(dict(candidate_id=name,status='estimated',pareto_member=True,metrics=dict(expected_calendar_days_to_funded=sum(times)/4),
            uncertainty=dict(calendar_mean_se=3),paths=[dict(path=i,start_date='2026-11-16',calendar_days_to_funded=t,paid_fees=c) for i,(t,c) in enumerate(zip(times,costs))]))
    result=paired_precision(rows)
    ab=next(p for p in result['paired_comparisons'] if p['candidate_a']=='a' and p['candidate_b']=='b')
    assert ab['time']['family_95_interval']==[0,0] and ab['funding_time_difference_unresolved']
    ac=next(p for p in result['paired_comparisons'] if p['candidate_a']=='a' and p['candidate_b']=='c')
    assert ac['time']['family_95_interval']==[-10,-10] and ac['cost']['family_95_interval']==[-80,-80]
    assert all(r['pareto_member'] for r in rows)
    assert rows[0]['funding_time_near_ties']==['b']


def wait_assessment(client,prefix,id):
    deadline=time.monotonic()+90
    while True:
        state=client.get(prefix).json();attempt=next(a for a in state['assessments'] if a['request_id']==id)
        if attempt['status'] not in ('launching','queued','running'):break
        assert time.monotonic()<deadline,attempt
        time.sleep(.05)
    assert attempt['status']=='complete',json.dumps(attempt,indent=2)
    response=client.get(prefix+'/'+id);assert response.status_code==200,response.text
    return attempt,response.json()


from test_research_workflow import client
from test_prop_sim import qualified_source,body,wait_prop


def test_variant_phase_independence_frozen_oos_robustness_precision_and_reopen(client):
    from unittest.mock import patch
    workflow,source=qualified_source(client)
    request=dict(body(source),profile_id='lucidflex-50k',evaluation_price='99.50',activation_fee='0',
        commission_per_mnq_side='0.50',evaluation_consistency_percent=50,maximum_funded_breach_probability=None)
    missing={k:v for k,v in request.items() if k!='evaluation_price'}
    assert client.post('/api/prop-sim/check',json=missing).status_code==422
    assert client.post('/api/prop-sim/check',json=dict(request,evaluation_consistency_percent=52)).status_code==422
    before=client.post('/api/prop-sim/check',json=request);assert before.status_code==200,before.text
    standard=client.post('/api/prop-sim/check',json=dict(request,evaluation_consistency_percent=40)).json()
    assert before.json()['phases']['funded']['calculation_key']==standard['phases']['funded']['calculation_key']
    assert before.json()['phases']['evaluation']['calculation_key']!=standard['phases']['evaluation']['calculation_key']
    response=client.post('/api/prop-sim',json=request);assert response.status_code==202,response.text
    saved=wait_prop(client,response.json()['id'])
    evidence={}
    for phase in ('evaluation','funded'):
        report=client.get('/api/prop-sim/'+saved['id']+'/results/'+phase).json()
        prefix='/api/prop-sim/'+saved['id']+'/validation/'+phase
        req=dict(request_id=uuid4().hex,kind='oos')
        assert client.post(prefix,json=req).status_code==409
        calc=report['calculations'];ids=calc['frontier'] if phase=='evaluation' else calc['ranking']
        assert ids,calc
        chosen=ids[:1];freeze=dict(candidate_ids=chosen,rationale='Independent synthetic product validation')
        response=client.post(prefix+'/freeze',json=freeze);assert response.status_code==200,response.text
        frozen=deepcopy(response.json());assert client.post(prefix+'/freeze',json=dict(freeze,rationale='Changed')).status_code==409
        if phase=='evaluation':
            for row in calc['candidates']:
                assert row['manifest']['configuration']['profile']['consistency_percent']==50
                if row['status']=='estimated':
                    m=row['metrics'];assert abs(sum(m['mean_'+key] for key in ['days_before_final_attempt','final_attempt_days_before_target','final_attempt_days_after_target','pass_to_ready_days'])-m['expected_calendar_days_to_funded'])<1e-8
            assert 'paired_comparisons' in calc
        studies=[]
        # Emulate a historical descriptive assessment, retaining its sealed bytes.
        cid=saved['campaign_ids'][phase];legacy_id=uuid4().hex
        client.app.state.campaigns.assess_saved(cid,legacy_id,'oos',oos_sources={source['source_backtest_id']:saved['qualification']['oos_report_id']})
        legacy_attempt,legacy=wait_assessment(client,prefix,legacy_id)
        original=client.app.state.prop_analyses.fingerprint(legacy['id'])
        assert 'assessment_policy' not in legacy['calculations']
        limits=dict(maximum_cost_per_funded='100000',maximum_calendar_days_to_funded=180) if phase=='evaluation' else dict(minimum_funded_receipts='1')
        response=client.post(prefix+'/policy',json=limits);assert response.status_code==200,response.text
        policy=response.json();assert policy['declaration_timing']=='retrospective' and policy['prior_completed_oos_assessments']==1
        assert client.post(prefix+'/policy',json=limits).json()==policy
        assert client.post(prefix+'/policy',json=dict(limits,account_start_count=6)).status_code==409
        for kind,paths_count in [('oos',None),('account_starts',None),('is_robustness',8),('precision',64)]:
            declared=dict(request_id=uuid4().hex,kind=kind)
            if paths_count is not None:declared['paths']=paths_count
            if kind in ('oos','account_starts'):
                # Re-review and start replay must not run the MC optimizer again.
                with patch('alphaquest.prop.'+phase+'_optimization.optimize_'+phase,side_effect=AssertionError('MC must be reused')):
                    response=client.post(prefix,json=declared);assert response.status_code==202,response.text
                    attempt,study=wait_assessment(client,prefix,declared['request_id'])
            else:
                response=client.post(prefix,json=declared);assert response.status_code==202,response.text
                attempt,study=wait_assessment(client,prefix,declared['request_id'])
            assert client.post(prefix,json=declared).json()['analysis_id']==attempt['analysis_id']
            rows=study['calculations']['candidates'];assert rows
            assert study['calculations']['selection_status']=='assessment_only_no_reselection'
            assert study['calculations']['winner'] is None
            assert {r['frozen_candidate_id'] for r in rows}==set(chosen)
            assert study['assessment']['frozen_package']==frozen
            if kind=='is_robustness':assert {r['scenario'] for r in rows}=={'block_1','block_5','block_20','first_half','second_half'}
            if kind in ('oos','account_starts'):
                assert all(r['is_comparison'] and r['chronological_replay'] for r in rows)
                assert all(r['manifest']['source']['backtest']['run_metadata']['research']['phase']=='oos' for r in rows)
                assert all(r['economic_assessment']['verdict'] in ('PASS','FAIL','INCONCLUSIVE') for r in rows)
                assert study['calculations']['assessment_policy']==policy
                assert client.get('/api/prop-analyses/'+attempt['analysis_id']+'/downloads/economic_assessment.json').status_code==200
                if kind=='account_starts':
                    sensitivity=study['calculations']['account_start_sensitivity'];assert sensitivity['status']=='COMPLETE'
                    assert len(sensitivity['candidates'][0]['paths'])==5
                    assert [r['paths'] for r in rows]==[r['paths'] for r in studies[0]['calculations']['candidates']]
                    assert study['assessment']['prop_sim_review']['base_report']['analysis_id']==studies[0]['id']
            else:assert all(r['manifest']['source']['backtest']['run_metadata']['research']['phase']=='is' for r in rows)
            if kind=='precision':assert all(len(r['paths'])==64 for r in rows)
            assert client.get('/api/jobs/prop_analysis/'+attempt['analysis_id']).json()['links'][0]['href']=='#prop-sim?analysis='+saved['id']
            assert client.get('/api/prop-analyses/'+attempt['analysis_id']+'/downloads/analysis.zip').status_code==200
            summary=client.get(prefix+'/'+declared['request_id']+'?summary=true').json()
            assert all('paths' not in r and 'manifest' not in r for r in summary['calculations']['candidates'])
            assert [r['metrics'] for r in summary['calculations']['candidates']]==[r['metrics'] for r in rows]
            studies.append(study)
        assert len(client.get(prefix).json()['assessments'])==5
        assert client.app.state.prop_analyses.fingerprint(legacy['id'])==original
        assert client.get(prefix).json()['frozen']['package_sha256']==frozen['package_sha256']
        assert client.get('/api/prop-sim/'+saved['id']+'/results/'+phase).json()==report
        assert client.post(prefix,json=dict(request_id=uuid4().hex,kind='precision',paths=8)).status_code==409
        with patch.object(client.app.state.prop_analyses,'fingerprint',return_value=None):
            assert client.post(prefix,json=dict(request_id=uuid4().hex,kind='account_starts')).status_code==409
        from alphaquest.prop.assessment_review import implementation
        with patch('alphaquest.prop.assessment_review.implementation',return_value=dict(implementation(),source_sha256='changed')):
            assert client.post(prefix,json=dict(request_id=uuid4().hex,kind='oos')).status_code==409
        revision=dict(limits,previous_policy_sha256=policy['policy_sha256'],reason='Correct business limits after reviewing costs',account_start_count=3)
        assert client.post(prefix+'/policy/revisions',json=dict(revision,reason='  ')).status_code==409
        response=client.post(prefix+'/policy/revisions',json=revision);assert response.status_code==200,response.text
        revised=response.json();assert revised['revision']==2 and revised['declaration_timing']=='retrospective'
        assert revised['previous_policy_sha256']==policy['policy_sha256'] and revised['start_plan']['requested_starts']==3
        assert client.post(prefix+'/policy/revisions',json=revision).json()==revised  # Retry does not append twice.
        assert client.post(prefix+'/policy/revisions',json=dict(revision,account_start_count=4)).status_code==409
        assert client.get(prefix).json()['assessment_policy_history']==[policy,revised]
        assert client.post(prefix,json=dict(request_id=uuid4().hex,kind='account_starts')).status_code==409
        old=client.app.state.prop_analyses.fingerprint(studies[0]['id'])
        with patch('alphaquest.prop.'+phase+'_optimization.optimize_'+phase,side_effect=AssertionError('MC must be reused')):
            declared=dict(request_id=uuid4().hex,kind='oos')
            assert client.post(prefix,json=declared).status_code==202
            _,updated=wait_assessment(client,prefix,declared['request_id'])
            assert updated['calculations']['assessment_policy']==revised
            assert [r['paths'] for r in updated['calculations']['candidates']]==[r['paths'] for r in studies[0]['calculations']['candidates']]
            declared=dict(request_id=uuid4().hex,kind='account_starts')
            assert client.post(prefix,json=declared).status_code==202
            _,updated=wait_assessment(client,prefix,declared['request_id'])
            assert updated['calculations']['account_start_sensitivity']['simulations']==3
        assert client.app.state.prop_analyses.fingerprint(studies[0]['id'])==old
        if phase=='evaluation':
            # A new substantive policy is required to start another review;
            # repeated requests under version 2 now reopen its saved result.
            third_request=dict(limits,previous_policy_sha256=revised['policy_sha256'],reason='Change the diagnostic window before queued review',account_start_count=4)
            response=client.post(prefix+'/policy/revisions',json=third_request);assert response.status_code==200,response.text
            third=response.json()
            from threading import Event
            from alphaquest.prop.assessment_review import enrich
            entered,release=Event(),Event()
            def paused(*args,**kwargs):
                entered.set()
                assert release.wait(15),'Test did not release the active assessment'
                return enrich(*args,**kwargs)
            declared=dict(request_id=uuid4().hex,kind='oos')
            with patch('alphaquest.prop.assessment_review.enrich',side_effect=paused):
                try:
                    assert client.post(prefix,json=declared).status_code==202
                    assert entered.wait(10)
                    revert=dict(limits,previous_policy_sha256=third['policy_sha256'],reason='Restore the original business decision')
                    response=client.post(prefix+'/policy/revisions',json=revert);assert response.status_code==200,response.text
                    restored=response.json();assert restored['revision']==4 and restored['limits']==policy['limits']
                finally:release.set()
                _,running=wait_assessment(client,prefix,declared['request_id'])
            assert running['calculations']['assessment_policy']==third  # Running job retains version 3.
            assert client.get(prefix).json()['assessment_policy_history']==[policy,revised,third,restored]
        evidence[phase]=studies
    # Report readers remain valid even after a numerical implementation changes.
    with patch('alphaquest.prop.evaluation_optimization.implementation_identity',return_value={}):
        prefix='/api/prop-sim/'+saved['id']+'/validation/evaluation'
        assert client.post(prefix,json=dict(request_id=uuid4().hex,kind='oos')).status_code==409
        assert client.get('/api/prop-sim/'+saved['id']+'/results/evaluation').status_code==200
    assert client.app.state.campaign_workflows.get(workflow['id'])['narrow']==workflow['narrow']


def test_account_reaching_target_then_breaching_is_counted_as_retry(monkeypatch):
    from itertools import repeat
    from alphaquest.prop.evaluation_profiles import DatedEvaluationPreparation
    from alphaquest.prop import native_engine
    calls=0
    def prescribed(*args):
        nonlocal calls
        calls+=1
        return iter([0,1]) if calls%2 else repeat(2)
    monkeypatch.setattr(native_engine,'sampled_days',prescribed)
    # Account 1 reaches 3000 but fails consistency, then an observed gap
    # breaches both floors. Account 2 earns 1000 on Wed/Thu/Fri; ready Monday.
    days=[[(3000.,0.)],[(-4000.,4000.,((4000.,True),))],[(1000.,0.)]]
    profile=EvaluationProfile('lucidflex-50k',rule_version('lucidflex-50k'),'80.50','0')
    result=calendar_evaluation_paths(days,profile,10,SimulationConfig(8,42,40),EvaluationSamplingConfig(5,8,42),
        SequentialRetry(activation_delay_sessions=0,max_calendar_days=15),PhaseCalendar(('2026-11-16',),'2027-01-31'),
        # This prescribed finite stream deliberately ends at a breach; do not
        # prefetch its nonexistent suffix as if it were the real infinite RNG.
        preparation=DatedEvaluationPreparation(0))[0]
    for p in result:
        assert p['calendar_days_to_funded']==7 and p['attempts_started']==2 and p['paid_fees']==161
        d=p['acquisition_diagnostics']
        assert d==dict(failed_attempts_before_target=0,failed_attempts_after_target=1,consistency_blocked_sessions=1,
            days_before_final_attempt=2,final_attempt_days_before_target=2,final_attempt_days_after_target=0,pass_to_ready_days=3)
