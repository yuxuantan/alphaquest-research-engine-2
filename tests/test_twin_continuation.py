"""Independent prices/arithmetic, not fixture outcomes embedded in the product."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal as D
from zoneinfo import ZoneInfo

import pytest

from alphaquest.execution import ExecutionError, Trade, execute
from alphaquest.intratrade import IntratradeRisk
from alphaquest.strategy import Bar, BracketIntent, CloseIntent, EntryIntent, StopEntriesIntent, ExecutionConfig
from alphaquest.strategies.twin_continuation import Parameters, TwinContinuation

CT = ZoneInfo('America/Chicago')


def prices(number, stamp, o=100, h=101, l=99, c=100):
    stamp = stamp.astimezone(timezone.utc)
    return Bar(number, stamp, stamp.strftime('%m/%d/%Y'), stamp.strftime('%H:%M:%S'),
               *map(lambda x:D(str(x)), (o,h,l,c,100,50,50)), ())


def config():
    return ExecutionConfig(D(10000), D('.25'), D(20), 1, D(1))


def momentum_parameters(**overrides):
    values = dict(use_breakout=False, mo_basis_len=3, mo_range_len=1, mo_signal_len=1,
                  mo_trigger=D(10), mo_warmup=2, immediate_protection=False)
    values.update(overrides)
    return Parameters(**values)


def momentum_rows(day='2024-01-16', short=False):
    start = datetime.fromisoformat(day+'T08:16:00').replace(tzinfo=CT)
    rows = [prices(i+1, start+timedelta(minutes=i)) for i in range(15)]
    for i in range(10):
        rows.append(prices(len(rows)+1, start+timedelta(minutes=15+i),100,111,100,110))
    # Entry on 08:41; Low=30 cannot stop a position whose stop is submitted
    # only at this bar's Close. Later MO time exit submits at 14:50.
    rows.extend([prices(26,start+timedelta(minutes=25),112,114,30,113),
                 prices(27,start.replace(hour=14,minute=50),120,121,119,120),
                 prices(28,start.replace(hour=14,minute=51),120,121,118,119)])
    if short:
        rows=[replace(b,open=200-b.open,high=200-b.low,low=200-b.high,close=200-b.close) for b in rows]
    return rows


def breakout_rows(short=False):
    start = datetime(2024,1,15,17,1,tzinfo=CT)
    # Seven completed candles, candidate at index 3: high 110, low 90.
    # Equal neighbours are legal source pivots (>= and <=).
    ranges=[(104,96),(105,95),(106,94),(110,90),(106,94),(105,95),(104,96)]
    rows=[prices(i+1,start+timedelta(minutes=i),100,*ranges[i//15],100) for i in range(105)]
    # Final ATR (period=1) = 104-96=8. Stop entry 110; slippage gives
    # 110.25; target=110.25+2*8=126.25; no exit on entry bar.
    rows += [prices(106,start+timedelta(minutes=105),109,130,99,111),
             prices(107,start+timedelta(minutes=106),120,127,119,126)]
    if short:
        rows=[replace(b,open=200-b.open,high=200-b.low,low=200-b.high,close=200-b.close) for b in rows]
    return rows


def momentum_two_session_rows():
    """Legacy product-review source with enough ordinary warmup on day two."""
    second=momentum_rows('2024-01-17')
    warm=[prices(i+1,second[0].timestamp_utc-timedelta(minutes=30-i)) for i in range(30)]
    return [replace(b,bar_number=i+1) for i,b in enumerate(momentum_rows()+warm+second)]


@pytest.mark.parametrize('short',[False,True])
def test_momentum_cross_next_open_owned_stop_and_time_exit(short):
    rows=momentum_rows(short=short)
    events=list(execute(rows,TwinContinuation(momentum_parameters()),config(),capture_risk=True))
    trade=next(e for e in events if type(e) is Trade)
    assert trade.side == ('short' if short else 'long')
    assert trade.entry_reason == ('MO-S' if short else 'MO-L')
    assert trade.exit_reason == ('MO-SX' if short else 'MO-LX')
    assert (trade.entry_bar_number,trade.exit_bar_number)==(26,28)
    assert trade.entry_fill_price == D('87.75' if short else '112.25')
    assert trade.exit_fill_price == D('80.25' if short else '119.75')
    assert trade.net_pnl == 148  # 7.5 points * $20 - $2 commission


@pytest.mark.parametrize('short',[False,True])
def test_breakout_confirmed_seven_candles_frozen_atr_and_stop_entry(short):
    p=Parameters(max_bars_back=0,use_momentum=False,bo_pivot_tf=15,bo_atr_period=1,immediate_protection=False)
    s=TwinContinuation(p)
    events=list(execute(breakout_rows(short),s,config(),capture_risk=True))
    trade=next(e for e in events if type(e) is Trade)
    assert trade.entry_reason == ('BO-S' if short else 'BO-L')
    assert (trade.entry_bar_number,trade.exit_bar_number)==(106,107)
    assert trade.entry_fill_price == D('89.75' if short else '110.25')
    assert trade.exit_fill_price == D('73.75' if short else '126.25')
    assert trade.net_pnl == 318  # 16 points * $20 - $2 commission
    risk=next(e for e in events if type(e) is IntratradeRisk)
    assert risk.entry_phase == 'entry_stop' and risk.mae_lower < risk.mae_upper
    assert s.arm_atr == 8


def test_equal_swing_levels_are_confirmed_and_consumed_touch_is_not_reopened():
    s=TwinContinuation(Parameters(max_bars_back=0,bo_pivot_tf=15,bo_atr_period=1))
    for b in breakout_rows()[:105]:intent=s.on_bar(b,None)
    assert s.swing_hi==110 and s.swing_lo==90 and s.hi_open and s.lo_open
    assert type(intent) is StopEntriesIntent
    # No position fill in this isolated callback probe: touching the high
    # consumes it, while the pre-armed next-bar order still exists until rearm.
    s.on_bar(breakout_rows()[105],None)
    assert not s.hi_open and s.armed


@pytest.mark.parametrize('disabled', [{'use_momentum':False},{'mo_allow_long':False}])
def test_disabled_momentum_still_consumes_daily_opportunity(disabled):
    s=TwinContinuation(momentum_parameters(**disabled))
    intents=[s.on_bar(b,None) for b in momentum_rows()[:25]]
    assert not any(type(i) is EntryIntent for i in intents) and s.traded_today


@pytest.mark.parametrize('day',['2024-07-03','2024-12-24','2024-11-29'])
def test_source_half_day_heuristic_suppresses_momentum(day):
    events=list(execute(momentum_rows(day),TwinContinuation(momentum_parameters()),config()))
    assert not any(type(e) is Trade for e in events)


def test_momentum_partial_bucket_filter_and_late_finalization():
    rows=momentum_rows()[:25]
    sparse=[b for b in rows if b.bar_number!=24]
    sparse=[replace(b,bar_number=i+1) for i,b in enumerate(sparse)]
    s=TwinContinuation(momentum_parameters())
    assert not any(type(s.on_bar(b,None)) is EntryIntent for b in sparse)
    s=TwinContinuation(momentum_parameters(mo_full_bars_only=False))
    assert any(type(s.on_bar(b,None)) is EntryIntent for b in sparse)
    # Missing 08:40 finalizes its unfinished bucket at 08:41, using only
    # previous bucket OHLC/count. With full-bars false this may trigger then.
    late=rows[:-1]+[prices(25,rows[-1].timestamp_utc+timedelta(minutes=1),100,101,99,100)]
    s=TwinContinuation(momentum_parameters(mo_full_bars_only=False))
    intents=[s.on_bar(b,None) for b in late]
    assert type(intents[-1]) is EntryIntent and s.s_count==2


class Orders:
    def __init__(self,orders):self.orders=orders
    def on_bar(self,bar,position):return self.orders.get(bar.bar_number)
    def on_finish(self,bar,position):return CloseIntent('end_of_data') if position else None


def test_entry_stop_gap_priority_expiry_dual_touch_and_no_future_fill():
    a=prices(1,datetime(2024,1,16,9,tzinfo=CT))
    stop=StopEntriesIntent(((EntryIntent(1,'BO-L',timing='next_open'),D(110)),
                           (EntryIntent(1,'BO-S',side='short',timing='next_open'),D(90))))
    b=replace(a,bar_number=2,timestamp_utc=a.timestamp_utc+timedelta(minutes=1),open=D(112),high=D(115),low=D(80),close=D(100))
    trade=next(e for e in execute([a,b],Orders({1:stop}),config()) if type(e) is Trade)
    assert trade.side=='long' and trade.entry_fill_price==D('112.25')
    both=replace(b,open=D(100))
    with pytest.raises(ExecutionError,match='Both OCO entry stops'):
        list(execute([a,both],Orders({1:stop}),config()))
    missed=replace(b,open=D(100),high=D(105),low=D(95))
    c=replace(b,bar_number=3,timestamp_utc=b.timestamp_utc+timedelta(minutes=1))
    assert not any(type(e) is Trade for e in execute([a,missed,c],Orders({1:stop}),config()))
    assert not any(type(e) is Trade for e in execute([a],Orders({1:stop}),config()))


def test_stop_only_exit_and_no_target():
    a=prices(1,datetime(2024,1,16,9,tzinfo=CT))
    b=replace(a,bar_number=2,timestamp_utc=a.timestamp_utc+timedelta(minutes=1),high=D(200))
    c=replace(b,bar_number=3,timestamp_utc=b.timestamp_utc+timedelta(minutes=1),low=D(90))
    trade=next(e for e in execute([a,b,c],Orders({1:EntryIntent(1,'MO-L'),2:BracketIntent(D(95))}),config()) if type(e) is Trade)
    assert trade.exit_reason=='stop_loss' and trade.exit_fill_price==D('94.75')


@pytest.mark.parametrize('values', [{'qty':True},{'bo_atr_period':0},{'bo_pivot_tf':0},{'mo_exit_time':1460},
                                   {'mo_signal_len':0},{'bo_target_mult':D('NaN')},{'mo_stop_points':D(0)},
                                   {'clock_shift':1.5},{'mo_window_start':1000,'mo_window_end':900}])
def test_invalid_parameters_reject(values):
    with pytest.raises(ValueError):Parameters(**values)


def test_missing_held_session_close_rejects_before_pending_stop():
    rows=momentum_rows()[:26]
    rows.append(prices(27,datetime(2024,1,16,17,1,tzinfo=CT),100,101,99,100))
    with pytest.raises(ValueError,match='crossed the configured session close'):
        list(execute(rows,TwinContinuation(momentum_parameters()),config()))


def momentum_two_session_rows():
    """Two labelled synthetic sessions, separated by a zero-trade weekday."""
    first=momentum_rows()
    second=[prices(1,b.timestamp_utc+timedelta(days=2),b.open,b.high,b.low,b.close) for b in first]
    start=second[0].timestamp_utc
    leading=[prices(1,start-timedelta(minutes=15-i)) for i in range(15)]
    return [replace(b,bar_number=i+1) for i,b in enumerate(first+leading+second)]


def test_stop_only_bracket_retains_valid_native_decision_evidence(tmp_path):
    from alphaquest.reporting import generate_report
    a=prices(1,datetime(2024,1,16,9,tzinfo=CT))
    b=replace(a,bar_number=2,timestamp_utc=a.timestamp_utc+timedelta(minutes=1))
    c=replace(b,bar_number=3,timestamp_utc=b.timestamp_utc+timedelta(minutes=1),low=D(90))
    events=list(execute([a,b,c],Orders({1:EntryIntent(1,'market',initial_stop=D(95)),
        2:BracketIntent(D(95))}),config(),capture_decisions=True))
    report=generate_report(events,tmp_path/'report',config(),capture_decisions=True,expected_bar_count=3)
    assert report['execution_decisions']['filled_trades']==1
    assert report['execution_decisions']['bracket_submissions']==1


def test_oco_entry_capture_and_invalid_order_shapes_reject():
    a=prices(1,datetime(2024,1,16,9,tzinfo=CT))
    stops=StopEntriesIntent(((EntryIntent(1,'BO-L',timing='next_open'),D(110)),))
    with pytest.raises(ExecutionError,match='decision capture'):
        list(execute([a],Orders({1:stops}),config(),capture_decisions=True))
    for orders in ([],(),((EntryIntent(1,'same-close'),D(110)),),
                   ((EntryIntent(1,'next',timing='next_open'),D('NaN')),)):
        with pytest.raises(ValueError):StopEntriesIntent(orders)


def test_breakout_ignores_momentum_flatten_and_exits_at_own_same_close():
    rows=breakout_rows()[:106]
    rows.extend([prices(107,datetime(2024,1,16,14,50,tzinfo=CT),120,121,119,120),
                 prices(108,datetime(2024,1,16,15,45,tzinfo=CT),123,124,122,123)])
    p=Parameters(max_bars_back=0,use_momentum=False,bo_pivot_tf=15,bo_atr_period=1,immediate_protection=False)
    trade=next(e for e in execute(rows,TwinContinuation(p),config()) if type(e) is Trade)
    assert trade.entry_bar_number==106 and trade.exit_bar_number==108
    assert trade.exit_reason=='BO-LX' and trade.exit_fill_price==D('122.75')
    assert trade.net_pnl==248


def test_zero_breakout_target_disables_limit_and_eof_remains_explicit():
    p=Parameters(max_bars_back=0,use_momentum=False,bo_pivot_tf=15,bo_atr_period=1,bo_target_mult=D(0))
    trade=next(e for e in execute(breakout_rows(),TwinContinuation(p),config()) if type(e) is Trade)
    assert trade.exit_reason=='end_of_data' and trade.exit_fill_price==D('125.75') and trade.net_pnl==308
