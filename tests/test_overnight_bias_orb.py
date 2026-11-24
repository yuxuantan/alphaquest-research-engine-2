"""Source-rule oracles and the normal campaign mechanics journey."""

from dataclasses import replace
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal as D

import pytest

from alphaquest.backtest_data import DatasetReadError
from alphaquest.execution import Trade, execute
from alphaquest.strategy import Bar, ExecutionConfig, Position
from alphaquest.strategies.overnight_bias_orb import ET, OvernightBiasORB, Parameters, _Candle
from test_research_workflow import client


CFG = ExecutionConfig(D(10000), D(".25"), D(20), 0, D(0))


def candle(op, hi, lo, close):
    return _Candle(*(D(str(x)) for x in (op, hi, lo, close)))


def stamp(day, hhmm):
    return datetime.combine(day, time(*divmod(hhmm, 100)), ET)


def session_bars(day, minutes):
    for i, (hhmm, prices) in enumerate(minutes, 1):
        yield Bar(i, stamp(day, hhmm).astimezone(timezone.utc), "", "",
                  prices.open, prices.high, prices.low, prices.close, D(10), D(5), D(5), ())


def strategy(**kwargs):
    return OvernightBiasORB(replace(Parameters(adx_len=1, bar_avg_len=1, max_bars_back=1,
                                                atr_days=1, adx_min=D(0)), **kwargs), execution_config=CFG)


def test_midnight_rth_gap_and_regime_gate_use_the_previous_reference():
    s = strategy(atr_days=2, or_median_days=3)
    day = date(2026, 3, 2)
    for offset, low, high in ((0, 100, 104), (1, 112, 116), (2, 110, 124)):
        current = day + timedelta(days=offset)
        s._step(stamp(current - timedelta(days=1), 2345), candle(200, 210, 190, 200), None)
        s._step(stamp(current, 0), candle(100, 101, 99, 100), None)
        s._step(stamp(current, 930), candle(100, 110, 90, 100), None)
        assert (s.on_low, s.on_high) == (90, 110)
        s._step(stamp(current, 945), candle(high, high, low, high - 1), None)
        s._step(stamp(current, 1000), candle(high, high + 1, high - 1, high), None)
        assert s.bias == 1 and s.or_count == offset + 1
        assert s.regime_ok == (offset < 2)
    # Day 1: TR 5, close 104. Day 2: TR 13 from previous close, then (5+13)/2.
    assert s.atr_ref == 9
    # The third width (14) fails against twice the previous EMA (4), then updates it to 9.
    assert s.or_reference == 9


@pytest.mark.parametrize("long", [True, False])
def test_fill_bar_bracket_survives_entry_gap_and_uses_signal_close(long):
    s = strategy(max_trades_per_day=1, break_skip_mult=D(20))
    first = date(2026, 3, 2)
    template = [(15, candle(100, 110, 90, 100)), (16, candle(100, 100, 100, 100)),
                (930, candle(100, 110, 90, 100)), (945, candle(108, 110, 90, 100)),
                (1600, candle(100, 110, 90, 100))]
    if long:
        entry = [(945, candle(108, 110, 107, 108)), (1000, candle(108, 112, 107, 111)),
                 (1001, candle(120, 130, 118, 121))]
        expected = ("long", D(120), D(129), "take_profit")
    else:
        entry = [(945, candle(92, 93, 90, 92)), (1000, candle(92, 93, 88, 89)),
                 (1001, candle(80, 82, 70, 79))]
        expected = ("short", D(80), D(71), "take_profit")
    source = [*session_bars(first, template),
              *session_bars(first + timedelta(days=1), template[:3] + entry)]
    trades = [e for e in execute([replace(b, bar_number=i) for i, b in enumerate(source, 1)], s, CFG)
              if type(e) is Trade]
    assert len(trades) == 1
    t = trades[0]
    assert (t.side, t.entry_fill_price, t.exit_fill_price, t.exit_reason) == expected
    assert t.entry_time_utc == t.exit_time_utc == stamp(first + timedelta(days=1), 1001)
    assert s.submissions == 1


def product_fixture():
    """Close-stamped synthetic minute bars with a hand-computable signal day."""
    start = date(2026, 2, 23)
    days = [start + timedelta(days=i) for i in range(36) if (start + timedelta(days=i)).weekday() < 5]
    signal, oos = days[-2:]
    lines = ['Date,Time,Open,High,Low,Close,Volume,UpVol,DownVol']
    for day in days:
        for minute in range(0, 17 * 60 + 1):
            hhmm = divmod(minute, 60)
            if minute <= 570:
                mid = D(110) + D("0.25") * ((minute - 1) // 15)
                op, hi, lo, close = mid, mid + D(".75"), mid - D(".75"), mid
            elif minute == 945:
                op, hi, lo, close = D(120), D(130), D(110), D(120)
            else:
                op, hi, lo, close = D(120), D(121), D(119), D(120)
            if day == signal and minute == 600:
                op, hi, lo, close = D(120), D(122), D(119), D(122)
            elif day == signal and minute == 601:
                op, hi, lo, close = D(124), D(141), D(122), D(124)
            lines.append(f'{day:%m/%d/%Y},{hhmm[0]:02}:{hhmm[1]:02},{op},{hi},{lo},{close},10,5,5')
    return ('\n'.join(lines) + '\n').encode(), start, signal, oos


def test_default_strategy_in_normal_campaign_mechanics(client):
    raw, start, signal, oos = product_fixture()
    dataset = client.post('/api/datasets', params=dict(filename='synthetic-overnight-orb.csv',
        name='SYNTHETIC Overnight Bias ORB mechanics', symbol='NQ', source_timezone=ET.key,
        tick_size='.25', point_value='20'), content=raw)
    assert dataset.status_code == 201, dataset.text
    body = dict(strategy_id='overnight_bias_orb', dataset_id=dataset.json()['id'],
        sample_split=dict(mode='dates', is_start=str(start), is_end=str(signal), oos_start=str(oos), oos_end=str(oos)),
        execution_settings=dict(initial_capital='10000', slippage_ticks=0, commission_per_contract_per_side='0'))
    new = client.post('/api/campaign-workflows', json=body)
    assert new.status_code == 201, new.text
    url = '/api/campaign-workflows/' + new.json()['id']
    launched = client.post(url + '/run')
    assert launched.status_code == 200, launched.text
    saved = client.get(url).json()
    report = saved['report']
    assert report['summary']['trades_taken'] == 1, saved
    trades = client.get('/api/backtests/' + report['id'] + '/trades').json()['items']
    trade = trades[0]
    assert trade['entry_reason'] == 'ORB_L' and trade['exit_reason'] == 'take_profit'
    assert D(trade['entry_fill_price']) == 124 and D(trade['exit_fill_price']) == 140
    assert D(trade['net_pnl']) == 320


def test_source_and_missing_session_close_reject():
    from alphaquest.strategies.registry import get_strategy
    definition = get_strategy('overnight_bias_orb')
    with pytest.raises(ValueError, match='one-minute'):
        definition.validate_source(Parameters(), dict(symbol='NQ', interval_seconds=900))
    with pytest.raises(ValueError, match='one-minute OHLC dataset'):
        definition.validate_source(Parameters(), dict(symbol='NQ', interval_seconds=60, tick_data=True))
    day = date(2026, 3, 2)
    s = strategy()
    held = Position(1, stamp(day, 1001).astimezone(timezone.utc), D(100), 1)
    late = next(session_bars(day, [(1701, candle(100, 100, 100, 100))]))
    with pytest.raises(DatasetReadError, match='missing scheduled close'):
        s.validate_holding_bar(late, held)


@pytest.mark.parametrize('day,prior,exit_minutes,reason,price', [
    (date(2026, 3, 3), date(2026, 3, 2), (1530, 1531), 'XL', 114),
    (date(2026, 5, 25), date(2026, 5, 22), (1245, 1300), 'session_close', 115),
])
def test_market_flat_next_open_and_scheduled_early_close(day, prior, exit_minutes, reason, price):
    overnight = [(15, candle(100, 110, 90, 100)), (16, candle(100, 100, 100, 100)),
                 (930, candle(100, 110, 90, 100))]
    source = [*session_bars(prior, overnight + [(945, candle(108, 110, 90, 100)),
                                               (1600, candle(100, 110, 90, 100))]),
              *session_bars(day, overnight + [(945, candle(108, 110, 107, 108)),
                                              (1000, candle(108, 112, 107, 111)),
                                              (1001, candle(112, 114, 108, 111)),
                                              (exit_minutes[0], candle(111, 113, 109, 111)),
                                              (exit_minutes[1], candle(114, 116, 114, 115))])]
    rows = [replace(bar, bar_number=i) for i, bar in enumerate(source, 1)]
    trades = [event for event in execute(rows, strategy(), CFG) if type(event) is Trade]
    assert len(trades) == 1
    assert (trades[0].exit_reason, trades[0].exit_fill_price) == (reason, price)
    assert trades[0].exit_time_utc == stamp(day, exit_minutes[1])
