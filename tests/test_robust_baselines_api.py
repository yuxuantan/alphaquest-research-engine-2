"""Real nested references retain failed edge status and independent authority."""
from copy import deepcopy
import csv
from decimal import Decimal
import io
import json
from threading import Event

from fastapi.testclient import TestClient
import pytest

from alphaquest.app import create_app
from alphaquest.prop.phase_dispatch import module_for
from alphaquest.prop.phase_search import verify_training_context
from test_robust_economic_api import economic, fingerprint
from test_robust_research_api import PREFIX, declaration, save_grid, save, run, wait_research


def baseline_body(client,job,records,phase='funded',*,no_qualified=False):
    study=economic(client,phase)
    if phase=='funded':study['selector']['tie_policy']='configuration_id'
    body=declaration(job,records,economic_studies=[study])
    body['qualification'].update(minimum_mean_session_net='1000' if no_qualified else '200',
        minimum_neighbors=0,minimum_neighbor_pass_fraction=0.)
    body['reliability']=dict(client.get(PREFIX+'/defaults').json()['reliability'],
        minimum_outer_blocks=2,minimum_calibration_blocks=2,historical_bootstrap_replicates=400)
    response=client.post(PREFIX+'/preview',json=body)
    assert response.status_code==200,response.text
    source=next(c for c in response.json()['candidates'] if c['parameters']['green_bar_count']==2)
    body['baselines']=[dict(id='Predeclared one MNQ reference',phase=phase,
        source_configuration_id=source['id'],profile=study['profiles'][0],policy={'micros':1},required=True)]
    return body


def test_failed_edge_reference_normal_reports_seals_comparison_and_reopen(tmp_path,monkeypatch):
    with TestClient(create_app(tmp_path/'datasets.sqlite3')) as client:
        _,job,records=save_grid(client);body=baseline_body(client,job,records)
        preview=client.post(PREFIX+'/preview',json=body)
        assert preview.status_code==200,preview.text
        plan=preview.json()
        assert plan['economic_plan']['baseline_count']==1
        assert plan['economic_plan']['estimated_baseline_training_backtests']==2
        assert plan['economic_plan']['estimated_baseline_outer_backtests']==2
        assert plan['estimated_backtests']==32
        row=run(client,save(client,body)['campaign_id']);id=row['campaign_id']
        children=[];packages=[]
        for fold in row['result']['folds']:
            assert len(fold['qualification']['approved_ids'])==1
            reference,=fold['baseline_results'];children.append(reference['analysis_id'])
            assert reference['status']=='REFERENCE_MEASURED'
            assert reference['edge_qualification']['status']=='FAIL'
            assert reference['recommendation_eligible'] is False
            package=reference['frozen_package'];packages.append(package)
            assert package['package_role']=='predeclared_reference'
            assert package['selector']['mode']=='predeclared_reference'
            assert package['configuration']['micros']==1
            assert Decimal(reference['chronological_replay']['cash_received'])==0
            child=client.get('/api/prop-analyses/'+reference['analysis_id']+'/downloads/report.json').json()
            ctx=child['training_context'];search=module_for('funded').parse_request(child['request'])
            assert verify_training_context(client.app.state.runs,search,ctx)==ctx['train_window']['sessions']
            assert ctx['version']=='nested-phase-reference-v1'
            assert not {'qualified_configuration_ids','qualification_sha256'} & set(ctx)
            assert ctx['reference_declarations']==body['baselines'] or ctx['reference_declarations']==plan['baselines']
            assert client.post('/api/prop-analyses/check',json=child['request']).status_code==422
            forged=dict(child['request'],training_context=ctx)
            assert client.post('/api/prop-analyses/check',json=forged).status_code==422
            for role,run_id in [('baseline_train',next(iter(ctx['training_sources']))),('baseline_outer_test',reference['outer_run_id'])]:
                saved=client.get('/api/backtests/'+run_id).json();research=saved['run_metadata']['research']
                assert research['role']==role and research['recommendation_eligible'] is False
                assert client.delete('/api/backtests/'+run_id).status_code==409
            assert client.delete('/api/prop-analyses/'+reference['analysis_id']).status_code==409
            bad=deepcopy(ctx);bad['qualified_configuration_ids']=bad['source_configuration_ids']
            bad['context_sha256']=fingerprint({k:v for k,v in bad.items() if k!='context_sha256'})
            with pytest.raises(ValueError,match='masquerade'):verify_training_context(client.app.state.runs,search,bad)
            bad=deepcopy(ctx);bad['recommendation_eligible']=True
            bad['context_sha256']=fingerprint({k:v for k,v in bad.items() if k!='context_sha256'})
            with pytest.raises(ValueError,match='reference'):verify_training_context(client.app.state.runs,search,bad)
            bad=deepcopy(child['request']);bad['candidates'][0]['micros']=2
            with pytest.raises(ValueError,match='outside its declaration'):
                verify_training_context(client.app.state.runs,module_for('funded').parse_request(bad),ctx)
            from alphaquest.prop.phase_profiles import SavedTradeSource, FundedProfile, SourceCosts, ReplayWindow, verify_frozen_replay
            from alphaquest.prop.phase_search import PhaseCalendar
            config=package['configuration'];calendar=deepcopy(package['calendar'])
            calendar['start_dates']=tuple(calendar['start_dates']);calendar['closures']=tuple(calendar['closures'])
            arguments=dict(runs=client.app.state.runs,source=SavedTradeSource(reference['outer_run_id']),phase='funded',
                profile=FundedProfile(**config['profile']),micros=config['micros'],max_micros=config['simulation']['max_micros'],
                costs=SourceCosts(**config['costs']),sizing=None,calendar=PhaseCalendar(**calendar),
                window=ReplayWindow(package['outer_window']['first_session'],package['outer_window']['cutoff_date_exclusive']),
                receipt_delay_calendar_days=package['receipt_delay_calendar_days'],receipt_amount_convention=package['receipt_amount_convention'])
            verify_frozen_replay(binding=package,**arguments)
            for changes in ({'package_role':'selected_policy'},{'baseline_id':'undeclared'},
                            {'recommendation_eligible':True},{'reference_declaration_sha256':'0'*64}):
                bad=dict(deepcopy(package),**changes)
                bad['package_sha256']=fingerprint({k:v for k,v in bad.items() if k!='package_sha256'})
                with pytest.raises(ValueError):verify_frozen_replay(binding=bad,**arguments)
        selected_seals={};reference_seals={}
        for event in row['result']['event_journal']:
            if event['kind']=='selection_seal':selected_seals[event['selection_seal_sha256']]=event
            elif event['kind']=='baseline_seal':reference_seals[event['reference_seal_sha256']]=event
            else:
                assert selected_seals[event['selection_seal_sha256']]['sequence']<event['sequence']
                assert reference_seals[event['reference_seal_sha256']]['sequence']<event['sequence']
        reliability=row['result']['reliability'];phase=reliability['phases']['funded']
        assert reliability['production_qualified'] is False
        assert phase['coverage']['historical_outer_blocks']==2
        assert phase['scalar_metrics']['mean_cash_received']==0
        comparison,=phase['baseline_comparisons']
        assert comparison['paired_mean_improvement']==0
        assert [p['improvement'] for p in comparison['pairs']]==[0,0]
        assert comparison['decision']=='THRESHOLD_NOT_MET'
        assert comparison['historical_interval']['interval']==[0,0]
        names=('report.json','baseline_results.json','reliability.json','reliability_folds.csv','baseline_comparison.csv','analysis.zip')
        exports={name:client.get(PREFIX+'/'+id+'/exports/'+name).content for name in names}
        assert json.loads(exports['reliability.json'])==reliability
        assert len(list(csv.DictReader(io.StringIO(exports['baseline_comparison.csv'].decode()))))==2
    def forbidden(*args,**kwargs):pytest.fail('Opening saved references/reliability recomputed a result')
    monkeypatch.setattr('alphaquest.robust_research.run_backtest',forbidden)
    monkeypatch.setattr('alphaquest.prop.funded_optimization.optimize_funded',forbidden)
    monkeypatch.setattr('alphaquest.research_reliability.consolidate_reliability',forbidden)
    with TestClient(create_app(tmp_path/'datasets.sqlite3')) as client:
        assert client.get(PREFIX+'/'+id).json()['status']=='complete'
        for name,content in exports.items():assert client.get(PREFIX+'/'+id+'/exports/'+name).content==content


def test_no_qualified_choice_still_measures_unresolved_predeclared_evaluation_reference(tmp_path,monkeypatch):
    with TestClient(create_app(tmp_path/'datasets.sqlite3')) as client:
        _,job,records=save_grid(client);body=baseline_body(client,job,records,'evaluation',no_qualified=True)
        def forbidden(*args,**kwargs):pytest.fail('Reference admission must not invoke a selector')
        monkeypatch.setattr('alphaquest.robust_research.select_evaluation',forbidden)
        row=run(client,save(client,body)['campaign_id'])
        for fold in row['result']['folds']:
            assert fold['economic_selection']['status']=='NO_QUALIFIED_CONFIGURATION'
            assert fold['chronological_replay']['items']==[]
            reference,=fold['baseline_results']
            assert reference['edge_qualification']['status']=='FAIL'
            assert reference['training_forecast']['status']!='estimated'
            assert Decimal(reference['chronological_replay']['paid_fees'])==30
            assert reference['chronological_replay']['censored']
        assert row['result']['reliability']['status']=='INSUFFICIENT_EVIDENCE'


def test_reference_child_cancel_resume_is_immutable_before_any_outer_access(tmp_path,monkeypatch):
    with TestClient(create_app(tmp_path/'datasets.sqlite3')) as client:
        _,job,records=save_grid(client);body=baseline_body(client,job,records)
        id=save(client,body)['campaign_id'];analyses=client.app.state.prop_analyses
        original=analyses.run_phase_inline;entered=Event();release=Event();children=[]
        def pause_reference(*args,**kwargs):
            result=original(*args,**kwargs)
            if kwargs['training_context']['version']=='nested-phase-reference-v1':
                children.append(result['id'])
                if len(children)==1:entered.set();assert release.wait(20)
            return result
        monkeypatch.setattr(analyses,'run_phase_inline',pause_reference)
        assert client.post(PREFIX+'/'+id+'/run').status_code==202
        try:
            assert entered.wait(20),client.get(PREFIX+'/'+id).json()
            assert client.post(PREFIX+'/'+id+'/cancel').status_code==200
        finally:release.set()
        stopped=wait_research(client,id);assert stopped['status']=='error' and 'Cancelled' in stopped['error']
        with analyses.connect() as db:
            assert db.execute("SELECT count(*) FROM research_access_intervals WHERE campaign_id=? AND purpose IN ('outer_test','baseline_outer_test')",(id,)).fetchone()[0]==0
        original_bytes=(analyses.root/children[0]/'report.json').read_bytes()
        resumed=run(client,id)
        assert resumed['result']['folds'][0]['baseline_results'][0]['analysis_id']==children[0]
        assert (analyses.root/children[0]/'report.json').read_bytes()==original_bytes
        assert len(children)==2


def test_reference_preview_rejects_stale_duplicate_unsupported_and_unbounded_work(tmp_path):
    with TestClient(create_app(tmp_path/'datasets.sqlite3')) as client:
        _,job,records=save_grid(client);body=baseline_body(client,job,records);cases=[]
        bad=deepcopy(body);bad['baselines'][0]['source_configuration_id']='f'*64;cases.append(bad)
        bad=deepcopy(body);bad['baselines'][0]['profile']['daily_loss_limit']=False;cases.append(bad)
        bad=deepcopy(body);bad['baselines']*=2;cases.append(bad)
        bad=deepcopy(body);other=deepcopy(bad['baselines'][0]);other['id']='Same definition';bad['baselines'].append(other);cases.append(bad)
        bad=deepcopy(body);bad['baselines'][0]['policy']['micros']=True;cases.append(bad)
        bad=deepcopy(body);bad['baselines'][0]['policy']['sizing']=dict(policy={'kind':'fixed_dollar_risk','risk_dollars':'100'},initial_configured_capital='50000',planning_execution={'tick_size':'.25','commission_per_contract_per_side':'0'});cases.append(bad)
        bad=deepcopy(body);bad['economic_studies'][0]['simulation']['simulations']=100000;cases.append(bad)
        for malformed in ('not-a-number',{},[]):
            bad=deepcopy(body);bad['reliability']['minimum_baseline_mean_improvement']=malformed;cases.append(bad)
        for invalid in cases:
            response=client.post(PREFIX+'/preview',json=invalid)
            assert response.status_code==422,response.text
        assert client.get('/api/backtests').json()['total']==2
        assert client.get(PREFIX).json()['items']==[]
