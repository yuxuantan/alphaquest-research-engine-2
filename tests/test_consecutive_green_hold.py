from dataclasses import FrozenInstanceError, asdict, fields
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from alphaquest.execution import EquityPoint, Trade, execute
from alphaquest.strategy import Bar, CloseIntent, EntryIntent, ExecutionConfig, Position
from alphaquest.strategies.consecutive_green_hold import DESCRIPTION, STRATEGY_ID, ConsecutiveGreenHold, Parameters
from review_execution import fixtures
from review_strategy import entry_exit_table, review_fixture


D = Decimal
START = datetime(2026, 1, 5, 10, tzinfo=timezone.utc)
CONFIG = ExecutionConfig(D("10000"), D("0.25"), D("10"), 0, D("0"))


def bar(number, minute=None, color="green"):
    stamp = START + timedelta(minutes=number - 1 if minute is None else minute)
    opening, close = {
        "green": (D("100"), D("101")),
        "red": (D("101"), D("100")),
        "doji": (D("100"), D("100")),
    }[color]
    high, low = max(opening, close), min(opening, close)
    cells = (stamp.strftime("%m/%d/%Y"), stamp.strftime("%H:%M"),
             str(opening), str(high), str(low), str(close), "0", "0", "0")
    return Bar(number, stamp, cells[0], cells[1], opening, high, low, close, D(0), D(0), D(0), cells)


def replay(bars, parameters=None, config=CONFIG):
    events = list(execute(bars, ConsecutiveGreenHold(parameters), config))
    return [e for e in events if isinstance(e, Trade)], [e for e in events if isinstance(e, EquityPoint)]


def test_identity_and_exactly_three_documented_immutable_parameters_with_defaults():
    assert STRATEGY_ID == "consecutive_green_hold" and DESCRIPTION
    assert asdict(Parameters()) == {"green_bar_count": 3, "hold_minutes": 20, "contracts": 1}
    assert {field.name for field in fields(Parameters)} == {"green_bar_count", "hold_minutes", "contracts"}
    assert all(field.metadata["description"] for field in fields(Parameters))
    with pytest.raises(FrozenInstanceError):
        Parameters().hold_minutes = 2
    with pytest.raises(TypeError):
        Parameters(slippage_ticks=1)
    with pytest.raises(TypeError, match="Parameters"):
        ConsecutiveGreenHold({"green_bar_count": 3})


@pytest.mark.parametrize("name", ["green_bar_count", "hold_minutes", "contracts"])
@pytest.mark.parametrize("value", [True, False, 0, -1, 1.0, 2.5, D("1"), "1", None])
def test_parameters_reject_invalid_values_without_coercion(name, value):
    with pytest.raises(ValueError, match=name):
        Parameters(**{name: value})


def test_enters_on_third_green_close_with_requested_quantity_and_deadline():
    strategy = ConsecutiveGreenHold()
    assert strategy.on_bar(bar(1), None) is None
    assert strategy.on_bar(bar(2), None) is None
    assert strategy.on_bar(bar(3), None) == EntryIntent(1, "consecutive_green", START + timedelta(minutes=22))


@pytest.mark.parametrize("reset", ["red", "doji"])
def test_red_or_doji_discards_partial_streak_while_flat(reset):
    bars = [bar(i, color=reset if i == 3 else "green") for i in range(1, 7)]
    trades, points = replay(bars)
    assert len(trades) == 1 and trades[0].entry_bar_number == 6
    assert [p.position_contracts for p in points[:6]] == [0] * 6


def test_adjacent_observed_greens_across_large_gaps_still_form_one_streak():
    trades, _ = replay([bar(1, 0), bar(2, 1), bar(3, 500), bar(4, 520)])
    assert trades[0].entry_bar_number == 3
    assert trades[0].entry_time_utc == START + timedelta(minutes=500)
    assert trades[0].exit_reason == "hold_elapsed"


def test_long_green_run_never_pyramids_or_reuses_holding_bars_for_next_entry():
    trades, _ = replay([bar(i) for i in range(1, 15)], Parameters(hold_minutes=4))
    assert [(t.entry_bar_number, t.exit_bar_number) for t in trades] == [(3, 7), (10, 14)]
    assert all(t.contracts == 1 and t.exit_reason == "hold_elapsed" for t in trades)


def test_red_and_doji_while_holding_do_not_exit_before_deadline():
    colors = ["green", "green", "green", "red", "doji", "red"]
    trades, _ = replay([bar(i, color=color) for i, color in enumerate(colors, 1)], Parameters(hold_minutes=3))
    assert [(t.entry_bar_number, t.exit_bar_number, t.exit_reason) for t in trades] == [(3, 6, "hold_elapsed")]


@pytest.mark.parametrize("interval, exit_bar, hold", [(1, 23, 20), (5, 7, 20), (7, 6, 21), (30, 4, 30)])
def test_hold_uses_elapsed_utc_minutes_instead_of_counting_bars(interval, exit_bar, hold):
    bars = [bar(i, minute=(i - 1) * interval) for i in range(1, exit_bar + 1)]
    trades, _ = replay(bars)
    trade = trades[0]
    assert trade.entry_bar_number == 3 and trade.exit_bar_number == exit_bar
    assert trade.exit_deadline_utc == trade.entry_time_utc + timedelta(minutes=20)
    assert trade.actual_holding_minutes == D(hold)
    assert trade.exit_reason == "hold_elapsed"


def test_deadline_inside_gap_exits_at_first_observed_close_after_it():
    trades, _ = replay([bar(i, minute) for i, minute in enumerate([0, 1, 2, 7, 17, 42], 1)])
    trade = trades[0]
    assert trade.exit_deadline_utc == START + timedelta(minutes=22)
    assert trade.exit_time_utc == START + timedelta(minutes=42)
    assert trade.actual_holding_minutes == 40 and trade.exit_bar_number == 6


def test_holding_deadline_is_anchored_to_actual_position_entry_time():
    strategy = ConsecutiveGreenHold()
    position = Position(4, START + timedelta(minutes=50), D("101.25"), 1)
    assert strategy.on_bar(bar(2, 69), position) is None
    assert strategy.on_bar(bar(3, 70), position) == CloseIntent("hold_elapsed")


def test_one_green_parameter_cannot_reenter_on_exit_bar():
    trades, points = replay([bar(i) for i in range(1, 5)], Parameters(green_bar_count=1, hold_minutes=1))
    assert [(t.entry_bar_number, t.exit_bar_number) for t in trades] == [(1, 2), (3, 4)]
    assert [point.position_contracts for point in points] == [0, 1, 0, 1, 0]


def test_red_exit_bar_resets_and_next_observed_bar_begins_fresh_streak():
    bars = [bar(i, color="red" if i == 5 else "green") for i in range(1, 11)]
    trades, _ = replay(bars, Parameters(hold_minutes=2))
    assert [(t.entry_bar_number, t.exit_bar_number) for t in trades] == [(3, 5), (8, 10)]


def test_end_of_data_requests_close_before_deadline_and_finish_flat_is_noop():
    trades, points = replay([bar(i) for i in range(1, 5)])
    assert trades[0].exit_bar_number == 4 and trades[0].exit_reason == "end_of_data"
    assert trades[0].actual_holding_minutes == 1
    assert points[-1].position_contracts == 0
    assert ConsecutiveGreenHold().on_finish(bar(1), None) is None


def test_entry_on_last_bar_is_closed_at_same_time_by_finish_with_both_costs():
    config = ExecutionConfig(D("10000"), D("0.25"), D("10"), 1, D("1"))
    trades, points = replay([bar(i) for i in range(1, 4)], Parameters(contracts=2), config)
    assert len(trades) == 1
    trade = trades[0]
    assert trade.entry_time_utc == trade.exit_time_utc
    assert (trade.entry_bar_number, trade.exit_bar_number) == (3, 3)
    assert trade.exit_reason == "end_of_data" and trade.actual_holding_minutes == 0
    assert trade.net_pnl == D("-14") and points[-1].equity == D("9986")
    assert len(points) == 4


def test_final_bar_at_deadline_uses_ordinary_exit_reason_without_extra_finish_trade():
    trades, _ = replay([bar(1, 0), bar(2, 1), bar(3, 2), bar(4, 22)])
    assert len(trades) == 1 and trades[0].exit_reason == "hold_elapsed"


@pytest.mark.parametrize("green_count", [1, 2, 3, 5])
def test_changing_green_count_changes_entry_ordinal(green_count):
    trades, _ = replay([bar(i) for i in range(1, 6)], Parameters(green_bar_count=green_count))
    assert len(trades) == 1 and trades[0].entry_bar_number == green_count


@pytest.mark.parametrize("hold_minutes, exit_bar", [(1, 4), (2, 5), (5, 8)])
def test_changing_hold_minutes_changes_exit_deadline_and_ordinal(hold_minutes, exit_bar):
    # Red bars after entry prevent another entry when a shorter hold exits early.
    bars = [bar(i, color="green" if i <= 3 else "red") for i in range(1, 9)]
    trades, _ = replay(bars, Parameters(hold_minutes=hold_minutes))
    assert len(trades) == 1 and trades[0].exit_bar_number == exit_bar
    assert trades[0].exit_deadline_utc == START + timedelta(minutes=2 + hold_minutes)


@pytest.mark.parametrize("contracts", [1, 2, 7])
def test_changing_contracts_changes_requested_and_filled_quantity(contracts):
    strategy = ConsecutiveGreenHold(Parameters(contracts=contracts))
    for i in range(1, 4):
        intent = strategy.on_bar(bar(i), None)
    assert intent.contracts == contracts
    trades, points = replay([bar(i) for i in range(1, 5)], Parameters(contracts=contracts))
    assert trades[0].contracts == contracts and points[3].position_contracts == contracts


def test_new_strategy_instances_do_not_share_streak_state_and_finish_clears_it():
    first, second = ConsecutiveGreenHold(), ConsecutiveGreenHold()
    assert first.on_bar(bar(1), None) is None
    assert first.on_bar(bar(2), None) is None
    assert second.on_bar(bar(3), None) is None
    assert first.on_bar(bar(3), None) is not None
    second.on_finish(bar(3), None)
    assert second.on_bar(bar(4), None) is None
    assert second.on_bar(bar(5), None) is None
    assert second.on_bar(bar(6), None) is not None


@pytest.mark.parametrize("case", fixtures(), ids=lambda case: case["id"])
def test_actual_strategy_matches_every_reviewed_trade_field_and_equity_point(case, tmp_path):
    review = review_fixture(case, tmp_path)
    table = entry_exit_table([review])
    assert len(review["trades"]) == len(case["expected_trades"])
    for row in review["trades"]:
        assert row["actual"]["entry_reason"] == "consecutive_green"
        assert row["actual"]["exit_reason"] in table
