"""Combination ranking over saved IS/OOS sources with independently known outcomes."""

import csv
from dataclasses import replace
from decimal import Decimal
from io import StringIO
from uuid import uuid4

import numpy as np
import pytest

from alphaquest.app import create_app
from alphaquest.prop import desk, desk_basket, desk_optimizer
from prop_desk_fixtures import desk_calculator_sources
from research_fixtures import ResearchClient
from test_prop_desk_basket import run
from test_prop_phases import phase_history


def optimizer_members(client):
    response = client.post('/api/datasets', params=dict(filename='SYNTHETIC-optimizer.csv',
        name='SYNTHETIC Prop Desk optimizer', source_timezone='UTC', tick_size='.25', point_value='20', symbol='NQ'),
        content=phase_history(days=9))
    assert response.status_code == 201, response.text
    dataset = response.json()
    plan = dict(mode='dates', is_start='2026-01-05', is_end='2026-01-14',
                oos_start='2026-01-15', oos_end='2026-01-15')
    members = []
    for hold, commission in ((1, '1500'), (2, '5'), (3, '5')):
        progress_id = str(uuid4())
        response = client.post('/api/backtests', params=dict(progress_id=progress_id), json=dict(dataset_id=dataset['id'],
            strategy_id='consecutive_green_hold',
            strategy_parameters=dict(green_bar_count=1, hold_minutes=hold, contracts=1),
            execution_settings=dict(initial_capital='10000', tick_size='.25', point_value='20',
                slippage_ticks=0, commission_per_contract_per_side=commission), sample_split=plan))
        assert response.status_code == 201, (response.text, client.get(f'/api/progress/{progress_id}').json())
        source_id = response.json()['id']
        oos = client.post(f'/api/backtests/{source_id}/oos', json=dict(request_id=str(uuid4())))
        assert oos.status_code == 201, oos.text
        members.append(dict(source_backtest_id=source_id, oos_backtest_id=oos.json()['id'], weight=1))
    return dataset, members


def assert_rankings(result, phase):
    # AB, AC, and BC each receive a 1/1 target at 2 MNQ and one unused
    # contract at 3 MNQ. Ties in entry are won by the first member.
    # A's NQ round trip earns exactly $3,000 gross and costs $3,000.
    # B's round trip earns $4,000 gross minus $10, or $399 per MNQ.
    # B passes $3,000 on day 8. At $399/day it reaches Apex's $3,600
    # first request threshold on day 10. All six payouts fit in 261 days.
    winner = 1 if phase == 'evaluation' else 13000
    actual = [(row['combination'], row['micros'], row['rank'], row['score'], row['tied'])
              for row in result['ranking']]
    assert actual == [(3, 2, 1, winner, True), (3, 3, 1, winner, True),
                      (1, 2, 3, 0, True), (2, 2, 3, 0, True),
                      (1, 3, 3, 0, True), (2, 3, 3, 0, True)]
    assert result['workload'] == dict(combinations=3, pairs=6)
    assert [row['members'] for row in result['combinations']] == [[0, 1], [0, 2], [1, 2]]
    for combo in result['combinations']:
        assert [row['allocation'] for row in combo['sizes']] == [
            dict(micros=[1, 1], unused=0), dict(micros=[1, 1], unused=1)]
    metrics = result['combinations'][2]['sizes'][0]['metrics']
    if phase == 'evaluation':
        assert metrics['median_trading_days_to_target'] == 8
        assert metrics['outcome_counts'] == dict(passed=1000, breached=0, provider_expired=0)
    else:
        assert metrics['milestones'][0]['median_trading_day'] == 10
        assert metrics['open_at_cutoff'] == 0


@pytest.mark.parametrize('profile_id', ['apex-50k-eod', 'lucidflex-50k'])
def test_optimizer_reuses_path_streams_and_funded_tiers(profile_id):
    seeds = [17, 89, 23, 19]
    days = {'2026-01-05': [(0, {'scenario': (15000., 0.)})], '2026-01-06': []}
    version = desk.rule_version(profile_id)
    lucid = profile_id == 'lucidflex-50k'
    simulation = desk.SimulationConfig(len(seeds), 42, 40)
    prepared = dict(profile=desk.EvaluationProfile(profile_id, version, '80.50' if lucid else '49', '0'),
                    simulation=simulation, sampling=desk.SamplingConfig(1), evidence={'kernel': 'test'})
    for target in (1, 2):
        _, outcomes, _ = desk_optimizer.evaluation(days, [target], prepared, 7, seeds)
        required = 3 if lucid else 2 // target
        expected = []
        for seed in seeds:
            winning_days = [day for day, index in enumerate(np.random.RandomState(seed).randint(2, size=7), 1)
                            if index == 0]
            expected.append(dict(outcome='passed', trading_sessions=winning_days[required - 1])
                            if len(winning_days) >= required else dict(
                                outcome='observation_cutoff' if lucid else 'provider_expired', trading_sessions=7))
        assert outcomes == expected

    prepared['profile'] = desk.FundedProfile(profile_id, version)
    days['2026-01-05'][0][1]['scenario'] = (300., 0.)
    for target in (1, 23):
        _, outcomes, rules = desk_optimizer.funded(days, [target], prepared, 25, seeds)
        expected = []
        for seed in seeds:
            setup = dict(prepared, simulation=replace(simulation, simulations=1, seed=seed))
            paths, ordinary_rules = desk_basket.funded_paths(days, [target], setup, 25)
            assert ordinary_rules == rules
            expected.extend(paths)
        assert outcomes == expected


def test_optimizer_shared_inventory_rank_parity_and_oos_independence(tmp_path, monkeypatch, desk_calculator_sources):
    inventories, books = [], []
    original_inventory, original_book = desk_basket.inventory_sessions, desk_basket.source_book

    def inventory(source, dataset_id, **settings):
        inventories.append(dataset_id)
        return original_inventory(source, dataset_id, **settings)

    def source_book(runs, analyses, record, profile, days):
        books.append(record['id'])
        return original_book(runs, analyses, record, profile, days)

    monkeypatch.setattr(desk_basket, 'inventory_sessions', inventory)
    monkeypatch.setattr(desk_basket, 'source_book', source_book)
    endpoint = '/api/prop-desk/optimizer'
    with ResearchClient(create_app(tmp_path / 'datasets.sqlite3')) as client:
        dataset, members = optimizer_members(client)
        def unexpected_bar_parse(*args, **kwargs):
            pytest.fail('Warm Prop Desk searches must not parse dataset bars again.')

        monkeypatch.setattr('alphaquest.research_folds.read_bars', unexpected_bar_parse)
        config = dict(members=members, minimum_members=2, maximum_members=2,
                      minimum_micros=2, maximum_micros=3, phase='evaluation', profile_id='apex-50k-eod')
        oversized = client.post(endpoint, json=dict(config, maximum_micros=60))
        assert oversized.status_code == 422 and '177 combination-size pairs' in oversized.json()['detail']
        wrong_child = [dict(members[0], oos_backtest_id=members[1]['oos_backtest_id']), *members[1:]]
        rejected = client.post(endpoint, json=dict(config, members=wrong_child))
        assert rejected.status_code == 422 and 'retain its selected IS parent' in rejected.json()['detail']
        assert inventories == [] and books == []
        evaluation = run(client, endpoint, config)
        assert inventories == [dataset['id']]
        assert books == [member[key] for key in ('source_backtest_id', 'oos_backtest_id') for member in members]
        result = evaluation['report']['optimizer']
        assert_rankings(result, 'evaluation')
        assert len(result['is_days']) == 8
        assert result['combinations'][2]['oos_days'] == ['2026-01-15']

        # Remove A's OOS child. AB and AC lose their OOS charts, but BC and
        # the full ranking (including the ranking seal) stay the same.
        partial = [dict(members[0], oos_backtest_id=None), *members[1:]]
        oos_comparison = run(client, endpoint, dict(config, members=partial))['report']['optimizer']
        assert oos_comparison['ranking'] == result['ranking']
        assert oos_comparison['ranking_sha256'] == result['ranking_sha256']
        assert not oos_comparison['combinations'][0]['oos_days']
        assert oos_comparison['combinations'][2]['oos_days'] == ['2026-01-15']

        for phase in ('evaluation', 'funded'):
            optimized = evaluation if phase == 'evaluation' else run(client, endpoint, dict(config,
                phase='funded', observation_sessions=261))
            assert_rankings(optimized['report']['optimizer'], phase)
            ordinary = run(client, '/api/prop-desk/basket', dict(members=members[1:], phase=phase,
                profile_id='apex-50k-eod', minimum_micros=2, maximum_micros=3,
                observation_sessions=21 if phase == 'evaluation' else 261))
            optimizer = optimized['report']['optimizer']
            assert optimizer['is_days'] == ordinary['report']['basket']['windows']['is']
            assert optimizer['combinations'][2]['sizes'] == ordinary['report']['basket']['sizes']
            prefix = f"/api/prop-analyses/{optimized['id']}/files/combination_3/"
            expected = f"/api/prop-analyses/{ordinary['id']}/files/"
            assert client.get(prefix + 'paths_3.json').json() == client.get(expected + 'paths_3.json').json()
            equity = client.get(prefix + 'equity_3.json').json()
            trades = list(csv.DictReader(StringIO(client.get(prefix + equity['trades_file']).text)))
            assert len(trades) == 9
            assert sum(Decimal(trade['net_pnl']) for trade in trades) == Decimal('3591')
            assert equity['final_equity_change'] == 3591
            assert all(trade['source_backtest_id'] in {
                members[1]['source_backtest_id'], members[1]['oos_backtest_id']} for trade in trades)
