"""Independent account expectations over actual saved/reconciled source events."""

from dataclasses import replace
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, localcontext

import pytest

from alphaquest.prop import get_profile, resolve_simulation
from alphaquest.prop.engine import ReplaySession, SimulationError, replay_evaluation
from alphaquest.prop.sessions import prepare_backtest
from alphaquest.prop.types import DatedFee, UserFees
from alphaquest.strategy import CloseIntent, EntryIntent
from review_execution import ScheduledStrategy
from test_prop_sessions import DECLARATION, SETTINGS, bars_at, calendar_for, resolved, save_run


D = Decimal


def source_days(tmp_path, prices, entries, closes, first=date(2026, 1, 5), strategy=None):
    stamps = [datetime.combine(first + timedelta(days=day), datetime.min.time(), timezone.utc) + timedelta(hours=14, minutes=i)
              for day, day_prices in enumerate(prices) for i in range(len(day_prices))]
    bars = bars_at(stamps, [p for day in prices for p in day])
    strategy = strategy or ScheduledStrategy({i: EntryIntent(2, "fixture") for i in entries}, {i: CloseIntent("exit") for i in closes})
    store, record, bars = save_run(tmp_path, bars, strategy)
    return store, record, calendar_for(bars)


def replay(store, record, calendar, *, profile=None, quantity=2, config_changes=None):
    profile = profile or get_profile()
    base = resolved(record, calendar, quantity=quantity)
    config = replace(base.config, **(config_changes or {}))
    request = resolve_simulation(config, profile)
    events = []
    with prepare_backtest(store, request, calendar, DECLARATION) as source:
        sessions = (ReplaySession(s, source.trades(s.trading_date), source.observations(s.trading_date)) for s in source.sessions())
        result = replay_evaluation(request, calendar, SETTINGS, sessions, events.append)
    assert sum((e["realized_delta"] for e in events), D(0)) == result["realized_net_trading_pnl"]
    assert [e["timestamp_utc"] for e in events] == sorted(e["timestamp_utc"] for e in events)
    return result, events


@pytest.mark.parametrize("mode", ["trade_close", "bar_close"])
@pytest.mark.parametrize("quantity,balance", [(2, "50026"), (1, "50013")])
def test_source_costs_once_and_unresolved_end(tmp_path, mode, quantity, balance):
    args = source_days(tmp_path, [["100", "100.5", "102"]], [1], [3])
    result, events = replay(*args, quantity=quantity, config_changes={"observation_mode": mode})
    assert result["balance"] == result["equity"] == D(balance)
    assert result["outcome"] == "unresolved_data_end"
    assert (result["processed_trades"], result["completed_source_trades"], result["forced_exits"]) == (1, 1, 0)
    assert len([e for e in events if e["kind"] == "observation"]) == (1 if mode == "trade_close" else 3)


def test_dll_overshoot_skips_winner_and_next_session_resumes(tmp_path):
    args = source_days(tmp_path, [["100", "40.7", "100", "140.7"], ["100", "101.2"]], [1, 3, 5], [2, 4, 6])
    result, events = replay(*args, config_changes={"observation_mode": "trade_close"})
    assert result["balance"] == 48810  # -1200, skipped +800, next session +10
    assert (result["suspensions"], result["processed_trades"], result["skipped_trades"]) == (1, 2, 1)
    assert result["completed_source_trades"] == 2
    suspended, = [e for e in events if e["kind"] == "session_suspended"]
    assert suspended["equity"] == 48800


def test_simultaneous_floor_crossing_keeps_overshoot_and_fails(tmp_path):
    args = source_days(tmp_path, [["100", "-4.3", "100", "140.7"]], [1, 3], [2, 4])
    result, events = replay(*args, config_changes={"observation_mode": "trade_close"})
    assert result["outcome"] == "failed_drawdown" and result["balance"] == 47900
    assert result["suspensions"] == 0 and result["processed_trades"] == 1
    assert result["completed_source_trades"] == 1


@pytest.mark.parametrize("amount, outcome", [("2000", "unresolved_data_end"), ("1015", "failed_drawdown")])
def test_forced_close_costs_replace_source_exit_and_can_reach_permanent_floor(tmp_path, amount, outcome):
    args = source_days(tmp_path, [["100", "49.85", "150"]], [1], [3])
    profile = get_profile()
    profile = replace(profile, evaluation=replace(profile.evaluation, drawdown=replace(profile.evaluation.drawdown, amount=D(amount))))
    result, events = replay(*args, profile=profile)
    assert result["balance"] == result["equity"] == 48983  # observed48990 - exit commission2 - slippage5
    assert result["outcome"] == outcome and result["forced_exits"] == 1
    assert result["completed_source_trades"] == 0
    assert result["suspensions"] == (outcome == "unresolved_data_end")
    assert len([e for e in events if e["kind"] == "liquidated"]) == 1


def test_eod_ratchet_never_decreases(tmp_path):
    args = source_days(tmp_path, [["100", "140.7"], ["100", "95.7"]], [1, 3], [2, 4])
    result, events = replay(*args)
    closes = [e for e in events if e["kind"] == "session_closed"]
    assert [e["trailing_floor"] for e in closes] == [48800, 48800]
    assert result["balance"] == 50700 and result["high_water"] == 50800


@pytest.mark.parametrize("platform,floor", [("rithmic", "53000"), ("wealthcharts", "53000"), ("tradovate", "56000")])
def test_platform_lock_and_eod_target_recognition(tmp_path, platform, floor):
    args = source_days(tmp_path, [["100", "500.7", "100", "40.7"]], [1, 3], [2, 4])
    result, events = replay(*args, profile=get_profile("apex_50k_eod_" + platform), config_changes={"observation_mode": "trade_close"})
    assert result["outcome"] == "passed" and result["balance"] == 58000
    assert result["trailing_floor"] == D(floor) and result["skipped_trades"] == 1
    assert result["target_reached_at_utc"] < result["reviewed_at_utc"] < result["recognized_at_utc"]
    assert result["recognized_at_utc"] == args[2].bounds(args[2].days[0])[2]


def test_six_wins_reach_target_at_flat_close(tmp_path):
    args = source_days(tmp_path, [["100", "125.7"]] * 6, list(range(1, 12, 2)), list(range(2, 13, 2)))
    result, _ = replay(*args)
    assert result["outcome"] == "passed" and result["balance"] == 53000
    assert result["processed_trades"] == 6


@pytest.mark.parametrize("last_day_pass", [False, True])
def test_calendar_deadline_zero_days_and_pass_precedence(tmp_path, last_day_pass):
    days = [["100", "100"]] * 29  # purchase Jan5 18ET; sessions Jan6 through Feb3
    days[-1] = ["100", "250.7"] if last_day_pass else days[-1]
    args = source_days(tmp_path, days, [57] if last_day_pass else [], [58] if last_day_pass else [], first=date(2026, 1, 6))
    result, _ = replay(*args)
    assert result["outcome"] == ("passed" if last_day_pass else "expired")
    assert result["expiry_at_utc"] == datetime(2026, 2, 3, 23, tzinfo=timezone.utc)
    assert result["zero_trade_sessions"] == 29 - last_day_pass


def test_no_trade_history_does_not_invent_expiry(tmp_path):
    args = source_days(tmp_path, [["100", "100"]], [], [])
    result, _ = replay(*args)
    assert result["balance"] == 50000 and result["outcome"] == "unresolved_data_end"
    assert result["zero_trade_sessions"] == 1 and result["processed_trades"] == 0


def test_external_fees_do_not_modify_trading_balance_and_stop_at_financial_end(tmp_path):
    args = source_days(tmp_path, [["100", "-4.3"]], [1], [2])
    fee = DatedFee("later platform fee", D("100"), datetime(2026, 1, 5, 20, tzinfo=timezone.utc))
    result, events = replay(*args, config_changes={"observation_mode": "trade_close", "fees": UserFees("USD", attempt_fee=D("25"), scheduled=(fee,))})
    assert result["balance"] == 47900 and result["modeled_net_cash"] == -25
    assert result["external_costs"] == 25


def test_explicit_scheduled_fees_and_decimal_context(tmp_path):
    args = source_days(tmp_path, [["100", "102"]], [1], [2])
    fee = DatedFee("platform", D("12.34"), datetime(2026, 1, 5, 20, tzinfo=timezone.utc))
    with localcontext() as ctx:
        ctx.prec = 2
        result, _ = replay(*args, config_changes={"fees": UserFees("USD", attempt_fee=D("1.23"), scheduled=(fee,))})
    assert result["balance"] == 50026 and result["external_costs"] == D("13.57")


@pytest.mark.parametrize("change", ["partial_start", "partial_end", "future_end", "oversize"])
def test_invalid_operations_are_rejected(tmp_path, change):
    args = source_days(tmp_path, [["100", "102"]], [1], [2])
    config = resolved(args[1], args[2]).config
    changes = {"partial_start": dict(account_start_utc=config.account_start_utc + timedelta(hours=1)),
               "partial_end": dict(end_utc=config.end_utc - timedelta(minutes=1)),
               "future_end": dict(end_utc=config.end_utc + timedelta(days=1)), "oversize": {}}
    with pytest.raises(SimulationError):
        replay(*args, quantity=7 if change == "oversize" else 2, config_changes=changes[change])


@pytest.mark.parametrize("exit_price,balance,outcome,suspensions", [("50.7", "49000", "unresolved_data_end", 1), ("0.7", "48000", "failed_drawdown", 0)])
def test_exact_threshold_touch(tmp_path, exit_price, balance, outcome, suspensions):
    args = source_days(tmp_path, [["100", exit_price]], [1], [2])
    result, _ = replay(*args, config_changes={"observation_mode": "trade_close"})
    assert result["balance"] == D(balance) and result["outcome"] == outcome
    assert result["suspensions"] == suspensions and result["forced_exits"] == 0


def test_open_target_mark_is_not_a_pass(tmp_path):
    args = source_days(tmp_path, [["100", "251", "100"]], [1], [3])
    result, events = replay(*args)
    assert max(e["equity"] for e in events) > 53000
    assert result["outcome"] == "unresolved_data_end" and result["target_reached_at_utc"] is None
    assert result["balance"] == 49986


@pytest.mark.parametrize("passes", [False, True])
def test_cost_exactly_at_expiry_counts_for_pass_or_expiration(tmp_path, passes):
    days = [["100", "100"]] * 29
    if passes:
        days[-1] = ["100", "250.7"]
    args = source_days(tmp_path, days, [57] if passes else [], [58] if passes else [], first=date(2026, 1, 6))
    fee = DatedFee("due at closure", D("10"), datetime(2026, 2, 3, 23, tzinfo=timezone.utc))
    result, _ = replay(*args, config_changes={"fees": UserFees("USD", attempt_fee=D("0"), scheduled=(fee,))})
    assert result["outcome"] == ("passed" if passes else "expired")
    assert result["external_costs"] == 10 and result["modeled_net_cash"] == -10


def test_exact_contract_limit_is_supported(tmp_path):
    args = source_days(tmp_path, [["100", "102"]], [1], [2])
    result, _ = replay(*args, quantity=6)
    assert result["balance"] == 50078 and result["processed_trades"] == 1


def test_early_market_close_preserves_profile_review_and_recognition_times(tmp_path):
    store, record, calendar = source_days(tmp_path, [["100", "250.7"]], [1], [2])
    calendar = replace(calendar, days=(replace(calendar.days[0], close_time=time(13)),))
    result, events = replay(store, record, calendar)
    assert result["outcome"] == "passed"
    assert result["reviewed_at_utc"] == datetime(2026, 1, 5, 21, 59, 59, tzinfo=timezone.utc)
    assert result["recognized_at_utc"] == datetime(2026, 1, 5, 23, tzinfo=timezone.utc)


def test_expiry_uses_local_dates_across_dst_without_extending_short_history(tmp_path):
    args = source_days(tmp_path, [["100", "100"]], [], [], first=date(2026, 3, 2))
    result, _ = replay(*args)
    assert args[2].bounds(args[2].days[0])[0] == datetime(2026, 3, 1, 23, tzinfo=timezone.utc)
    assert result["expiry_at_utc"] == datetime(2026, 3, 30, 22, tzinfo=timezone.utc)
    assert result["outcome"] == "unresolved_data_end"
