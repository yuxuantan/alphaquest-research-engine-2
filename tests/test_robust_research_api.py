"""Normal source grid → inner research → immutable AnalysisStore evidence."""
from copy import deepcopy
import csv
from decimal import Decimal
from hashlib import sha256
import io
import json
from threading import Event
import time
from uuid import uuid4
from zipfile import ZipFile

from fastapi.testclient import TestClient
import pytest

from alphaquest.app import create_app
from alphaquest.backtest_api import run_backtest
from alphaquest.backtest_data import DateRange
from alphaquest.backtest_requests import ExecutionSettings
from alphaquest.strategies.registry import get_strategy
from test_optimization import wait_job
from test_prop_phases import phase_history


PREFIX = '/api/research-campaigns/robust'


def save_grid(client, *, raw=None, is_end='2026-01-22', oos_start='2026-01-23'):
    response = client.post('/api/datasets', params=dict(
        filename='SYNTHETIC-robust-research.csv', name='SYNTHETIC inner research arithmetic',
        source_timezone='UTC', symbol='MNQ', tick_size='.25', point_value='2'),
        content=raw or phase_history(20))
    assert response.status_code == 201, response.text
    dataset = response.json()
    response = client.post('/api/optimizations', json=dict(
        dataset_id=dataset['id'], strategy_id='consecutive_green_hold', method='exhaustive',
        workers=1, automatic_prop=False,
        parameter_ranges=dict(green_bar_count=dict(start=1, end=2, step=1),
                              hold_minutes=dict(start=1, end=1, step=0),
                              contracts=dict(start=1, end=1, step=0)),
        execution_settings=dict(initial_capital='10000', tick_size='.25', point_value='2',
                                slippage_ticks=0, commission_per_contract_per_side='0'),
        sample_split=dict(mode='dates', is_start='2026-01-05', is_end=is_end,
                          oos_start=oos_start, oos_end='2026-01-30')))
    assert response.status_code == 202, response.text
    job = wait_job(client, response.json()['id'])
    assert job['status'] == 'complete', job
    rows = client.get('/api/optimizations/' + job['id'] + '/results').json()['items']
    records = [client.get('/api/backtests/' + row['run_id']).json() for row in rows]
    assert len(records) == 2
    return dataset, job, records


def declaration(job, records, **extra):
    return dict(campaign_id=uuid4().hex, name='SYNTHETIC nested arithmetic',
        source_backtest_id=records[0]['id'], sources=[dict(optimization_id=job['id'], sizes=[1])],
        folds=dict(outer_train_sessions=8, outer_test_sessions=2,
                   inner_train_sessions=2, inner_validation_sessions=2, mode='rolling',
                   purge_sessions=1, embargo_sessions=1, minimum_inner_folds=2, minimum_outer_folds=2),
        qualification=dict(minimum_folds=2, minimum_sessions=4, minimum_trades=4,
            minimum_trades_per_fold=2, minimum_positive_fold_fraction=1.0,
            maximum_profit_concentration=.6, additional_round_trip_cost='10',
            minimum_neighbors=1, bootstrap_replicates=400, bootstrap_block_sessions=1,
            confidence_level=.95, minimum_bootstrap_tail_samples=5), **extra)


def save(client, body):
    response = client.post(PREFIX, json=body)
    assert response.status_code == 201, response.text
    return response.json()


def wait_research(client, id):
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        response = client.get(PREFIX + '/' + id)
        assert response.status_code == 200, response.text
        row = response.json()
        if row['status'] not in ('queued', 'running'):
            return row
        time.sleep(.02)
    pytest.fail('Nested research did not finish within 60 seconds.')


def run(client, id):
    response = client.post(PREFIX + '/' + id + '/run')
    assert response.status_code == 202, response.text
    row = wait_research(client, id)
    assert row['status'] == 'complete', row
    return row


def file_hashes(directory):
    return {str(path.relative_to(directory)): sha256(path.read_bytes()).hexdigest()
            for path in directory.rglob('*') if path.is_file()}


def test_normal_grid_nested_qualification_saved_outputs_and_reopen(tmp_path, monkeypatch):
    with TestClient(create_app(tmp_path / 'datasets.sqlite3')) as client:
        dataset, job, records = save_grid(client)
        # Native one-contract MNQ arithmetic: 150 * $2 = $300; 50 * $2 = $100.
        assert {Decimal(r['summary']['total_net_pnl']) for r in records} == {Decimal('4200'), Decimal('1400')}
        before = file_hashes(client.app.state.runs.root)
        body = declaration(job, records)
        preview = client.post(PREFIX + '/preview', json=body)
        assert preview.status_code == 200, preview.text
        plan = preview.json()
        assert plan['estimated_backtests'] == 16
        assert len(plan['folds']) == 2
        assert not plan['prior_access']['untouched']
        assert client.get('/api/backtests').json()['total'] == 2, 'Preview must not launch backtests.'
        row = save(client, body); id = row['campaign_id']
        assert save(client, body)['campaign_id'] == id
        changed = deepcopy(body); changed['name'] = 'Changed decision'
        assert client.post(PREFIX, json=changed).status_code == 409
        assert client.post(PREFIX + '/' + id + '/check').json()['status'] == 'compatible'
        row = run(client, id)
        assert client.post(PREFIX + '/' + id + '/run').json()['analysis_id'] == row['analysis_id']
        report_url = PREFIX + '/' + id + '/exports/report.json'
        original = client.get(report_url).content
        report = json.loads(original)
        assert report['calculations']['readiness']['status'] == 'INCOMPLETE'
        assert report['id'] == row['analysis_id']
        assert report['plan']['input_identity'] == plan['input_identity']
        assert len(report['calculations']['folds']) == 2
        observed = []
        for fold in report['calculations']['folds']:
            assert fold['outer_test_status'] == 'not_run'
            assert fold['policy_selection_status'] == 'not_run'
            qualification = fold['qualification']
            assert len(qualification['approved_ids']) == 2
            for candidate in qualification['candidates']:
                expected = Decimal('300') if candidate['parameters']['green_bar_count'] == 1 else Decimal('100')
                assert candidate['status'] == 'PASS', candidate
                assert Decimal(candidate['metrics']['mean_session_net']) == expected
                assert Decimal(candidate['metrics']['net_pnl']) == expected * 4
                assert candidate['metrics']['validation_sessions'] == 4
                assert candidate['metrics']['validation_trades'] == 4
                assert Decimal(candidate['execution_stress']['stressed_mean_session_net']) == expected - 10
                assert candidate['uncertainty']['lower'] == candidate['uncertainty']['upper'] == float(expected)
            for reference in fold['backtests']:
                saved = client.get('/api/backtests/' + reference['run_id']).json()
                research = saved['run_metadata']['research']
                assert research['role'] in ('inner_train', 'inner_validation')
                assert research['phase'] == 'inner'
                assert research['cold_start']
                assert saved['run_metadata']['selection']['date_convention'] == 'cme_chicago_1700_v1'
                assert research['window']['last_session'] <= plan['folds'][fold['index'] - 1]['information_cutoff_session']
                assert client.delete('/api/backtests/' + reference['run_id']).status_code == 409
                observed.append(reference['run_id'])
        assert len(observed) == len(set(observed)) == 16
        assert client.get('/api/backtests').json()['total'] == 18
        assert client.get('/api/backtests/research-plan', params=dict(dataset_id=dataset['id'], strategy_id='consecutive_green_hold')).json()['used'] == 0
        with client.app.state.prop_analyses.connect() as db:
            accesses = db.execute('SELECT purpose,last_session FROM research_access_intervals WHERE campaign_id=?', (id,)).fetchall()
        assert len(accesses) == 16
        assert set(purpose for purpose, _ in accesses) == {'inner_train', 'inner_validation'}
        assert max(last for _, last in accesses) == '2026-01-16'
        assert client.delete('/api/backtests/' + records[0]['id']).status_code == 409
        assert client.delete('/api/optimizations/' + job['id']).status_code == 409
        assert client.delete('/api/prop-analyses/' + row['analysis_id']).status_code == 409
        csv = client.get(PREFIX + '/' + id + '/exports/qualification.csv')
        assert csv.status_code == 200 and len(csv.text.splitlines()) == 5
        archive = client.get(PREFIX + '/' + id + '/exports/analysis.zip')
        with ZipFile(io.BytesIO(archive.content)) as zipped:
            assert zipped.read('report.json') == original
            assert {'research_plan.json', 'calculations.json', 'qualification.csv'} <= set(zipped.namelist())
        assert all(sha256((client.app.state.runs.root / name).read_bytes()).hexdigest() == value for name, value in before.items())
        (tmp_path / 'independent-expected-values.json').write_text(json.dumps(dict(
            synthetic=True, campaign_id=id, report_id=row['analysis_id'],
            expected_per_validation_session={'green_bar_count=1': 300, 'green_bar_count=2': 100},
            expected_validation_sessions_per_outer_fold=4, expected_new_backtests=16,
            expected_outer_test_status='not_run', report_sha256=sha256(original).hexdigest()), indent=2))
    with TestClient(create_app(tmp_path / 'datasets.sqlite3')) as reopened:
        def forbidden(*args, **kwargs):
            pytest.fail('Reopening completed research must not recalculate.')
        monkeypatch.setattr('alphaquest.robust_research.run_backtest', forbidden)
        assert reopened.get(report_url).content == original
        assert reopened.get(PREFIX + '/' + id).json()['status'] == 'complete'
        assert reopened.post(PREFIX + '/' + id + '/run').json()['analysis_id'] == row['analysis_id']
        assert reopened.get(PREFIX, params=dict(source_id=records[0]['id'])).json()['items'][0]['campaign_id'] == id


def test_strict_rejections_and_changed_code_keep_declaration_and_sources(tmp_path, monkeypatch):
    from sizing_fixtures import sizing_configuration
    with TestClient(create_app(tmp_path / 'datasets.sqlite3')) as client:
        dataset, job, records = save_grid(client)
        body = declaration(job, records)
        for patch in [dict(folds=dict(body['folds'], purge_sessions=True)),
                      dict(qualification=dict(body['qualification'], minimum_folds=True)),
                      dict(outer_outcomes=[100000]),
                      dict(sources=[dict(optimization_id=job['id'], sizes=[1],
                                         sizing_policies=[sizing_configuration('fixed_contracts', contracts=1)])]),
                      dict(confirmed_backtest_count=15)]:
            rejected = client.post(PREFIX + '/preview', json=body | patch)
            assert rejected.status_code == 422, rejected.text
        row = save(client, body); id = row['campaign_id']
        with monkeypatch.context() as local:
            local.setattr('alphaquest.robust_research.engine_identity', lambda: 'changed-implementation')
            assert client.post(PREFIX + '/' + id + '/check').status_code == 409
            assert client.post(PREFIX + '/' + id + '/run').status_code == 409
        assert client.get(PREFIX + '/' + id).json()['analysis_id'] is None
        assert client.get('/api/backtests').json()['total'] == 2
        assert client.get(PREFIX + '/' + id + '/exports/report.json').status_code == 409
        assert client.post(PREFIX + '/' + id + '/cancel').status_code == 409
        # A real OOS report is generated through the ordinary backtest function,
        # with native execution/risk/report publication and no automatic prop work.
        source = records[0]; meta = source['run_metadata']; split = meta['research']['plan']
        definition = get_strategy(meta['strategy']['id'])
        config = ExecutionSettings.model_validate(source['execution_settings']).execution_config(dataset)
        oos = run_backtest(client.app.state.store, client.app.state.runs, uuid4().hex,
            dataset, definition, definition.parameters(meta['strategy']['parameters']), config,
            DateRange.parse(split['oos_start'], split['oos_end']), lambda *args: None,
            prop_analyses=None, research=dict(phase='oos', plan=split, parent_run_id=source['id']))
        invalid = deepcopy(body); invalid['campaign_id'] = uuid4().hex
        invalid['sources'] = [dict(backtest_id=oos['id'], sizes=[1])]
        assert client.post(PREFIX, json=invalid).status_code == 422
        invalid['source_backtest_id'] = oos['id']
        invalid['sources'] = body['sources']
        assert client.post(PREFIX, json=invalid).status_code == 422


def test_cancel_and_resume_preserves_completed_steps_and_rejects_changed_source(tmp_path, monkeypatch):
    with TestClient(create_app(tmp_path / 'datasets.sqlite3')) as client:
        _, job, records = save_grid(client)
        body = declaration(job, records)
        row = save(client, body); id = row['campaign_id']
        import alphaquest.robust_research as implementation
        original = implementation.run_backtest
        entered, release = Event(), Event()
        completed = []

        def pause_after_publication(*args, **kwargs):
            result = original(*args, **kwargs)
            if not completed:
                completed.append(result['id'])
                entered.set()
                assert release.wait(20), 'Test release was not signalled.'
            return result

        with monkeypatch.context() as local:
            # Pause after native publication but before the research checkpoint
            # reference is saved. Its reserved ID must already block deletion.
            local.setattr(implementation, 'run_backtest', pause_after_publication)
            started = client.post(PREFIX + '/' + id + '/run')
            assert started.status_code == 202, started.text
            try:
                assert entered.wait(20)
                assert client.delete('/api/backtests/' + completed[0]).status_code == 409
                assert client.post(PREFIX + '/' + id + '/run').json()['analysis_id'] == started.json()['analysis_id']
                cancelled = client.post(PREFIX + '/' + id + '/cancel')
                assert cancelled.status_code == 200 and cancelled.json()['cancel_requested']
            finally:
                release.set()
            stopped = wait_research(client, id)
            assert stopped['status'] == 'error' and 'Cancelled' in stopped['error']
        with client.app.state.prop_analyses.connect() as db:
            assert db.execute('SELECT count(*) FROM robust_research_steps WHERE campaign_id=?', (id,)).fetchone()[0] == 1
        resumed = run(client, id)
        assert resumed['analysis_id'] != stopped['analysis_id']
        report = client.get(PREFIX + '/' + id + '/exports/report.json').json()
        steps = [ref['run_id'] for fold in report['calculations']['folds'] for ref in fold['backtests']]
        assert completed[0] in steps and len(steps) == len(set(steps)) == 16
        assert client.get('/api/backtests').json()['total'] == 18
        # A new declaration still pins the immutable source manifest at save.
        new = declaration(job, records); saved = save(client, new)
        with client.app.state.runs.connect() as db:
            original_manifest = db.execute('SELECT manifest FROM runs WHERE id=?', (records[0]['id'],)).fetchone()[0]
            changed = json.loads(original_manifest)
            changed['execution_settings']['slippage_ticks'] = 1
            db.execute('UPDATE runs SET manifest=? WHERE id=?', (json.dumps(changed), records[0]['id']))
        try:
            assert client.post(PREFIX + '/' + saved['campaign_id'] + '/run').status_code in (409, 422)
            # Published prior report remains readable without source recalculation.
            assert client.get(PREFIX + '/' + id + '/exports/report.json').json() == report
        finally:
            with client.app.state.runs.connect() as db:
                db.execute('UPDATE runs SET manifest=? WHERE id=?', (original_manifest, records[0]['id']))


def test_preview_excludes_session_partly_outside_source_timezone_is_window(tmp_path):
    header, rows = phase_history(20).split(b'\n', 1)
    # Sunday evening belongs to Monday's Chicago session but lies outside the
    # source report's UTC-date IS start. Admitting the whole Monday session would
    # load data outside the declared source research window.
    raw = header + b'\n01/04/2026,23:01,99,100,99,100,100,60,40\n' + rows
    with TestClient(create_app(tmp_path / 'datasets.sqlite3')) as client:
        dataset, job, records = save_grid(client, raw=raw, is_end='2026-01-23', oos_start='2026-01-26')
        body = declaration(job, records)
        response = client.post(PREFIX + '/preview', json=body)
        assert response.status_code == 200, response.text
        plan = response.json()
        from alphaquest.research_folds import inventory_sessions
        original=inventory_sessions(client.app.state.store,dataset['id'])
        assert original['bounds']['2026-01-05']['first_utc'] == '2026-01-04T23:01:00Z'
        assert '2026-01-05' not in plan['session_inventory']['sessions']
        assert '2026-01-05' not in plan['session_inventory']['bounds']
        assert records[0]['period_start_utc'] == '2026-01-05T18:00:00Z'
        assert plan['folds'][0]['train']['first_session'] == '2026-01-06'
        assert plan['estimated_backtests'] == 16
        assert all('2026-01-05' not in window['sessions']
            for fold in plan['folds'] for window in (fold['train'], fold['test']))
        assert client.get('/api/backtests').json()['total'] == 2


def test_missing_required_assessment_returns_insufficient_without_advancing(tmp_path):
    with TestClient(create_app(tmp_path / 'datasets.sqlite3')) as client:
        _, job, records = save_grid(client)
        body = declaration(job, records)
        body['qualification']['required_regimes'] = ['predeclared_trend']
        body['qualification']['required_scenarios'] = ['conservative_limit_fills']
        campaign = save(client, body)
        result = run(client, campaign['campaign_id'])['result']
        for fold in result['folds']:
            assert fold['qualification']['approved_ids'] == []
            assert fold['outer_test_status'] == 'not_run'
            assert fold['policy_selection_status'] == 'not_run'
            for candidate in fold['qualification']['candidates']:
                assert candidate['status'] == 'INSUFFICIENT_EVIDENCE'
                assert 'missing_regime:predeclared_trend' in candidate['reasons']
                assert 'missing_scenario:conservative_limit_fills' in candidate['reasons']
        assert result['readiness']['status'] == 'INCOMPLETE'


def test_adversarial_outer_prices_cannot_change_inner_admission(tmp_path):
    raw = phase_history(20)
    changed = []
    for line in raw.decode().splitlines():
        fields = line.split(',')
        if fields[0].startswith('01/') and int(fields[0][3:5]) >= 19:
            # The untouched inner sessions end Jan 16. Extreme later prices
            # turn the saved whole-IS report into a very different apparent
            # opportunity; source-report outcomes must not screen candidates.
            fields[2:6] = ['0', '1000000', '-1000000', '0']
        changed.append(','.join(fields))
    altered = ('\n'.join(changed) + '\n').encode()
    with TestClient(create_app(tmp_path / 'datasets.sqlite3')) as client:
        qualification, source_outcomes = [], []
        for content in (raw, altered):
            _, job, records = save_grid(client, raw=content)
            source_outcomes.append([record['summary']['total_net_pnl'] for record in records])
            campaign = save(client, declaration(job, records))
            result = run(client, campaign['campaign_id'])['result']
            qualification.append([fold['qualification'] for fold in result['folds']])
            assert all(fold['outer_test_status'] == 'not_run' for fold in result['folds'])
        assert source_outcomes[0] != source_outcomes[1]
        assert qualification[0] == qualification[1]


def test_real_vwap_decimal_parameters_round_trip_into_nested_preview(tmp_path):
    with TestClient(create_app(tmp_path / 'datasets.sqlite3')) as client:
        dataset, _, _ = save_grid(client)
        definition = get_strategy('vwap_pullback_risk_sizing')
        values = {field['name']: field['default'] for field in definition.description()['parameters']}
        # The synthetic four-bar sessions are intentionally inadequate for this
        # strategy. They test native provenance/parameter handling, not an edge.
        values['use_eod_flat'] = False
        axes = {key: dict(start=value, end=value, step='0' if type(value) is str else 0)
                for key, value in values.items()}
        axes['min_rr'] = dict(start='0', end='0.5', step='0.5')
        response = client.post('/api/optimizations', json=dict(
            dataset_id=dataset['id'], strategy_id=definition.description()['id'],
            method='exhaustive', parameter_ranges=axes, workers=1, automatic_prop=False,
            execution_settings=dict(initial_capital='10000', tick_size='.25', point_value='2',
                slippage_ticks=0, commission_per_contract_per_side='0'),
            sample_split=dict(mode='dates', is_start='2026-01-05', is_end='2026-01-22',
                oos_start='2026-01-23', oos_end='2026-01-30')))
        assert response.status_code == 202, response.text
        job = wait_job(client, response.json()['id'])
        assert job['status'] == 'complete', job
        rows = client.get('/api/optimizations/' + job['id'] + '/results').json()['items']
        records = [client.get('/api/backtests/' + row['run_id']).json() for row in rows]
        body = declaration(job, records)
        preview = client.post(PREFIX + '/preview', json=body)
        assert preview.status_code == 200, preview.text
        candidates = preview.json()['candidates']
        assert {candidate['parameters']['min_rr'] for candidate in candidates} == {'0', '0.5'}
        assert all('min_rr' in c['numeric_parameters'] for c in candidates)
        assert all('use_eod_flat' not in c['numeric_parameters'] for c in candidates)
        campaign = save(client, body)
        result = run(client, campaign['campaign_id'])['result']
        for fold in result['folds']:
            assert fold['qualification']['approved_ids'] == []
            for candidate in fold['qualification']['candidates']:
                assert candidate['status'] == 'INSUFFICIENT_EVIDENCE'
                assert candidate['metrics']['validation_trades'] == 0
                assert len(candidate['parameter_stability']['neighbor_ids']) == 1


def test_changed_generated_trade_evidence_blocks_aggregate_publication(tmp_path, monkeypatch):
    with TestClient(create_app(tmp_path / 'datasets.sqlite3')) as client:
        _, job, records = save_grid(client)
        campaign = save(client, declaration(job, records)); id = campaign['campaign_id']
        store = client.app.state.robust_research
        original = store._backtest
        changed = []

        def damage_after_checkpoint(*args, **kwargs):
            result = original(*args, **kwargs)
            if not changed and args[-1] == 'inner_validation':
                path = client.app.state.runs.root / result['id'] / 'trades.csv'
                before = path.read_bytes()
                rows = list(csv.DictReader(io.StringIO(before.decode())))
                rows[0]['net_pnl'] = str(Decimal(rows[0]['net_pnl']) + 99999)
                buffer = io.StringIO(newline='')
                writer = csv.DictWriter(buffer, fieldnames=list(rows[0]))
                writer.writeheader(); writer.writerows(rows)
                path.write_text(buffer.getvalue())
                changed.append((path, before))
            return result

        with monkeypatch.context() as local:
            local.setattr(store, '_backtest', damage_after_checkpoint)
            response = client.post(PREFIX + '/' + id + '/run')
            assert response.status_code == 202, response.text
            try:
                stopped = wait_research(client, id)
                assert stopped['status'] == 'error', stopped
                assert 'changed' in stopped['error'].lower() or 'integrity' in stopped['error'].lower()
                assert client.get(PREFIX + '/' + id + '/exports/report.json').status_code == 409
                assert not (client.app.state.prop_analyses.root / stopped['analysis_id'] / 'report.json').exists()
            finally:
                for path, before in changed:
                    path.write_bytes(before)


def test_campaign_ids_cannot_collide_across_research_kinds(tmp_path):
    from test_research_campaigns import declaration as phase_declaration
    with TestClient(create_app(tmp_path / 'datasets.sqlite3')) as client:
        _, job, records = save_grid(client)
        robust_body = declaration(job, records)
        robust = save(client, robust_body)
        phase_body = phase_declaration(records[0], records[1], 'evaluation')
        phase_body['campaign_id'] = robust['campaign_id']
        response = client.post('/api/research-campaigns', json=phase_body)
        assert response.status_code == 409, response.text
        phase_body['campaign_id'] = uuid4().hex
        response = client.post('/api/research-campaigns', json=phase_body)
        assert response.status_code == 201, response.text
        robust_body['campaign_id'] = phase_body['campaign_id']
        response = client.post(PREFIX, json=robust_body)
        assert response.status_code == 409, response.text
        assert len(client.get(PREFIX).json()['items']) == 1
        with client.app.state.prop_analyses.connect() as db:
            assert db.execute('SELECT count(*) FROM research_campaigns').fetchone()[0] == 1
            assert db.execute('SELECT count(*) FROM robust_research').fetchone()[0] == 1
