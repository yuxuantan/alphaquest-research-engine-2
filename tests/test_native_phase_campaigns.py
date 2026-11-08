"""Actual native strategy forecasts in the existing independent campaign workflow."""
from copy import deepcopy
from hashlib import sha256
import json
from uuid import uuid4

import pytest
from alphaquest.app import create_app
from research_fixtures import ResearchClient
from test_native_replay_api import source, body as native_body, wait


def declaration(client, original, phase='funded', *, dynamic=False):
    profile=native_body(client,original,phase)['profile']
    horizon=3 if dynamic else 9
    settings=dict(calendar=dict(start_dates=['2026-01-26'],coverage_end='2026-02-05',closures=[],
        timezone='America/Chicago',version='explicit-synthetic-native-campaign-v1'),
        native_execution=dict(model='observed_contiguous_blocks_with_prior_prefix_v1',
            horizon_calendar_days=horizon,early_closes={},capture_paths=1))
    sampling=dict(block_weekdays=1)
    sizes=[3,10] if phase=='evaluation' else [1,3]
    if phase=='evaluation':sampling.update(chain_simulations=4,chain_seed=1729)
    else:settings.update(horizon_calendar_days=horizon,receipt_delay_calendar_days=2,
        bootstrap_replicates=100,bootstrap_seed=137)
    reference=dict(backtest_id=original['id'],sizes=sizes)
    if dynamic:
        policy=native_body(client,original)['sizing']
        dollar=deepcopy(policy);dollar['policy']=dict(kind='fixed_dollar_risk',risk_dollars='100')
        reference.update(sizes=[40],sizing_policies=[dollar,policy])
    return dict(campaign_id=uuid4().hex,phase=phase,profile=profile,sources=[reference],
        is_window=dict(first_session='2026-01-05',last_session='2026-01-07' if dynamic else '2026-01-13'),
        simulation=dict(simulations=4,seed=1729,max_micros=40),sampling=sampling,
        costs=dict(mode='source',instrument='MNQ'),search_settings=settings)


@pytest.mark.parametrize('phase,dynamic',[('funded',False),('evaluation',False),('funded',True)])
def test_native_campaign_complete_candidates_selection_freeze_and_immutable_reopen(tmp_path,phase,dynamic):
    library=tmp_path/'library'
    with ResearchClient(create_app(library/'datasets.sqlite3')) as client:
        original=source(client,**({} if dynamic else dict(days=7,payout=True)))
        source_bytes=client.get(f"/api/backtests/{original['id']}/exports/trades").content
        request=declaration(client,original,phase,dynamic=dynamic)
        created=client.post('/api/research-campaigns',json=request)
        assert created.status_code==201,created.text
        campaign=created.json();id=campaign['campaign_id']
        assert campaign['manifest']['candidate_search_count']==2
        assert client.post(f'/api/research-campaigns/{id}/check').status_code==200
        response=client.post(f'/api/research-campaigns/{id}/run');assert response.status_code==202,response.text
        analysis_id=response.json()['analysis_id'];wait(client,analysis_id)
        saved=client.get(f'/api/prop-analyses/{analysis_id}/downloads/report.json')
        report=saved.json();calc=report['calculations'];rows=calc['candidates']
        assert len(rows)==2 and len({r['candidate_id'] for r in rows})==2
        assert report['request']['native_execution']==request['search_settings']['native_execution']
        if phase=='evaluation':
            assert sorted(r['metrics']['cost_per_funded'] for r in rows)==[70,70]
            assert sorted(r['metrics']['expected_calendar_days_to_funded'] for r in rows)==[2,7]
            selected=calc['frontier'];assert len(selected)==1
            assert next(r for r in rows if r['candidate_id']==selected[0])['manifest']['configuration']['micros']==10
        elif dynamic:
            assert sorted(r['metrics']['expected_payouts'] for r in rows)==[0,0]
            assert {r['manifest']['configuration']['sizing']['policy']['kind'] for r in rows}=={'fixed_dollar_risk','percentage_risk'}
            selected=calc['ranking'];assert len(selected)==2
        else:
            assert sorted(r['metrics']['expected_payouts'] for r in rows)==[0,1500]
            selected=[calc['winner']]
            assert next(r for r in rows if r['candidate_id']==selected[0])['manifest']['configuration']['micros']==3
        frozen=client.post(f'/api/research-campaigns/{id}/freeze',json=dict(candidate_ids=selected,
            rationale='Synthetic independent cash and complete native membership verified.'))
        assert frozen.status_code==200,frozen.text
        assert frozen.json()['search_settings']['native_execution']==request['search_settings']['native_execution']
        assert client.delete('/api/prop-analyses/'+analysis_id).status_code==409
        assert client.delete('/api/backtests/'+original['id']).status_code==409
        assert client.post(f'/api/research-campaigns/{id}/run').json()['analysis_id']==analysis_id
        archive=client.get(f'/api/prop-analyses/{analysis_id}/downloads/analysis.zip').content
        files={}
        for name,item in report['files'].items():
            data=client.get(f'/api/prop-analyses/{analysis_id}/files/{name}').content
            files[name]=sha256(data).hexdigest();assert files[name]==item['sha256']
        assert client.get(f"/api/backtests/{original['id']}/exports/trades").content==source_bytes
        assert client.get('/api/backtests/'+original['id']).json()==original
        (tmp_path/'evidence.json').write_text(json.dumps(dict(library=str(library),source_id=original['id'],
            campaign_id=id,analysis_id=analysis_id,request=request,selection=selected,
            metrics=[dict(candidate_id=r['candidate_id'],configuration=r['manifest']['configuration'],metrics=r['metrics']) for r in rows],
            files=files,report_sha256=sha256(saved.content).hexdigest(),zip_sha256=sha256(archive).hexdigest()),indent=2))
    with ResearchClient(create_app(library/'datasets.sqlite3')) as client:
        assert client.get(f'/api/prop-analyses/{analysis_id}/downloads/report.json').content==saved.content
        assert client.get(f'/api/prop-analyses/{analysis_id}/downloads/analysis.zip').content==archive


def source_with_complete_oos(client):
    from datetime import datetime,timedelta
    from native_replay_fixtures import source_bytes,parameter_values
    from test_optimization import wait_job
    raw=source_bytes(days=5,payout=True)
    lines=raw.decode().splitlines();later=[]
    for line in lines[1:]:
        cells=line.split(',');cells[0]=(datetime.strptime(cells[0],'%m/%d/%Y')+timedelta(days=21)).strftime('%m/%d/%Y')
        later.append(','.join(cells))
    data=('\n'.join(lines+later)+'\n').encode()
    uploaded=client.post('/api/datasets',params=dict(filename='synthetic-native-split.csv',
        name='SYNTHETIC complete IS and manual OOS MNQ sessions',symbol='MNQ',source_timezone='UTC',
        tick_size='.25',point_value='2'),content=data)
    assert uploaded.status_code==201,uploaded.text
    values=parameter_values()
    response=client.post('/api/optimizations',json=dict(dataset_id=uploaded.json()['id'],method='exhaustive',
        workers=1,automatic_prop=False,strategy_id='vwap_pullback_risk_sizing',
        parameter_ranges={k:dict(start=v,end=v,step='0' if isinstance(v,str) else 0) for k,v in values.items()},
        execution_settings=dict(initial_capital='10000',slippage_ticks=0,commission_per_contract_per_side='0'),
        sample_split=dict(mode='dates',is_start='2026-01-04',is_end='2026-01-09',oos_start='2026-01-25',oos_end='2026-01-30')))
    assert response.status_code==202,response.text
    job=wait_job(client,response.json()['id']);assert job['status']=='complete',job
    row,=client.get('/api/optimizations/'+job['id']+'/results').json()['items']
    return client.get('/api/backtests/'+row['run_id']).json()


def test_native_manual_oos_is_actual_chronology_with_frozen_horizon_and_no_reselection(tmp_path):
    from fastapi.testclient import TestClient
    library=tmp_path/'library'
    with TestClient(create_app(library/'datasets.sqlite3')) as client:
        original=source_with_complete_oos(client)
        request=declaration(client,original)
        request['is_window']['last_session']='2026-01-09'
        request['search_settings']['horizon_calendar_days']=7
        request['search_settings']['native_execution']['horizon_calendar_days']=7
        request['search_settings']['calendar'].update(start_dates=['2026-01-12'],coverage_end='2026-01-19')
        response=client.post('/api/research-campaigns',json=request);assert response.status_code==201,response.text
        id=response.json()['campaign_id']
        response=client.post(f'/api/research-campaigns/{id}/run');assert response.status_code==202,response.text
        wait(client,response.json()['analysis_id'])
        selected=client.get(f'/api/research-campaigns/{id}/exports/results.json').json()['winner']
        frozen=client.post(f'/api/research-campaigns/{id}/freeze',json=dict(candidate_ids=[selected],rationale='Predeclared synthetic frozen native receipt comparison.'))
        assert frozen.status_code==200,frozen.text
        frozen_bytes=frozen.content
        response=client.post(f'/api/research-campaigns/{id}/assessments',json=dict(request_id=uuid4().hex))
        assert response.status_code==202,response.text
        attempt=response.json();analysis_id=attempt['analysis_id'];wait(client,analysis_id)
        saved=client.get(f'/api/prop-analyses/{analysis_id}/downloads/report.json');report=saved.json()
        calc=report['calculations'];row,=calc['candidates']
        assert calc['selection_status']=='assessment_only_no_reselection'
        assert not calc.get('ranking') and not calc.get('winner')
        assert row['frozen_candidate_id']==selected
        actual=row['native_chronological_replay']
        assert actual['historical_paths']==1 and actual['horizon_observations_complete'] is True
        assert float(actual['cash_received'])==1500 and float(actual['pending_cash'])==0
        assert actual['payout_events'][0]['request_date']=='2026-01-30'
        assert actual['payout_events'][0]['receipt_date']=='2026-02-01'
        child=row['native_backtest_id']
        trades=client.get(f'/api/backtests/{child}/trades').json()['items']
        assert len(trades)==5 and all(t['contracts']==3 for t in trades)
        assert all(t['entry_time_utc'][:10] in ['2026-01-26','2026-01-27','2026-01-28','2026-01-29','2026-01-30'] for t in trades)
        assert report['native_backtests'][child]['record']['id']==child
        assert f'native_backtests/{child}/native_account_control.json' in report['files']
        assert client.delete('/api/backtests/'+child).status_code==409
        assert client.get(f'/api/research-campaigns/{id}/exports/frozen_package.json').json()==json.loads(frozen_bytes)
        # Reusing the same manual request must verify both the live child
        # catalogue manifest and its files against the saved capture.
        store=client.app.state.prop_analyses
        assert store.native_children_unchanged(client.app.state.runs,analysis_id)
        retry=dict(request_id=attempt['request_id'])
        assert client.post(f'/api/research-campaigns/{id}/assessments',json=retry).status_code==202
        with client.app.state.runs.connect() as db:
            original_manifest=db.execute('SELECT manifest FROM runs WHERE id=?',(child,)).fetchone()[0]
            changed=json.loads(original_manifest);changed['run_metadata']['research']['unverified_catalogue_edit']=True
            db.execute('UPDATE runs SET manifest=? WHERE id=?',(json.dumps(changed),child))
        try:
            assert not store.native_children_unchanged(client.app.state.runs,analysis_id)
            repeated=client.post(f'/api/research-campaigns/{id}/assessments',json=retry)
            assert repeated.status_code==409 and 'capture changed' in repeated.text,repeated.text
            assert client.get(f'/api/prop-analyses/{analysis_id}/downloads/report.json').content==saved.content
        finally:
            with client.app.state.runs.connect() as db:
                db.execute('UPDATE runs SET manifest=? WHERE id=?',(original_manifest,child))
        assert store.native_children_unchanged(client.app.state.runs,analysis_id)
        (tmp_path/'evidence.json').write_text(json.dumps(dict(library=str(library),source_id=original['id'],campaign_id=id,
            analysis_id=analysis_id,controlled_oos_child=child,request=request,
            expected=dict(cash_received=1500,request_date='2026-01-30',receipt_date='2026-02-01',quantity=3,trades=5),
            report_sha256=sha256(saved.content).hexdigest()),indent=2))
