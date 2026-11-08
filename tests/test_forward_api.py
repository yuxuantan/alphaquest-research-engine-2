"""Complete current procedure → supplied paper observations → saved monitor."""
from copy import deepcopy
from datetime import datetime,timedelta,timezone
from decimal import Decimal
import json
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest
from alphaquest.app import create_app
from alphaquest.forward_reconcile import digest
from test_robust_research_api import PREFIX,save_grid,declaration,save,run
from test_robust_economic_api import economic
from test_research_procedure_api import wait_application
from tests.test_forward_reconcile import fixture


def current_policy(client):
    dataset,grid,records=save_grid(client,is_end='2026-01-26',oos_start='2026-01-27')
    study=economic(client,'funded');study['policies']=[dict(micros=3)]
    body=declaration(grid,records,economic_studies=[study])
    body['folds'].update(outer_train_sessions=6,outer_test_sessions=5,inner_train_sessions=2,
        inner_validation_sessions=2,purge_sessions=0,embargo_sessions=0)
    body['reliability']=dict(client.get(PREFIX+'/defaults').json()['reliability'],minimum_outer_blocks=2,
        minimum_calibration_blocks=2,historical_bootstrap_replicates=400)
    preview=client.post(PREFIX+'/preview',json=body);assert preview.status_code==200,preview.text
    candidate=next(c for c in preview.json()['candidates'] if c['parameters']['green_bar_count']==1)
    body['baselines']=[dict(id='Predeclared same-signal one MNQ',source_configuration_id=candidate['id'],
        phase='funded',profile=study['profiles'][0],policy=dict(micros=1),required=True)]
    saved=save(client,body);campaign_id=saved['campaign_id'];complete=run(client,campaign_id)
    reliability=complete['result']['reliability']['phases']['funded']
    assert reliability['status']=='ASSESSABLE_WITH_LIMITATIONS',reliability['reasons']
    assert reliability['scalar_metrics']['mean_cash_received']==1500
    assert reliability['baseline_comparisons'][0]['paired_mean_improvement']==1500
    preview=client.post(f'{PREFIX}/{campaign_id}/procedure/preview',json={});assert preview.status_code==200,preview.text
    freeze=client.post(f'{PREFIX}/{campaign_id}/procedure/freeze',json=dict(procedure_id=uuid4().hex,expected_preview_sha256=preview.json()['preview_sha256']))
    assert freeze.status_code==201,freeze.text
    application_id=uuid4().hex
    launched=client.post(f'{PREFIX}/{campaign_id}/development-selection/run',json=dict(request_id=application_id,procedure_sha256=freeze.json()['procedure_sha256']))
    assert launched.status_code==202,launched.text
    application=wait_application(client,campaign_id,application_id)
    recommendation,=application['result']['recommendation']
    assert recommendation['status']=='RESEARCH_CANDIDATE_ONLY',recommendation
    package,=recommendation['selected_packages']
    return dataset,campaign_id,application,package


def wait_monitor(client,analysis_id):
    client.app.state.prop_analyses.worker.submit(lambda:None).result(timeout=15)
    response=client.get('/api/prop-analyses/'+analysis_id)
    assert response.status_code==200,response.text
    assert response.json()['status']=='complete',response.json()
    response=client.get('/api/prop-analyses/'+analysis_id+'/downloads/report.json')
    assert response.status_code==200,response.text
    return response.json(),response.content


def test_current_policy_bound_paper_observation_exact_cash_authority_and_reopen(tmp_path,monkeypatch):
    database=tmp_path/'datasets.sqlite3'
    with TestClient(create_app(database)) as client:
        dataset,campaign_id,application,package=current_policy(client)
        monitor_id=uuid4().hex
        body=dict(monitor_id=monitor_id,name='SYNTHETIC supplied paper observation of current policy',observation_kind='paper',
            policy_binding=dict(campaign_id=campaign_id,application_id=application['application_id'],phase='funded',package_sha256=package['package_sha256']),
            source=dict(source_id='paper-fixture',label='SYNTHETIC supplied paper event fixture, no broker connection'),
            instrument=dict(symbol='MNQ',tick_size='.25',point_value='2'),thresholds=dict(maximum_position_contracts=3))
        checked=client.post('/api/forward-monitors/check',json=body);assert checked.status_code==200,checked.text
        assert checked.json()['policy_snapshot']['recommendation_status']=='RESEARCH_CANDIDATE_ONLY'
        assert checked.json()['policy_snapshot']['source_execution_settings']['point_value']=='2'
        for change in ({'phase':'evaluation'},{'package_sha256':'0'*64},{'application_id':uuid4().hex}):
            wrong=deepcopy(body);wrong['policy_binding'].update(change)
            assert client.post('/api/forward-monitors/check',json=wrong).status_code in (404,422)
        saved=client.post('/api/forward-monitors',json=body);assert saved.status_code==201,saved.text
        base='/api/forward-monitors/'+monitor_id
        # Independent incoming observations follow monitor creation. They do not
        # reuse or relabel source backtest trades or forecast paths.
        start=datetime.now(timezone.utc);events=fixture()
        for i,event in enumerate(events):
            event['event_time_utc']=(start+timedelta(microseconds=i*10)).isoformat().replace('+00:00','Z')
            if 'execution_kind' in event:event['execution_kind']='paper'
            if event.get('quantity')==2:event['quantity']=3
            if event['kind']=='fill':event['commission']='1.5'
            if event['kind']=='position' and event.get('account_balance')=='50002':event['account_balance']='50003'
        payload=json.dumps(dict(schema_version='aq-forward-events-v1',source_id='paper-fixture',batch_id=uuid4().hex,events=events)).encode()
        checked_events=client.post(base+'/events/check',content=payload);assert checked_events.status_code==200,checked_events.text
        imported=client.post(base+'/events',content=payload);assert imported.status_code==201,imported.text
        assert client.post(base+'/events',content=payload).json()['new_event_count']==0
        job=client.post(base+'/assess',json=dict(request_id=uuid4().hex,as_of_utc=datetime.now(timezone.utc).isoformat().replace('+00:00','Z')))
        assert job.status_code==200,job.text
        report,bytes_before=wait_monitor(client,job.json()['id']);result=report['calculations']
        assert Decimal(result['metrics']['gross_realized_pnl'])==6
        assert Decimal(result['metrics']['commissions'])==3 and Decimal(result['metrics']['net_realized_pnl'])==3
        assert result['advisory']['state']=='ACTIVE'
        assert result['forward_evidence']['status']=='SUPPLIED_FORWARD_OBSERVATIONS'
        assert result['forward_evidence']['authoritative_policy_publication_utc'] is None
        assert result['forward_evidence']['application_reservation_utc']
        assert result['forward_evidence']['conservative_publication_upper_bound_utc']==saved.json()['created_at_utc']
        assert not result['forward_evidence']['eligible_for_future_certification']
        assert result['forecast_comparison']['status']=='NOT_COMPARABLE'
        assert client.get(base+'/batches/'+imported.json()['batch_id']+'/download').content==payload
        assert client.delete('/api/prop-analyses/'+report['id']).status_code==409
        assert client.delete('/api/backtests/'+package['configuration']['source']['source_backtest_id']).status_code==409
        assert client.post(base+'/control',json=dict(request_id=uuid4().hex,action='pause',reason='Operator inspection')).status_code==200
        assert client.get(base).json()['advisory_state']=='PAUSED'
        assert client.post(base+'/control',json=dict(request_id=uuid4().hex,action='resume',reason='Current exact report reviewed',acknowledged_snapshot_sha256=digest(report))).status_code==200
        assert client.get(base).json()['advisory_state']=='ACTIVE'
    def forbidden(*args,**kwargs):pytest.fail('Saved forward read recomputed or reselected')
    monkeypatch.setattr('alphaquest.forward_monitoring.reconcile',forbidden)
    monkeypatch.setattr('alphaquest.forward_policy.resolve_policy',forbidden)
    with TestClient(create_app(database)) as client:
        assert client.get(base).json()['latest_assessment']['id']==report['id']
        assert client.get('/api/prop-analyses/'+report['id']+'/downloads/report.json').content==bytes_before
        assert client.get(base+'/batches/'+imported.json()['batch_id']+'/download').content==payload
