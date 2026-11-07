"""Declared native Monte Carlo beside an unchanged actual historical replay."""
from copy import deepcopy
from decimal import Decimal
from hashlib import sha256
import io
import json
import zipfile

import pytest
from alphaquest.app import create_app
from research_fixtures import ResearchClient
from test_native_replay_api import source, body, wait


def forecast(horizon=9, block=1):
    return dict(model='observed_contiguous_blocks_with_prior_prefix_v1', simulations=4,
        seed=1729, block_sessions=block, horizon_calendar_days=horizon, capture_paths=2,
        calendar=dict(start_dates=['2026-01-26'],coverage_end='2026-02-05',closures=[],
            timezone='America/Chicago',version='explicit-synthetic-weekdays-v1'),early_closes={})


@pytest.mark.parametrize('phase,horizon,block', [('funded',9,1),('evaluation',9,1),('evaluation',3,1),('funded',9,5)])
def test_actual_source_to_native_forecast_and_immutable_report(tmp_path, phase, horizon, block):
    library=tmp_path/'library'
    with ResearchClient(create_app(library/'datasets.sqlite3')) as client:
        original=source(client,days=7,payout=True)
        request=body(client,original,phase);request.update(micros=3,sizing=None,native_forecast=forecast(horizon,block))
        checked=client.post('/api/prop-analyses/check',json=request)
        assert checked.status_code==200,checked.text
        plan=checked.json()['native']['native_forecast_plan']
        assert plan['simulations']==4 and plan['retained_path_indices']==[0,1]
        assert plan['target_calendar']['observed'] is False and plan['target_calendar']['exchange_verified'] is False
        assert plan['work']['source_validation_bars']==9660*4
        assert plan['work']['executed_bars']==1380*(3 if horizon==3 else 7)*4
        assert all(c['observed_target_bars']==0 for c in plan['cohorts'])
        assert len(plan['schedules'])==4
        submitted=client.post('/api/prop-analyses',json=request)
        assert submitted.status_code==202,submitted.text
        id=submitted.json()['id'];wait(client,id)
        saved=client.get(f'/api/prop-analyses/{id}/downloads/report.json')
        report=saved.json();result=report['native_forecast'];metrics=result['metrics']
        assert result['plan_sha256']==plan['plan_sha256']
        assert result['schedules']==plan['schedules']
        assert result['observed_future_data'] is False and result['readiness']=='MODELED_SCENARIO_ONLY'
        assert len(result['paths'])==4 and result['capture_path_indices']==[0,1]
        assert [c['path_index'] for c in result['captures']]==[0,1]
        assert report['calculations']['historical_paths']==1
        assert report['calculations']['mode']=='native_historical_chronological_replay'
        assert report['production_qualified'] is False
        if phase=='funded':
            assert metrics['mean_received_cash']==metrics['mean_gross_account_deductions']==1500
            assert metrics['mean_pending_cash']==0 and metrics['mean_provider_equity_change']==4800
            assert result['uncertainty']['metrics']['mean_received_cash']['mc_standard_error']==0
            for path in result['paths']:
                payout,=path['payout_events']
                assert payout['request_date']=='2026-01-30' and payout['receipt_date']=='2026-02-01'
            # The old observed path remains on its original actual dates.
            assert report['calculations']['payout_events'][0]['receipt_date']=='2026-01-11'
        elif horizon==3:
            assert result['status']=='unresolved_censoring'
            assert metrics['completed_paths']==0 and metrics['censored_paths']==4
            assert metrics['restricted_mean_paid_fees']==30
            assert metrics['mean_acquisition_cost'] is None and metrics['mean_calendar_days_to_funded'] is None
        else:
            assert result['status']=='identified_model_mean'
            assert metrics['completed_paths']==4 and metrics['censored_paths']==0
            assert metrics['mean_acquisition_cost']==70 and metrics['mean_calendar_days_to_funded']==7
        assert client.get('/api/backtests/'+original['id']).json()==original
        assert client.post('/api/prop-analyses',json=request).json()['id']==id
        files={}
        for name,description in report['files'].items():
            response=client.get(f'/api/prop-analyses/{id}/files/{name}')
            assert response.status_code==200
            files[name]=sha256(response.content).hexdigest()
            assert files[name]==description['sha256']
        archive=client.get(f'/api/prop-analyses/{id}/downloads/analysis.zip').content
        with zipfile.ZipFile(io.BytesIO(archive)) as zipped:
            assert json.loads(zipped.read('native_forecast_schedules.json'))==plan['schedules']
            assert json.loads(zipped.read('native_forecast_paths.json'))==result['paths']
        (tmp_path/'evidence.json').write_text(json.dumps(dict(source_id=original['id'],analysis_id=id,
            child_id=report['native_backtest_id'],request=request,metrics=metrics,files=files,
            engine_identity=report['engine_identity'],report_sha256=sha256(saved.content).hexdigest(),
            zip_sha256=sha256(archive).hexdigest(),library=str(library)),indent=2))
    with ResearchClient(create_app(library/'datasets.sqlite3')) as client:
        assert client.get(f'/api/prop-analyses/{id}/downloads/report.json').content==saved.content
        assert client.get(f'/api/prop-analyses/{id}/downloads/analysis.zip').content==archive


def test_native_forecast_rejects_missing_pools_past_targets_and_excess_work(tmp_path,monkeypatch):
    from alphaquest.prop import native_replay
    with ResearchClient(create_app(tmp_path/'datasets.sqlite3')) as client:
        original=source(client,days=7,payout=True)
        request=body(client,original);request.update(micros=3,sizing=None,native_forecast=forecast())
        for change,message in [({'block_sessions':10},'source'),
            ({'early_closes':{'2026-01-26':'12:15'}},'matches modeled target shape')]:
            raw=deepcopy(request);raw['native_forecast'].update(change)
            response=client.post('/api/prop-analyses/check',json=raw)
            assert response.status_code==422 and message in response.text,response.text
        raw=deepcopy(request);raw['native_forecast']['calendar']['start_dates']=['2026-01-13']
        response=client.post('/api/prop-analyses/check',json=raw)
        assert response.status_code==422 and 'follow the last admitted' in response.text
        # Resource rejection occurs during Check before reserving any job.
        before=client.app.state.prop_analyses.list(original['id'])
        with monkeypatch.context() as patch:
            patch.setattr(native_replay,'MAX_FORECAST_BAR_WORK',100)
            response=client.post('/api/prop-analyses',json=request)
            assert response.status_code==422 and 'no paths were truncated' in response.text
        assert client.app.state.prop_analyses.list(original['id'])==before
