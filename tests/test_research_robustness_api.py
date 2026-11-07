"""Actual scenario reruns and causal condition evidence in saved research."""
from copy import deepcopy
from decimal import Decimal
import json
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest

from alphaquest.app import create_app
from alphaquest.backtest_api import run_backtest
from alphaquest.backtest_data import DateRange
from alphaquest.backtest_requests import ExecutionSettings
from alphaquest.strategies.registry import get_strategy
from test_robust_research_api import PREFIX, declaration, file_hashes, run, save, save_grid


def stress_request(job, records):
    body = declaration(job, records)
    body['execution_scenarios'] = [dict(name='cost_stress',
        additional_commission_per_contract_per_side='1', additional_slippage_ticks=1,
        stop_extra_slippage_ticks=2, limit_penetration_ticks=1, limit_price_improvement=False)]
    body['regimes'] = dict(enabled_names=['us_session', 'trend'], lookback_bars=2, minimum_training_features=2)
    body['qualification'].update(required_regimes=['us_session'], minimum_regime_sessions=4,
        minimum_regime_trades=4, maximum_signal_search_dimensions=1, maximum_enabled_optional_filters=0)
    return body


def test_actual_cost_scenario_reruns_and_causal_regimes_are_saved(tmp_path):
    with TestClient(create_app(tmp_path/'datasets.sqlite3')) as client:
        _, job, records = save_grid(client)
        before = file_hashes(client.app.state.runs.root)
        body = stress_request(job, records)
        preview = client.post(PREFIX+'/preview', json=body)
        assert preview.status_code == 200, preview.text
        plan = preview.json()
        assert plan['estimated_backtests'] == 24  # 16 baseline + 8 genuine validation reruns.
        assert plan['qualification']['required_scenarios'] == ['cost_stress']
        assert all(c['non_signal_parameters'] == ['contracts'] for c in plan['candidates'])
        saved = run(client, save(client, body)['campaign_id'])
        for fold in saved['result']['folds']:
            assert fold['outer_test_status'] == 'not_run'
            for row in fold['qualification']['candidates']:
                expected = Decimal('300') if row['parameters']['green_bar_count'] == 1 else Decimal('100')
                assert row['status'] == 'PASS', row
                scenario = row['execution_stress']['scenarios'][0]
                # One MNQ: extra commission =2*$1; extra market slip=2*.25*$2=$1.
                # Timed exits are not stop exits, so extra stop ticks do not apply.
                assert Decimal(scenario['mean_session_net']) == expected-3
                assert scenario['required'] and scenario['status'] == 'PASS'
                regimes = {r['name']: r for r in row['market_conditions']}
                assert regimes['us_session']['required']
                assert regimes['us_session']['classification_complete']
                assert regimes['us_session']['active_sessions'] == 4
                assert Decimal(regimes['us_session']['mean_session_net']) == expected
                assert not regimes['trend']['required']
                assert regimes['trend']['status'] == 'INSUFFICIENT_EVIDENCE'
                assert row['complexity']['signal_search_dimensions'] == 1
            assert len(fold['backtests']) == 12
            for reference in fold['backtests']:
                record = client.get('/api/backtests/'+reference['run_id']).json()
                if reference['role'] == 'execution_scenario':
                    assert record['run_metadata']['research']['phase'] == 'inner'
                    scenario = record['run_metadata']['execution_scenario']
                    assert scenario['declaration']['name'] == 'cost_stress'
                    assert scenario['baseline_execution_settings']['commission_per_contract_per_side'] == '0'
                    assert record['execution_settings']['commission_per_contract_per_side'] == '1'
                    assert record['execution_settings']['slippage_ticks'] == 1
                    assert client.post('/api/backtests/'+record['id']+'/oos', json=dict(request_id=uuid4().hex)).status_code == 409
            for evidence in fold['regime_evidence']:
                assert evidence['fit']['status'] == 'complete'
                assert all(a['feature_asof'] is None or a['feature_asof'] < a['entry_time'] for a in evidence['assignments'])
                assert evidence['availability']['us_session']['complete']
        after = file_hashes(client.app.state.runs.root)
        assert all(after[name] == value for name,value in before.items())
        report = client.get(PREFIX+'/'+saved['campaign_id']+'/exports/report.json')
        (tmp_path/'actual-robustness-report.json').write_bytes(report.content)
        (tmp_path/'independent-expectations.json').write_text(json.dumps(dict(
            synthetic=True, new_backtests=24, baseline_means=[300,100], scenario_means=[297,97],
            scenario_additional_cost='2 sides * 1 contract * $1 commission + 2 sides * 0.25 points * $2/point',
            required_regime='us_session', trend_classification='insufficient warmup; diagnostic only',
            outer_status='not_run', campaign_id=saved['campaign_id']), indent=2))


def test_stress_failure_or_required_unknown_regime_prevents_admission(tmp_path):
    with TestClient(create_app(tmp_path/'datasets.sqlite3')) as client:
        _, job, records = save_grid(client)
        body = stress_request(job, records)
        body['execution_scenarios'][0]['additional_commission_per_contract_per_side'] = '200'
        result = run(client, save(client, body)['campaign_id'])['result']
        assert all(not f['qualification']['approved_ids'] for f in result['folds'])
        assert all('scenario_failed:cost_stress' in c['reasons'] for f in result['folds'] for c in f['qualification']['candidates'])
        body = stress_request(job, records)
        body['qualification']['required_regimes'] = ['trend']
        result = run(client, save(client, body)['campaign_id'])['result']
        assert all(not f['qualification']['approved_ids'] for f in result['folds'])
        assert all(c['status'] == 'INSUFFICIENT_EVIDENCE' for f in result['folds'] for c in f['qualification']['candidates'])


def test_named_scenarios_strict_identity_and_unknown_required_evidence(tmp_path):
    with TestClient(create_app(tmp_path/'datasets.sqlite3')) as client:
        _, job, records = save_grid(client)
        body = stress_request(job, records)
        for mutate in (
            lambda b:b['execution_scenarios'].append(deepcopy(b['execution_scenarios'][0])),
            lambda b:b['execution_scenarios'][0].update(name='baseline'),
            lambda b:b['execution_scenarios'][0].update(additional_slippage_ticks=True),
            lambda b:b['regimes'].update(enabled_names=['future_outperformance']),
        ):
            invalid = deepcopy(body); mutate(invalid)
            response = client.post(PREFIX+'/preview', json=invalid)
            assert response.status_code == 422, response.text
        saved = save(client, body)
        changed = deepcopy(body); changed['execution_scenarios'][0]['limit_penetration_ticks'] = 2
        assert client.post(PREFIX, json=changed).status_code == 409


def native_sources(client, dataset, source, strategy_id, variants):
    """Ordinary native IS reports; no fixture manifests are edited or fabricated."""
    definition = get_strategy(strategy_id)
    defaults = {p['name']: p['default'] for p in definition.description()['parameters']}
    config = ExecutionSettings.model_validate(source['execution_settings']).execution_config(dataset)
    split = dict(source['run_metadata']['research']['plan'], strategy_id=strategy_id)
    return [run_backtest(client.app.state.store, client.app.state.runs, uuid4().hex,
        dataset, definition, definition.parameters(dict(defaults, **changes)), config,
        DateRange.parse(split['is_start'], split['is_end']), lambda *args: None,
        prop_analyses=None, research=dict(phase='is', plan=split), reuse_results=False,
        report_detail='compact') for changes in variants]


@pytest.mark.parametrize('variants', [
    [dict(use_adx_elev=False, adx_elev_thr='10'), dict(use_adx_elev=False, adx_elev_thr='20')],
    [dict(plot_trade_levels=True), dict(plot_trade_levels=False)],
    [dict(min_rr='1.0', mm_risk_pct='2.0'), dict(min_rr='1.00', mm_risk_pct='2.00')],
])
def test_preview_rejects_duplicate_effective_configurations_before_research(tmp_path, variants):
    with TestClient(create_app(tmp_path/'datasets.sqlite3')) as client:
        dataset, job, initial = save_grid(client)
        sources = native_sources(client, dataset, initial[0], 'vwap_pullback_risk_sizing',
                                 [dict(use_eod_flat=False, **v) for v in variants])
        body = declaration(job, sources)
        body['sources'] = [dict(backtest_id=s['id'], sizes=[1]) for s in sources]
        before = file_hashes(client.app.state.runs.root)
        for endpoint in (PREFIX+'/preview', PREFIX):
            rejected = client.post(endpoint, json=body)
            assert rejected.status_code == 422, rejected.text
            assert 'Duplicate effective signal configurations' in rejected.text
        assert client.get('/api/backtests').json()['total'] == 4
        assert file_hashes(client.app.state.runs.root) == before


def test_preview_normalizes_source_sizing_spelling_but_rejects_quantity_search(tmp_path):
    with TestClient(create_app(tmp_path/'datasets.sqlite3')) as client:
        dataset, job, initial = save_grid(client)
        sources = native_sources(client, dataset, initial[0], 'vwap_pullback_risk_sizing', [
            dict(use_eod_flat=False, min_rr='1', mm_risk_pct='2.0'),
            dict(use_eod_flat=False, min_rr='2', mm_risk_pct='2.00')])
        body = declaration(job, sources)
        body['sources'] = [dict(backtest_id=s['id'], sizes=[1]) for s in sources]
        before = file_hashes(client.app.state.runs.root)
        response = client.post(PREFIX+'/preview', json=body)
        assert response.status_code == 200, response.text
        assert {c['parameters']['mm_risk_pct'] for c in response.json()['candidates']} == {'2.0', '2.00'}
        assert file_hashes(client.app.state.runs.root) == before
        larger = native_sources(client, dataset, initial[0], 'consecutive_green_hold', [
            dict(green_bar_count=1, hold_minutes=1, contracts=2)])[0]
        body = declaration(job, [initial[0], larger])
        body['sources'] = [dict(backtest_id=s['id'], sizes=[1]) for s in [initial[0], larger]]
        before = file_hashes(client.app.state.runs.root)
        for endpoint in (PREFIX+'/preview', PREFIX):
            rejected = client.post(endpoint, json=body)
            assert rejected.status_code == 422, rejected.text
            assert 'one fixed source-sizing configuration per strategy' in rejected.text
        assert file_hashes(client.app.state.runs.root) == before


def test_scenario_bearing_is_sources_cannot_silently_drop_fill_assumptions(tmp_path):
    with TestClient(create_app(tmp_path/'datasets.sqlite3')) as client:
        dataset, job, records = save_grid(client)
        source = records[0]
        definition = get_strategy(source['run_metadata']['strategy']['id'])
        split = source['run_metadata']['research']['plan']
        config = ExecutionSettings.model_validate(source['execution_settings']).execution_config(dataset)
        scenario = run_backtest(client.app.state.store, client.app.state.runs, uuid4().hex,
            dataset, definition, definition.parameters(source['run_metadata']['strategy']['parameters']),
            config, DateRange.parse(split['is_start'], split['is_end']), lambda *args: None,
            prop_analyses=None, research=dict(phase='is', plan=split), reuse_results=False,
            execution_scenario=dict(name='programmatic-stop-assumption', stop_extra_slippage_ticks=2))
        body = declaration(job, [scenario])
        body['sources'] = [dict(backtest_id=scenario['id'], sizes=[1])]
        before = file_hashes(client.app.state.runs.root)
        response = client.post(PREFIX+'/preview', json=body)
        assert response.status_code == 422, response.text
        assert 'scenario-bearing' in response.text
        response = client.post('/api/backtests/'+scenario['id']+'/oos', json=dict(request_id=uuid4().hex))
        assert response.status_code == 409, response.text
        assert 'scenario' in response.text
        assert file_hashes(client.app.state.runs.root) == before
