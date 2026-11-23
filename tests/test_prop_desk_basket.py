"""Basket contracts on ordinary saved NQ backtests and licensed-free synthetic data."""
import csv
from copy import deepcopy
from decimal import Decimal
from io import StringIO
import json
from threading import Event
from uuid import uuid4

import pytest

from alphaquest.app import create_app
from alphaquest.prop import desk, desk_basket
from prop_desk_fixtures import desk_calculator_sources
from research_fixtures import ResearchClient
from test_prop_analysis_api import wait
from test_prop_phases import phase_history


def saved_members(client):
    query = dict(filename='SYNTHETIC-basket.csv', name='SYNTHETIC Prop Desk basket',
        source_timezone='UTC', tick_size='.25', point_value='20', symbol='NQ')
    uploaded = client.post('/api/datasets', params=query, content=phase_history(days=9))
    assert uploaded.status_code == 201, uploaded.text
    dataset = uploaded.json()
    plan = dict(mode='dates', is_start='2026-01-05', is_end='2026-01-14',
                oos_start='2026-01-15', oos_end='2026-01-15')
    members = []
    for hold, weight in ((1, 2), (2, 1)):
        response = client.post('/api/backtests', json=dict(dataset_id=dataset['id'],
            strategy_id='consecutive_green_hold',
            strategy_parameters=dict(green_bar_count=1, hold_minutes=hold, contracts=1),
            execution_settings=dict(initial_capital='10000', tick_size='.25', point_value='20',
                slippage_ticks=0, commission_per_contract_per_side='5'), sample_split=plan))
        assert response.status_code == 201, response.text
        id = response.json()['id']
        oos = client.post(f'/api/backtests/{id}/oos', json=dict(request_id=str(uuid4())))
        assert oos.status_code == 201, oos.text
        members.append(dict(source_backtest_id=id, oos_backtest_id=oos.json()['id'], weight=weight))
    return dataset, members


def run(client, path, config):
    launch = client.post(path, json=config)
    assert launch.status_code == 202, launch.text
    id = launch.json()['id']
    job = wait(client, id)
    assert job['status'] == 'complete', job
    response = client.get('/api/prop-desk/' + id)
    assert response.status_code == 200, response.text
    return response.json()


def test_strategy_catalogue_uses_the_qualified_child(tmp_path):
    with ResearchClient(create_app(tmp_path / 'datasets.sqlite3')) as client:
        # Metadata-only catalogue fixtures. The browser journey creates and verifies real artifacts.
        plan = dict(is_start='2026-01-05', is_end='2026-01-14', oos_start='2026-01-15', oos_end='2026-01-15')
        source = dict(id='a' * 32, status='complete', period_start_utc='2026-01-05T18:00:00Z',
                      period_end_utc='2026-01-14T18:15:00Z', execution_settings={'commission': '5'},
                      run_metadata=dict(strategy={'id': 'consecutive_green_hold', 'parameters': {'hold_minutes': 1}},
                                        dataset={'id': 'dataset', 'name': 'Example NQ', 'symbol': 'NQ'},
                                        research={'phase': 'is', 'plan': plan}))
        other = deepcopy(source)
        other['id'] = 'b' * 32
        other['run_metadata']['strategy']['parameters']['hold_minutes'] = 2
        child = deepcopy(source)
        child.update(period_start_utc='2026-01-15T18:00:00Z', period_end_utc='2026-01-15T18:15:00Z')
        child['run_metadata']['research'].update(phase='oos', parent_run_id=source['id'])
        attempts = []
        for id in ('c' * 32, 'd' * 32, 'e' * 32):
            attempts.append(deepcopy(dict(child, id=id)))
        attempts[-1]['execution_settings']['commission'] = '10'
        with client.app.state.runs.connect() as db:
            for sequence, record in enumerate([other, source, *attempts], 1):
                db.execute('INSERT INTO runs VALUES (?,?,?)', (record['id'], str(sequence), json.dumps(record)))
        from alphaquest.prop_desk import catalogue_page
        candidates = [dict(source_backtest_id=source['id'], oos_report_id='c' * 32)]
        page = catalogue_page(client.app.state.runs, candidates, 0, 1)
        item, = page['items']
        assert page['total'] == 1 and item['id'] == source['id']
        assert item['oos'] == dict(id='c' * 32, first_session='2026-01-15', last_session='2026-01-15')


def test_basket_window_conflicts_costs_and_m1_identity(tmp_path, monkeypatch, desk_calculator_sources):
    root = '/api/prop-desk'
    path = root + '/basket'
    inventories = []
    inventory_sessions = desk_basket.inventory_sessions

    def count_inventory(source, dataset_id, **settings):
        inventories.append(dataset_id)
        return inventory_sessions(source, dataset_id, **settings)

    monkeypatch.setattr(desk_basket, 'inventory_sessions', count_inventory)
    with ResearchClient(create_app(tmp_path / 'datasets.sqlite3')) as client:
        dataset, members = saved_members(client)
        # The normal backtest source check prepared the shared inventory.
        with client.app.state.store.connect() as db:
            assert db.execute('SELECT 1 FROM dataset_session_inventory WHERE dataset_id=?',
                              (dataset['id'],)).fetchone()

        def unexpected_bar_parse(*args, **kwargs):
            pytest.fail('Warm Prop Desk launches must not parse dataset bars again.')

        monkeypatch.setattr('alphaquest.research_folds.read_bars', unexpected_bar_parse)
        config = dict(members=members, profile_id='apex-50k-eod', phase='evaluation',
                      minimum_micros=3, maximum_micros=5)
        swapped = [dict(m, oos_backtest_id=members[1-i]['oos_backtest_id']) for i, m in enumerate(members)]
        rejected = client.post(path + '/check', json=dict(config, members=swapped))
        assert rejected.status_code == 422
        assert 'retain its selected IS parent' in rejected.json()['detail']
        job = run(client, path, config)
        assert inventories == [dataset['id']]
        report = job['report']
        basket = report['basket']
        assert basket['windows']['is'] == ['2026-01-05', '2026-01-06', '2026-01-07', '2026-01-08',
                                            '2026-01-09', '2026-01-12', '2026-01-13', '2026-01-14']
        assert basket['windows']['oos'] == ['2026-01-15']
        assert [r['allocation'] for r in basket['sizes']] == [
            dict(micros=[2, 1], unused=0), dict(micros=[2, 1], unused=1), dict(micros=[3, 1], unused=1)]
        assert [row['metrics']['median_trading_days_to_target'] for row in basket['sizes']] == [6, 6, 4]
        assert basket['sizes'][0]['overlap_skips'] == {'is': 8, 'oos': 1}
        prefix = '/api/prop-analyses/' + job['id'] + '/files/'
        for size, target in ((3, 2), (5, 3)):
            chart = client.get(prefix + f'equity_{size}.json').json()
            trades = list(csv.DictReader(StringIO(client.get(prefix + chart['trades_file']).text)))
            # Only the higher-weight same-time entry gets the position.
            # $3,000 gross less $10 round trip per NQ. Divide by 10 for MNQ.
            net = Decimal(299 * target)
            assert len(trades) == 9
            assert all(row['member'] == '1' and Decimal(row['commission']) == target
                       and Decimal(row['net_pnl']) == net for row in trades)
            assert Decimal(str(chart['final_equity_change'])) == sum(Decimal(t['net_pnl']) for t in trades) == 9 * net
            assert chart['levels'][-1] == [9 * net, 9 * net, 0]
            assert chart['metrics']['annual_return'] == net * 252
            assert chart['metrics']['maximum_drawdown'] == 0
            assert chart['oos_start'] == '2026-01-15'
        assert client.get(root + '/' + job['id']).json()['report'] == report
        single = dict(source_backtest_id=members[0]['source_backtest_id'], profile_id='apex-50k-eod',
                      phase='evaluation', micros=3)
        fixed = run(client, root, single)
        one = run(client, path, dict(config, members=[dict(members[0], oos_backtest_id=None)], maximum_micros=3))
        assert one['report']['basket']['sizes'][0]['metrics'] == fixed['report']['calculations']
        def paths(job, file):
            return client.get('/api/prop-analyses/' + job['id'] + '/files/' + file).json()
        assert paths(one, 'paths_3.json') == paths(fixed, 'path_outcomes.json')

        funded_spec = dict(single, phase='funded', profile_id='lucidflex-50k', observation_sessions=261)
        fixed_funded = run(client, root, funded_spec)
        one_funded = run(client, path, dict(config, members=[members[0]], maximum_micros=3,
            phase='funded', profile_id='lucidflex-50k', observation_sessions=261))
        assert paths(one_funded, 'paths_3.json') == paths(fixed_funded, 'path_outcomes.json')
        multi_funded = run(client, path, dict(config, phase='funded', maximum_micros=3,
                                              observation_sessions=261))
        metrics = multi_funded['report']['basket']['sizes'][0]['metrics']
        # At USD 598/day the first USD 1,500 payout needs seven days to
        # clear the USD 2,100 buffer. Each subsequent cap needs five days.
        assert [p['median_trading_day'] for p in metrics['milestones']] == [7, 12, 17, 22, 27, 32]
        assert metrics['first_year_mean_receipts'] == metrics['account_life_mean_receipts'] == 13000


@pytest.mark.parametrize('tamper', ['dataset', 'trades'])
def test_queued_basket_rejects_changed_verified_input(tmp_path, tamper, desk_calculator_sources):
    with ResearchClient(create_app(tmp_path / 'datasets.sqlite3')) as client:
        dataset, members = saved_members(client)
        state = client.app.state
        release = Event()
        state.prop_analyses.worker.submit(release.wait, 15)
        try:
            launched = client.post('/api/prop-desk/basket', json=dict(
                members=members, profile_id='apex-50k-eod', phase='evaluation',
                minimum_micros=3, maximum_micros=3))
            assert launched.status_code == 202, launched.text
            assert launched.json()['status'] == 'queued'
            if tamper == 'dataset':
                with state.store.connect() as db:
                    db.execute('UPDATE dataset_chunks SET data=? WHERE dataset_id=?', (b'invalid', dataset['id']))
                error = 'saved basket dataset bytes changed'
            else:
                with (state.runs.root / members[0]['source_backtest_id'] / 'trades.csv').open('ab') as stream:
                    stream.write(b' ')
                error = 'Source trades/risk/export changed'
        finally:
            release.set()
        job = wait(client, launched.json()['id'])
        assert job['status'] == 'error' and error in job['error']
        assert not (state.prop_analyses.root / job['id']).exists()


def test_funded_member_target_respects_opening_tiers_and_censoring():
    # Each source opportunity is $300 net per NQ. Request 23 MNQ for member 1.
    # Lucid opens at 20 MNQ so day one earns $600, with no payout or termination.
    prepared = dict(profile=desk.FundedProfile('lucidflex-50k', desk.rule_version('lucidflex-50k')),
        simulation=desk.SimulationConfig(4, 42, 40), sampling=desk.SamplingConfig(1))
    days = {'2026-01-05': [(0, dict(scenario=(300., 0., (), True)))]}
    paths, rules = desk_basket.funded_paths(days, [23, 3], prepared, 1)
    assert {p['equity'] for p in paths} == {600}
    metrics = desk_basket.funded_results(paths, rules)
    assert metrics['account_life_mean_receipts'] is None and metrics['open_at_cutoff'] == 4
