"""Frozen independent campaigns continue through ordinary OOS and prop APIs."""
from datetime import datetime,timedelta
from decimal import Decimal
import json
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest

from alphaquest.app import create_app
from native_replay_fixtures import source_bytes,parameter_values
from test_optimization import wait_job
from test_native_phase_campaigns import declaration
from test_native_replay_api import wait



def save_complete_native_split(client):
    # Five actual synthetic IS sessions and ten separately dated OOS sessions.
    # Source records retain the ordinary full-session native-data checks.
    training=source_bytes(days=5,payout=True).decode().splitlines()
    target=[]
    for line in source_bytes(days=10,payout=True).decode().splitlines()[1:]:
        cells=line.split(',');cells[0]=(datetime.strptime(cells[0],'%m/%d/%Y')+timedelta(days=21)).strftime('%m/%d/%Y')
        target.append(','.join(cells))
    data=('\n'.join(training+target)+'\n').encode()
    response=client.post('/api/datasets',params=dict(filename='SYNTHETIC-frozen-pair.csv',
        name='SYNTHETIC frozen Evaluation/Funded pair cash',symbol='MNQ',source_timezone='UTC',tick_size='.25',point_value='2'),content=data)
    assert response.status_code==201,response.text
    values=parameter_values();dataset=response.json()
    response=client.post('/api/optimizations',json=dict(dataset_id=dataset['id'],method='exhaustive',workers=1,
        automatic_prop=False,strategy_id='vwap_pullback_risk_sizing',
        parameter_ranges={k:dict(start=v,end=v,step='0' if isinstance(v,str) else 0) for k,v in values.items()},
        execution_settings=dict(initial_capital='10000',slippage_ticks=0,commission_per_contract_per_side='0'),
        sample_split=dict(mode='dates',is_start='2026-01-04',is_end='2026-01-09',oos_start='2026-01-25',oos_end='2026-02-06')))
    assert response.status_code==202,response.text
    job=wait_job(client,response.json()['id']);assert job['status']=='complete',job
    row,=client.get('/api/optimizations/'+job['id']+'/results').json()['items']
    return client.get('/api/backtests/'+row['run_id']).json()


def frozen_phase(client,parent,phase):
    body=declaration(client,parent,phase)
    body['sources'][0]['sizes']=[3]
    body['is_window']['last_session']='2026-01-09'
    body['simulation']['simulations']=2
    if phase=='evaluation':body['sampling']['chain_simulations']=2
    else:body['search_settings']['horizon_calendar_days']=14
    body['search_settings']['native_execution']['horizon_calendar_days']=14
    body['search_settings']['calendar'].update(start_dates=['2026-01-12'],coverage_end='2026-01-27')
    response=client.post('/api/research-campaigns',json=body);assert response.status_code==201,response.text
    id=response.json()['campaign_id']
    response=client.post(f'/api/research-campaigns/{id}/run');assert response.status_code==202,response.text
    wait(client,response.json()['analysis_id'])
    calculations=client.get(f'/api/research-campaigns/{id}/exports/results.json').json()
    candidate=(calculations['frontier'] if phase=='evaluation' else calculations['ranking'])[0]
    response=client.post(f'/api/research-campaigns/{id}/freeze',json=dict(candidate_ids=[candidate],
        rationale='Synthetic predefined pair selected on IS; manual OOS comparison is descriptive and unreselected.'))
    assert response.status_code==200,response.text
    package=response.json()
    frozen_bytes=client.get(f'/api/research-campaigns/{id}/exports/frozen_package.json').content
    return dict(campaign_id=id,package_sha256=package['package_sha256'],candidate_id=candidate),frozen_bytes


def test_existing_report_to_check_run_download_and_reopen_predefined_pair(tmp_path):
    library=tmp_path/'library'
    with TestClient(create_app(library/'datasets.sqlite3')) as client:
        parent=save_complete_native_split(client)
        evaluation,evaluation_bytes=frozen_phase(client,parent,'evaluation')
        funded,funded_bytes=frozen_phase(client,parent,'funded')
        # This normal explicit manual action precedes comparison. Pair Check
        # must never create another OOS run or alter either frozen selection.
        response=client.post('/api/backtests/'+parent['id']+'/oos',json=dict(request_id=uuid4().hex))
        assert response.status_code==201,response.text
        oos=response.json();prior=client.get('/api/backtests/'+parent['id']+'/oos').json()['used']
        request=dict(mode='predefined_lifecycle_comparison',request_id=uuid4().hex,
            window=dict(first_session='2026-01-26',cutoff_date_exclusive='2026-02-09'),
            pairs=[dict(id='Frozen 3-MNQ Evaluation then 3-MNQ Funded',
                evaluation=dict(evaluation,source_backtest_id=oos['id']),funded=dict(funded,source_backtest_id=oos['id']))])
        response=client.post('/api/prop-analyses/check',json=request)
        assert response.status_code==200,response.text
        assert response.json()['mode']==request['mode']
        assert client.get('/api/backtests/'+parent['id']+'/oos').json()['used']==prior
        response=client.post('/api/prop-analyses',json=request);assert response.status_code==202,response.text
        id=response.json()['id'];wait(client,id)
        saved=client.get('/api/prop-analyses/'+id+'/downloads/report.json');assert saved.status_code==200
        report=saved.json();row,=report['calculations']['pairs']
        assert report['calculations']['selection_status']=='comparison_only_no_selection'
        assert report['calculations']['winner'] is None
        assert Decimal(row['cash']['paid_fees'])==70
        assert Decimal(row['cash']['cash_received'])==1500
        assert Decimal(row['cash']['net_trader_cash'])==1430
        assert row['evaluation']['ready_date']=='2026-02-02'
        assert row['funded']['payout_events'][0]['request_date']=='2026-02-06'
        assert row['funded']['payout_events'][0]['receipt_date']=='2026-02-08'
        assert row['continuation_binding']['estimand']=='remaining_horizon_chronological_continuation'
        assert len(report['native_backtests'])==2
        assert all(client.delete('/api/backtests/'+child).status_code==409 for child in report['native_backtests'])
        assert client.delete('/api/backtests/'+parent['id']).status_code==409
        assert client.delete('/api/backtests/'+oos['id']).status_code==409
        duplicate=client.post('/api/prop-analyses',json=request)
        assert duplicate.status_code==202 and duplicate.json()['id']==id,duplicate.text
        changed_name=json.loads(json.dumps(request));changed_name['pairs'][0]['id']='Changed declaration'
        assert client.post('/api/prop-analyses',json=changed_name).status_code==409
        # Captured report remains readable while reuse fails closed on a live
        # child-manifest mutation, even if all child artifact bytes are intact.
        child_id=next(iter(report['native_backtests']))
        with client.app.state.runs.connect() as db:
            original_manifest=db.execute('SELECT manifest FROM runs WHERE id=?',(child_id,)).fetchone()[0]
            changed_manifest=json.loads(original_manifest);changed_manifest['audit_probe']='changed identity'
            db.execute('UPDATE runs SET manifest=? WHERE id=?',(json.dumps(changed_manifest),child_id))
        assert client.post('/api/prop-analyses',json=request).status_code==409
        assert client.get('/api/prop-analyses/'+id+'/downloads/report.json').content==saved.content
        with client.app.state.runs.connect() as db:
            db.execute('UPDATE runs SET manifest=? WHERE id=?',(original_manifest,child_id))
        assert client.get(f"/api/research-campaigns/{evaluation['campaign_id']}/exports/frozen_package.json").content==evaluation_bytes
        assert client.get(f"/api/research-campaigns/{funded['campaign_id']}/exports/frozen_package.json").content==funded_bytes
        changed=json.loads(json.dumps(request));changed['pairs'][0]['funded']['package_sha256']='0'*64
        assert client.post('/api/prop-analyses/check',json=changed).status_code==422
        unsupported=dict(request,monthly_budget='100')
        assert client.post('/api/prop-analyses/check',json=unsupported).status_code==422
        (tmp_path/'evidence.json').write_text(json.dumps(dict(source_id=parent['id'],oos_id=oos['id'],analysis_id=id,
            request=request,expected=dict(fees=70,received=1500,net=1430)),indent=2))
    with TestClient(create_app(library/'datasets.sqlite3')) as client:
        assert client.get('/api/prop-analyses/'+id+'/downloads/report.json').content==saved.content
        duplicate=client.post('/api/prop-analyses',json=request)
        assert duplicate.status_code==202 and duplicate.json()['id']==id,duplicate.text
