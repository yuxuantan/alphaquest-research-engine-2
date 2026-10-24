"""Independent order schedules test generic execution without VWAP rules."""

from dataclasses import replace
from decimal import Decimal

import pytest

from alphaquest.execution import EquityPoint, ExecutionError, Trade, execute
from alphaquest.strategy import BracketIntent, CloseIntent, EntryIntent
from test_execution import bar, config


D = Decimal


class Orders:
    def __init__(self, schedule, finish=None):
        self.schedule = schedule
        self.finish = finish
        self.observed = []

    def on_bar(self, bar, position):
        self.observed.append((bar.bar_number, position))
        return self.schedule.get(bar.bar_number)

    def on_finish(self, bar, position):
        return self.finish if self.finish is not None else CloseIntent("end_of_data") if position else None


def prices(number, o, h, l, c):
    return replace(bar(number, str(c)), open=D(o), high=D(h), low=D(l))


@pytest.mark.parametrize("short", [False, True])
@pytest.mark.parametrize("open_price, high, low, reason, long_fill", [
    ("90", "120", "80", "stop_loss", "89.75"),
    ("115", "120", "80", "take_profit", "115"),
    ("100", "110", "95", "stop_loss", "94.75"),
    ("100", "110", "96", "take_profit", "110"),
])
def test_gap_priority_dual_touch_limit_prices_and_short_symmetry(short, open_price, high, low, reason, long_fill):
    last = prices(3, open_price, high, low, open_price)
    if short:
        last = replace(last, open=200-last.open, high=200-last.low, low=200-last.high, close=200-last.close)
    stop, target = (D(105), D(90)) if short else (D(95), D(110))
    orders = Orders({1: EntryIntent(2, "entry", side="short" if short else "long", timing="next_open"),
                     2: BracketIntent(stop, target)})
    events = list(execute([bar(1), bar(2), last], orders, config()))
    trade = next(e for e in events if type(e) is Trade)
    fill = 200-D(long_fill) if short else D(long_fill)
    assert trade.exit_reason == reason
    assert trade.exit_fill_price == fill
    assert trade.entry_fill_price == D("99.75" if short else "100.25")
    assert orders.observed[0][1] is None
    assert orders.observed[1][1].side == trade.side
    assert orders.observed[2][1] is None  # Execution precedes the close callback.
    assert events[-1].equity == config().initial_capital + trade.net_pnl


def test_unrenewed_bracket_expires_and_is_not_filled_retroactively():
    orders = Orders({1: EntryIntent(1, "entry", timing="next_open"), 2: BracketIntent(D(95), D(110))})
    rows = [bar(1), bar(2), bar(3), prices(4, "100", "120", "90", "101")]
    events = list(execute(rows, orders, config()))
    trade = next(e for e in events if type(e) is Trade)
    assert trade.exit_reason == "end_of_data" and trade.exit_reference_price == 101


def test_next_open_fill_uses_open_and_cannot_prefetch():
    orders = Orders({1: EntryIntent(1, "entry", timing="next_open"), 2: CloseIntent("exit", timing="next_open")})

    def bars():
        yield bar(1)
        assert len(orders.observed) == 1 and orders.observed[0][1] is None
        yield prices(2, "104", "120", "100", "119")
        assert orders.observed[1][1].entry_fill_price == D("104.25")
        yield prices(3, "108", "120", "100", "101")

    trade = next(e for e in execute(bars(), orders, config()) if type(e) is Trade)
    assert (trade.entry_reference_price, trade.exit_reference_price) == (104, 108)
    assert (trade.entry_fill_price, trade.exit_fill_price, trade.net_pnl) == (D("104.25"), D("107.75"), D(33))


@pytest.mark.parametrize("schedule, finish, message", [
    ({1: BracketIntent(D(95), D(110))}, None, "BracketIntent while flat"),
    ({1: CloseIntent("exit", timing="next_open")}, None, "next-open close requires"),
    ({1: EntryIntent(1, "entry"), 2: EntryIntent(1, "entry", timing="next_open")}, None, "entry requires flat"),
    ({1: EntryIntent(1, "entry"), 2: BracketIntent(D(110), D(95))}, None, "Bracket stop and target"),
    ({1: EntryIntent(1, "entry")}, CloseIntent("exit", timing="next_open"), "on_finish cannot schedule"),
    ({1: EntryIntent(1, "entry"), 2: BracketIntent(D(95), D(110)), 3: EntryIntent(1, "entry")}, None, "Same-close re-entry"),
])
def test_invalid_pending_order_states_fail_explicitly(schedule, finish, message):
    with pytest.raises(ExecutionError, match=message):
        list(execute([bar(1), bar(2), prices(3, "100", "120", "90", "100")], Orders(schedule, finish), config()))


def test_intents_reject_unsupported_types_and_nonfinite_brackets():
    for constructor in (lambda: EntryIntent(1, "entry", side="both"),
                        lambda: EntryIntent(1, "entry", timing="future"),
                        lambda: CloseIntent("exit", timing="future"),
                        lambda: BracketIntent(D("NaN"), D(110)),
                        lambda: BracketIntent(D(95), 110.0)):
        with pytest.raises(ValueError):
            constructor()
