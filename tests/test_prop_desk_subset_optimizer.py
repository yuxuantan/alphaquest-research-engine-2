"""Bridge-style subset selection and independent sizing/ranking arithmetic."""

from copy import deepcopy

from alphaquest.prop import desk_subset_optimizer
from alphaquest.prop_desk import SubsetOptimizerLaunch


def candidate(micros, metrics, targets=None):
    return dict(micros=micros, metrics=metrics, allocation=dict(micros=targets or [micros], unused=0))


def result(*rows):
    return dict(combinations=[dict(id=index, sizes=sizes) for index, sizes in enumerate(rows, 1)])


def evaluation(passed, days):
    return dict(probabilities=dict(passed=passed), median_trading_days_to_target=days)


def funded(any_payout, first_year, through_cutoff, open_accounts=0):
    return dict(probability_any_payout=any_payout, first_year_mean_receipts=first_year,
                account_life_mean_receipts=None if open_accounts else through_cutoff,
                mean_trader_receipts=through_cutoff, open_at_cutoff=open_accounts)


def test_choose_one_evaluation_size_per_subset_then_rank_near_best_by_speed():
    data = result(
        [candidate(1, evaluation(.69, 5)), candidate(2, evaluation(.70, 12)), candidate(3, evaluation(.70, 10))],
        [candidate(1, evaluation(.69, 8))],
        [candidate(1, evaluation(.68, 3))],
        [candidate(1, evaluation(.99, 2), [1, 0])],
    )
    chosen = desk_subset_optimizer.select(data, 'evaluation', 'optimal', 1000)
    # SE of 0.70 is about 0.01449. 0.69 enters the leading group, 0.68 stays outside.
    assert [(row['combination'], row['micros'], row['rank'], row['near_best'])
            for row in chosen['ranking']] == [(2, 1, 1, True), (1, 2, 2, True), (3, 1, 3, False)]
    assert chosen['unranked'][0]['combination'] == 4
    with_oos = deepcopy(data)
    with_oos['combinations'][0]['oos_days'] = ['2026-01-15']
    assert desk_subset_optimizer.select(with_oos, 'evaluation', 'optimal', 1000)['ranking_sha256'] == chosen['ranking_sha256']


def test_funded_size_rules_select_cash_and_rank_any_payout():
    data = result(
        [candidate(1, funded(.9, 1000, 2200, 5)), candidate(2, funded(.5, 1800, 1800))],
        [candidate(1, funded(.7, 800, 1300))],
    )
    first_year = desk_subset_optimizer.select(data, 'funded', 'first_year', 1000)['ranking']
    assert [(row['combination'], row['micros'], row['score'], row['size_score'], row['size_provisional'])
            for row in first_year] == [(2, 1, .7, 800, False), (1, 2, .5, 1800, False)]
    account_life = desk_subset_optimizer.select(data, 'funded', 'account_life', 1000)['ranking']
    assert [(row['combination'], row['micros'], row['score'], row['size_score'], row['size_provisional'])
            for row in account_life] == [(1, 1, .9, 2200, True), (2, 1, .7, 1300, False)]


def test_subset_request_defaults_to_all_pool_members_as_upper_bound():
    body = SubsetOptimizerLaunch(phase='evaluation', profile_id='apex-50k-eod', minimum_micros=1,
        maximum_micros=6, members=[dict(source_backtest_id=hex(i)[2:].zfill(32), weight=1) for i in range(3)])
    assert body.resolved()['minimum_members'] == 1
    assert body.resolved()['maximum_members'] == 3
    assert body.resolved()['size_rule'] == 'optimal'
    funded_body = body.model_copy(update={'phase': 'funded'})
    assert funded_body.resolved()['observation_sessions'] == 261
    assert funded_body.resolved()['size_rule'] == 'first_year'
