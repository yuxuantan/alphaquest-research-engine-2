"""Normal-product causal sizing with independent, declared synthetic outcomes."""
from copy import deepcopy
from dataclasses import asdict
from decimal import Decimal
from hashlib import sha256
import csv
import io
import json
from uuid import uuid4
import zipfile

import pytest

from alphaquest.app import create_app
from alphaquest.prop.phase_profiles import (EvaluationProfile, EvaluationSamplingConfig,
    FundedProfile, SavedTradeSource, SamplingConfig, SimulationConfig, SourceCosts,
    SizingConfiguration, SizingTrace, rule_version)
from alphaquest.prop.phase_search import PhaseCalendar
from alphaquest.prop.evaluation_optimization import EvaluationCandidate, EvaluationSearch, AcquisitionCalendar
from alphaquest.prop.funded_optimization import FundedCandidate, FundedSearch
from research_fixtures import ResearchClient
from sizing_fixtures import sizing_document, sizing_bytes, sizing_configuration
from test_canonical_trades import raw
from test_prop_analysis_api import wait
from test_prop_phases import save_source
from test_trade_imports import save, snapshot


def search_request(source_id, phase='funded', configurations=None, micros=40):
    configurations=configurations or [sizing_configuration(), sizing_configuration('percentage_risk'),
                                      sizing_configuration(risk_dollars='1')]
    candidates=[]
    for configuration in configurations:
        common=dict(source=SavedTradeSource(source_id),micros=micros,
            simulation=SimulationConfig(simulations=8,seed=42,max_micros=40),costs=SourceCosts(mode='source'),
            sizing=SizingConfiguration(**configuration) if configuration is not None else None)
        if phase=='evaluation':
            candidates.append(EvaluationCandidate(profile=EvaluationProfile('apex-50k-eod',rule_version('apex-50k-eod'),'30','40'),
                sampling=EvaluationSamplingConfig(block_weekdays=1,chain_simulations=8),**common))
        else:
            candidates.append(FundedCandidate(profile=FundedProfile('apex-50k-eod',rule_version('apex-50k-eod')),
                sampling=SamplingConfig(block_weekdays=1),**common))
    if phase=='evaluation':
        search=EvaluationSearch(source_id,tuple(candidates),AcquisitionCalendar(('2026-01-05',),'2037-01-01'))
    else:
        search=FundedSearch(source_id,tuple(candidates),PhaseCalendar(('2026-01-05',),'2037-01-01'),
            horizon_calendar_days=2,receipt_delay_calendar_days=0,bootstrap_replicates=100)
    return json.loads(json.dumps(asdict(search)))


def launch(client,request):
    checked=client.post('/api/prop-analyses/check',json=request)
    assert checked.status_code==200,checked.text
    started=client.post('/api/prop-analyses',json=request)
    assert started.status_code==202,started.text
    id=started.json()['id'];result=wait(client,id)
    assert result['status']=='complete',result
    response=client.get(f'/api/prop-analyses/{id}/downloads/report.json')
    assert response.status_code==200,response.text
    return checked.json(),response


def provenance(candidate):
    return candidate.get('provenance') or candidate['component']['provenance']


@pytest.mark.parametrize('phase',['evaluation','funded'])
def test_normal_import_check_run_download_reopen_and_independent_sizing(tmp_path,monkeypatch,phase):
    content=sizing_bytes();database=tmp_path/'datasets.sqlite3'
    with ResearchClient(create_app(database)) as client:
        source=save(client,content,filename='SYNTHETIC-causal-sizing.json')
        original=snapshot(tmp_path/'backtest_runs'/source['id'])
        def forbidden(*args,**kwargs):pytest.fail('Opposite phase or legacy joint calculation was invoked.')
        monkeypatch.setattr('alphaquest.prop.joint_sizing.select',forbidden)
        if phase=='evaluation':
            monkeypatch.setattr('alphaquest.prop.funded_profiles.simulate_dated_funded_profile',forbidden)
            monkeypatch.setattr('alphaquest.prop.native_analysis.account_backend',forbidden)
        else:
            monkeypatch.setattr('alphaquest.prop.evaluation_profiles.simulate_evaluation_profile',forbidden)
            monkeypatch.setattr('alphaquest.prop.native_analysis.evaluation_model',forbidden)
        request=search_request(source['id'],phase)
        checked,response=launch(client,request);report=response.json();id=report['id']
        rows=report['calculations']['candidates'];assert len(rows)==3
        expectations={}
        for row in rows:
            sizing=provenance(row)['sizing'];policy=sizing['configuration']['policy']
            decisions=sizing['decisions'];first=[d for d in decisions if d['path_index']==0 and d['session_index']==1]
            assert len(first)==3
            if policy['kind']=='percentage_risk':
                quantities=[10,9,5]
                assert [Decimal(d['decision']['denominator_value']) for d in first]==[50000,49900,50080]
                assert Decimal(first[-1]['state_after']['equity_change_from_initial'])==80
                label='current_balance'
            elif policy['risk_dollars']=='100':
                quantities=[10,10,5];label='fixed_dollars'
                assert Decimal(first[-1]['state_after']['equity_change_from_initial'])==100
            else:
                quantities=[0,0,0];label='skip'
                assert all(d['action']=='skip' and d['state_after']==d['state_before'] for d in decisions)
                assert sizing['summary']['trade_count']==0
            assert [d['quantity'] for d in first]==quantities
            assert sizing['trace_complete'] and sizing['summary']['decision_count']==len(decisions)
            assert all(d['source_trade_id'].startswith('SYNTHETIC-') for d in decisions)
            assert row['manifest']['source']['external_assumptions']['sizing_invariance_verified'] is False
            if phase=='evaluation':
                assert row['component']['evaluation']['passed']==0
                assert row['metrics']['cost_per_funded'] is None
                assert 'expected_payouts' not in row['metrics']
            else:
                assert row['metrics']['expected_payouts']==0
                assert all(path['observed_sessions']==2 and path['outcome']=='open' for path in row['paths'])
                assert {path['equity'] for path in row['paths']}=={160 if label=='current_balance' else 200 if label=='fixed_dollars' else 0}
                assert 'cost_per_funded' not in row['metrics']
            expectations[label]=dict(candidate_id=row['candidate_id'],first_quantities=quantities)
        archive=client.get(f'/api/prop-analyses/{id}/downloads/analysis.zip').content
        with zipfile.ZipFile(io.BytesIO(archive)) as zipped:
            assert zipped.read(f"inputs/{source['id']}/source.json")==content
            assert json.loads(zipped.read('calculations.json'))==report['calculations']
            summaries=json.loads(zipped.read('sizing_summary.json'));assert len(summaries)==3
            csv_rows=list(csv.DictReader(io.StringIO(zipped.read('sizing_decisions.csv').decode())))
            assert len(csv_rows)==sum(provenance(row)['sizing']['summary']['decision_count'] for row in rows)
            assert any(r['quantity']=='0' and r['action']=='skip' for r in csv_rows)
            for name,info in report['files'].items():assert sha256(zipped.read(name)).hexdigest()==info['sha256']
        reordered=deepcopy(request);reordered['candidates'].reverse()
        assert client.post('/api/prop-analyses',json=reordered).json()['id']==id
        assert snapshot(tmp_path/'backtest_runs'/source['id'])==original
        monkeypatch.setattr('alphaquest.prop.'+phase+'_optimization.optimize_'+phase,forbidden)
        assert client.get(f'/api/prop-analyses/{id}/downloads/report.json').content==response.content
        (tmp_path/'analysis.zip').write_bytes(archive)
        (tmp_path/'independent-expectations.json').write_text(json.dumps(dict(synthetic=True,phase=phase,source_id=source['id'],
            analysis_id=id,source_sha256=sha256(content).hexdigest(),expected=expectations,request=request),indent=2))
    with ResearchClient(create_app(database)) as reopened:
        assert reopened.get(f'/api/prop-analyses/{id}/downloads/report.json').content==response.content
        assert reopened.get(f"/api/backtests/{source['id']}/exports/source").content==content


@pytest.mark.parametrize('phase',['evaluation','funded'])
def test_explicit_fixed_contracts_preserve_old_phase_metrics_and_paths(tmp_path,phase):
    with ResearchClient(create_app(tmp_path/'datasets.sqlite3')) as client:
        source=save(client,sizing_bytes())
        request=search_request(source['id'],phase,[None,sizing_configuration('fixed_contracts')],micros=10)
        _,response=launch(client,request);rows=response.json()['calculations']['candidates']
        old=next(row for row in rows if row['manifest']['configuration']['sizing'] is None)
        explicit=next(row for row in rows if row['manifest']['configuration']['sizing'] is not None)
        assert old['metrics']==explicit['metrics'] and old['paths']==explicit['paths']
        if phase=='evaluation':
            for field in ('evaluation','acquisition','outcomes','duration_weekdays','censoring'):
                assert old['component'][field]==explicit['component'][field]
        assert {d['quantity'] for d in provenance(explicit)['sizing']['decisions']}=={10}


@pytest.mark.parametrize('phase',['evaluation','funded'])
def test_sizing_identity_captures_policy_costs_cap_and_explicit_base(tmp_path,phase):
    from alphaquest.prop import evaluation_optimization,funded_optimization
    module=evaluation_optimization if phase=='evaluation' else funded_optimization
    with ResearchClient(create_app(tmp_path/'datasets.sqlite3')) as client:
        source=save(client,sizing_bytes());request=search_request(source['id'],phase,[sizing_configuration()])
        keys=[];candidate_ids=[]
        variants=[request]
        for change in ('dollars','planning_cost','ceiling','reference'):
            variant=deepcopy(request);candidate=variant['candidates'][0]
            if change=='dollars':candidate['sizing']['policy']['risk_dollars']='99'
            elif change=='planning_cost':candidate['sizing']['planning_execution']['commission_per_contract_per_side']='1'
            elif change=='ceiling':candidate['micros']=3
            else:candidate['sizing']=sizing_configuration('percentage_risk',reference='initial_configured_capital')
            variants.append(variant)
        for variant in variants:
            search=module.parse_request(variant);checks=module.check_search(client.app.state.runs,search)
            candidate_ids.append(checks[0]['candidate_id']);keys.append(module.search_key(search,checks))
        assert len(set(candidate_ids))==len(set(keys))==5
        assert 'sizing_runtime.py' in module.implementation_identity()['files']
        assert '../canonical_trades.py' in module.implementation_identity()['files']


@pytest.mark.parametrize('case,reason',[
    ('unknown','Invalid'),('wrong_capital','50000'),('observed_fill','Extra inputs'),
    ('opposite_phase','Invalid'),('future_stop','known'),('invariance','invariance'),
    ('oos','declared IS'),('missing_stop','causal'),('off_tick','tick')])
def test_phase_source_and_sizing_contract_rejections(tmp_path,case,reason):
    with ResearchClient(create_app(tmp_path/'datasets.sqlite3')) as client:
        document=sizing_document()
        if case=='invariance':document['manifest']['execution']['sizing_path_invariance']='unverified'
        elif case=='oos':document['manifest']['research']['phase']='oos'
        elif case=='missing_stop':document['payload']['trades'][0]['initial_stop']=None
        elif case=='off_tick':document['payload']['trades'][0]['initial_stop']['price']='95.125'
        elif case=='future_stop':document['payload']['trades'][0]['initial_stop']['known_at_utc']='2026-01-05T15:01:00Z'
        if case=='future_stop':
            rejected=client.post('/api/backtests/imports',params={'filename':'SYNTHETIC-invalid.json'},content=raw(document))
            assert rejected.status_code==422 and reason.lower() in rejected.text.lower()
            return
        source=save(client,raw(document));request=search_request(source['id'],'funded',[sizing_configuration()])
        config=request['candidates'][0]['sizing']
        if case=='unknown':config['selected_after_outcome']=True
        elif case=='wrong_capital':config['initial_configured_capital']='10000'
        elif case=='observed_fill':config['planning_execution']['actual_entry_fill']='100'
        elif case=='opposite_phase':request['candidates'][0]['profile']['activation_fee']='40'
        rejected=client.post('/api/prop-analyses/check',json=request)
        assert rejected.status_code==422,rejected.text
        assert reason.lower() in rejected.text.lower(),rejected.text


def test_native_dynamic_source_rejects_but_fixed_path_remains_usable(tmp_path):
    with ResearchClient(create_app(tmp_path/'datasets.sqlite3')) as client:
        source=save_source(client,days=2)
        dynamic=search_request(source['id'],'funded',[sizing_configuration()])
        rejected=client.post('/api/prop-analyses/check',json=dynamic)
        assert rejected.status_code==422 and 'rerun' in rejected.text
        fixed=search_request(source['id'],'funded',[sizing_configuration('fixed_contracts')],micros=10)
        assert client.post('/api/prop-analyses/check',json=fixed).status_code==200


def test_retained_trace_bound_keeps_complete_aggregate_counts():
    collector=SizingTrace(SizingConfiguration(**sizing_configuration()),limit=2)
    for quantity in [10,0,4,4,0]:
        collector(dict(quantity=quantity,reasons=['below_minimum_tradable_quantity'] if not quantity else []))
    result=collector.result()
    assert len(result['decisions'])==2 and not result['trace_complete']
    assert result['summary']==dict(decision_count=5,trade_count=3,skipped_count=2,min_quantity=0,max_quantity=10,
        quantity_counts={'10':1,'0':2,'4':2},reason_counts={'below_minimum_tradable_quantity':2})


def test_external_campaign_freezes_sizing_family_but_rejects_native_oos_launch(tmp_path):
    from test_research_campaigns import create,run
    with ResearchClient(create_app(tmp_path/'datasets.sqlite3')) as client:
        source=save(client,sizing_bytes());request=search_request(source['id'])
        campaign=dict(campaign_id=uuid4().hex,phase='funded',profile=request['candidates'][0]['profile'],
            sources=[dict(backtest_id=source['id'],sizes=[40],sizing_policies=[sizing_configuration(),sizing_configuration('percentage_risk')])],
            maximum_candidates=2,is_window=dict(first_session='2026-01-05',last_session='2026-01-06'),
            simulation=request['candidates'][0]['simulation'],sampling=request['candidates'][0]['sampling'],
            costs=request['candidates'][0]['costs'],search_settings={k:request[k] for k in ('calendar','horizon_calendar_days','receipt_delay_calendar_days','bootstrap_replicates')})
        saved=create(client,campaign);prefix=f"/api/research-campaigns/{saved['campaign_id']}"
        assert client.post(prefix+'/check').status_code==200
        run(client,saved['campaign_id'])
        results=client.get(prefix+'/exports/results.json').json()
        assert len(results['candidates'])==2
        ids=[row['candidate_id'] for row in results['candidates']]
        frozen=client.post(prefix+'/freeze',json=dict(candidate_ids=ids,rationale='Predeclared synthetic sizing family.'))
        assert frozen.status_code==200,frozen.text
        assert all(c['sizing'] is not None for c in frozen.json()['selected_candidates'])
        before=client.get(prefix+'/exports/frozen_package.json').content
        rejected=client.post(prefix+'/assessments',json=dict(request_id=uuid4().hex))
        assert rejected.status_code==422 and 'external OOS' in rejected.text,rejected.text
        assert client.get(prefix+'/assessments').json()['items']==[]
        assert client.get(prefix+'/exports/frozen_package.json').content==before


def test_native_frozen_family_distinguishes_policies_with_the_same_quantity_ceiling(tmp_path,monkeypatch):
    from test_campaign_assessments import saved_is
    from test_research_campaigns import create,run,declaration
    with ResearchClient(create_app(tmp_path/'datasets.sqlite3')) as client:
        source=saved_is(client)
        request=declaration(source,phase='funded')
        request['sources']=[dict(backtest_id=source['id'],sizes=[10],sizing_policies=[
            sizing_configuration('fixed_contracts',contracts=1),sizing_configuration('fixed_contracts',contracts=3)])]
        request['maximum_candidates']=2
        request['search_settings'].update(horizon_calendar_days=2,receipt_delay_calendar_days=0)
        campaign=run(client,create(client,request)['campaign_id'])
        prefix=f"/api/research-campaigns/{campaign['campaign_id']}"
        result=client.get(prefix+'/exports/results.json').json()
        selected=[row['candidate_id'] for row in result['candidates']]
        frozen=client.post(prefix+'/freeze',json=dict(candidate_ids=selected,rationale='Two explicit fixed policies, same declared maximum.'))
        assert frozen.status_code==200,frozen.text
        def forbidden(*args,**kwargs):pytest.fail('Frozen assessment must not rank policies again.')
        monkeypatch.setattr('alphaquest.prop.funded_optimization.rank_candidates',forbidden)
        response=client.post(prefix+'/assessments',json=dict(request_id=uuid4().hex))
        assert response.status_code==202,response.text
        id=response.json()['analysis_id'];assert wait(client,id)['status']=='complete',wait(client,id)
        report=client.get(f'/api/prop-analyses/{id}/downloads/report.json').json()
        assert report['calculations']['selection_status']=='assessment_only_no_reselection'
        candidates=report['calculations']['candidates']
        assert len(candidates)==2
        assert {row['manifest']['configuration']['micros'] for row in candidates}=={10}
        assert {row['manifest']['configuration']['sizing']['policy']['contracts'] for row in candidates}=={1,3}
