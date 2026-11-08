"""Native account control through ordinary source/check/run/durable reports."""
from copy import deepcopy
from decimal import Decimal
from hashlib import sha256
import io
import json
import os
from pathlib import Path
from threading import Event
from time import monotonic
import zipfile

import pytest
from alphaquest.app import create_app
from research_fixtures import ResearchClient
from native_replay_fixtures import source_bytes, parameter_values


def source(client, *, dataset_changes=None, parameter_changes=None, execution_changes=None, raw=None, **fixture):
    metadata = dict(filename='synthetic-native-mnq.csv',
        name='SYNTHETIC complete MNQ native account arithmetic', symbol='MNQ', source_timezone='UTC',
        tick_size='0.25', point_value='2')
    metadata.update(dataset_changes or {})
    values = {**parameter_values(), **(parameter_changes or {})}
    saved = client.post('/api/datasets', params=metadata, content=source_bytes(**fixture) if raw is None else raw)
    assert saved.status_code == 201, saved.text
    result = client.post('/api/optimizations', json=dict(dataset_id=saved.json()['id'], method='exhaustive',
        workers=1, automatic_prop=False, strategy_id='vwap_pullback_risk_sizing',
        parameter_ranges={k:dict(start=v,end=v,step='0' if isinstance(v,str) else 0) for k,v in values.items()},
        execution_settings={**dict(initial_capital='10000', slippage_ticks=0, commission_per_contract_per_side='0'), **(execution_changes or {})}))
    assert result.status_code == 202, result.text
    from test_optimization import wait_job
    job = wait_job(client, result.json()['id'])
    assert job['status'] == 'complete', job
    row, = client.get('/api/optimizations/'+job['id']+'/results').json()['items']
    return client.get('/api/backtests/'+row['run_id']).json()


def body(client, record, phase='funded', policy=None):
    defaults = client.get('/api/prop-analyses/defaults').json()['native_phase_replay']
    result = dict(mode='native_phase_replay', phase=phase, source_backtest_id=record['id'],
        profile=defaults['profiles'][phase][0], micros=40, max_micros=40,
        sizing=dict(policy=policy or dict(kind='percentage_risk', risk_percent='0.2', reference='current_account_balance'),
            initial_configured_capital='50000', planning_execution=dict(tick_size='0.25', point_value='2',
                entry_slippage_ticks=0, stop_exit_slippage_ticks=0, commission_per_contract_per_side='0')))
    if phase == 'funded':
        result.update(receipt_delay_calendar_days=2, receipt_amount_convention='kernel_entitlement_unrounded')
    else:
        result['profile'].update(evaluation_price='30', activation_fee='40')
    return result


def wait(client, id):
    deadline = monotonic()+45
    while monotonic() < deadline:
        result = client.get('/api/prop-analyses/'+id).json()
        if result['status'] not in ('queued', 'running'):
            assert result['status'] == 'complete', result
            return result
        Event().wait(.02)
    raise AssertionError('Native replay did not finish.')


@pytest.mark.parametrize('phase,gap,policy,quantities,nets', [
    ('funded',False,None,[10,9,5],[-100,180,100]),
    ('evaluation',False,None,[10,9,5],[-100,180,100]),
    ('funded',True,None,[10,9,5],[-140,180,100]),
    ('funded',False,dict(kind='fixed_dollar_risk',risk_dollars='100'),[10,10,5],[-100,200,100]),
])
def test_real_native_report_workflow(tmp_path, phase, gap, policy, quantities, nets):
    library = tmp_path/'library'
    with ResearchClient(create_app(library/'datasets.sqlite3')) as client:
        original = source(client, gap=gap)
        original_bytes = client.get(f"/api/backtests/{original['id']}/exports/trades").content
        request = body(client, original, phase, policy)
        check = client.post('/api/prop-analyses/check', json=request)
        assert check.status_code == 200, check.text
        assert check.json()['native']['source_check']['observed_sessions'] == 3
        assert check.json()['native']['source_check']['observed_bars'] == 4140
        response = client.post('/api/prop-analyses', json=request)
        assert response.status_code == 202, response.text
        id = response.json()['id']; wait(client,id)
        report_response = client.get(f'/api/prop-analyses/{id}/downloads/report.json')
        report = report_response.json(); calc = report['calculations']
        native_id = report['native_backtest_id']
        native = client.get('/api/backtests/'+native_id).json()
        trades = client.get(f'/api/backtests/{native_id}/trades').json()['items']
        assert [row['contracts'] for row in trades] == quantities
        assert [Decimal(row['net_pnl']) for row in trades] == list(map(Decimal,nets))
        assert Decimal(native['summary']['final_equity']) == 10000+sum(nets)
        assert Decimal(calc['trading_profit']) == sum(nets)
        assert Decimal(calc['equity']) == sum(nets)
        assert calc['historical_paths'] == 1 and calc['native_forecast_available'] is False
        assert len(calc['trace']) == 3
        assert [row['quantity'] for row in calc['sizing_decisions']] == quantities
        assert all(row['state_before']['balance'] != '10000' for row in calc['sizing_decisions'])
        if phase == 'evaluation':
            assert Decimal(calc['paid_evaluation_fees']) == 30
            assert Decimal(calc['paid_activation_fees']) == 0
            assert calc['acquisition_completed'] is False and calc['censored'] is True
        else:
            assert Decimal(calc['cash_received']) == Decimal(calc['pending_cash']) == 0
        assert client.post('/api/prop-analyses', json=request).json()['id'] == id
        assert client.get('/api/backtests/'+original['id']).json() == original
        assert client.get(f"/api/backtests/{original['id']}/exports/trades").content == original_bytes
        controlled = deepcopy(request); controlled['source_backtest_id'] = native_id
        assert client.post('/api/prop-analyses/check',json=controlled).status_code == 422
        assert client.post(f'/api/backtests/{native_id}/detailed').status_code in (409,422)
        capture = client.get(f'/api/backtests/{native_id}/exports/native_account_control')
        assert capture.status_code == 200 and capture.json() == calc
        archive = client.get(f'/api/prop-analyses/{id}/downloads/analysis.zip').content
        with zipfile.ZipFile(io.BytesIO(archive)) as zipped:
            assert zipped.read('trades.csv') == client.get(f'/api/backtests/{native_id}/exports/trades').content
            assert {'source_check.json','session_trace.json','cash_ledger.json','control_events.json','sizing_decisions.json'} <= set(zipped.namelist())
        saved = {name:sha256(client.get(f'/api/prop-analyses/{id}/files/{name}').content).hexdigest() for name in report['files']}
        assert saved == {name:desc['sha256'] for name,desc in report['files'].items()}
    with ResearchClient(create_app(library/'datasets.sqlite3')) as client:
        assert client.get(f'/api/prop-analyses/{id}/downloads/report.json').content == report_response.content
        assert client.get(f'/api/prop-analyses/{id}/downloads/analysis.zip').content == archive
    (tmp_path/'evidence.json').write_text(json.dumps(dict(source_id=original['id'],analysis_id=id,native_backtest_id=native_id,
        request=request, expected=dict(quantities=quantities,nets=nets), report_sha256=sha256(report_response.content).hexdigest(),
        zip_sha256=sha256(archive).hexdigest(), artifacts=saved, library=str(library)),indent=2))


def test_native_rejections_are_checkable_before_publication(tmp_path):
    with ResearchClient(create_app(tmp_path/'datasets.sqlite3')) as client:
        record = source(client); request = body(client, record)
        for patch, message in [({'phase':'unknown'},'literal_error'), ({'micros':True},'int_type'),
            ({'retry':{}},'Funded replay'), ({'receipt_delay_calendar_days':None},'Funded replay'),
            ({'costs':{'mode':'override','per_side':'1'}},'saved MNQ fill costs'),
            ({'period':dict(first_session='2026-01-04',last_session='2026-01-07')},'whole observed'),
            ({'sampling':{'block_weekdays':5}},'extra_forbidden')]:
            result = client.post('/api/prop-analyses/check', json={**request, **patch})
            assert result.status_code == 422 and message in result.text, result.text
        before = client.app.state.prop_analyses.list(record['id'])
        missing = deepcopy(request); missing['period'] = dict(first_session='2026-01-05',last_session='2026-01-08')
        assert client.post('/api/prop-analyses',json=missing).status_code == 422
        assert client.app.state.prop_analyses.list(record['id']) == before


@pytest.mark.parametrize('variant,expected', [('missing_minute','every observed minute'),('nq','continuous/base MNQ'),
    ('point_value','point_value=2'),('local_sizing','Use Vol Sizing disabled'),('no_flat','Use EOD Flat enabled'),
    ('costs','planning costs must match')])
def test_native_source_boundaries(tmp_path, variant, expected):
    with ResearchClient(create_app(tmp_path/'datasets.sqlite3')) as client:
        options = {}
        if variant == 'missing_minute':
            lines = source_bytes().splitlines(keepends=True)
            options['raw'] = b''.join(lines[:100]+lines[101:])
        elif variant == 'nq': options['dataset_changes'] = dict(symbol='NQ', point_value='20')
        elif variant == 'point_value': options['dataset_changes'] = dict(point_value='20')
        elif variant == 'local_sizing': options['parameter_changes'] = dict(use_vol_sizing=True)
        elif variant == 'no_flat': options['parameter_changes'] = dict(use_eod_flat=False)
        else: options['execution_changes'] = dict(slippage_ticks=1, commission_per_contract_per_side='1')
        record = source(client, **options)
        response = client.post('/api/prop-analyses/check',json=body(client,record))
        assert response.status_code == 422 and expected in response.text, response.text


def test_native_active_deletion_guard_and_artifact_cache_invalidation(tmp_path, monkeypatch):
    from alphaquest.prop import native_replay
    with ResearchClient(create_app(tmp_path/'datasets.sqlite3')) as client:
        record = source(client); request = body(client,record)
        entered, release = Event(), Event()
        original = native_replay.run_replay
        def held(*args,**kwargs):
            entered.set(); assert release.wait(10)
            return original(*args,**kwargs)
        with monkeypatch.context() as patch:
            patch.setattr(native_replay,'run_replay',held)
            response = client.post('/api/prop-analyses',json=request)
            assert response.status_code == 202, response.text
            try:
                assert entered.wait(10)
                assert client.delete('/api/backtests/'+record['id']).status_code == 409
                assert client.delete('/api/prop-analyses/'+response.json()['id']).status_code == 409
            finally: release.set()
            wait(client,response.json()['id'])
        first = response.json()['id']
        path = client.app.state.prop_analyses.root/first/'sizing_decisions.json'
        path.write_text('[]')
        second = client.post('/api/prop-analyses',json=request)
        assert second.status_code == 202 and second.json()['id'] != first, second.text
        wait(client,second.json()['id'])
