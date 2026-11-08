"""Real MNQ/VWAP Lucid Evaluation campaigns, with independent cash/date oracles.

Synthetic complete minutes, source commission $0.50/contract/side, no slippage.
Each 1-MNQ source trade buys 118 and exits 268: $300 gross - $1 = $299.
No Funded owner participates in this Evaluation qualification.
"""
from copy import deepcopy
from datetime import datetime, timedelta
from decimal import Decimal
from hashlib import sha256
import io
import json
from threading import Event
from time import monotonic
from uuid import uuid4
import zipfile

import pytest
from fastapi.testclient import TestClient

from alphaquest.app import create_app
from native_replay_fixtures import parameter_values, source_bytes
from test_optimization import wait_job


def lucid_source(client, *, commission='0.5'):
    """Normal saved IS source with a separate complete ordinary manual OOS split."""
    lines = source_bytes(days=5, payout=True).decode().splitlines()
    later = []
    for line in lines[1:]:
        cells = line.split(',')
        cells[0] = (datetime.strptime(cells[0], '%m/%d/%Y') + timedelta(days=21)).strftime('%m/%d/%Y')
        later.append(','.join(cells))
    upload = client.post('/api/datasets', params=dict(filename='synthetic-lucid-evaluation-mnq.csv',
        name='SYNTHETIC Lucid Evaluation complete MNQ IS and manual OOS', symbol='MNQ',
        source_timezone='UTC', tick_size='0.25', point_value='2'),
        content=('\n'.join(lines + later) + '\n').encode())
    assert upload.status_code == 201, upload.text
    values = parameter_values()
    response = client.post('/api/optimizations', json=dict(dataset_id=upload.json()['id'],
        method='exhaustive', workers=1, automatic_prop=False, strategy_id='vwap_pullback_risk_sizing',
        parameter_ranges={key: dict(start=value, end=value, step='0' if isinstance(value, str) else 0)
                          for key, value in values.items()},
        execution_settings=dict(initial_capital='10000', slippage_ticks=0,
            commission_per_contract_per_side=commission),
        sample_split=dict(mode='dates', is_start='2026-01-04', is_end='2026-01-09',
            oos_start='2026-01-25', oos_end='2026-01-30')))
    assert response.status_code == 202, response.text
    job = wait_job(client, response.json()['id'])
    assert job['status'] == 'complete', job
    row, = client.get('/api/optimizations/' + job['id'] + '/results').json()['items']
    return client.get('/api/backtests/' + row['run_id']).json()


def lucid_declaration(client, original, *, sizes=(3, 10), horizon=7):
    """Explicit native Evaluation law; the calendar/delays are synthetic assumptions."""
    defaults = client.get('/api/prop-analyses/defaults').json()['native_phase_replay']
    profile = deepcopy(next(row for row in defaults['profiles']['evaluation']
                            if row['profile_id'] == 'lucidflex-50k'))
    profile.update(evaluation_price='80.5', activation_fee='0')
    return dict(campaign_id=uuid4().hex, phase='evaluation', profile=profile,
        sources=[dict(backtest_id=original['id'], sizes=list(sizes))],
        is_window=dict(first_session='2026-01-05', last_session='2026-01-09'),
        simulation=dict(simulations=4, seed=1729, max_micros=40),
        sampling=dict(block_weekdays=1, chain_simulations=4, chain_seed=1729),
        costs=dict(mode='source', instrument='MNQ'),
        retry=dict(activation_delay_sessions=0, max_calendar_days=30), search_settings=dict(
            calendar=dict(start_dates=['2026-01-12'], coverage_end='2026-01-20', closures=[],
                timezone='America/Chicago', version='explicit-synthetic-lucid-evaluation-v1'),
            native_execution=dict(model='observed_contiguous_blocks_with_prior_prefix_v1',
                horizon_calendar_days=horizon, early_closes={}, capture_paths=1)))


def wait_lucid_analysis(client, analysis_id):
    deadline = monotonic() + 120
    while monotonic() < deadline:
        row = client.get('/api/prop-analyses/' + analysis_id).json()
        if row['status'] not in ('queued', 'running'):
            assert row['status'] == 'complete', row
            return row
        Event().wait(.05)
    raise AssertionError('Native Lucid Evaluation analysis did not finish.')


def _campaign(client, request):
    response = client.post('/api/research-campaigns', json=request)
    assert response.status_code == 201, response.text
    campaign = response.json()
    checked = client.post('/api/research-campaigns/' + campaign['campaign_id'] + '/check')
    assert checked.status_code == 200, checked.text
    launched = client.post('/api/research-campaigns/' + campaign['campaign_id'] + '/run')
    assert launched.status_code == 202, launched.text
    analysis_id = launched.json()['analysis_id']
    wait_lucid_analysis(client, analysis_id)
    saved = client.get('/api/prop-analyses/' + analysis_id + '/downloads/report.json')
    assert saved.status_code == 200, saved.text
    return campaign, checked.json(), analysis_id, saved


@pytest.fixture(scope='module')
def lucid_library(tmp_path_factory):
    root = tmp_path_factory.mktemp('native-lucid-evaluation')
    with TestClient(create_app(root / 'library' / 'datasets.sqlite3')) as client:
        original = lucid_source(client)
        trades = client.get('/api/backtests/' + original['id'] + '/trades').json()['items']
        assert len(trades) == 5
        for row in trades:
            assert row['contracts'] == 1
            assert Decimal(row['entry_fill_price']) == 118
            assert Decimal(row['exit_fill_price']) == 268
            assert Decimal(row['gross_pnl']) == 300
            assert Decimal(row['total_commissions']) == 1
            assert Decimal(row['net_pnl']) == 299
        assert Decimal(original['summary']['final_equity']) == 11495
    return root, original


def _forbid_funded(*args, **kwargs):
    raise AssertionError('Funded simulation or payout selection entered Evaluation.')


def test_native_lucid_evaluation_campaign_consistency_fees_freeze_manual_oos_and_reopen(lucid_library, monkeypatch):
    root, original = lucid_library
    from alphaquest.prop import funded_profiles, funded_optimization, evaluation_optimization
    monkeypatch.setattr(funded_profiles, 'forecast_native_funded', _forbid_funded)
    monkeypatch.setattr(funded_profiles, 'NativeFundedController', _forbid_funded)
    monkeypatch.setattr(funded_optimization, 'optimize_funded', _forbid_funded)
    with TestClient(create_app(root / 'library' / 'datasets.sqlite3')) as client:
        request = lucid_declaration(client, original)
        # Explicit native support must not relax the separate saved-path guard.
        legacy = deepcopy(request)
        legacy['campaign_id'] = uuid4().hex
        del legacy['search_settings']['native_execution']
        rejected = client.post('/api/research-campaigns', json=legacy)
        assert rejected.status_code == 422 and 'native dated strategy rerun' in rejected.text, rejected.text
        original_trades = client.get('/api/backtests/' + original['id'] + '/exports/trades').content
        campaign, checked, analysis_id, saved = _campaign(client, request)
        campaign_id = campaign['campaign_id']
        assert campaign['manifest']['candidate_search_count'] == 2
        report = saved.json()
        rows = report['calculations']['candidates']
        by_size = {row['manifest']['configuration']['micros']: row for row in rows}
        assert set(by_size) == {3, 10}
        for quantity, pass_date, ready_date, days, profit, trades_count in [
            (3, '2026-01-15', '2026-01-16', 4, 3588, 4),
            (10, '2026-01-14', '2026-01-15', 3, 8970, 3),
        ]:
            row = by_size[quantity]
            assert row['metrics']['cost_per_funded'] == 80.5
            assert row['metrics']['expected_calendar_days_to_funded'] == days
            forecast = row['native_forecast']
            assert forecast['status'] == 'identified_model_mean'
            assert forecast['metrics']['completed_paths'] == 4
            assert forecast['metrics']['censored_paths'] == 0
            assert forecast['readiness'] == 'MODELED_SCENARIO_ONLY'
            for path in forecast['paths']:
                assert path['pass_date'] == pass_date and path['ready_date'] == ready_date
                assert path['eligibility_date'] == pass_date
                assert path['acquisition_completed'] is True and path['censored'] is False
                assert Decimal(path['paid_evaluation_fees']) == Decimal('80.5')
                assert Decimal(path['paid_activation_fees']) == 0
                assert Decimal(path['paid_fees']) == Decimal('80.5')
                assert Decimal(path['net_cash']) == Decimal('-80.5')
                assert Decimal(path['trading_profit']) == profit
                assert path['execution_counts']['completed_trades'] == trades_count
                assert len(path['attempts']) == 1
            detail = forecast['captures'][0]['result']
            assert detail['modeled_rules']['consistency_fraction'] == '0.4'
            assert detail['modeled_rules']['profit_target'] == '3000'
            assert detail['modeled_rules']['inactivity_calendar_days'] == 30
            assert detail['modeled_rules']['maximum_contracts'] == 40
            closes = [event for event in detail['control_events'] if event['event'] == 'trade_close']
            assert len(closes) == trades_count
            assert all(Decimal(event['net_pnl']) == 299 * quantity for event in closes)
            assert all(Decimal(event['total_commissions']) == quantity for event in closes)
        # q10 exceeds target after two days, but 2990/5980=50% violates 40%.
        states = by_size[10]['native_forecast']['captures'][0]['result']['trace']
        assert [Decimal(row['state_after']['equity_from_initial']) for row in states[:3]] == [2990, 5980, 8970]
        assert [row['state_after']['outcome'] for row in states[:3]] == ['open', 'open', 'activation_pending']
        assert Decimal(2990) > Decimal('.4') * 5980
        assert Decimal(2990) <= Decimal('.4') * 8970
        selected = by_size[10]['candidate_id']
        assert report['calculations']['frontier'] == [selected]
        assert report['calculations']['winner'] is None
        frozen = client.post('/api/research-campaigns/' + campaign_id + '/freeze', json=dict(
            candidate_ids=[selected], rationale='Synthetic Lucid target, 40% consistency, exact costs and independent acquisition dates verified.'))
        assert frozen.status_code == 200, frozen.text
        frozen_bytes = client.get('/api/research-campaigns/' + campaign_id + '/exports/frozen_package.json').content
        attempt = client.post('/api/research-campaigns/' + campaign_id + '/assessments', json=dict(request_id=uuid4().hex))
        assert attempt.status_code == 202, attempt.text
        assessment_id = attempt.json()['analysis_id']
        wait_lucid_analysis(client, assessment_id)
        actual_response = client.get('/api/prop-analyses/' + assessment_id + '/downloads/report.json')
        actual_report = actual_response.json()
        assert actual_report['calculations']['selection_status'] == 'assessment_only_no_reselection'
        assert actual_report['calculations']['frontier'] == []
        assert actual_report['calculations']['winner'] is None
        observed, = actual_report['calculations']['candidates']
        assert observed['frozen_candidate_id'] == selected
        actual = observed['native_chronological_replay']
        assert actual['historical_paths'] == 1 and actual['acquisition_completed'] is True
        assert actual['pass_date'] == '2026-01-28' and actual['ready_date'] == '2026-01-29'
        assert actual['calendar_days_to_funded'] == 3
        assert Decimal(actual['paid_fees']) == Decimal('80.5')
        assert Decimal(actual['paid_activation_fees']) == 0
        assert Decimal(actual['trading_profit']) == 8970
        child_id = observed['native_backtest_id']
        child = client.get('/api/backtests/' + child_id).json()
        trades = client.get('/api/backtests/' + child_id + '/trades').json()['items']
        assert len(trades) == 3
        assert [row['entry_time_utc'][:10] for row in trades] == ['2026-01-26', '2026-01-27', '2026-01-28']
        assert all(row['contracts'] == 10 and Decimal(row['gross_pnl']) == 3000
                   and Decimal(row['total_commissions']) == 10 and Decimal(row['net_pnl']) == 2990 for row in trades)
        assert Decimal(child['summary']['final_equity']) == 18970
        assert child_id in actual_report['native_backtests']
        assert client.delete('/api/backtests/' + child_id).status_code == 409
        archive = client.get('/api/prop-analyses/' + assessment_id + '/downloads/analysis.zip').content
        with zipfile.ZipFile(io.BytesIO(archive)) as zipped:
            assert f'native_backtests/{child_id}/native_account_control.json' in zipped.namelist()
        assert client.get('/api/backtests/' + original['id']).json() == original
        assert client.get('/api/backtests/' + original['id'] + '/exports/trades').content == original_trades
        # Identity changes remain launch blockers even for wording-bearing source files.
        identity = evaluation_optimization.implementation_identity()
        assert {'native_replay.py', 'native_control.py', 'lucid_engine.py',
                'lucid_rules.py', 'lucid_backend.py'} <= set(identity['files'])
        changed = deepcopy(identity)
        changed['files']['native_replay.py'] = '0' * 64
        with monkeypatch.context() as patch:
            patch.setattr(evaluation_optimization, 'implementation_identity', lambda: changed)
            blocked = client.post('/api/research-campaigns/' + campaign_id + '/assessments', json=dict(request_id=uuid4().hex))
            assert blocked.status_code == 409 and 'implementation changed' in blocked.text, blocked.text
            assert client.get('/api/prop-analyses/' + analysis_id + '/downloads/report.json').content == saved.content
            assert client.get('/api/prop-analyses/' + assessment_id + '/downloads/report.json').content == actual_response.content
            assert client.get('/api/research-campaigns/' + campaign_id + '/exports/frozen_package.json').content == frozen_bytes
        # A different selected Lucid runtime must also invalidate frozen launch,
        # independently of source-file text or the unchanged Apex backend.
        from alphaquest.prop import lucid_backend
        changed_lucid = {**lucid_backend.identity(), 'binary_sha256': '1' * 64}
        with monkeypatch.context() as patch:
            patch.setattr(lucid_backend, 'identity', lambda: changed_lucid)
            current = evaluation_optimization.implementation_identity()
            assert current['kernel'] == identity['kernel']
            assert current['lucid_kernel'] != identity['lucid_kernel']
            blocked = client.post('/api/research-campaigns/' + campaign_id + '/assessments', json=dict(request_id=uuid4().hex))
            assert blocked.status_code == 409 and 'implementation changed' in blocked.text, blocked.text
            assert client.get('/api/prop-analyses/' + assessment_id + '/downloads/report.json').content == actual_response.content
            assert client.get('/api/prop-analyses/' + assessment_id + '/downloads/analysis.zip').content == archive
        evidence = dict(library=str(root / 'library'), source_id=original['id'], campaign_id=campaign_id,
            analysis_id=analysis_id, assessment_id=assessment_id, native_backtest_id=child_id,
            request=request, selected_candidate_id=selected, source_check=checked,
            expected=dict(source_net_per_mnq=299, fees=80.5, activation_fee=0,
                calendar_days_by_quantity={'3': 4, '10': 3}, target_day_two_profit=5980,
                day_two_consistency='2990/5980 = 0.5 > 0.4', oos_pass_date='2026-01-28',
                oos_ready_date='2026-01-29', oos_trades=3, oos_quantity=10, oos_net=8970),
            report_sha256=sha256(saved.content).hexdigest(), assessment_sha256=sha256(actual_response.content).hexdigest(),
            archive_sha256=sha256(archive).hexdigest(), implementation=identity)
        (root / 'lucid-evaluation-evidence.json').write_text(json.dumps(evidence, indent=2))
    with TestClient(create_app(root / 'library' / 'datasets.sqlite3')) as client:
        assert client.get('/api/prop-analyses/' + analysis_id + '/downloads/report.json').content == saved.content
        assert client.get('/api/prop-analyses/' + assessment_id + '/downloads/report.json').content == actual_response.content
        assert client.get('/api/prop-analyses/' + assessment_id + '/downloads/analysis.zip').content == archive


def test_native_lucid_evaluation_readiness_at_exclusive_cutoff_is_censored(lucid_library):
    root, original = lucid_library
    with TestClient(create_app(root / 'library' / 'datasets.sqlite3')) as client:
        request = lucid_declaration(client, original, sizes=(10,), horizon=3)
        campaign, _, analysis_id, saved = _campaign(client, request)
        report = saved.json()
        row, = report['calculations']['candidates']
        assert report['calculations']['frontier'] == [] and report['calculations']['winner'] is None
        assert report['calculations']['unresolved_candidates'] == [row['candidate_id']]
        assert row['metrics']['cost_per_funded'] is None
        assert row['metrics']['expected_calendar_days_to_funded'] is None
        forecast = row['native_forecast']
        assert forecast['status'] == 'unresolved_censoring'
        assert forecast['metrics']['completed_paths'] == 0
        assert forecast['metrics']['censored_paths'] == 4
        assert forecast['metrics']['restricted_mean_paid_fees'] == 80.5
        assert forecast['metrics']['probability_acquisition_by_cutoff'] == 0
        for path in forecast['paths']:
            assert path['pass_date'] == '2026-01-14'
            assert path['ready_date'] == path['cutoff_date_exclusive'] == '2026-01-15'
            assert path['acquisition_completed'] is False and path['censored'] is True
            assert path['calendar_days_to_funded'] is None
            assert path['outcome'] == 'activation_pending'
            assert Decimal(path['paid_fees']) == Decimal('80.5')
            assert Decimal(path['trading_profit']) == 8970
        (root / 'lucid-censoring-evidence.json').write_text(json.dumps(dict(campaign_id=campaign['campaign_id'],
            analysis_id=analysis_id, request=request, expected=dict(pass_date='2026-01-14', ready_date='2026-01-15',
                cutoff_date_exclusive='2026-01-15', completed_paths=0, censored_paths=4, all_path_paid_fees=80.5,
                acquisition_means=None), report_sha256=sha256(saved.content).hexdigest()), indent=2))
