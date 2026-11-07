"""Normal saved campaign → complete procedure freeze → terminal applications."""
from copy import deepcopy
from decimal import Decimal
import json
import time
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest

from alphaquest.app import create_app
from test_robust_research_api import PREFIX, save_grid, declaration, save, run
from test_robust_economic_api import economic
from test_prop_phases import phase_history


def wait_application(client,id,app_id):
    deadline=time.monotonic()+90
    while time.monotonic()<deadline:
        response=client.get(f'{PREFIX}/{id}/applications/{app_id}')
        assert response.status_code==200,response.text
        value=response.json()
        if value['status'] not in ('queued','running'):
            assert value['status']=='complete',value
            return value
        time.sleep(.02)
    pytest.fail('Procedure application did not complete.')


def reservation(client,dataset,*,first='2026-01-23',last='2026-01-26'):
    body=dict(request_id=uuid4().hex,first_session=first,last_session=last,
              market_domain='CME:NASDAQ100',external_access='declared_not_inspected')
    url='/api/datasets/'+dataset['id']+'/research-reservations'
    preview=client.post(url+'/preview',json=body);assert preview.status_code==200,preview.text
    saved=client.post(url,json=body);assert saved.status_code==201,saved.text
    return saved.json(),preview.json()


def test_fresh_metadata_only_reservation_blocks_prices_and_retains_access(tmp_path):
    with TestClient(create_app(tmp_path/'datasets.sqlite3')) as client:
        params=dict(filename='SYNTHETIC-blind.csv',name='SYNTHETIC protected history',symbol='MNQ',
                    tick_size='.25',point_value='2',source_timezone='UTC',disclosure='metadata_only')
        response=client.post('/api/datasets',params=params,content=phase_history(20))
        assert response.status_code==201,response.text
        dataset=response.json();assert dataset['preview']==[] and dataset['disclosure']=='metadata_only'
        saved,preview=reservation(client,dataset,first='2026-01-05',last='2026-01-06')
        assert preview['access']['status']=='ELIGIBLE_UNDER_DECLARED_LOCAL_SCOPE'
        assert not preview['access']['untouched_certificate']
        assert client.get('/api/datasets/'+dataset['id']).json()['preview']==[]
        assert client.get('/api/datasets/'+dataset['id']+'/csv').status_code==409
        release=client.post('/api/datasets/'+dataset['id']+'/research-reservations/'+saved['id']+'/release',
            json=dict(request_id=uuid4().hex,reason='Explicitly inspect this history'))
        assert release.status_code==200,release.text
        assert client.get('/api/datasets/'+dataset['id']+'/csv').status_code==200
        body=dict(saved['declaration']);body.pop('dataset_id');body['request_id']=uuid4().hex
        check=client.post('/api/datasets/'+dataset['id']+'/research-reservations/preview',json=body)
        assert check.json()['access']['status']=='PREVIOUSLY_ACCESSED'


@pytest.mark.parametrize('with_reference',[False,True])
def test_complete_procedure_reruns_terminal_then_final_without_last_fold_promotion(tmp_path,monkeypatch,with_reference):
    with TestClient(create_app(tmp_path/'datasets.sqlite3')) as client:
        dataset,job,records=save_grid(client)
        reserved,preview=reservation(client,dataset)
        assert preview['access']['status']=='ELIGIBLE_UNDER_DECLARED_LOCAL_SCOPE',preview['access']
        body=declaration(job,records,economic_studies=[economic(client,'funded')])
        if with_reference:
            initial=client.post(PREFIX+'/preview',json=body).json()
            selected=next(c for c in initial['candidates'] if c['parameters']['green_bar_count']==1)
            body['baselines']=[dict(id='One MNQ reference',source_configuration_id=selected['id'],phase='funded',
                profile=body['economic_studies'][0]['profiles'][0],policy=dict(micros=1),required=True)]
        saved=save(client,body);id=saved['campaign_id'];completed=run(client,id)
        original=client.get(f'{PREFIX}/{id}/exports/report.json').content
        plan=completed['plan'];assert plan['session_inventory']['sessions'][-1]=='2026-01-22'
        args=dict(reservation_id=reserved['id'],source_snapshot_id=dataset['id'])
        response=client.post(f'{PREFIX}/{id}/procedure/preview',json=args)
        assert response.status_code==200,response.text
        p=response.json();assert p['final_verification_available']
        assert p['terminal_plan']['train']['sessions']==plan['session_inventory']['sessions'][-10:-2]
        freeze=dict(args,procedure_id=uuid4().hex,expected_preview_sha256=p['preview_sha256'])
        response=client.post(f'{PREFIX}/{id}/procedure/freeze',json=freeze)
        assert response.status_code==201,response.text
        procedure=response.json();assert len(procedure['algorithm']['configurations'])==2
        assert client.post(f'{PREFIX}/{id}/procedure/freeze',json=freeze).json()==procedure
        final_args=dict(procedure_sha256=procedure['procedure_sha256'],reservation_id=reserved['id'],source_snapshot_id=dataset['id'])
        checked=client.post(f'{PREFIX}/{id}/final-verification/preview',json=final_args)
        assert checked.status_code==200,checked.text
        app_id=uuid4().hex;request=dict(final_args,request_id=app_id,expected_preview_sha256=checked.json()['preview_sha256'])
        response=client.post(f'{PREFIX}/{id}/final-verification/run',json=request)
        assert response.status_code==202,response.text
        application=wait_application(client,id,app_id);result=application['result']
        assert result['final_verification']['status']=='COMPLETE_UNRESELECTED_ASSESSMENT'
        assert result['terminal_plan']['application_role']=='final_fit' and 'index' not in result['terminal_plan']
        assert result['qualification']['approved_ids']==[c['id'] for c in plan['candidates']]
        assert all(Decimal(row['metrics']['mean_session_net']) in (Decimal('100'),Decimal('300')) for row in result['qualification']['candidates'])
        phase=result['economic_selection']['phases'][0];assert len(phase['frozen_packages'])==4
        assert all(p['schema_version']=='procedure-phase-freeze-v1' for p in phase['frozen_packages'])
        for item in result['final_verification']['replay']['items']:
            assert Decimal(item['result']['cash_received'])==0
            record=client.get('/api/backtests/'+item['outer_run_id']).json()
            assert record['run_metadata']['research']['role']=='final_holdout'
            assert 'outer_fold' not in record['run_metadata']['research']
        if with_reference:
            reference=result['baseline_results'][0]
            assert reference['recommendation_eligible'] is False
            assert reference['frozen_package']['schema_version']=='procedure-phase-freeze-v1'
            record=client.get('/api/backtests/'+reference['outer_run_id']).json()
            assert record['run_metadata']['research']['role']=='final_holdout_reference'
            assert 'outer_fold' not in record['run_metadata']['research']
        assert result['recommendation'][0]['status']=='NO_QUALIFIED_DEPLOYMENT_CANDIDATE'
        assert client.get(f'{PREFIX}/{id}/exports/report.json').content==original
        current_id=uuid4().hex
        response=client.post(f'{PREFIX}/{id}/development-selection/run',json=dict(request_id=current_id,procedure_sha256=procedure['procedure_sha256']))
        assert response.status_code==202,response.text
        current=wait_application(client,id,current_id)
        assert current['result']['terminal_plan']['application_role']=='current_development'
        assert current['result']['final_verification']['replay'] is None
        assert current['result']['qualification']==result['qualification']
        raw=client.get(f'{PREFIX}/{id}/applications/{app_id}/exports/report.json').content
        def forbidden(*args,**kwargs):raise AssertionError('Saved report reopened by recomputing')
        monkeypatch.setattr(client.app.state.robust_research,'_qualify_window',forbidden)
        assert client.get(f'{PREFIX}/{id}/applications/{app_id}/exports/report.json').content==raw
        assert client.post(f'{PREFIX}/{id}/final-verification/run',json=request).json()['analysis_id']==application['analysis_id']


def test_reformatted_same_market_and_unknown_old_scope_cannot_be_cleaned(tmp_path):
    from alphaquest.datasets import DatasetStore
    old=tmp_path/'old'/'datasets.sqlite3';DatasetStore(old)
    with TestClient(create_app(old)) as client:
        raw=phase_history(20)
        response=client.post('/api/datasets',params=dict(filename='SYNTHETIC-old.csv',name='SYNTHETIC old scope',
            source_timezone='UTC',symbol='MNQ',tick_size='.25',point_value='2',disclosure='metadata_only'),content=raw)
        dataset=response.json();saved,preview=reservation(client,dataset)
        assert preview['access']['status']=='INSUFFICIENT_ACCESS_HISTORY'
        assert preview['access']['local_access_clear'] is None
    with TestClient(create_app(tmp_path/'new'/'datasets.sqlite3')) as client:
        params=dict(filename='SYNTHETIC-original.csv',name='SYNTHETIC local scope',source_timezone='UTC',symbol='MNQ',tick_size='.25',point_value='2')
        dataset=client.post('/api/datasets',params=params,content=raw).json()
        saved,_=reservation(client,dataset)
        alias=client.post('/api/datasets',params=dict(params,filename='SYNTHETIC-formatted.csv',name='SYNTHETIC formatting alias',symbol='NQ'),
            content=raw.replace(b'\n',b'\r\n')).json()
        assert alias['sha256']!=dataset['sha256']
        assert client.get('/api/datasets/'+alias['id']+'/csv').status_code==409
        assert client.delete('/api/datasets/'+dataset['id']).status_code==409
        client.post('/api/datasets/'+dataset['id']+'/research-reservations/'+saved['id']+'/release',
            json=dict(request_id=uuid4().hex,reason='Manual research access'))
        assert client.get('/api/datasets/'+alias['id']+'/csv').status_code==200
        body=dict(saved['declaration']);body.pop('dataset_id');body['request_id']=uuid4().hex
        again=client.post('/api/datasets/'+dataset['id']+'/research-reservations/preview',json=body)
        assert again.json()['access']['status']=='PREVIOUSLY_ACCESSED'


def test_terminal_cancel_resume_reuses_checked_steps_and_rehashed_procedure_rejects(tmp_path,monkeypatch):
    from threading import Event
    from alphaquest.prop.adapter import canonical
    from alphaquest.research_procedure import digest
    with TestClient(create_app(tmp_path/'datasets.sqlite3')) as client:
        dataset,job,records=save_grid(client)
        body=declaration(job,records,economic_studies=[economic(client,'funded')])
        id=save(client,body)['campaign_id'];run(client,id)
        preview=client.post(f'{PREFIX}/{id}/procedure/preview',json={}).json()
        response=client.post(f'{PREFIX}/{id}/procedure/freeze',json=dict(procedure_id=uuid4().hex,expected_preview_sha256=preview['preview_sha256']))
        assert response.status_code==201,response.text
        package=response.json();app_id=uuid4().hex;request=dict(request_id=app_id,procedure_sha256=package['procedure_sha256'])
        store=client.app.state.robust_research;original=store._phase_report;entered=Event();released=Event()
        def pause(*args,**kwargs):
            if 'application_id' in args[2]:
                entered.set();assert released.wait(10)
            return original(*args,**kwargs)
        monkeypatch.setattr(store,'_phase_report',pause)
        assert client.post(f'{PREFIX}/{id}/development-selection/run',json=request).status_code==202
        assert entered.wait(10)
        assert client.post(f'{PREFIX}/{id}/applications/{app_id}/cancel').status_code==200
        released.set()
        deadline=time.monotonic()+10
        while time.monotonic()<deadline:
            failed=client.get(f'{PREFIX}/{id}/applications/{app_id}').json()
            if failed['status']=='error':break
            time.sleep(.02)
        assert failed['status']=='error' and 'Cancelled' in failed['error']
        with store.analyses.connect() as db:
            saved_steps=list(db.execute('SELECT step_key,payload FROM robust_research_steps WHERE campaign_id=? AND step_key LIKE ?', (id,'application:'+app_id+':%')))
        assert saved_steps
        monkeypatch.setattr(store,'_phase_report',original)
        assert client.post(f'{PREFIX}/{id}/development-selection/run',json=request).status_code==202
        completed=wait_application(client,id,app_id)
        with store.analyses.connect() as db:
            assert all(db.execute('SELECT payload FROM robust_research_steps WHERE campaign_id=? AND step_key=?',(id,key)).fetchone()[0]==raw for key,raw in saved_steps)
        changed=deepcopy(package);changed['algorithm']['qualification']['minimum_trades']=1
        changed['algorithm_sha256']=digest(changed['algorithm']);changed['procedure_sha256']=digest({k:v for k,v in changed.items() if k!='procedure_sha256'})
        with store.analyses.connect() as db:db.execute('UPDATE research_procedures SET payload=? WHERE campaign_id=?',(canonical(changed),id))
        rejected=client.post(f'{PREFIX}/{id}/development-selection/run',json=dict(request,request_id=uuid4().hex))
        assert rejected.status_code==409 and 'authoritative' in rejected.text
        # Already saved application bytes remain independently inspectable.
        assert client.get(f'{PREFIX}/{id}/applications/{app_id}/exports/report.json').status_code==200


def test_consumed_interrupted_final_remains_incomplete_for_current_selection(tmp_path,monkeypatch):
    with TestClient(create_app(tmp_path/'datasets.sqlite3')) as client:
        dataset,job,records=save_grid(client);reserved,_=reservation(client,dataset)
        body=declaration(job,records,economic_studies=[economic(client,'funded')])
        id=save(client,body)['campaign_id'];run(client,id)
        args=dict(reservation_id=reserved['id'],source_snapshot_id=dataset['id'])
        preview=client.post(f'{PREFIX}/{id}/procedure/preview',json=args).json()
        response=client.post(f'{PREFIX}/{id}/procedure/freeze',json=dict(args,procedure_id=uuid4().hex,expected_preview_sha256=preview['preview_sha256']))
        assert response.status_code==201,response.text
        package=response.json();assert package['algorithm']['final_evidence']['require_final_holdout'] is False
        final_args=dict(procedure_sha256=package['procedure_sha256'],reservation_id=reserved['id'],source_snapshot_id=dataset['id'])
        check=client.post(f'{PREFIX}/{id}/final-verification/preview',json=final_args).json()
        store=client.app.state.robust_research
        def failure(*args,**kwargs):raise RuntimeError('Deliberate interruption after durable final authorization')
        monkeypatch.setattr(store,'_replay_economic',failure)
        app_id=uuid4().hex
        response=client.post(f'{PREFIX}/{id}/final-verification/run',json=dict(final_args,request_id=app_id,expected_preview_sha256=check['preview_sha256']))
        assert response.status_code==202,response.text
        deadline=time.monotonic()+30
        while time.monotonic()<deadline:
            failed=client.get(f'{PREFIX}/{id}/applications/{app_id}').json()
            if failed['status']=='error':break
            time.sleep(.02)
        assert failed['status']=='error' and 'Deliberate interruption' in failed['error']
        assert client.app.state.research_access.get(reserved['id'])['status']=='CONSUMED'
        current_id=uuid4().hex
        response=client.post(f'{PREFIX}/{id}/development-selection/run',json=dict(request_id=current_id,procedure_sha256=package['procedure_sha256']))
        assert response.status_code==202,response.text
        current=wait_application(client,id,current_id)
        assert current['result']['final_verification']['status']=='INCOMPLETE_REPLAY'
        recommendation=current['result']['recommendation'][0]
        assert recommendation['status']=='NO_QUALIFIED_DEPLOYMENT_CANDIDATE'
        assert 'frozen_final_verification_gate_not_met' in recommendation['evidence_blockers']
