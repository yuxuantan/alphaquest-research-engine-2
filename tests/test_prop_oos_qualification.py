"""Independent margin decisions and actual native historical-bootstrap oracles."""
from dataclasses import replace
from datetime import date,timedelta
import json
from types import SimpleNamespace
from uuid import uuid4

import numpy as np
import pytest

from alphaquest.prop.oos_qualification import RULES,complete_months,decide,historical_ratios,_means
from alphaquest.prop.phase_profiles import EvaluationProfile,FundedProfile,SimulationConfig,EvaluationSamplingConfig,SamplingConfig,SourceCosts,rule_version
from alphaquest.prop.phase_search import PhaseCalendar
from alphaquest.prop.evaluation_optimization import EvaluationCandidate,EvaluationSearch,SequentialRetry
from alphaquest.prop.funded_optimization import FundedCandidate,FundedSearch
from alphaquest.prop.phase_profiles import SavedTradeSource,ResearchPeriod


def test_fixed_margins_equality_fail_and_uncertain_are_distinct():
    ev=[dict(passed=True)]
    rows=[dict(cost_per_funded=1.5,expected_calendar_days_to_funded=1.5)]*10000
    assert decide(rows[0],rows,'evaluation',ev)['status']=='GO'
    rows=[dict(cost_per_funded=1.51,expected_calendar_days_to_funded=1.)]*10000
    assert decide(rows[0],rows,'evaluation',ev)['status']=='NO_GO'
    rows=[dict(cost_per_funded=1.,expected_calendar_days_to_funded=1.)]*5000+[dict(cost_per_funded=2.,expected_calendar_days_to_funded=1.)]*5000
    assert decide(dict(cost_per_funded=1.2),rows,'evaluation',ev)['status']=='INSUFFICIENT_EVIDENCE'
    cash=[dict(expected_funded_cash_payouts_within_horizon=.7)]*10000
    assert decide(cash[0],cash,'funded',ev)['status']=='GO'
    cash=[dict(expected_funded_cash_payouts_within_horizon=.69)]*10000
    assert decide(cash[0],cash,'funded',ev)['status']=='NO_GO'
    assert decide(cash[0],cash,'funded',[dict(passed=False)])['status']=='INSUFFICIENT_EVIDENCE'
    assert decide(cash[0],cash,'funded',ev,inner_precision_ok=False)['status']=='INSUFFICIENT_EVIDENCE'
    assert decide({},[{}],'funded',ev)['status']=='INSUFFICIENT_EVIDENCE'
    with pytest.raises(ValueError):decide({},[],'other',ev)


def test_observed_complete_months_and_family_tail():
    assert complete_months(dict(first_session='2025-01-01',last_session='2025-12-31'))==12
    assert complete_months(dict(first_session='2025-01-02',last_session='2025-12-30'))==10
    result=decide({},[],'funded',[dict(passed=True)])
    assert result['tail_probability']==pytest.approx(.05/24)
    assert result['family_test_budget']==12


def fixed_search(phase):
    source=SavedTradeSource('a'*32)
    period=ResearchPeriod('2025-01-01','2025-12-31')
    simulation=SimulationConfig(8,42,40)
    calendar=PhaseCalendar(('2026-11-16',),'2037-01-01')
    if phase=='evaluation':
        c=EvaluationCandidate(source=source,profile=EvaluationProfile('lucidflex-50k',rule_version('lucidflex-50k'),'99.50','0',True,50),micros=10,
            simulation=simulation,period=period,sampling=EvaluationSamplingConfig(5,8,42),costs=SourceCosts(),retry=SequentialRetry(activation_delay_sessions=0))
        return EvaluationSearch(source.source_backtest_id,(c,),calendar)
    c=FundedCandidate(source=source,profile=FundedProfile('lucidflex-50k',rule_version('lucidflex-50k')),micros=10,
        simulation=simulation,period=period,sampling=SamplingConfig(5),costs=SourceCosts())
    return FundedSearch(source.source_backtest_id,(c,),calendar,90,2)


@pytest.mark.parametrize('phase',['evaluation','funded'])
def test_actual_account_owners_resample_histories_and_preserve_path_count(phase,monkeypatch):
    import alphaquest.prop.oos_qualification as owner
    search=fixed_search(phase);c=search.candidates[0]
    # Constant source day: $1,500 net per NQ at 10 MNQ. Every historical
    # resample is numerically identical; genuine owner evaluations are memoized.
    days=[[(1500.,0.)]]*40
    monkeypatch.setitem(owner.RULES,'historical_replicates',32)
    data=historical_ratios(days,days,c,c,search,lambda:None,lambda message:None)
    assert data['unique_histories_evaluated']==[1,1]
    assert data['inner_precision_ok']
    for row in data['replicates']:assert set(row['ratios'].values())=={1.}
    means,error=_means(days,c,search,lambda:None)
    assert error==0
    if phase=='evaluation':assert means==dict(cost_per_funded=99.5,expected_calendar_days_to_funded=2.)
    else:assert means['expected_funded_cash_payouts_within_horizon']>0


def daily_csv():
    from test_campaign_mechanics import mechanics_csv
    template=mechanics_csv().decode().splitlines()[1:-1]
    lines=['Date,Time,Open,High,Low,Close,Volume,UpVol,DownVol']
    day=date(2024,1,1)
    while day<=date(2026,12,31):
        if day.weekday()<5:
            for raw in template:
                row=raw.split(',');row[0]=day.strftime('%m/%d/%Y');lines.append(','.join(row))
        day+=timedelta(days=1)
    return ('\n'.join(lines)+'\n').encode()


from test_research_workflow import client
from test_prop_sim import qualified_source,body,wait_prop
from test_prop_evaluation_validation import wait_assessment


def test_normal_qualified_workflow_has_no_required_dollar_limits_and_sealed_confidence(client,tmp_path,monkeypatch):
    import test_campaign_broad,test_campaign_narrow,test_campaign_oos
    wait=test_campaign_broad.wait_job
    for module in (test_campaign_broad,test_campaign_narrow,test_campaign_oos):
        monkeypatch.setattr(module,'wait_job',lambda client,id,timeout=600:wait(client,id,timeout=600))
    workflow,source=qualified_source(client,daily_csv())
    request=dict(body(source),evaluation_minimum_micros=10,evaluation_maximum_micros=10,
        funded_minimum_micros=10,funded_maximum_micros=10,simulations=8,maximum_funded_breach_probability=None)
    response=client.post('/api/prop-sim',json=request);assert response.status_code==202,response.text
    saved=wait_prop(client,response.json()['id'])
    for phase in ('evaluation','funded'):
        prefix=f"/api/prop-sim/{saved['id']}/validation/{phase}"
        report=client.get(f"/api/prop-sim/{saved['id']}/results/{phase}").json();calc=report['calculations']
        chosen=(calc['frontier'] if phase=='evaluation' else calc['ranking'])[:1];assert chosen
        assert client.post(prefix+'/freeze',json=dict(candidate_ids=chosen,rationale='SYNTHETIC constant-day independent oracle')).status_code==200
        assert client.get(prefix).json()['assessment_policy'] is None
        declared=dict(request_id=uuid4().hex,kind='qualification')
        response=client.post(prefix,json=declared);assert response.status_code==202,response.text
        attempt,result=wait_assessment(client,prefix,declared['request_id'])
        row=result['calculations']['candidates'][0];review=row['prop_qualification']
        assert review['status']=='GO',review
        assert review['historical_replicates']==10000
        assert all(c['lower']==c['upper']==1. for c in review['checks'])
        assert row['prop_qualification']['forward_execution']['status']=='PENDING'
        assert result['calculations']['qualification_bootstrap'][0]['unique_histories_evaluated']==[1,1]
        assert result['calculations']['winner'] is None and {row['frozen_candidate_id']}==set(chosen)
        assert client.get(f"/api/prop-sim/{saved['id']}/results/{phase}").json()==report
        summary=client.get(prefix+'/'+declared['request_id']+'?summary=true').json()
        assert 'qualification_bootstrap' not in summary['calculations']
        for name in ('qualification_policy.json','oos_qualification.json','historical_bootstrap.json'):
            assert client.get('/api/prop-analyses/'+attempt['analysis_id']+'/files/'+name).status_code==200
        if phase=='funded':exercise_forward_binding(client,saved,phase,prefix,result)
        # The coverage-only start diagnostic uses the same completed qualification,
        # without user dollar limits or another historical/MC search.
        with monkeypatch.context() as guard:
            guard.setattr('alphaquest.prop.oos_qualification.historical_ratios',lambda *a,**k:pytest.fail('Account starts refit historical means'))
            request_id=uuid4().hex
            response=client.post(prefix,json=dict(request_id=request_id,kind='account_starts'));assert response.status_code==202,response.text
            starts,diagnostic=wait_assessment(client,prefix,request_id)
        assert diagnostic['calculations']['account_start_sensitivity']['status']=='COMPLETE'
        assert diagnostic['calculations']['qualification_bootstrap']==result['calculations']['qualification_bootstrap']
        assert client.get('/api/prop-analyses/'+starts['analysis_id']+'/files/account_start_sensitivity.json').status_code==200


def test_forward_execution_gate_requires_real_provenance_every_review_and_zero_issues():
    """Analytical test fixture only: no synthetic sample becomes live evidence."""
    from copy import deepcopy
    from hashlib import sha256
    from alphaquest.prop.adapter import canonical
    from alphaquest.prop_sim_forward import execution_check
    episodes=[dict(start_utc=f'2026-01-{i%20+1:02}T15:{i//20:02}:00Z',
                   end_utc=f'2026-01-{i%20+1:02}T15:{i//20:02}:30Z',net_pnl='10') for i in range(30)]
    report=dict(request=dict(observation_kind='paper'),calculations=dict(metrics=dict(episodes=episodes),
        reconciliation=dict(issues=[],fills=[]),policy_conformance=dict(status='MATCH'),
        forward_evidence=dict(status='SUPPLIED_FORWARD_OBSERVATIONS')))
    reviewed=[sha256(canonical(e).encode()).hexdigest() for e in episodes]
    assert execution_check(report,reviewed,'Test-only complete manual review')['status']=='GO'
    assert execution_check(report,reviewed[:-1],'Test-only incomplete review')['status']=='INSUFFICIENT_EVIDENCE'
    assert execution_check(report,reviewed,' ')['status']=='INSUFFICIENT_EVIDENCE'
    for category,status in [('synthetic_harness','SYNTHETIC_ONLY'),('paper','RETROSPECTIVE_OR_UNKNOWN_POLICY_SCOPE')]:
        changed=deepcopy(report);changed['request']['observation_kind']=category;changed['calculations']['forward_evidence']['status']=status
        assert execution_check(changed,reviewed,'Test-only review')['status']=='INSUFFICIENT_EVIDENCE'
    report['calculations']['reconciliation']['issues']=[dict(code='wrong_size',acknowledged=False)]
    assert execution_check(report,reviewed,'Discrepancy unresolved')['status']=='NO_GO'


def exercise_forward_binding(client,saved,phase,prefix,result):
    from copy import deepcopy
    from datetime import datetime,timezone
    from tests.test_forward_reconcile import fixture
    from tests.test_forward_api import wait_monitor
    launch=client.get(prefix+'/forward');assert launch.status_code==200,launch.text
    package,=launch.json()['calculations']['recommendation'][0]['selected_packages']
    monitor=uuid4().hex
    declaration=dict(monitor_id=monitor,name='SYNTHETIC Prop Sim execution boundary probe',observation_kind='synthetic_harness',
        policy_binding=dict(campaign_id=saved['campaign_ids'][phase],application_id=saved['id'],phase=phase,package_sha256=package['package_sha256']),
        source=dict(source_id='synthetic-prop-forward',label='SYNTHETIC arithmetic; no real paper trading'),
        instrument=dict(symbol='MNQ',tick_size='.25',point_value='2'),thresholds=dict(maximum_position_contracts=10))
    checked=client.post('/api/forward-monitors/check',json=declaration);assert checked.status_code==200,checked.text
    wrong=deepcopy(declaration);wrong['policy_binding']['package_sha256']='0'*64
    assert client.post('/api/forward-monitors/check',json=wrong).status_code==422
    created=client.post('/api/forward-monitors',json=declaration);assert created.status_code==201,created.text
    events=fixture();start=datetime.now(timezone.utc)
    for i,event in enumerate(events):
        event['event_time_utc']=(start+timedelta(microseconds=i)).isoformat().replace('+00:00','Z')
        if event.get('quantity')==2:event['quantity']=10
        if event['kind']=='fill':event['commission']='5'
        if event['kind']=='position' and event.get('account_balance')=='50002':event['account_balance']='50010'
    raw=json.dumps(dict(schema_version='aq-forward-events-v1',source_id='synthetic-prop-forward',batch_id=uuid4().hex,events=events)).encode()
    url='/api/forward-monitors/'+monitor
    imported=client.post(url+'/events',content=raw);assert imported.status_code==201,imported.text
    launched=client.post(url+'/assess',json=dict(request_id=uuid4().hex,as_of_utc=datetime.now(timezone.utc).isoformat().replace('+00:00','Z')))
    forward,_=wait_monitor(client,launched.json()['id'])
    assert forward['calculations']['policy_conformance']['status']=='MATCH',forward['calculations']
    preview=client.get(prefix+'/forward-review/'+forward['id']);assert preview.status_code==200,preview.text
    assert preview.json()['preview']['status']=='INSUFFICIENT_EVIDENCE'
    body=dict(request_id=uuid4().hex,analysis_id=forward['id'],reviewed_episode_ids=[e['id'] for e in preview.json()['episodes']],notes='SYNTHETIC arithmetic review only; insufficient real forward evidence')
    submitted=client.post(prefix+'/forward-review',json=body);assert submitted.status_code==202,submitted.text
    attempt,report=wait_assessment(client,prefix,body['request_id'])
    assert report['calculations']['candidates'][0]['prop_qualification']['forward_execution']['status']=='INSUFFICIENT_EVIDENCE'
    assert report['calculations']['qualification_bootstrap']==result['calculations']['qualification_bootstrap']
    assert client.post(prefix+'/forward-review',json=body).json()['analysis_id']==report['id']
    assert not client.get('/api/prop-sim/'+saved['id']+'/deletion').json()['deletable']
    assert client.get('/api/prop-analyses/'+attempt['analysis_id']+'/files/forward_execution_review.json').status_code==200
    foreign=client.get(prefix.replace('/'+phase,'/'+('funded' if phase=='evaluation' else 'evaluation'))+'/forward-review/'+forward['id'])
    assert foreign.status_code==409
