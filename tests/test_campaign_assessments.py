"""Frozen family → ordinary manual OOS → assessment-only AnalysisStore reports."""
from copy import deepcopy
from hashlib import sha256
import json
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from alphaquest.app import create_app
from test_prop_phases import phase_history
from test_research_campaigns import declaration, create, run, files
from test_prop_analysis_api import wait


def saved_is(client, green=1):
    response=client.post('/api/datasets',params=dict(filename='SYNTHETIC-campaign-IS-OOS.csv',
        name='SYNTHETIC phase campaign with reserved OOS',source_timezone='UTC',tick_size='.25',point_value='20',symbol='NQ'),content=phase_history(24))
    assert response.status_code in (201,409),response.text
    dataset=response.json()['id'] if response.status_code==201 else response.json()['dataset_id']
    response=client.post('/api/backtests',json=dict(dataset_id=dataset,strategy_id='consecutive_green_hold',
        strategy_parameters=dict(green_bar_count=green,hold_minutes=1,contracts=1),
        execution_settings=dict(initial_capital='10000',tick_size='.25',point_value='20',slippage_ticks=0,commission_per_contract_per_side='0'),
        sample_split=dict(mode='dates',is_start='2026-01-05',is_end='2026-01-14',oos_start='2026-01-15',oos_end='2026-02-05')))
    assert response.status_code==201,response.text
    return response.json()


@pytest.mark.parametrize('phase',['evaluation','funded'])
def test_frozen_manual_oos_no_reselection_and_durable_history(tmp_path,monkeypatch,phase):
    with TestClient(create_app(tmp_path/'datasets.sqlite3')) as client:
        a=saved_is(client);b=saved_is(client,2)
        body=declaration(a,b,phase)
        if phase=='evaluation':
            body['sources'][0]['sizes']=[3,10];body['sources'][1]['sizes']=[3,10]
        campaign=run(client,create(client,body)['campaign_id']);id=campaign['campaign_id']
        prefix=f'/api/research-campaigns/{id}'
        assert client.post(prefix+'/assessments',json=dict(request_id=uuid4().hex)).status_code==409
        is_result=client.get(prefix+'/exports/results.json').json()
        # Funded freezes a named two-size family: assessment cannot call a
        # ranking function, even for individual candidates. Evaluation freezes
        # the resolved frontier (selection on IS only).
        selected=is_result['frontier'] if phase=='evaluation' else [r['candidate_id'] for r in is_result['candidates']
            if r['manifest']['configuration']['source']['source_backtest_id']==a['id']]
        names={k:f'Predeclared {phase} choice {i+1}' for i,k in enumerate(selected)}
        response=client.post(prefix+'/freeze',json=dict(candidate_ids=selected,names=names,rationale='IS decision before manual OOS.'))
        assert response.status_code==200,response.text
        frozen=response.json();assert frozen['names']==names
        assert frozen['candidate_definitions'] and frozen['rule_sources']
        for source in frozen['rule_sources'].values():
            assert sha256(source['source'].encode()).hexdigest()==source['sha256']
        # A changed implementation fails before any OOS access, rather than
        # silently substituting a current engine for the frozen package.
        import alphaquest.research_campaigns as campaigns
        module=campaigns.module_for(phase)
        with monkeypatch.context() as m:
            m.setattr(module,'implementation_identity',lambda:dict(changed=True))
            assert client.post(prefix+'/assessments',json=dict(request_id=uuid4().hex)).status_code==409
        assert client.get(prefix+'/assessments').json()['items']==[]
        before=files(tmp_path);freeze_bytes=client.get(prefix+'/exports/frozen_package.json').content
        original=client.get(prefix+'/exports/results.json').content
        for overrides in [dict(micros=9),dict(profile={}),dict(candidate_ids=[]),dict(horizon_calendar_days=1),dict(strategy_parameters={})]:
            assert client.post(prefix+'/assessments',json=dict(request_id=uuid4().hex,**overrides)).status_code==422
        def forbidden(*a,**k):pytest.fail('OOS must not invoke a selector')
        monkeypatch.setattr('alphaquest.prop.'+phase+'_optimization.'+('pareto_sort' if phase=='evaluation' else 'rank_candidates'),forbidden)
        evidence=[]
        for _ in range(2):
            request_id=uuid4().hex
            response=client.post(prefix+'/assessments',json=dict(request_id=request_id))
            assert response.status_code==202,response.text
            attempt=response.json();assert attempt['analysis_id'],attempt
            assert wait(client,attempt['analysis_id'])['status']=='complete',wait(client,attempt['analysis_id'])
            report=client.get(f'/api/prop-analyses/{attempt["analysis_id"]}/downloads/report.json').json()
            calc=report['calculations'];assert calc['selection_status']=='assessment_only_no_reselection'
            assert calc['winner'] is None and calc.get('frontier',calc.get('ranking'))==[]
            assert len(calc['candidates'])==len(selected)
            assert report['assessment']['frozen_package']==frozen
            from alphaquest.prop.phase_search import check_candidates
            invalid=deepcopy(report['request']);invalid['candidates'][0]['micros']+=1
            with pytest.raises(ValueError,match='frozen'):
                check_candidates(client.app.state.runs,module.parse_request(invalid),report['assessment'])
            for row in calc['candidates']:
                source=row['manifest']['source']['backtest']
                assert source['run_metadata']['research']['phase']=='oos'
                parent=source['run_metadata']['research']['parent_run_id']
                assert source['run_metadata']['strategy']==client.get('/api/backtests/'+parent).json()['run_metadata']['strategy']
                assert client.delete('/api/backtests/'+source['id']).status_code==409
                config=row['manifest']['configuration'];m=row['metrics']
                if phase=='evaluation':
                    assert m['cost_per_funded']==70 and m['expected_calendar_days_to_funded']==2
                    assert row['pareto_rank'] is None
                else:
                    assert m['expected_payouts']==(1500 if config['micros']==3 else 0)
                    assert m['expected_pending_cash']==(1500 if config['micros']==3 else 0)
                    assert row['rank'] is None
            assert client.post(prefix+'/assessments',json=dict(request_id=request_id)).json()['analysis_id']==attempt['analysis_id']
            assert client.get(prefix+'/exports/frozen_package.json').content==freeze_bytes
            assert client.get(prefix+'/exports/results.json').content==original
            evidence.append(dict(attempt=attempt,report_id=report['id'],metrics=[r['metrics'] for r in calc['candidates']]))
        history=client.get(prefix+'/assessments').json()['items'];assert len(history)==2
        assert any(c['prior_access']['attempts'] for c in history[1]['prior_access'])
        from alphaquest.prop.store import AnalysisStore
        from alphaquest.research_campaigns import CampaignStore
        reopened=AnalysisStore(tmp_path,recover_interrupted=False)
        try:
            assert len(CampaignStore(client.app.state.runs,reopened,client.app.state.optimizations).assessments(id))==2
        finally:reopened.close()
        assert all(sha256((tmp_path/name).read_bytes()).hexdigest()==value for name,value in before.items())
        # Public search cannot admit the assessed OOS report as a new IS candidate.
        illegal=deepcopy(body);illegal['campaign_id']=uuid4().hex
        illegal['sources'][0]['backtest_id']=next(iter(history[0]['oos_sources'].values()))
        assert client.post('/api/research-campaigns',json=illegal).status_code==422
        (tmp_path/'assessment-verification.json').write_text(json.dumps(dict(phase=phase,campaign_id=id,frozen=frozen,
            is_result_sha256=sha256(original).hexdigest(),unchanged_files=len(before),assessments=evidence),indent=2))
