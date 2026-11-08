"""Normal robust product: all PASS configurations → phase reports → sealed outer."""
from copy import deepcopy
import csv
import io
from decimal import Decimal
from datetime import date
from hashlib import sha256
import json
from threading import Event

from fastapi.testclient import TestClient
import pytest

from alphaquest.app import create_app
from alphaquest.prop.adapter import canonical
from alphaquest.prop.phase_dispatch import module_for
from alphaquest.prop.phase_search import check_candidates, verify_training_context
from test_robust_research_api import PREFIX, declaration, save_grid, save, run, file_hashes, wait_research


def economic(client,phase):
    body=deepcopy(client.get(PREFIX+'/defaults').json()['economic_studies'][phase])
    body['policies']=[dict(micros=10),dict(micros=20)]
    body['simulation']['simulations']=8
    body['sampling']['block_weekdays']=1
    if phase=='evaluation':body['sampling']['chain_simulations']=8
    return body


def fingerprint(value):return sha256(canonical(value).encode()).hexdigest()


def test_normal_product_economic_selection_freeze_outer_and_reopen(tmp_path,monkeypatch):
    with TestClient(create_app(tmp_path/'datasets.sqlite3')) as client:
        dataset,job,records=save_grid(client)
        body=declaration(job,records,economic_studies=[economic(client,'evaluation'),economic(client,'funded')])
        preview=client.post(PREFIX+'/preview',json=body)
        assert preview.status_code==200,preview.text
        plan=preview.json()
        assert plan['estimated_backtests']==36
        assert plan['economic_plan']['maximum_phase_candidates']==16
        assert plan['economic_plan']['estimated_training_backtests']==4
        assert plan['economic_plan']['estimated_outer_backtests']==16
        for target in plan['economic_plan']['resolved_folds']:
            if target['phase']=='funded':
                window=next(f['test'] for f in plan['folds'] if f['index']==target['outer_fold_index'])
                assert target['horizon_calendar_days']==(date.fromisoformat(window['last_session'])-date.fromisoformat(window['first_session'])).days+1
        before=file_hashes(client.app.state.runs.root)
        id=save(client,body)['campaign_id']
        row=run(client,id);folds=row['result']['folds']
        assert len(folds)==2
        children=[];outer_ids=[]
        for fold in folds:
            selection=fold['economic_selection'];replay=fold['chronological_replay']
            assert selection['status']=='SELECTION_FROZEN'
            assert len(selection['membership']['configuration_ids'])==2
            assert selection['deployment_recommendation'] is None
            assert len(selection['phases'])==2
            assert replay['status']=='complete' and replay['mode']=='historical_chronological'
            assert replay['selection_seal_sha256']==selection['selection_seal_sha256']
            for phase in selection['phases']:
                children.append(phase['analysis_id'])
                child=client.get('/api/prop-analyses/'+phase['analysis_id']+'/downloads/report.json')
                assert child.status_code==200,child.text
                report=child.json();assert len(report['calculations']['candidates'])==4
                assert {c['micros'] for c in report['request']['candidates']}=={10,20}
                assert len({c['source']['source_backtest_id'] for c in report['request']['candidates']})==2
                assert report['training_context']==selection['training_context']
                for source in report['request']['candidates']:
                    record=client.get('/api/backtests/'+source['source']['source_backtest_id']).json()
                    assert record['run_metadata']['research']['phase']=='inner'
                    assert record['run_metadata']['research']['role']=='policy_train'
                assert client.delete('/api/prop-analyses/'+phase['analysis_id']).status_code==409
                if phase['phase']=='evaluation':
                    assert {r['metrics']['cost_per_funded'] for r in phase['training_forecasts']}=={70}
                    # Both positive 300/session signal policies reach $3000 in
                    # one session at 10/20 MNQ. Exact cost/time ties stay whole.
                    assert len(phase['frozen_packages'])==2
                else:
                    assert len(phase['frozen_packages'])==4
                    assert {r['metrics']['expected_funded_cash_payouts_within_horizon'] for r in phase['training_forecasts']}=={0}
            for observed in replay['items']:
                outer_ids.append(observed['outer_run_id'])
                record=client.get('/api/backtests/'+observed['outer_run_id']).json()
                research=record['run_metadata']['research']
                assert research['phase']=='outer' and research['role']=='outer_test'
                assert research['selection_seal_sha256']==selection['selection_seal_sha256']
                assert research['frozen_package_sha256']==observed['frozen_package_sha256']
                if observed['phase']=='evaluation':
                    assert Decimal(observed['result']['paid_fees'])==Decimal('70')
                    assert Decimal(observed['result']['net_cash'])==Decimal('-70')
                    assert observed['result']['evaluation_passed'] and observed['result']['censored']
                    assert not observed['result']['acquisition_completed']
                else:
                    assert Decimal(observed['result']['cash_received'])==0
                    assert Decimal(observed['result']['pending_cash'])==0
                assert client.delete('/api/backtests/'+record['id']).status_code==409
                assert client.post('/api/backtests/'+record['id']+'/oos',json={'request_id':body['campaign_id']}).status_code==409
        assert len(children)==4 and len(outer_ids)==12
        # Existing source reports remain byte-for-byte unchanged.
        after=file_hashes(client.app.state.runs.root)
        assert all(after[path]==hash for path,hash in before.items())
        url=PREFIX+'/'+id+'/exports/report.json';raw=client.get(url).content
        exports={name:client.get(PREFIX+'/'+id+'/exports/'+name).content for name in ('economic_selection.json','chronological_replay.json','analysis.zip')}
        with client.app.state.prop_analyses.connect() as db:
            steps=[json.loads(p) for (p,) in db.execute('SELECT payload FROM robust_research_steps WHERE campaign_id=?',(id,))]
            access=db.execute("SELECT purpose FROM research_access_intervals WHERE campaign_id=?",(id,)).fetchall()
        assert sum(step.get('kind')=='selection_seal' for step in steps)==2
        assert sum(step.get('kind')=='phase_analysis' for step in steps)==4
        assert sum(purpose=='outer_test' for (purpose,) in access)==12
        seals={}
        for event in row['result']['event_journal']:
            if event['kind']=='selection_seal':seals[event['selection_seal_sha256']]=event
            else:
                assert event['selection_seal_sha256'] in seals
                assert seals[event['selection_seal_sha256']]['sequence']<event['sequence']
                assert event['frozen_package_sha256'] in seals[event['selection_seal_sha256']]['frozen_package_sha256']
        assert not row['result']['readiness']['status']=='READY'
    def forbidden(*a,**k):pytest.fail('Saved report opening recomputed research')
    monkeypatch.setattr('alphaquest.robust_research.run_backtest',forbidden)
    monkeypatch.setattr('alphaquest.prop.evaluation_optimization.optimize_evaluation',forbidden)
    monkeypatch.setattr('alphaquest.prop.funded_optimization.optimize_funded',forbidden)
    monkeypatch.setattr('alphaquest.robust_research.select_evaluation',forbidden)
    monkeypatch.setattr('alphaquest.robust_research.select_funded',forbidden)
    with TestClient(create_app(tmp_path/'datasets.sqlite3')) as client:
        assert client.get(url).content==raw
        assert client.get(PREFIX+'/'+id).json()['status']=='complete'
        for name,value in exports.items():assert client.get(PREFIX+'/'+id+'/exports/'+name).content==value


def test_internal_training_context_integrity_and_public_rejection(tmp_path):
    with TestClient(create_app(tmp_path/'datasets.sqlite3')) as client:
        _,job,records=save_grid(client)
        body=declaration(job,records,economic_studies=[economic(client,'funded')])
        row=run(client,save(client,body)['campaign_id'])
        phase=row['result']['folds'][0]['economic_selection']['phases'][0]
        report=client.get('/api/prop-analyses/'+phase['analysis_id']+'/downloads/report.json').json()
        request=report['request'];search=module_for('funded').parse_request(request)
        ctx=report['training_context'];runs=client.app.state.runs
        assert verify_training_context(runs,search,ctx)==ctx['train_window']['sessions']
        assert len(check_candidates(runs,search,training_context=ctx))==4
        # This is server-only authority, never public phase JSON or IS relabel.
        response=client.post('/api/prop-analyses/check',json=request)
        assert response.status_code==422 and 'declared IS' in response.text
        forged=deepcopy(request);forged['training_context']=ctx
        assert client.post('/api/prop-analyses/check',json=forged).status_code==422
        for key in ('engine_identity','input_identity','qualification_sha256','information_cutoff_session'):
            bad=deepcopy(ctx);bad[key]='changed';bad['context_sha256']=fingerprint({k:v for k,v in bad.items() if k!='context_sha256'})
            with pytest.raises(ValueError,match='training context'):verify_training_context(runs,search,bad)
        bad=deepcopy(ctx);bad['qualified_configuration_ids'].pop();bad['context_sha256']=fingerprint({k:v for k,v in bad.items() if k!='context_sha256'})
        with pytest.raises(ValueError,match='membership|omit'):verify_training_context(runs,search,bad)
        bad=deepcopy(ctx);first=next(iter(bad['session_inventory']));bad['session_inventory'][first]=0
        bad['context_sha256']=fingerprint({k:v for k,v in bad.items() if k!='context_sha256'})
        with pytest.raises(ValueError,match='observed bars'):verify_training_context(runs,search,bad)
        from alphaquest.prop.phase_profiles import SavedTradeSource, FundedProfile, SourceCosts, ReplayWindow, verify_frozen_replay
        from alphaquest.prop.phase_search import PhaseCalendar
        fold=row['result']['folds'][0];observed=fold['chronological_replay']['items'][0]
        package=next(p for p in phase['frozen_packages'] if p['candidate_id']==observed['candidate_id'])
        config=package['configuration'];cal=deepcopy(package['calendar'])
        cal['start_dates']=tuple(cal['start_dates']);cal['closures']=tuple(cal['closures'])
        arguments=dict(runs=runs,source=SavedTradeSource(observed['outer_run_id']),phase='funded',
            profile=FundedProfile(**config['profile']),micros=config['micros'],max_micros=config['simulation']['max_micros'],
            costs=SourceCosts(**config['costs']),sizing=None,window=ReplayWindow(package['outer_window']['first_session'],package['outer_window']['cutoff_date_exclusive']),
            calendar=PhaseCalendar(**cal),receipt_delay_calendar_days=report['request']['receipt_delay_calendar_days'],
            receipt_amount_convention='kernel_entitlement_unrounded')
        verify_frozen_replay(binding=package,**arguments)
        for field in ('quantity','profile','phase','fold','source'):
            bad=deepcopy(package)
            if field=='quantity':bad['configuration']['micros']+=1
            elif field=='profile':bad['configuration']['profile']['daily_loss_limit']=False
            elif field=='phase':bad['phase']='evaluation'
            elif field=='fold':bad['outer_fold_index']+=1
            else:bad['configuration']['source']['source_backtest_id']=records[0]['id']
            bad['package_sha256']=fingerprint({k:v for k,v in bad.items() if k!='package_sha256'})
            with pytest.raises(ValueError):verify_frozen_replay(binding=bad,**arguments)
        training_file=client.app.state.prop_analyses.root/phase['analysis_id']/'source_checks.json'
        content=training_file.read_bytes();training_file.unlink()
        try:
            with pytest.raises((ValueError,OSError)):verify_frozen_replay(binding=package,**arguments)
        finally:training_file.write_bytes(content)
        train_id=next(iter(ctx['training_sources']));path=runs.root/train_id/'trades.csv';original=path.read_bytes()
        path.write_bytes(original+b'\n')
        try:
            with pytest.raises(ValueError,match='artifact'):verify_training_context(runs,search,ctx)
        finally:path.write_bytes(original)


def test_economic_preview_rejects_foreign_phase_dates_dynamic_and_count_changes(tmp_path):
    with TestClient(create_app(tmp_path/'datasets.sqlite3')) as client:
        _,job,records=save_grid(client)
        source=declaration(job,records,economic_studies=[economic(client,'funded')])
        cases=[]
        body=deepcopy(source);body['economic_studies']*=2;cases.append(body)
        body=deepcopy(source);body['economic_studies'][0]['search_settings']['horizon_calendar_days']=999;cases.append(body)
        body=deepcopy(source);body['economic_studies'][0]['search_settings']['calendar']['start_dates']=['2099-01-01'];cases.append(body)
        body=deepcopy(source);body['economic_studies'][0]['retry']={};cases.append(body)
        body=deepcopy(source);body['confirmed_economic_candidate_count']=999;cases.append(body)
        body=deepcopy(source);body['economic_studies'][0]['policies'][0]['sizing']=dict(policy=dict(kind='fixed_dollar_risk',risk_dollars='100'),
            initial_configured_capital='50000',planning_execution=dict(tick_size='.25',commission_per_contract_per_side='0'));cases.append(body)
        for body in cases:
            response=client.post(PREFIX+'/preview',json=body)
            assert response.status_code==422,response.text
        assert client.get('/api/backtests').json()['total']==2
        assert not client.get(PREFIX).json()['items']


def test_no_qualified_configuration_abstains_and_preserves_all_folds(tmp_path):
    with TestClient(create_app(tmp_path/'datasets.sqlite3')) as client:
        _,job,records=save_grid(client)
        body=declaration(job,records,economic_studies=[economic(client,'funded')])
        body['qualification']['minimum_mean_session_net']='1000'
        row=run(client,save(client,body)['campaign_id'])
        assert len(row['result']['folds'])==2
        for fold in row['result']['folds']:
            assert fold['economic_selection']['status']=='NO_QUALIFIED_CONFIGURATION'
            assert fold['economic_selection']['membership']['configuration_ids']==[]
            assert fold['economic_selection']['phases']==[]
            assert fold['chronological_replay']['items']==[]
            assert fold['outer_test_status']=='selection_abstained'
        assert len(row['result']['event_journal'])==2
        assert all(event['kind']=='selection_seal' for event in row['result']['event_journal'])
        assert client.get('/api/backtests').json()['total']==18


def test_completed_child_cancel_resume_no_same_worker_wait(tmp_path,monkeypatch):
    with TestClient(create_app(tmp_path/'datasets.sqlite3')) as client:
        _,job,records=save_grid(client)
        body=declaration(job,records,economic_studies=[economic(client,'evaluation'),economic(client,'funded')])
        id=save(client,body)['campaign_id'];analyses=client.app.state.prop_analyses
        original=analyses.run_phase_inline;entered=Event();release=Event();children=[]
        def pause_after_complete(*args,**kwargs):
            result=original(*args,**kwargs);children.append(result['id'])
            if len(children)==1:
                entered.set();assert release.wait(20)
            return result
        monkeypatch.setattr(analyses,'run_phase_inline',pause_after_complete)
        assert client.post(PREFIX+'/'+id+'/run').status_code==202
        try:
            assert entered.wait(20),'Inline child must complete on the parent worker without deadlock'
            assert analyses.get(children[0])['status']=='complete'
            assert client.delete('/api/prop-analyses/'+children[0]).status_code==409
            assert client.post(PREFIX+'/'+id+'/cancel').status_code==200
        finally:release.set()
        stopped=wait_research(client,id);assert stopped['status']=='error' and 'Cancelled' in stopped['error']
        with analyses.connect() as db:
            assert db.execute("SELECT count(*) FROM research_access_intervals WHERE campaign_id=? AND purpose='outer_test'",(id,)).fetchone()[0]==0
        first_report=(analyses.root/children[0]/'report.json').read_bytes()
        resumed=run(client,id)
        assert resumed['result']['folds'][0]['economic_selection']['phases'][0]['analysis_id']==children[0]
        assert (analyses.root/children[0]/'report.json').read_bytes()==first_report
        assert len(children)==4,'First completed child is reused; the other three independent phase children calculate'
        assert len(resumed['result']['folds'])==2


def no_trade_outer_source(*,missing=False):
    from test_prop_phases import phase_history
    raw=phase_history(20)
    rows=list(csv.reader(io.StringIO(raw.decode() if isinstance(raw,bytes) else raw)))
    output=[rows[0]]
    for row in rows[1:]:
        if missing and row[0]=='01/20/2026':continue
        if row[0] in ('01/19/2026','01/20/2026'):
            row[2:6]=['100','101','99','100'] # Actual observed doji bars; no strategy entry.
        output.append(row)
    stream=io.StringIO();csv.writer(stream,lineterminator='\n').writerows(output)
    return stream.getvalue().encode()


def test_generated_outer_all_no_trades_replays_real_observed_sessions(tmp_path):
    with TestClient(create_app(tmp_path/'datasets.sqlite3')) as client:
        _,job,records=save_grid(client,raw=no_trade_outer_source(),is_end='2026-01-20',oos_start='2026-01-21')
        body=declaration(job,records,economic_studies=[economic(client,'evaluation'),economic(client,'funded')])
        body['folds']['minimum_outer_folds']=1
        row=run(client,save(client,body)['campaign_id'])
        assert len(row['result']['folds'])==1
        fold=row['result']['folds'][0]
        assert fold['economic_selection']['status']=='SELECTION_FROZEN'
        assert fold['chronological_replay']['status']=='complete'
        for item in fold['chronological_replay']['items']:
            record=client.get('/api/backtests/'+item['outer_run_id']).json()
            assert record['summary']['trades_taken']==0
            assert record['run_metadata']['research']['window']['sessions']==['2026-01-19','2026-01-20']
            assert record['run_metadata']['selection']['row_count']==8
            output=item['result'];assert output['observations']['source_opportunities']==0
            if item['phase']=='evaluation':
                assert not output['evaluation_passed'] and output['censored']
                assert Decimal(output['paid_fees'])==30 and Decimal(output['paid_activation_fees'])==0
            else:
                assert output['observed_sessions']==2
                assert Decimal(output['cash_received'])==0 and Decimal(output['trading_profit'])==0
        assert len(fold['chronological_replay']['items'])==6


def test_unknown_missing_outer_session_is_not_filled_as_zero(tmp_path):
    with TestClient(create_app(tmp_path/'datasets.sqlite3')) as client:
        _,job,records=save_grid(client,raw=no_trade_outer_source(missing=True),is_end='2026-01-21',oos_start='2026-01-22')
        body=declaration(job,records,economic_studies=[economic(client,'funded')]);body['folds']['minimum_outer_folds']=1
        response=client.post(PREFIX+'/preview',json=body)
        assert response.status_code==422,response.text
        assert 'do not match the declared economic calendar' in response.text
        assert client.get('/api/backtests').json()['total']==2
