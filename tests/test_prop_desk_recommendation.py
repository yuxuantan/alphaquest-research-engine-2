"""Independent allocation oracles and parity with the existing account path owners."""

from dataclasses import replace

import pytest

from alphaquest.prop import desk, desk_global_ranking, desk_optimizer, desk_recommendation as recommendation
from alphaquest.prop_desk import automatic_oos_candidates


def prepared(phase, profile_id, days, paths=8):
    version = desk.rule_version(profile_id)
    profile = (desk.EvaluationProfile(profile_id, version, '49', '0') if phase == 'evaluation'
               else desk.FundedProfile(profile_id, version))
    simulation = desk.SimulationConfig(paths, 42, desk.PROFILES[profile_id]['caps'][phase])
    return dict(profile=profile, simulation=simulation, sampling=desk.SamplingConfig(1),
                evidence=dict(kernel='fixture', implementation_sha256={}, profile=profile_id, dataset='fixture',
                              sampling=dict(block=1), simulation=dict(paths=paths)),
                is_days=list(days), oos_days={}, oos_books={})


@pytest.mark.parametrize('profile_id', ['apex-50k-eod', 'lucidflex-50k'])
@pytest.mark.parametrize('phase', ['evaluation', 'funded'])
def test_batched_owning_engine_matches_legacy_path_for_path(profile_id, phase):
    days = {'win': [(0, {'scenario': (15000., 280.)}), (1, {'scenario': (1100., 88.)})],
            'lose': [(0, {'scenario': (-1100., 3000.)})], 'flat': []}
    setup = prepared(phase, profile_id, days)
    configuration = dict(phase=phase, observation_sessions=21 if phase == 'evaluation' else 261,
                         size_rule='optimal' if phase == 'evaluation' else 'first_year', overlap_policy='sequential_mae')
    old = desk_optimizer.evaluation if phase == 'evaluation' else desk_optimizer.funded
    seeds = recommendation.path_seeds(setup['simulation'])
    for sizes in ([3, 1], [20, 6]):
        comparison, actual_paths, rules = recommendation.evaluate(days, sizes, setup, configuration, seeds)
        baseline, expected_paths, expected_rules = old(days, sizes, setup, configuration['observation_sessions'],
                                                       seeds, sequential=True)
        assert actual_paths == expected_paths
        assert rules == expected_rules
        if phase == 'evaluation':
            assert comparison['probabilities'] == baseline['probabilities']
        else:
            assert comparison['mean_trader_receipts'] == baseline['first_year_mean_receipts']


def test_whole_mnq_same_total_can_change_the_best_stage_allocation():
    # With one identical session as the population, daily net is $190*A + $20*B.
    # 1+1 = $210 (no qualifying day), 1+2 = $230 (no qualifying day), 2+1
    # = $400 (qualifies). All three pass Evaluation within 21 sessions.
    days = ['2026-01-05']
    members = [dict(weight=1), dict(weight=1)]
    books = [{days[0]: [dict(entry=0, exit=2, id='1', scenario=(pnl, 0.))]} for pnl in (1900., 200.)]
    for phase, targets in [('evaluation', [1, 1]), ('funded', [2, 1])]:
        setup = prepared(phase, 'apex-50k-eod', days)
        setup.update(is_books=books, snapshots={'is': [dict(manifest_sha256=f'strategy-{i}',
            trades_sha256=f'trades-{i}', excursion_input={}) for i in range(2)]})
        config = dict(members=members, minimum_members=2, minimum_micros=2, maximum_micros=3,
                      allocation_search='individual', phase=phase, observation_sessions=21 if phase == 'evaluation' else 261,
                      overlap_policy='sequential_mae', size_rule='optimal' if phase == 'evaluation' else 'first_year')
        result, _, _ = recommendation.calculate(setup, config, lambda message: None)
        assert result['workload']['feasible'] == result['workload']['tested'] == 3
        rows = {row['targets']: row['metrics'] for row in result['groups'][0]['candidates']}
        winner = result['ranking'][0]['candidate']
        assert winner == '1-' + '-'.join(map(str, targets))
        if phase == 'evaluation':
            assert rows[1, 2]['median_trading_days_to_target'] == 14
            assert rows[2, 1]['median_trading_days_to_target'] == 8
        else:
            assert rows[1, 2]['probability_any_payout'] == 0
            assert rows[2, 1]['mean_trader_receipts'] == 13000
            assert rows[2, 1]['milestones'][0]['median_trading_day'] == 9


def test_bounded_has_a_reproducible_budget_and_exact_count():
    assert sum(recommendation.feasible_count(size, 1, 5) * n for size, n in [(1, 4), (2, 6), (3, 4), (4, 1)]) == 125
    assert list(recommendation.positive_mixes(3, 4, 4)) == [(1, 1, 2), (1, 2, 1), (2, 1, 1)]


def test_refinement_keeps_paired_close_contenders_and_exact_ties():
    leader = [1] * 48 + [0] * 48
    outcomes = {(1, 5): leader, (2, 4): [0] + leader[1:], (3, 3): [0] * 3 + leader[3:],
                (4, 2): [0] * 40 + leader[40:], (5, 1): leader}
    leaders = [dict(targets=target) for target in ((1, 5), (5, 1), (2, 4), (3, 3), (4, 2))]
    assert recommendation.refine_targets(leaders, outcomes) == [(1, 5), (5, 1), (2, 4), (3, 3)]
    leaders = [leaders[i] for i in (0, 2, 1, 3, 4)]
    assert recommendation.refine_targets(leaders, outcomes) == [(1, 5), (2, 4), (5, 1), (3, 3)]


def test_automatic_oos_uses_ranked_sizes_and_verified_coverage():
    parent = dict(configuration={'members': [{'oos_backtest_id':'a'}, {'oos_backtest_id':None}]},
                  recommendation={'oos_days':['2026-01-15'],
                      'ranking':[dict(combination=1, candidate='1-2', path_count=1000),
                                 dict(combination=2, candidate='2-3', path_count=1000)],
                      'groups':[dict(id=1, members=[0], candidates=[dict(id='1-2', paths=1000),
                          dict(id='1-3', paths=1000), dict(id='1-4', paths=96)]),
                          dict(id=2, members=[1], candidates=[dict(id='2-3', paths=1000)])]})
    assert automatic_oos_candidates(parent) == ['1-2']
    parent['configuration']['fixed_basket'] = True
    assert automatic_oos_candidates(parent) == ['1-2', '1-3']
    parent['recommendation']['oos_days'] = []
    assert automatic_oos_candidates(parent) == []


def test_full_grid_workload_and_strict_payout_ranking():
    config = dict(phase='funded', size_rule='first_year', members=[{}, {}], minimum_members=1,
                  minimum_micros=2, maximum_micros=40, observation_sessions=90)
    assert desk_global_ranking.workload(config) == 858
    with pytest.raises(ValueError, match='858 allocations.*383'):
        desk_global_ranking.workload(dict(config, observation_sessions=261))

    def candidate(id, micros, probability, day):
        return dict(id=id, combination=1, targets=(micros,), tested_total=micros, paths=1000,
                    size_provisional=False, metrics=dict(probability_any_payout=probability,
                        mean_trader_receipts=100, milestones=[dict(median_trading_day=day)]))

    rows = [candidate('1-4', 4, .5, 10), candidate('1-3', 3, .499, 5), candidate('1-2', 2, .5, 10)]
    result = desk_global_ranking.top_allocations([dict(candidates=rows)], config, 1000)
    assert [row['candidate'] for row in result] == ['1-2', '1-4', '1-3']
