"""Independent long evaluation, reset, sampling and censoring boundaries."""
import numpy as np
import pytest

from alphaquest.prop import lucid_engine as reference, lucid_backend as backend
from alphaquest.prop.native_analysis import calculate, evaluation_diagnostics, resolved_settings


@pytest.mark.parametrize('engine', [reference, backend])
def test_slow_valid_evaluation_continues_and_passes_at_3000_sessions(engine):
    # 10 CU per NQ / 10 = $1 per MNQ each day: target 3000 takes 3000 days.
    days = [[(10., 0.)]]
    initial = engine.evaluation(days, 1, 3, 45, deadline=2000)
    assert initial['outcomes'].tolist() == ['timeout'] * 3
    assert initial['days'].tolist() == [2000] * 3
    continued = engine.evaluation(days, 1, 3, 45, chain=True)
    assert continued['outcomes'].tolist() == ['passed'] * 3
    assert continued['days'].tolist() == [3000] * 3
    assert continued['attempts'].tolist() == [1] * 3
    assert evaluation_diagnostics(continued) == dict(initial_horizon_weekdays=2000,
        horizon_weekdays=20000, continued_paths=3, longest_attempt_weekdays=3000,
        censored_paths=0, simulations=3)
    assert engine.evaluation(days, 1, 1, 45, deadline=2999)['outcomes'][0] == 'timeout'
    assert engine.evaluation(days, 1, 1, 45, deadline=3000)['outcomes'][0] == 'passed'


@pytest.mark.parametrize('engine', [reference, backend])
def test_unresolved_chain_is_never_dropped_or_restarted_as_a_failed_evaluation(engine):
    with pytest.raises(ValueError, match='censored at 10 sessions'):
        engine.evaluation([[(10., 0.)]], 1, 3, 45, deadline=10, chain=True)


def independent_chains(count, seed, block):
    # 5001 cyclic sessions: one observed fatal adverse excursion, otherwise $1.
    # No production transition or sampling helper is used by this oracle.
    rng = np.random.RandomState(seed)
    values = []
    for _ in range(count):
        duration = longest = remaining = index = 0
        for attempt in range(1, 10001):
            balance = high = 0.
            for day in range(1, 20001):
                if not remaining:
                    index = int(rng.randint(5001))
                    remaining = block
                fatal = index == 0
                index = (index + 1) % 5001
                remaining -= 1
                if fatal:break
                balance += 1.
                high = max(high, balance)
                if balance >= 3000:break  # Largest-day consistency is 1/3000.
            duration += day
            longest = max(longest, day)
            if not fatal:break
        values.append((duration, attempt, longest))
    return values


@pytest.mark.parametrize('block', [1, 5001])
def test_continuation_matches_independent_chain_ledger_and_random_draws(block):
    # A long block gives both >2000-day failed attempts and >2000-day passes.
    # Block 1 has frequent failures, so use a shorter winning target equivalent
    # through 3000-dollar daily wins for the short-block stream check below.
    if block == 1:
        days = [[(30000., 0.)], [(30000., 30000.)]]
        left = reference.evaluation(days, 1, 12, 45, block, chain=True)
        right = backend.evaluation(days, 1, 12, 45, block, chain=True)
        assert all(np.array_equal(left[key], right[key]) for key in left)
        return
    days = [[(10., 30000.)]] + [[(10., 0.)] for _ in range(5000)]
    expected = independent_chains(12, 45, block)
    assert any(attempt > 1 for _, attempt, _ in expected)
    for engine in (reference, backend):
        actual = engine.evaluation(days, 1, 12, 45, block, chain=True, daily_loss=None)
        assert actual['outcomes'].tolist() == ['passed'] * 12
        assert list(zip(actual['days'], actual['attempts'], actual['longest_attempt_days'])) == expected


def test_training_and_holdout_calibration_use_all_standard_count_long_paths():
    import pandas as pd
    rows = [dict(trade_id=i+1, entry_utc=str(day.date())+'T18:00:00Z',
                 exit_utc=str(day.date())+'T18:01:00Z', source_net_pnl='10',
                 export_net_pnl=None, quantity='1', measured_mae='0')
            for i, day in enumerate(pd.bdate_range('2026-01-05', periods=8))]
    settings = resolved_settings(dict(PROP_FIRM='Lucid', MAX_TOTAL_NQ='0.1', SLOTS='4'))
    result = calculate(rows, settings)
    training = result['training_economics']
    assert training['status'] == 'calibrated'
    assert training['funding_chain_simulations'] == 20000
    assert training['replacement_days'] == training['replacement_days_median'] == 3000
    assert training['funding_chain_diagnostics']['continued_paths'] == 20000
    assert training['cost_per_funded'] == 80.5
    assert result['evaluation']['days_to_funded'] == 3000
    assert result['evaluation']['continued_paths'] == 20000
    assert result['funded']['selected']['micros'] == 1
    assert result['funded']['selected']['E[payout]'] == 0
    assert result['history']['totals']['payouts'] == 0
    assert result['history']['totals']['net'] == -322
