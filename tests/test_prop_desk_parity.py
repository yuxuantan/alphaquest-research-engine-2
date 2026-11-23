"""Independent sizing, tie and funded horizon boundaries."""

from alphaquest.prop.desk_parity import funded_order, metrics, select_size
from alphaquest.prop.desk_diagnostics import held_out_status


def test_conservative_selects_from_in_sample_breach_at_most_twenty_percent():
    def size(mnq, passed, breached, allocation):
        return dict(micros=mnq, allocation=dict(micros=allocation),
                    metrics=dict(probabilities=dict(passed=passed, breached=breached)))
    sizes = [size(2, .85, .1, [2, 0]), size(3, .7, .2, [2, 1]),
             size(4, .75, .201, [2, 2]), size(5, .7, .15, [3, 2])]
    assert select_size(sizes, 'optimal') == (sizes[2], None)
    assert select_size(sizes, 'conservative') == (sizes[1], None)
    assert select_size([sizes[2]], 'conservative') == (
        None, 'No tested size has an in-sample breach rate of 20% or less.')


def test_funded_order_and_first_year_account_cutoff():
    ranked = [
        dict(combination=1, micros=4, score=.6, median_days=18, path_count=1000),
        dict(combination=2, micros=3, score=.59, median_days=12, path_count=1000),
        dict(combination=3, micros=2, score=.58, median_days=4, path_count=1000),
    ]
    ordered = funded_order(ranked)
    assert [row['combination'] for row in ordered] == [2, 1, 3]
    assert [row['near_best'] for row in ordered] == [True, True, False]
    paths = [
        dict(outcome='blown', observed_weekdays=260, lifetime_censored=False,
             trader_payouts=[], gross_account_deductions=[]),
        dict(outcome='graduated', observed_weekdays=262, lifetime_censored=False,
             trader_payouts=[[261, 900], [262, 900]], gross_account_deductions=[[261, 1000], [262, 1000]]),
        dict(outcome='open', observed_weekdays=300, lifetime_censored=True,
             trader_payouts=[[262, 900]], gross_account_deductions=[[262, 1000]]),
    ]
    first = metrics('funded', paths, dict(ladder=[1000, 1000]), 300, 'first_year', None)
    life = metrics('funded', paths, dict(ladder=[1000, 1000]), 300, 'account_life', None)
    assert first['probability_any_payout'] == 1/3 and life['probability_any_payout'] == 2/3
    assert first['open_at_cutoff'] == 2 and life['open_at_cutoff'] == 1
    assert first['mean_trader_receipts'] == 300 and first['median_trader_receipts'] == 0
    assert life['mean_trader_receipts'] == life['median_trader_receipts'] == 900


def test_held_out_warning_critical_recovery_and_new_high():
    # Peak 100, then depths 25, 65, 80, 40, 0 and finally a new high at 101.
    rows = [dict(net_pnl=pnl, role='oos', exit_utc=f'2026-01-{index:02d}T00:00:00Z')
            for index, pnl in enumerate([100, -25, -40, -15, 40, 40, 1], 1)]
    result = held_out_status(rows, 20, 60)
    assert [(item['trade'], item['status']) for item in result['transitions']] == [
        (2, 'Warning'), (3, 'Critical'), (5, 'Warning'), (7, 'OK')]
    assert result['status'] == 'OK' and result['drawdown'] == 0
