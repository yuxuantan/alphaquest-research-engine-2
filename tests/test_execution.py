from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal, getcontext, localcontext
import tracemalloc

import pytest

from alphaquest.execution import EquityPoint, ExecutionError, Trade, execute
from alphaquest.strategy import Bar, CloseIntent, EntryIntent, ExecutionConfig
from review_execution import ScheduledStrategy, fixtures, review_fixture


D = Decimal
START = datetime(2026, 1, 5, 10, tzinfo=timezone.utc)


def config(**overrides):
    return replace(ExecutionConfig(D("10000"), D("0.25"), D("10"), 1, D("1")), **overrides)


def bar(number, close="100"):
    price = D(close)
    stamp = START + timedelta(minutes=number - 1)
    cells = (stamp.strftime("%m/%d/%Y"), stamp.strftime("%H:%M"), close, close, close, close, "0", "0", "0")
    return Bar(number, stamp, cells[0], cells[1], price, price, price, price, D(0), D(0), D(0), cells)


def result(prices, strategy, settings=None):
    events = list(execute((bar(i, p) for i, p in enumerate(prices, 1)), strategy, settings or config()))
    return [event for event in events if isinstance(event, Trade)], [event for event in events if isinstance(event, EquityPoint)]


@pytest.mark.parametrize("case", fixtures(), ids=lambda case: case["id"])
def test_all_reviewed_trade_fields_and_every_equity_point(case, tmp_path):
    review_fixture(case, tmp_path)


@pytest.mark.parametrize("quantity, gross, commissions, net", [(1, "15", "2", "13"), (2, "30", "4", "26"), (7, "105", "14", "91")])
def test_exact_slippage_commission_and_quantity_scaling(quantity, gross, commissions, net):
    strategy = ScheduledStrategy({1: EntryIntent(quantity, "entry")}, {2: CloseIntent("close")})
    trades, equity = result(["100", "102"], strategy)
    trade = trades[0]
    assert trade.entry_fill_price == D("100.25")
    assert trade.exit_fill_price == D("101.75")
    assert (trade.gross_pnl, trade.total_commissions, trade.net_pnl) == (D(gross), D(commissions), D(net))
    assert trade.slippage_cost == D(quantity) * D("5")
    assert equity[-1].equity == D("10000") + D(net)


def test_zero_cost_arithmetic_and_entry_notional_is_not_debited():
    settings = config(slippage_ticks=0, commission_per_contract_per_side=D(0))
    trades, points = result(["100", "100.50", "102"], ScheduledStrategy({1: EntryIntent(2, "entry")}, {3: CloseIntent("close")}), settings)
    assert trades[0].gross_pnl == trades[0].net_pnl == D("40")
    assert trades[0].total_commissions == trades[0].slippage_cost == 0
    assert [p.cash_balance for p in points] == [D("10000"), D("10000"), D("10000"), D("10040")]
    assert [p.equity for p in points] == [D("10000"), D("10000"), D("10010"), D("10040")]


def test_unrealized_entry_commission_and_realized_expense_accounting():
    trades, points = result(["100", "100.50", "102"], ScheduledStrategy({1: EntryIntent(2, "entry")}, {3: CloseIntent("close")}))
    assert points[0] == EquityPoint(0, None, D("10000"), D(0), D(0), D("10000"), 0)
    assert (points[1].cash_balance, points[1].realized_net_pnl, points[1].unrealized_pnl, points[1].equity) == (D("9998"), D("-2"), D("-5"), D("9993"))
    assert (points[2].cash_balance, points[2].realized_net_pnl, points[2].unrealized_pnl, points[2].equity) == (D("9998"), D("-2"), D("5"), D("10003"))
    assert points[3].realized_net_pnl == trades[0].net_pnl == D("26")
    assert points[3].position_contracts == points[3].unrealized_pnl == 0
    for point in points:
        assert point.equity == point.cash_balance + point.unrealized_pnl


def test_strategy_receives_current_bar_and_actual_immutable_position_without_prefetch():
    seen, supplied, finished = [], [], []

    def source():
        for number in range(1, 4):
            # Every callback for earlier bars must finish before pulling this one.
            assert len(seen) == number - 1
            supplied.append(number)
            yield bar(number, str(99 + number))

    class CausalStrategy:
        def on_bar(self, current, position):
            assert supplied == list(range(1, current.bar_number + 1))
            assert not hasattr(current, "bars") and not hasattr(current, "dataset")
            with pytest.raises(FrozenInstanceError):
                current.close = D("999")
            seen.append(current.bar_number)
            if current.bar_number == 1:
                assert position is None
                return EntryIntent(2, "entry")
            assert position.contracts == 2
            assert position.entry_time_utc == START
            assert position.entry_bar_number == 1
            assert position.entry_fill_price == D("100.25")
            with pytest.raises(FrozenInstanceError):
                position.contracts = 100
            return CloseIntent("close") if current.bar_number == 3 else None

        def on_finish(self, last_bar, position):
            assert seen == supplied == [1, 2, 3]
            assert position is None
            finished.append(last_bar.bar_number)

    events = list(execute(source(), CausalStrategy(), config()))
    assert seen == [1, 2, 3] and finished == [3]
    assert [e.bar_number for e in events if isinstance(e, EquityPoint)] == [0, 1, 2, 3]


def test_deadline_metadata_does_not_make_the_engine_exit():
    # A deliberately overdue deadline does not cause execution without an intent.
    entry = EntryIntent(2, "test", START + timedelta(minutes=1))
    trades, points = result(["100", "101", "102", "103"], ScheduledStrategy({1: entry}, {4: CloseIntent("chosen exit")}))
    assert trades[0].exit_bar_number == 4
    assert trades[0].exit_deadline_utc == START + timedelta(minutes=1)
    assert [p.position_contracts for p in points] == [0, 2, 2, 2, 0]


def test_final_bar_entry_then_finish_closes_same_time_with_both_costs():
    calls = []

    class FinalEntry:
        def on_bar(self, current, position):
            calls.append(("bar", position))
            return EntryIntent(2, "entry")

        def on_finish(self, current, position):
            calls.append(("finish", position))
            assert position.entry_time_utc == current.timestamp_utc
            assert position.entry_fill_price == D("100.25")
            return CloseIntent("end_of_data")

    trades, points = result(["100"], FinalEntry())
    assert [call[0] for call in calls] == ["bar", "finish"]
    assert calls[0][1] is None
    assert trades[0].entry_time_utc == trades[0].exit_time_utc == START
    assert trades[0].actual_holding_minutes == 0
    assert trades[0].entry_fill_price == D("100.25") and trades[0].exit_fill_price == D("99.75")
    assert trades[0].net_pnl == D("-14")
    assert len(points) == 2 and points[-1].equity == D("9986")
    assert points[-1].position_contracts == 0


def test_ordinary_final_exit_keeps_its_reason_and_finish_sees_flat():
    class FinishCheck(ScheduledStrategy):
        def on_finish(self, last_bar, position):
            assert position is None
            assert last_bar.bar_number == 2

    trades, points = result(["100", "102"], FinishCheck({1: EntryIntent(1, "entry")}, {2: CloseIntent("hold_elapsed")}))
    assert len(trades) == 1 and trades[0].exit_reason == "hold_elapsed"
    assert len(points) == 3


@pytest.mark.parametrize("strategy, message", [
    (ScheduledStrategy({1: EntryIntent(1, "first"), 2: EntryIntent(1, "pyramid")}), "pyramiding"),
    (ScheduledStrategy(closes={1: CloseIntent("flat")}), "while flat"),
    (ScheduledStrategy({1: EntryIntent(1, "unclosed")}), "open position"),
    (ScheduledStrategy(finish=EntryIntent(1, "unsupported")), "on_finish"),
    (ScheduledStrategy(finish=CloseIntent("flat")), "while flat"),
    (ScheduledStrategy({1: [EntryIntent(1, "multiple"), CloseIntent("multiple")]}), "Unsupported intent list"),
    (ScheduledStrategy({1: {"side": "short", "contracts": 1}}), "Unsupported intent dict"),
    (ScheduledStrategy({1: EntryIntent(1, "invalid deadline", START - timedelta(minutes=1))}), "precede"),
])
def test_inconsistent_or_unsupported_intents_are_explicit_errors(strategy, message):
    with pytest.raises(ExecutionError, match=message):
        result(["100", "102"], strategy)


@pytest.mark.parametrize("second, message", [
    (replace(bar(2), timestamp_utc=START), "chronological"),
    (replace(bar(2), timestamp_utc=START - timedelta(minutes=1)), "chronological"),
    (replace(bar(2), timestamp_utc=START.replace(tzinfo=None)), "UTC"),
    (replace(bar(2), bar_number=3), "bar_number 2"),
    (replace(bar(2), close=100.0), "finite Decimal"),
    (replace(bar(2), volume=D("NaN")), "finite Decimal"),
    (replace(bar(2), close=D("101")), "OHLC"),
    (replace(bar(2), up_vol=D("-1")), "non-negative"),
])
def test_bad_bars_are_rejected_before_the_strategy_observes_them(second, message):
    seen = []

    class Observer(ScheduledStrategy):
        def on_bar(self, current, position):
            seen.append(current.bar_number)

        def on_finish(self, last_bar, position):
            pytest.fail("A failed run must not invoke on_finish")

    with pytest.raises(ExecutionError, match=message):
        list(execute([bar(1), second], Observer(), config()))
    assert seen == [1]


def test_empty_input_invalid_strategy_config_and_nonbar_input():
    for bars, strategy, settings, message in [
        ([], ScheduledStrategy(), config(), "empty dataset"),
        ([bar(1)], object(), config(), "callbacks"),
        ([bar(1)], ScheduledStrategy(), {}, "ExecutionConfig"),
        ([{}], ScheduledStrategy(), config(), "normalized Bar"),
    ]:
        with pytest.raises(ExecutionError, match=message):
            list(execute(bars, strategy, settings))


def test_iterator_failure_is_not_end_of_data_and_does_not_liquidate():
    class BrokenSource(Exception):
        pass

    def source():
        yield bar(1)
        raise BrokenSource("source truncated")

    class NoFinish(ScheduledStrategy):
        def on_finish(self, last_bar, position):
            pytest.fail("A source error is not normal EOF")

    with pytest.raises(BrokenSource):
        list(execute(source(), NoFinish({1: EntryIntent(1, "entry")}), config()))


def test_strategy_exception_is_not_swallowed_or_treated_as_completion():
    class Broken(ScheduledStrategy):
        def on_bar(self, current, position):
            raise RuntimeError("strategy bug")

        def on_finish(self, last_bar, position):
            pytest.fail("Cannot finish a failed strategy")

    with pytest.raises(RuntimeError, match="strategy bug"):
        result(["100"], Broken())


def test_more_than_28_digit_prices_and_context_mutation_do_not_round_pnl():
    class ChangesPrecision(ScheduledStrategy):
        def on_bar(self, current, position):
            getcontext().prec = 2
            return super().on_bar(current, position)

    prices = ["100000000000000000000000000000.123456789123456789", "100000000000000000000000000002.123456789123456789"]
    with localcontext() as context:
        context.prec = 3
        trades, points = result(prices, ChangesPrecision({1: EntryIntent(2, "entry")}, {2: CloseIntent("exit")}))
        assert trades[0].entry_fill_price == D("100000000000000000000000000000.373456789123456789")
        assert trades[0].exit_fill_price == D("100000000000000000000000000001.873456789123456789")
        assert trades[0].gross_pnl == D("30") and trades[0].net_pnl == D("26")
        assert points[1].equity == D("9993") and points[-1].equity == D("10026")
        # A suspended generator must not install an engine-owned Decimal context.
        assert getcontext().prec == 2


@pytest.mark.parametrize("prices, expected", [(["-10", "-8"], "26"), (["0", "-2"], "-54")])
def test_zero_and_negative_reference_prices_are_supported(prices, expected):
    trades, points = result(prices, ScheduledStrategy({1: EntryIntent(2, "entry")}, {2: CloseIntent("exit")}))
    assert trades[0].net_pnl == D(expected)
    assert points[-1].equity == D("10000") + D(expected)


def test_trade_and_equity_records_are_immutable():
    trades, points = result(["100", "102"], ScheduledStrategy({1: EntryIntent(1, "entry")}, {2: CloseIntent("exit")}))
    with pytest.raises(FrozenInstanceError):
        trades[0].net_pnl = D(0)
    with pytest.raises(FrozenInstanceError):
        points[0].equity = D(0)


def test_incremental_events_are_available_without_exhausting_the_source():
    pulled = []

    def source():
        for number in range(1, 1000):
            pulled.append(number)
            yield bar(number)

    events = execute(source(), ScheduledStrategy({1: EntryIntent(1, "entry")}, {2: CloseIntent("exit")}), config())
    assert next(events).bar_number == 0
    assert pulled == []
    assert next(events).bar_number == 1
    assert pulled == [1, 2]  # one pending equity point; no callback prefetch
    assert isinstance(next(events), Trade)
    assert pulled == [1, 2]  # completed trade is emitted immediately
    events.close()
    assert pulled == [1, 2]


def test_large_input_and_many_trades_do_not_accumulate_results():
    class Alternating(ScheduledStrategy):
        def on_bar(self, current, position):
            return CloseIntent("exit") if position else EntryIntent(1, "entry")

    bars = (bar(number) for number in range(1, 20_001))
    equity_count = trade_count = 0
    tracemalloc.start()
    try:
        for event in execute(bars, Alternating(), config()):
            if isinstance(event, Trade):
                trade_count += 1
                assert event.trade_number == trade_count
            else:
                equity_count += 1
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert equity_count == 20_001 and trade_count == 10_000
    assert peak < 2 * 1024 * 1024
