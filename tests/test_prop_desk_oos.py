"""Arithmetic oracles for the frozen OOS presentation window."""

import pytest

from alphaquest.prop import desk_oos


@pytest.mark.parametrize('expiry, cutoff', [(21, 'provider_expired'), (None, 'observation_cutoff')])
def test_evaluation_keeps_expiry_and_cutoff_distinct(expiry, cutoff):
    paths = [dict(outcome='passed', trading_sessions=4), dict(outcome='passed', trading_sessions=7),
             dict(outcome='breached', trading_sessions=2), dict(outcome=cutoff, trading_sessions=21)]
    rules = {'provider_expiry_trading_sessions': expiry}
    result = desk_oos.evaluation_summary(paths, rules)
    assert result == dict(path_count=4, outcome_counts={'passed':2, 'breached':1, cutoff:1},
                          probabilities={'passed':.5, 'breached':.25, cutoff:.25},
                          median_trading_days_to_target=5.5)
    assert desk_oos.evaluation_summary(paths[-1:], rules)['median_trading_days_to_target'] is None


def test_funded_windows_keep_zero_and_open_accounts():
    def account(outcome, day, payouts):
        return dict(outcome=outcome, observed_weekdays=day,
                    trader_payouts=[[payout,1800] for payout in payouts],
                    gross_account_deductions=[[payout,2000] for payout in payouts])
    paths = [account('paid_all', 250, [25,50,75,100,250]), account('blown',270,[]),
             account('open',300,[261]), account('open',300,[262])]
    rules = {'ladder':[2000]*5}
    first_year = desk_oos.funded_summary(paths, rules, 261, 'first_year')
    assert first_year == dict(path_count=4, any_payout_count=2, breach_before_first_payout_count=0,
                              open_at_window_end=3, open_without_payout=2,
                              mean_trader_receipts=2700, mean_account_deductions=3000,
                              resolved_lifetime_mean_receipts=None)
    lifetime = desk_oos.funded_summary(paths, rules, 300, 'account_life')
    assert lifetime == dict(path_count=4, any_payout_count=3, breach_before_first_payout_count=1,
                            open_at_window_end=2, open_without_payout=0,
                            mean_trader_receipts=3150, mean_account_deductions=3500,
                            resolved_lifetime_mean_receipts=None)
    completed = desk_oos.funded_summary(paths[:2], rules, 300, 'account_life')
    assert completed['resolved_lifetime_mean_receipts'] == 4500
