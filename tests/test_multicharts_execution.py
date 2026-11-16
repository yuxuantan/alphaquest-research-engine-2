"""Independent small-grid and cash oracles for documented MultiCharts emulation."""
from dataclasses import replace
from decimal import Decimal as D
from itertools import product

import pytest

from alphaquest.execution import execute, Trade
from alphaquest.intratrade import IntratradeRisk
from alphaquest.ohlc_path import prices as path_prices
from alphaquest.strategy import EntryIntent, EntryProtection, StopEntriesIntent, BracketIntent
from test_execution import config, bar
from test_next_bar_execution import Orders, prices
from test_twin_immediate_protection import EntryOnly, sample


def settings():
    return config(tick_size=D(1), point_value=D(1), slippage_ticks=0, commission_per_contract_per_side=D(0))


def discrete_oracle(o, h, l, c):
    # Independent, deliberately slow expansion of every price increment from
    # the vendor's documented rule. Production traverses only three segments.
    vertices = [o,h,l,c] if h-o < o-l else [o,l,h,c]
    tape = [o]
    for a,b in zip(vertices,vertices[1:]):
        tape.extend(range(a+1,b+1) if b>a else range(a-1,b-1,-1))
    return tape


def test_nearest_extreme_and_exact_tie():
    assert path_prices(prices(1,'100','105','90','101')) == tuple(map(D,(100,105,90,101)))
    assert path_prices(prices(1,'100','110','95','101')) == tuple(map(D,(100,95,110,101)))
    assert path_prices(prices(1,'100','110','90','101')) == tuple(map(D,(100,90,110,101)))


@pytest.mark.parametrize('short',[False,True])
def test_all_small_grid_oco_fills_and_post_entry_exits_match_tick_expansion(short):
    for o,c in product(range(1,6), repeat=2):
        tape=discrete_oracle(o,6,0,c)
        long=EntryIntent(1,'long',timing='next_open',protection=EntryProtection(stop_distance=D(2),target_distance=D(1)))
        sell=EntryIntent(1,'short',side='short',timing='next_open',protection=EntryProtection(stop_distance=D(2),target_distance=D(1)))
        active=((long,D(4)),(sell,D(2)))
        # Mirror prices and order-side ownership to cover both entry sides.
        if short:
            o,c=6-o,6-c;tape=discrete_oracle(o,6,0,c)
        entry_i=next(i for i,p in enumerate(tape) if p>=4 or p<=2)
        side=1 if tape[entry_i]>=4 else -1;fill=tape[entry_i]
        stop,target=fill-2*side,fill+side
        def exits(price):
            return (price <= stop or price >= target) if side == 1 else (price >= stop or price <= target)
        exit_i=next((i for i in range(entry_i,len(tape)) if exits(tape[i])),None)
        expected_exit=c if exit_i is None else tape[exit_i]
        expected_reason='end_of_data' if exit_i is None else ('stop_loss' if expected_exit==stop else 'take_profit')
        schedule={1:StopEntriesIntent(active)}
        events=list(execute([bar(1),prices(2,str(o),'6','0',str(c))],Orders(schedule),settings(),capture_risk=True))
        trade=next(e for e in events if type(e) is Trade)
        risk=next(e for e in events if type(e) is IntratradeRisk)
        assert (trade.side,trade.entry_fill_price,trade.exit_fill_price,trade.exit_reason)==(
            'long' if side==1 else 'short',D(fill),D(expected_exit),expected_reason)
        held=tape[entry_i:(exit_i+1) if exit_i is not None else len(tape)]
        assert risk.mae_lower==risk.mae_upper==max([D(0),*(D((fill-p)*side) for p in held)])
        assert risk.mfe_lower==risk.mfe_upper==max([D(0),*(D((p-fill)*side) for p in held)])


@pytest.mark.parametrize('ohlc,reason,price',[
    ((100,108,85,105),'take_profit',105),  # High closer; TP wins before later Low.
    ((100,120,95,105),'stop_loss',95),    # Low closer; stop wins.
    ((100,110,90,105),'stop_loss',95),    # Equal distance: Low first.
    ((110,120,80,110),'take_profit',110), # Opening improvement, before all later extrema.
    ((90,120,80,90),'stop_loss',90),      # Opening stop gap, before later recovery.
])
def test_held_bracket_has_independent_cash_oracle(ohlc,reason,price):
    events=list(execute([bar(1),bar(2),prices(3,*map(str,ohlc))],
                Orders({1:EntryIntent(1,'entry'),2:BracketIntent(D(95),D(105))}),settings()))
    trade=next(e for e in events if type(e) is Trade)
    assert trade.exit_reason==reason and trade.exit_fill_price==price and trade.net_pnl==price-100


def test_preentry_low_is_not_a_protective_stop_or_mae():
    entry=EntryIntent(1,'BO-L',timing='next_open',protection=EntryProtection(stop_price=D(90),target_distance=D(10)))
    events=list(execute(sample((100,130,85,115)),EntryOnly(entry,D(110)),settings(),capture_risk=True))
    trade=next(e for e in events if type(e) is Trade);risk=next(e for e in events if type(e) is IntratradeRisk)
    assert trade.exit_reason=='take_profit' and trade.entry_fill_price==110 and trade.exit_fill_price==120
    assert risk.mae_upper==0 and risk.mfe_upper==10


def test_high_first_diagnostic_can_exit_on_the_post_entry_low():
    entry=EntryIntent(1,'BO-L',timing='next_open',protection=EntryProtection(stop_price=D(90),target_distance=D(30)))
    strategy=EntryOnly(entry,D(110));strategy.ohlc_path_policy='high_first'
    trade=next(e for e in execute(sample((100,115,85,100)),strategy,settings()) if type(e) is Trade)
    assert trade.exit_reason=='stop_loss' and trade.exit_fill_price==90


def test_native_target_can_precede_later_provider_floor():
    from test_native_account_execution import bar as native_bar, ControlledSignals, owner, controlled
    rows=[native_bar(1),native_bar(2),native_bar(3,low='0',high='160')]
    signals=ControlledSignals({1:EntryIntent(1,'entry',initial_stop=D(95)),2:BracketIntent(D(25),D(150))})
    trade,=[e for e in controlled(rows,signals,owner(rows,dict(kind='fixed_contracts',contracts=10))) if type(e) is Trade]
    assert trade.exit_reason=='take_profit' and trade.net_pnl==1000
