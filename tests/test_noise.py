"""Noise source-rule oracles and the registered campaign entry point."""

from dataclasses import replace
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal as D

import pytest

from alphaquest.execution import ExecutionError, IntratradeRisk, Trade, execute
from alphaquest.strategies.noise import CT, Noise, Parameters
from alphaquest.strategies.registry import get_strategy
from alphaquest.strategy import Bar, ExecutionConfig

CFG = ExecutionConfig(D(10000), D(".25"), D(20), 0, D(0))
DAY = date(2026, 3, 5)


def stamp(day, hhmm):
    return datetime.combine(day, time(*divmod(hhmm, 100)), CT).astimezone(timezone.utc)


def row(day, hhmm, opening=1000, close=None, *, high=None, low=None):
    opening = D(str(opening))
    close = opening if close is None else D(str(close))
    return Bar(1, stamp(day, hhmm), "", "", opening,
               max(opening, close) if high is None else D(str(high)),
               min(opening, close) if low is None else D(str(low)),
               close, D(1), D(1), D(0), ())


def replay(rows, **settings):
    cfg = settings.pop("config", CFG)
    strategy = Noise(replace(Parameters(lookback_days=1), **settings), execution_config=cfg)
    bars = [replace(bar, bar_number=i) for i, bar in enumerate(rows, 1)]
    return [e for e in execute(bars, strategy, cfg, capture_risk=True)
            if isinstance(e, (Trade, IntratradeRisk))]


def history(*slots, prior_close=1000):
    return [row(DAY - timedelta(days=2), 1445), row(DAY - timedelta(days=2), 1500),
            row(DAY - timedelta(days=1), 845),
            *(row(DAY - timedelta(days=1), t) for t in slots),
            row(DAY - timedelta(days=1), 1445, prior_close)]


@pytest.mark.parametrize("long", [True, False])
@pytest.mark.parametrize("cap", [1, 10])
def test_next_open_reversal_always_exits_and_protects_the_new_side(long, cap):
    sign = 1 if long else -1
    rows = history(900, 915) + [
        row(DAY, 845), row(DAY, 900, close=1000 + sign * 5),
        row(DAY, 901, 1000 + sign * 6), row(DAY, 915, close=1000 - sign * 5),
        row(DAY, 916, 1000 - sign * 6, close=1000 - sign * 31),
    ]
    events = replay(rows, max_trades_per_day=cap)
    trades = events[::2]
    first = trades[0]
    assert (first.entry_reason, first.exit_reason) == (
        ("NoiseLong", "LongRevExit") if long else ("NoiseShort", "ShortRevExit"))
    assert first.exit_time_utc == stamp(DAY, 916)
    assert first.exit_fill_price == 1000 - sign * 6
    assert first.net_pnl == -480
    if cap == 1:
        assert len(trades) == 1
    else:
        assert len(trades) == 2
        second = trades[1]
        assert second.entry_reason == ("RevToShort" if long else "RevToLong")
        assert second.exit_reason == "take_profit"
        assert second.entry_time_utc == second.exit_time_utc == first.exit_time_utc
        assert second.net_pnl == 1000
        assert len(events) == 4 and isinstance(events[3], IntratradeRisk)


def test_slot_history_excludes_current_move_and_requires_strict_direction_and_band():
    old = DAY - timedelta(days=1)
    rows = [row(DAY - timedelta(days=2), 1445), row(DAY - timedelta(days=2), 1500), row(old, 845),
            row(old, 900, close=1010), row(old, 915, close=1010),
            row(old, 930, close=1010), row(old, 945, close=1010), row(old, 1445, 1020)]
    rows += [
        row(DAY, 845), row(DAY, 900, close="1030.20"),  # Exactly the upper band.
        row(DAY, 915, 1033, 1032),   # Clears the band on a bearish candle.
        row(DAY, 930, close=1031),   # Clears the band only using the previous day's 1%.
        row(DAY, 931, 1034, high=1059),
    ]
    trade, _ = replay(rows)
    assert trade.entry_time_utc == stamp(DAY, 931)
    assert (trade.entry_fill_price, trade.exit_fill_price) == (1034, 1059)
    assert trade.net_pnl == 1000


@pytest.mark.parametrize("long", [True, False])
def test_ema_exit_takes_the_next_open_after_entry_cutoff(long):
    sign = 1 if long else -1
    rows = history(1400, 1415) + [
        row(DAY, 845), row(DAY, 1400, close=1000 + sign * 10),
        row(DAY, 1401, 1000 + sign * 9), row(DAY, 1415, close=1000 - sign * 5),
        row(DAY, 1416, 1000 - sign * 7),
    ]
    trade, _ = replay(rows)
    assert trade.exit_reason == ("LongEMAExit" if long else "ShortEMAExit")
    assert trade.exit_time_utc == stamp(DAY, 1416)
    assert trade.net_pnl == -640


def test_missing_exact_flat_close_carries_and_no_eof_exit_is_invented():
    rows = history(900) + [row(DAY, 845), row(DAY, 900, close=1005),
        row(DAY, 901, 1006), row(DAY, 1429, 1006), row(DAY, 1445, 1007)]
    with pytest.raises(ExecutionError, match="ended with an open position"):
        replay(rows)
    tomorrow = DAY + timedelta(days=1)
    trade, _ = replay(rows + [row(tomorrow, 845, 1007),
        row(tomorrow, 1430, 1007), row(tomorrow, 1431, 1008)])
    assert trade.exit_reason == "FlatLong1430"
    assert trade.exit_time_utc == stamp(tomorrow, 1431)
    assert trade.net_pnl == 80


@pytest.mark.parametrize("exit_open,commission", [(956, "0"), ("956.25", "2.50")])
def test_daily_loss_gate_counts_a_market_exit_and_resets_on_date_change(exit_open, commission):
    tomorrow = DAY + timedelta(days=1)
    rows = history(900, 915, 930) + [row(DAY, 845), row(DAY, 900, close=1005),
        row(DAY, 901, 1006), row(DAY, 915, close=1000), row(DAY, 916, exit_open),
        row(DAY, 930, close=1005), row(DAY, 931, 1006, high=1031), row(DAY, 1445, 1000),
        row(tomorrow, 845), row(tomorrow, 900, close=1006), row(tomorrow, 901, 1006, high=1031)]
    first, _, second, _ = replay(rows, max_stops_per_day=1,
                                config=replace(CFG, commission_per_contract_per_side=D(commission)))
    assert (first.exit_reason, first.net_pnl) == ("LongEMAExit", -2000)
    assert second.entry_time_utc == stamp(tomorrow, 901)
    assert second.net_pnl == 1000 - 4 * D(commission)


def test_known_unsupported_source_and_parameter_ranges():
    definition = get_strategy("noise")
    for dataset in ({"interval_seconds": 900}, {"interval_seconds": 60, "tick_data": True}):
        with pytest.raises(ValueError, match="one-minute"):
            definition.validate_source(Parameters(), {"symbol": "NQ", **dataset})
    with pytest.raises(ValueError, match="lookback_days"):
        Parameters(lookback_days=101)
    with pytest.raises(ValueError, match="HHMM"):
        Parameters(flat_signal_time=1460)
    with pytest.raises(ValueError, match="paired reversals"):
        definition.sizing.require(Parameters(), "percentage_risk")


def product_fixture():
    """Synthetic RTH minutes with 20+ flat training observations and one known target."""
    start = date(2026, 2, 23)
    days = [start + timedelta(days=i) for i in range(36) if (start + timedelta(days=i)).weekday() < 5]
    signal, oos = days[-2:]
    lines = ["Date,Time,Open,High,Low,Close,Volume,UpVol,DownVol"]
    for day in days:
        for minute in range(8 * 60 + 31, 15 * 60 + 16):
            prices = (20000, 20000, 20000, 20000)
            if day == signal and minute == 9 * 60:
                prices = (20000, 20010, 20000, 20010)
            elif day == signal and minute == 9 * 60 + 1:
                prices = (20015, 20040, 20015, 20020)
            h, m = divmod(minute, 60)
            lines.append(f"{day:%m/%d/%Y},{h:02}:{m:02}," + ",".join(map(str, prices)) + ",10,5,5")
    return ("\n".join(lines) + "\n").encode(), start, signal, oos
